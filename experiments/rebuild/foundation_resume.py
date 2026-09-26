"""Resume one interrupted foundation experiment without resetting its limits.

Planning/restoration is offline. Execution independently rechecks the live cost
lock; this module cannot authorize an unknown-cost exception or release money.
Only the frozen candidate and runtime-test feedback may enter the resumed coder.
"""
import argparse
from datetime import datetime
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

from checkpoints import Checkpoints, application_manifest, digest
from grade import manifest
from run_foundation_trial import coding_pass, failure_feedback, grade_application
from run_trial import CACHE, IMAGE, ROOT, control


def read_json(path):
    return json.loads(path.read_text())


def money(value):
    from decimal import Decimal
    amount = Decimal(str(value)) * 1000000
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError('money must be nonnegative integer micro-CNY')
    return int(amount)


def receipt_proof(evidence):
    lines = (evidence / 'raw-controller.log').read_text().strip().splitlines()
    proof = json.loads(lines[-1])['export_manifest']
    actual = manifest(evidence)
    actual.pop('raw-controller.log')
    if actual != proof:
        raise ValueError('independent evidence export changed')
    return proof


def original_experiment(root, status):
    metadata = read_json(root / 'manifest.json')
    name = metadata['name']
    if root.name != name or metadata['model'] not in ('glm-5.3-flash', 'deepseek-v4-flash') or metadata['phase'] != 'mechanism':
        raise ValueError('not the recorded selected-kernel mechanism experiment')
    original = [t for t in status['trials'] if t['id'] == name]
    if len(original) != 1 or not original[0]['closed'] or 'finished' not in metadata:
        raise ValueError('original experiment must be authoritatively closed')
    if original[0]['cap'] != money(metadata['cap_cny']):
        raise ValueError('original cap differs from authoritative ledger')
    resume_name = name + '-resume-1'
    if any(t['id'].startswith(name + '-resume-') for t in status['trials']):
        raise ValueError('continuation already exists; inspect it instead of duplicating')
    if (root / 'continuation-1').exists():
        raise ValueError('continuation artifacts already exist; no automatic retry')
    return metadata, original[0], resume_name


def frozen_contract(root, metadata):
    bundle = manifest(root / 'bundle')
    if bundle != metadata['bundle_sha256']:
        raise ValueError('frozen candidate/grader bundle changed')
    compiler = Path(metadata['compiler_trial'])
    acceptance = compiler / 'result/acceptance'
    frozen = read_json(acceptance / 'frozen.json')
    if (manifest(acceptance / 'suite') != metadata['runtime_tests'] or
        frozen['tests_sha256'] != metadata['runtime_tests'] or
        frozen['requirements_sha256'] != metadata['source_sha256']):
        raise ValueError('frozen runtime acceptance/source changed')
    if not read_json(compiler / 'result/blank-control/verdict.json')['gate']:
        raise ValueError('runtime suite has no valid empty-UI negative control')
    return compiler, acceptance, frozen, bundle


def verified_checkpoint(root, metadata, frozen):
    store_contract = read_json(root / 'checkpoints/frozen.json')
    store = Checkpoints(root / 'checkpoints', frozen['tests_sha256'], store_contract['case_keys'])
    history = store.history()
    if not history or not metadata['passes']:
        raise ValueError('no independently checked working checkpoint')
    last = history[-1]
    if last['module'] != 'foundation' or last['accepted'] or last['pause_module']:
        raise ValueError('accepted/paused/foreign module is not eligible for interrupted repair')
    if last != metadata['passes'][-1].get('decision') or len(history) != len(metadata['passes']):
        raise ValueError('checkpoint history differs from original run records')
    attempted = len(metadata['passes'])
    evidence = root / f'attempt-{metadata["passes"][-1]["attempt"]}' / 'runtime-evidence'
    snapshot = root / 'checkpoints/snapshots' / last['snapshot']
    original_work = root / f'attempt-{metadata["passes"][-1]["attempt"]}' / 'pass/working'
    hashes, _, _, _, accepted = store.validated_evidence(original_work, evidence, receipt_proof(evidence))
    if accepted or hashes != last['source_manifest'] or digest(hashes) != last['snapshot']:
        raise ValueError('working checkpoint no longer matches its failed grading receipt')
    if application_manifest(snapshot) != hashes:
        raise ValueError('preserved snapshot no longer matches graded working bytes')
    return last, attempted, evidence, hashes


