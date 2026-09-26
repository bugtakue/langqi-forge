"""One evidence-bound recovery after dispatch died before pipeline creation.

No template reset, new cap, hidden tests or model change. The sole kernel change
is matching dispatch wait to its existing upstream timeout. This consumes the
LAST original coding-pass allowance and all prior charged/time usage carries.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

from foundation_resume import (execute, frozen_contract, read_json, verified_checkpoint)
from grade import manifest
from run_trial import control


def previous_transport_failure(root):
    previous = root / 'continuation-1'
    plan = read_json(previous / 'resume-plan.json')
    result = read_json(previous / 'result.json')
    if hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest() != plan['parent_manifest_sha256']:
        raise ValueError('original experiment record changed')
    if result.get('stop_reason') != 'no working export; not an application score' or len(result['passes']) != 1:
        raise ValueError('only one pre-implementation transport failure can be recovered')
    attempt = previous / ('attempt-' + str(result['passes'][0]['attempt'])) / 'pass'
    events = [json.loads(line) for line in (attempt / 'events.jsonl').read_text().splitlines()]
    if (attempt / 'working').exists() or (attempt / 'summary.json').exists():
        raise ValueError('implementation/export exists; do not duplicate it')
    if any(e['method'].startswith('tool/') or (e['method'] == 'progress/updated' and
           'tool' in str(e.get('params', {}).get('metadata', {}).get('kind', ''))) for e in events):
        raise ValueError('dispatch has tool activity; do not duplicate it')
    ended = [e['params'] for e in events if e['method'] == 'controller/dispatch_finished']
    if len(ended) != 1 or ended[0] != {'attempt': 1, 'ok': False, 'reply': 'octos turn timed out'}:
        raise ValueError('not the diagnosed dispatch-timeout failure')
    return plan, result


def terminal_request(plan, status):
    old_name = plan['resume_trial']
    prior = [t for t in status['trials'] if t['id'] == old_name and t['closed']]
    calls = [c for c in status['calls'] if c['trial'] == old_name]
    failures = {f['call_id']: f for f in status['failures']}
    if len(prior) != 1 or len(calls) != 1 or calls[0]['id'] not in failures:
        raise ValueError('request must have ended with an archived transport failure')
    if failures[calls[0]['id']]['error_type'] != 'RemoteDisconnected':
        raise ValueError('unreviewed error; not this recovery contract')
    return calls


def recovery_bundle(root, metadata):
    bundle = root / 'transport-recovery-bundle'
    hashes = manifest(bundle)
    expected = dict(metadata['bundle_sha256'])
    expected['candidate/kernel_pass.py'] = hashlib.sha256(
        (root / 'bundle/candidate/kernel_pass.py').read_bytes().replace(
            b'timeout=min(90, max(1, end-time.monotonic()))',
            b'timeout=min(240, max(1, end-time.monotonic()))')).hexdigest()
    if hashes != expected:
        raise ValueError('recovery bundle must differ ONLY in dispatch wait 90 to 240')
    return bundle, hashes


def recovery_slot(root, status, base):
    rows = [t for t in status['trials'] if t['id'] == base]
    if not rows and not (root / 'transport-recovery-1').exists():
        return base, 'transport-recovery-1', 0
    # Controller integration error: supplied 600s to the frozen CLI whose cap
    # is 360s. It exited before a session/model call. Preserve that failure and
    # permit exactly one corrected invocation, never an extra coding response.
    failed = root / 'transport-recovery-1'
    record = read_json(failed / 'result.json')
    attempt = failed / 'attempt-3'
    if (len(rows) != 1 or not rows[0]['closed'] or
        any(c['trial'] == base for c in status['calls']) or (attempt / 'pass').exists() or
        record['cost_upper_cny'] != 0 or record['active_seconds_used'] >= 5 or
        not (attempt / 'kernel.log').read_text().rstrip().endswith('ValueError: bounded output/seconds required')):
        raise ValueError('transport recovery already ran; no further attempt allowed')
    name, directory = base + '-entry-retry', 'transport-recovery-1-entry-retry'
    if any(t['id'] == name for t in status['trials']) or (root / directory).exists():
        raise ValueError('corrected entry already exists; no further retry')
    return name, directory, math.ceil(record['active_seconds_used'])


def build_recovery(root, status, unused=()):
    root = root.resolve()
    metadata = read_json(root / 'manifest.json')
    _, _, frozen, _ = frozen_contract(root, metadata)
    last, _, _, _ = verified_checkpoint(root, metadata, frozen)
    plan, result = previous_transport_failure(root)
    calls = terminal_request(plan, status)
    name, directory, entry_seconds = recovery_slot(root, status, metadata['name'] + '-transport-recovery-1')
    spent = sum(c['charged'] for c in calls)
    remaining = plan['remaining_cap_micro_cny'] - spent
    seconds = plan['remaining_seconds'] - math.ceil(result['active_seconds_used']) - entry_seconds
    passes = plan['remaining_passes'] - len(result['passes'])
    if remaining <= 0 or seconds < 1000 or passes != 1 or last['stagnant_rounds'] != 1:
        raise ValueError('original remaining budget/time/last-pass contract exhausted')
    bundle, hashes = recovery_bundle(root, metadata)
    blockers = []
    if status['unresolved_cost_lock'] or any(not t['closed'] for t in status['trials']):
        blockers.append('active request/trial or uncharged unknown cost')
    plan.update(resume_trial=name, continuation_directory=directory,
        bundle_path=str(bundle), bundle_sha256=hashes, coding_seconds=360,
        remaining_cap_micro_cny=remaining, remaining_cap_cny=remaining/1e6,
        prior_charged_micro_cny=plan['prior_charged_micro_cny']+spent,
        remaining_seconds=seconds, remaining_passes=passes, prior_passes=2,
        execution_allowed=not blockers, blockers=blockers,
        recovery_evidence_sha256=hashlib.sha256((root / 'continuation-1/result.json').read_bytes()).hexdigest())
    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('experiment', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = args.experiment.resolve()
    if args.prepare:
        bundle = root / 'transport-recovery-bundle'
        shutil.copytree(root / 'bundle', bundle)
        path = bundle / 'candidate/kernel_pass.py'
        before = path.read_bytes()
        needle = b'timeout=min(90, max(1, end-time.monotonic()))'
        if before.count(needle) != 1:
            raise ValueError('one exact dispatch timer required')
        path.write_bytes(before.replace(needle, b'timeout=min(240, max(1, end-time.monotonic()))'))
    plan = build_recovery(root, control('/status', {'read': True}))
    print(json.dumps({k: plan[k] for k in ('resume_trial','remaining_cap_cny','remaining_seconds',
        'remaining_passes','coding_seconds','execution_allowed','blockers')}), flush=True)
    return execute(plan, [], build_recovery) if args.execute else 0


if __name__ == '__main__':
    raise SystemExit(main())