def elapsed_allowance(root, metadata, post_close_evidence):
    started, finished = metadata['started'], metadata['finished']
    if not all(isinstance(t, (int, float)) and math.isfinite(t) for t in (started, finished)) or finished < started:
        raise ValueError('invalid original elapsed time')
    # Count the conservative wall interval through any explicitly supplied
    # post-close grading report. Time awaiting a user after all work stopped
    # does not create a fresh 1800s run; only the unused active allowance remains.
    extra = []
    # These are this controller's own documented outputs, not a search for
    # external/hidden tests. Omitting the CLI flag must not reclaim grading time.
    known = [root / name for name in ('holdout-evidence', 'holdout-after-billing-stop', 'cold-evidence')]
    directories = set(p.resolve() for p in post_close_evidence)
    directories.update(p.resolve() for p in known if p.exists())
    for directory in sorted(directories):
        directory = directory.resolve()
        if root not in directory.parents:
            raise ValueError('post-close evidence must belong to this experiment')
        proof = receipt_proof(directory)
        stats = read_json(directory / 'playwright.json')['stats']
        duration = float(stats['duration']) / 1000
        begin = datetime.fromisoformat(stats['startTime'].replace('Z', '+00:00')).timestamp()
        if not math.isfinite(duration) or duration < 0 or begin < started:
            raise ValueError('invalid post-close grading duration')
        finished = max(finished, begin + duration)
        extra.append({'path': str(directory), 'export_sha256': digest(proof)})
    return metadata['deadline_seconds'] - math.ceil(finished - started), extra


def remaining_money(metadata, original, status):
    name = metadata['name']
    calls = [c for c in status['calls'] if c['trial'] == name]
    if not calls or any(not isinstance(c['charged'], int) or c['charged'] < 0 for c in calls):
        raise ValueError('missing authoritative nonnegative call charges')
    spent = sum(c['charged'] for c in calls)
    return original['cap'] - spent, spent, [c['id'] for c in calls]


def build_plan(root, status, post_close_evidence=(), *, expected_image=None):
    """Read exact local evidence; never opens a new trial or changes a ledger."""
    root = root.resolve()
    metadata, original, resume_name = original_experiment(root, status)
    compiler, acceptance, frozen, bundle = frozen_contract(root, metadata)
    last, attempted, evidence, hashes = verified_checkpoint(root, metadata, frozen)
    seconds, extra = elapsed_allowance(root, metadata, post_close_evidence)
    remaining_micro, spent, call_ids = remaining_money(metadata, original, status)
    passes = metadata['max_passes'] - attempted
    if remaining_micro <= 0 or seconds < 800 or passes < 1:
        raise ValueError('original cost/time/pass allowance exhausted; cannot renew it')
    blockers = []
    if status['unresolved_cost_lock']:
        blockers.append('unresolved upstream cost; authorization/reconciliation required')
    if any(not t['closed'] for t in status['trials']):
        blockers.append('another live trial exists')
    compiler_manifest = compiler / 'manifest.json'
    image = metadata.get('image') or (read_json(compiler_manifest).get('image') if compiler_manifest.is_file() else None)
    recorded_image = image
    if expected_image and not re.fullmatch(r'sha256:[0-9a-f]{64}', expected_image):
        raise ValueError('expected image must be an exact SHA256 digest')
    if expected_image and image and expected_image != image:
        raise ValueError('reviewed image differs from recorded image')
    image = image or expected_image
    if not image:
        raise ValueError('legacy trial lacks image record; explicit reviewed expected image required')
    return {'schema': 'foundation-resume-v1', 'root': str(root), 'original_trial': metadata['name'],
        'resume_trial': resume_name, 'source_snapshot': last['snapshot'],
        'source_manifest': hashes, 'stagnant_rounds': last['stagnant_rounds'],
        'remaining_cap_micro_cny': remaining_micro, 'remaining_cap_cny': remaining_micro / 1000000,
        'prior_charged_micro_cny': spent, 'prior_call_ids': call_ids,
        'remaining_seconds': seconds, 'remaining_passes': passes, 'prior_passes': attempted,
        'acceptance': str(acceptance), 'bundle_sha256': bundle,
        'image': image,
        'image_record_source': 'recorded' if recorded_image else 'explicit_reviewed_recovery',
        'parent_manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
        'runtime_evidence': str(evidence), 'post_close_evidence': extra,
        'model': metadata['model'], 'phase': metadata['phase'],
        'holdout_input_to_coder': metadata.get('holdout_input_to_coder', False),
        'execution_allowed': not blockers, 'blockers': blockers,
        'official_upload_allowed': False, 'accepted': False}


def store_for(root):
    contract = read_json(root / 'checkpoints/frozen.json')
    return Checkpoints(root / 'checkpoints', contract['tests_sha256'], contract['case_keys'])


def restore(plan, destination):
    """Can run without a key; never changes or discards the original snapshot."""
    root = Path(plan['root'])
    if manifest(Path(plan.get('bundle_path', root / 'bundle'))) != plan['bundle_sha256']:
        raise ValueError('candidate bundle drifted before restoration')
    source = root / 'checkpoints/snapshots' / plan['source_snapshot']
    if application_manifest(source) != plan['source_manifest']:
        raise ValueError('working source changed before restoration')
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, destination / 'working')
    if application_manifest(destination / 'working') != plan['source_manifest']:
        raise ValueError('restored working bytes differ')
    # Only generated-runtime test failures enter feedback; never post-close holdout.
    (destination / 'feedback.txt').write_text(failure_feedback(Path(plan['runtime_evidence'])))
    (destination / 'resume-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return destination / 'working'


def execution_gate(plan, post_close_evidence, planner=build_plan):
    root = Path(plan['root'])
    fresh = planner(root, control('/status', {'read': True}), post_close_evidence)
    if fresh != plan or not fresh['execution_allowed']:
        raise ValueError('resume plan drifted or live cost/serialization gate is closed')
    active = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    if any(n.startswith(('factory26-trial', 'factory26-grade', 'factory26-acceptance')) for n in active):
        raise ValueError('candidate or grader is already active')
    image = subprocess.check_output(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True).strip()
    if image != plan['image']:
        raise ValueError('runner image changed since the frozen acceptance experiment')


def repair_loop(plan, out, source, token, deadline, result, store):
    root = Path(plan['root'])
    bundle = Path(plan.get('bundle_path', root / 'bundle'))
    acceptance = Path(plan['acceptance'])
    frozen = read_json(acceptance / 'frozen.json')
    last = None
    feedback = out / 'feedback.txt'
    for offset in range(1, plan['remaining_passes'] + 1):
        if deadline - time.monotonic() < 800:
            result['stop_reason'] = 'remaining active time reserved for independent checks'
            break
        if control('/status', {'read': True})['unresolved_cost_lock']:
            raise RuntimeError('new unresolved upstream fee; no next model call')
        number = plan['prior_passes'] + offset
        attempt = out / f'attempt-{number}'
        record = {'attempt': number, 'input_snapshot': digest(application_manifest(source)),
                  'feedback_sha256': hashlib.sha256(feedback.read_bytes()).hexdigest()}
        result['passes'].append(record)
        record['kernel_exit'] = coding_pass(bundle, source, acceptance, feedback, attempt, token,
                                           plan.get('coding_seconds', 360), model=plan['model'])
        if manifest(bundle) != plan['bundle_sha256']:
            raise RuntimeError('frozen candidate bundle changed')
        working = attempt / 'pass/working'
        if not working.exists():
            result['stop_reason'] = 'no working export; not an application score'
            break
        last = working
        evidence = attempt / 'runtime-evidence'
        verdict, proof = grade_application(working, acceptance / 'suite', evidence,
            frozen['expected'], min(850, max(1, deadline-time.monotonic()-300)), bundle / 'grader')
        decision = store.record('foundation', working, evidence, proof)
        record.update(passed=verdict['passed'], total=verdict['total'], decision=decision)
        print(json.dumps({'attempt': number, 'passed': verdict['passed'], 'total': verdict['total'],
                          'accepted': decision['accepted'], 'paused': decision['pause_module']}), flush=True)
        if decision['accepted']:
            result['runtime_accepted'] = True
            break
        if decision['pause_module']:
            result['stop_reason'] = 'two consecutive checks without newly passing behavior'
            break
        source = out / f'resumed-working-{number}'
        store.restore_working('foundation', source)
        feedback = out / f'feedback-{number+1}.txt'
        feedback.write_text(failure_feedback(evidence))
    return last


def frozen_holdout(plan):
    catalog = read_json(CACHE / 'foundation-v1.json')
    source_hash = read_json(Path(plan['acceptance']) / 'frozen.json')['requirements_sha256']
    matches = [(name, value) for name, value in catalog['suites'].items()
               if value['requirement_source_sha256'] == source_hash]
    if len(matches) != 1:
        raise ValueError('no unique source-bound frozen foundation holdout')
    name, contract = matches[0]
    tests = ROOT / 'experiments/rebuild/foundation' / name
    if manifest(tests) != contract['tests_sha256']:
        raise ValueError('frozen foundation holdout changed')
    return tests, contract


def independent_delivery(plan, out, last, deadline, result, store):
    # Never convert runtime-only acceptance to foundation/official success.
    # A separate evaluation, when the runtime suite passes, uses only the exact
    # already-frozen holdout whose public-source hash matches this experiment.
    if last is not None and result['runtime_accepted']:
        tests, contract = frozen_holdout(plan)
        grader = Path(plan['root']) / 'bundle/grader'
        holdout, _ = grade_application(last, tests, out / 'holdout-evidence', contract['expected_count'],
            min(300, max(1, deadline-time.monotonic())), grader)
        result['holdout'] = {k: holdout.get(k) for k in ('passed', 'total', 'gate', 'actual_restarts')}
        if holdout['gate']:
            store.export_accepted(out / 'clean-delivery')
            cold, _ = grade_application(out / 'clean-delivery', tests, out / 'cold-evidence', contract['expected_count'],
                min(300, max(1, deadline-time.monotonic())), grader)
            result['cold_delivery_gate'] = cold['gate']
            result['foundation_gate'] = cold['gate']


def execute(plan, post_close_evidence, planner=build_plan):
    execution_gate(plan, post_close_evidence, planner)
    root = Path(plan['root'])
    out = root / plan.get('continuation_directory', 'continuation-1')
    source = restore(plan, out)
    token = control('/trial', {'id': plan['resume_trial'], 'phase': 'mechanism',
        'cap_cny': plan['remaining_cap_cny'], 'seconds': plan['remaining_seconds']})['token']
    started = time.time()
    deadline = time.monotonic() + plan['remaining_seconds']
    result = {'schema': 'foundation-resume-result-v1', 'resume_trial': plan['resume_trial'],
        'model': plan['model'], 'holdout_input_to_coder': plan.get('holdout_input_to_coder', False),
        'foundation_evidence_kind': ('frozen_internal_regression' if plan.get('holdout_input_to_coder')
                                    else 'previously_unseen_internal_holdout'),
        'started': started, 'passes': [], 'runtime_accepted': False, 'foundation_gate': False,
        'official_upload_allowed': False, 'plan_sha256': digest(plan)}
    store = store_for(root)
    try:
        last = repair_loop(plan, out, source, token, deadline, result, store)
        independent_delivery(plan, out, last, deadline, result, store)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        # Keep the serialized trial open through independent/cold validation.
        control('/close', {'id': plan['resume_trial']})
        status = control('/status', {'read': True})
        (out / 'budget.json').write_text(json.dumps(status, indent=2))
        added = sum(c['charged'] for c in status['calls'] if c['trial'] == plan['resume_trial'])
        result.update(finished=time.time(), cost_upper_cny=added/1000000,
            cumulative_cost_upper_cny=(added+plan['prior_charged_micro_cny'])/1000000,
            active_seconds_used=time.time()-started, cost_locked=status['unresolved_cost_lock'])
        (out / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result.get(k) for k in ('runtime_accepted','foundation_gate','cost_upper_cny','stop_reason')}), flush=True)
    return 0 if result['foundation_gate'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('experiment', type=Path)
    parser.add_argument('--post-close-evidence', type=Path, action='append', default=[])
    parser.add_argument('--restore-only', type=Path, help='offline proof copy; no model, no new trial')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-image', help='explicit image digest for a reviewed legacy record missing image metadata')
    args = parser.parse_args()
    if args.execute and args.restore_only:
        raise ValueError('choose offline restoration or execution, not both')
    planner = partial(build_plan, expected_image=args.expected_image)
    plan = planner(args.experiment, control('/status', {'read': True}), args.post_close_evidence)
    if args.restore_only:
        restore(plan, args.restore_only.resolve())
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    return execute(plan, args.post_close_evidence, planner) if args.execute else 0


if __name__ == '__main__':
    raise SystemExit(main())
