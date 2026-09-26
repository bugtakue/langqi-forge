"""Selected kernel + frozen runtime tests + retained working checkpoints.

One module experiment, no extra agents. Private holdout source never enters
model containers. Its final result is separate from generated internal tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from checkpoints import Checkpoints, application_manifest, case_outcomes
from grade import manifest
from run_trial import CACHE, IMAGE, ROOT, bind, control

CODE = ROOT / 'experiments/rebuild'
MODULE_FILES = ('kernel_pass.py', 'grade.py', 'prompts/coding-pass.md')
UPSTREAM_FILES = ('main.py', 'octos_stdio.py', 'arc-policy.toml')
GRADER_FILES = ('foundation_grade.py', 'grade.py', 'restart_control.py')


def prepare_controller(destination):
    for source, relative in [(CODE / p, Path('candidate') / p) for p in MODULE_FILES] + [
            (CACHE / 'octos-upstream/arc' / p, Path('upstream/arc') / p) for p in UPSTREAM_FILES] + [
            (CACHE / 'octos-upstream/LICENSE', Path('upstream/LICENSE'))] + [
            (CODE / p, Path('grader') / p) for p in GRADER_FILES]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def refresh_coder(bundle):
    """An explicit candidate revision, never a mutation of old frozen bytes."""
    before = manifest(bundle)
    for name in MODULE_FILES:
        shutil.copy2(CODE / name, bundle / 'candidate' / name)
    after = manifest(bundle)
    changes = {name: {'before': before.get(name), 'after': digest}
               for name, digest in after.items() if before.get(name) != digest}
    if any(not name.startswith('candidate/') for name in changes):
        raise ValueError('a coder revision cannot change the independent grader/upstream')
    return changes


def grade_application(source, tests, output, expected, seconds, grader=CODE):
    output.mkdir(parents=True, exist_ok=False)
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-grade', '--network', 'none',
           '--memory', '2g', '--cpus', '2', '--shm-size', '512m', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges']
    for cap in ('CHOWN', 'SETUID', 'SETGID', 'KILL', 'DAC_OVERRIDE'):
        cmd += ['--cap-add', cap]
    cmd += bind(source, '/generated') + bind(tests, '/private-input/tests') + bind(output, '/evidence', True)
    for name in GRADER_FILES:
        cmd += bind(grader / name, '/grader/' + name)
    cmd += ['--entrypoint', 'python', IMAGE, '/grader/foundation_grade.py', '--private-tests', '--expected', str(expected)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(['docker', 'stop', '--time', '5', 'factory26-grade'], capture_output=True)
        raise
    (output / 'raw-controller.log').write_text(proc.stdout + proc.stderr)
    proof = json.loads(proc.stdout.strip().splitlines()[-1])['export_manifest']
    actual = manifest(output)
    actual.pop('raw-controller.log')
    if actual != proof:
        raise RuntimeError('grade evidence differs from independent controller export')
    verdict = json.loads((output / 'verdict.json').read_text())
    return verdict, proof


def failure_feedback(evidence):
    verdict = json.loads((evidence / 'verdict.json').read_text())
    report = json.loads((evidence / 'playwright.json').read_text()) if (evidence / 'playwright.json').exists() else {}
    errors = []
    def visit(suite):
        for spec in suite.get('specs', []):
            for test in spec.get('tests', []):
                if test.get('status') != 'expected':
                    errors.append({'case': spec['title'], 'errors': [r.get('errors', []) for r in test.get('results', [])]})
        for child in suite.get('suites', []):
            visit(child)
    visit(report)
    value = {'summary': {k: verdict.get(k) for k in ('passed', 'total', 'gate', 'error')}, 'failing_steps': errors}
    if verdict.get('error') == 'build failed':
        value['build_log'] = (evidence / 'build.log').read_text()[-8000:]
    # Browser connection failures alone conceal backend exceptions. These are
    # logs from the isolated disposable app, never model/gateway credentials.
    server_log = evidence / 'server.log'
    if not verdict.get('gate') and server_log.is_file():
        value['untrusted_application_server_log_tail'] = server_log.read_text(errors='replace')[-6000:]
    # Keep each concrete first failure and its page/error context, not a prose PASS.
    for item in value['failing_steps']:
        for attempts in item['errors']:
            for error in attempts:
                if 'message' in error:
                    error['message'] = error['message'][:5000]
                error.pop('stack', None)
    return json.dumps(value, ensure_ascii=False)


def coding_pass(bundle, source, acceptance, feedback, output, token, seconds, model='glm-5.3-flash'):
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-trial', '--network', 'factory26-ab-internal',
           '--memory', '3g', '--cpus', '2', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
           '--env', 'OPENAI_API_KEY', '--env', 'OPENAI_BASE_URL=http://factory26-gateway:8021/v1',
           '--env', 'OCTOS_PROVIDER=custom', '--env', 'OCTOS_MODEL=' + model,
           '--env', 'MODEL=' + model, '--env', 'PYTHONDONTWRITEBYTECODE=1']
    output.mkdir(exist_ok=False)
    cmd += bind(bundle / 'candidate', '/candidate') + bind(bundle / 'upstream', '/upstream')
    cmd += bind(CACHE / 'runtime', '/runtime') + bind(source, '/source') + bind(acceptance, '/acceptance')
    cmd += bind(feedback, '/feedback.txt') + bind(output, '/output', True)
    cmd += ['--entrypoint', 'python', IMAGE, '/candidate/kernel_pass.py', '--output', '/output/pass', '--seconds', str(seconds)]
    with (output / 'kernel.log').open('w') as stream:
        proc = subprocess.Popen(cmd, env=dict(os.environ, OPENAI_API_KEY=token), stdout=stream, stderr=subprocess.STDOUT)
        try:
            return proc.wait(timeout=seconds + 30)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker', 'stop', '--time', '5', 'factory26-trial'], capture_output=True)
            proc.wait(timeout=15)
            return 124


def previous_run(previous):
    if (previous / 'resume-plan.json').is_file():
        return (json.loads((previous / 'resume-plan.json').read_text()),
                json.loads((previous / 'result.json').read_text()))
    result = json.loads((previous / 'manifest.json').read_text())
    plan = {'root': str(previous), 'bundle_sha256': result['bundle_sha256']}
    return plan, dict(result, resume_trial=result['name'])


def foundation_feedback(previous, decision, frozen):
    """Visible failure evidence only; original test source stays unmounted.

    Once used, this suite is internal regression, no longer unseen holdout.
    """
    evidence = previous / 'holdout-evidence'
    proof = json.loads((evidence / 'raw-controller.log').read_text().strip().splitlines()[-1])['export_manifest']
    actual = manifest(evidence)
    actual.pop('raw-controller.log')
    verdict = json.loads((evidence / 'verdict.json').read_text())
    suites = json.loads((CACHE / 'foundation-v1.json').read_text())['suites'].values()
    matching = [s for s in suites if s['requirement_source_sha256'] == frozen['requirements_sha256']]
    if (actual != proof or len(matching) != 1 or verdict['gate'] or
        verdict['passed'] >= verdict['total'] or verdict['test_manifest'] != matching[0]['tests_sha256'] or
        verdict['source_manifest'] != decision['source_manifest'] or
        not all(verdict.get(k) for k in ('source_unchanged', 'tests_unchanged', 'process_cleaned'))):
        raise ValueError('foundation feedback lacks a frozen source-bound failed receipt')
    return failure_feedback(evidence)


def continue_working(previous, out, frozen, status, use_foundation_feedback=False, blocker_diagnosis=None):
    """Continue a closed, independently graded repair; no unverified template.

    The host-owned checkpoint history is inherited so the six passed cases and
    no-gain counter cannot be reset by opening another bounded repair tranche.
    """
    previous = previous.resolve()
    plan, result = previous_run(previous)
    rows = [t for t in status['trials'] if t['id'] == result['resume_trial']]
    if len(rows) != 1 or not rows[0]['closed'] or result.get('foundation_gate') or not result['passes']:
        raise ValueError('continuation needs an exact closed unaccepted trial')
    record = result['passes'][-1]
    decision = record['decision']
    parent = Path(plan['root'])
    contract = json.loads((parent / 'checkpoints/frozen.json').read_text())
    if contract['tests_sha256'] != frozen['tests_sha256']:
        raise ValueError('continuation cannot change frozen acceptance')
    store = Checkpoints(parent / 'checkpoints', contract['tests_sha256'], contract['case_keys'])
    reviewed = bool(blocker_diagnosis)
    prior_review = (result.get('continuation') or {}).get('reviewed_blocker_diagnosis_sha256')
    if reviewed and (not decision['pause_module'] or prior_review or not 20 <= len(blocker_diagnosis) <= 8000):
        raise ValueError('only one explicit bounded blocker review after a paused route')
    if (store.history()[-1] != decision or (decision['pause_module'] and not reviewed) or
        result.get('foundation_stagnant_rounds', 0) >= 2 or
        (decision['accepted'] and not use_foundation_feedback)):
        raise ValueError('checkpoint advanced/paused or accepted without new failure evidence')
    attempt = previous / f'attempt-{record["attempt"]}'
    evidence = attempt / 'runtime-evidence'
    proof = json.loads((evidence / 'raw-controller.log').read_text().strip().splitlines()[-1])['export_manifest']
    store.validated_evidence(attempt / 'pass/working', evidence, proof)
    bundle = Path(plan.get('bundle_path', parent / 'bundle'))
    if manifest(bundle) != plan['bundle_sha256']:
        raise ValueError('frozen kernel/grader changed')
    shutil.copytree(bundle, out / 'bundle')
    shutil.copytree(parent / 'checkpoints', out / 'checkpoints')
    copied = Checkpoints(out / 'checkpoints', contract['tests_sha256'], contract['case_keys'])
    source = out / 'initial-working'
    copied.restore_working('foundation', source)
    if application_manifest(source) != decision['source_manifest']:
        raise ValueError('continuation lost graded source bytes')
    feedback = failure_feedback(evidence)
    if use_foundation_feedback:
        feedback += '\nAdditional frozen internal regression failure:\n' + foundation_feedback(previous, decision, frozen)
        feedback += '\nRepair only the observed UI ambiguity while preserving the public contract. Do not add unrelated features or change tests. Prefer minimal edits, then hand off to the independent verifier.'
    if reviewed:
        feedback += '\nController-reviewed concrete blocker (not permission to change tests):\n' + blocker_diagnosis
    (out / 'feedback-1.txt').write_text(feedback)
    return {'previous_trial': result['resume_trial'], 'checkpoint': decision['snapshot'],
            'previous_model': result.get('model', 'glm-5.3-flash'),
            'previous_passed': record['passed'], 'previous_total': record['total'],
            'stagnant_rounds': decision['stagnant_rounds'],
            'foundation_feedback_consumed': bool(use_foundation_feedback or result.get('holdout_input_to_coder')),
            'previous_foundation_passed': result.get('holdout', {}).get('passed', 0),
            'foundation_stagnant_rounds': result.get('foundation_stagnant_rounds', 0),
            'reviewed_blocker_diagnosis_sha256': (hashlib.sha256(blocker_diagnosis.encode()).hexdigest()
                                                  if reviewed else prior_review)}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('acceptance_trial', type=Path)
    parser.add_argument('--holdout', choices=['github', 'sheet'], required=True)
    parser.add_argument('--continue-from', type=Path)
    parser.add_argument('--compare-from', type=Path)
    parser.add_argument('--model', choices=('glm-5.3-flash', 'deepseek-v4-flash'), default='glm-5.3-flash')
    parser.add_argument('--foundation-feedback', action='store_true')
    parser.add_argument('--refresh-coder', action='store_true')
    parser.add_argument('--reviewed-blocker', type=Path,
                        help='one explicitly reviewed blocker after an automatic route pause; one coding pass only')
    parser.add_argument('--cap-cny', type=float, default=3)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--passes', type=int, default=3)
    args = parser.parse_args()
    if not (0 < args.cap_cny <= 5 and 800 <= args.seconds <= 1800 and 1 <= args.passes <= 3):
        raise ValueError('bounded mechanism tranche required')
    if not args.name.replace('-', '').isalnum():
        raise ValueError('simple experiment name required')
    if args.foundation_feedback and not args.continue_from:
        raise ValueError('foundation feedback requires a verified previous run')
    if args.refresh_coder and not args.continue_from:
        raise ValueError('coder revision requires a verified retained checkpoint')
    if args.compare_from and args.continue_from:
        raise ValueError('a controlled model comparison is not an old-model continuation')
    if args.reviewed_blocker and (not args.continue_from or args.passes != 1 or args.refresh_coder or args.foundation_feedback):
        raise ValueError('reviewed blocker requires exact old coder/test/source, one pass, and no other experiment change')
    return args


def comparison_seed(previous, out, frozen, status, args):
    """Repeat the exact starting checkpoint/feedback with a different model.

    This new comparison keeps the old failed/paused route intact. It is not a
    reset or continuation of its no-gain counter and cannot use extra allowances.
    """
    prior = json.loads((previous / 'manifest.json').read_text())
    closed = [t for t in status['trials'] if t['id'] == prior['name'] and t['closed']]
    if (len(closed) != 1 or prior['model'] == args.model or not prior.get('finished_with_validation') or
            prior['runtime_tests'] != frozen['tests_sha256'] or prior['source_sha256'] != frozen['requirements_sha256'] or
            args.cap_cny != prior['cap_cny'] or args.seconds != prior['deadline_seconds'] or args.passes != prior['max_passes']):
        raise ValueError('model comparison requires same frozen inputs/allowances and a closed different-model trial')
    if manifest(previous / 'bundle') != prior['bundle_sha256']:
        raise ValueError('comparison controller changed')
    checkpoint = prior.get('continuation', {}).get('checkpoint')
    if not isinstance(checkpoint, str) or len(checkpoint) != 64:
        raise ValueError('comparison needs an explicit verified starting checkpoint')
    expected = application_manifest(previous / 'checkpoints/snapshots' / checkpoint)
    if not expected or application_manifest(previous / 'initial-working') != expected:
        raise ValueError('comparison starting source differs from original verified checkpoint')
    feedback = (previous / 'feedback-1.txt').read_text()
    original_input = json.loads((previous / 'attempt-1/pass/prompt.txt').read_text().split('\n\nRUNTIME DATA:\n')[-1])
    if feedback != original_input['previous_independent_verifier_feedback']:
        raise ValueError('comparison feedback differs from the original model input')
    shutil.copytree(previous / 'initial-working', out / 'initial-working')
    shutil.copytree(previous / 'bundle', out / 'bundle')
    shutil.copy2(previous / 'feedback-1.txt', out / 'feedback-1.txt')
    return {'kind': 'model_only_controlled_comparison_not_old_route_resume',
            'previous_trial': prior['name'], 'previous_model': prior['model'], 'model': args.model,
            'foundation_feedback_consumed': prior.get('holdout_input_to_coder', False),
            'starting_checkpoint': checkpoint, 'starting_source_manifest': expected,
            'previous_passed': prior['passes'][-1]['passed'], 'previous_total': prior['passes'][-1]['total'],
            'feedback_sha256': manifest(out).get('feedback-1.txt')}


def trial_inputs(args):
    status = control('/status', {'read': True})
    if status['unresolved_cost_lock'] or any(not t['closed'] for t in status['trials']):
        raise RuntimeError('another trial/unknown cost exists')
    active = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    if any(n.startswith(('factory26-trial', 'factory26-grade', 'factory26-acceptance')) for n in active):
        raise RuntimeError('a trial/grader is already active')
    compiler = args.acceptance_trial.resolve()
    acceptance = compiler / 'result/acceptance'
    frozen = json.loads((acceptance / 'frozen.json').read_text())
    blank = compiler / 'result/blank-control'
    if not json.loads((blank / 'verdict.json').read_text())['gate']:
        raise RuntimeError('frozen acceptance has not rejected blank UI')
    if manifest(acceptance / 'suite') != frozen['tests_sha256']:
        raise RuntimeError('runtime acceptance has changed')
    holdout = json.loads((CACHE / 'foundation-v1.json').read_text())['suites'][args.holdout]
    holdout_path = CODE / 'foundation' / args.holdout
    if manifest(holdout_path) != holdout['tests_sha256'] or frozen['requirements_sha256'] != holdout['requirement_source_sha256']:
        raise RuntimeError('holdout/public-source freeze differs')
    return status, compiler, acceptance, frozen, blank, holdout, holdout_path


def main():
    args = parse_args()
    status, compiler, acceptance, frozen, blank, holdout, holdout_path = trial_inputs(args)
    out = CACHE / 'mechanism' / args.name
    out.mkdir(parents=True, exist_ok=False)
    continuation, comparison = None, None
    if args.continue_from:
        diagnosis = args.reviewed_blocker.read_text() if args.reviewed_blocker else None
        continuation = continue_working(args.continue_from, out, frozen, status, args.foundation_feedback, diagnosis)
        if args.model != continuation['previous_model']:
            raise ValueError('continuation cannot silently change model; use the controlled comparison path')
        if args.refresh_coder:
            continuation['explicit_coder_revision'] = refresh_coder(out / 'bundle')
    elif args.compare_from:
        comparison = comparison_seed(args.compare_from.resolve(), out, frozen, status, args)
    else:
        prepare_controller(out / 'bundle')
        shutil.copytree(CACHE / 'octos-upstream/arc/template', out / 'initial-working')
        (out / 'feedback-1.txt').write_text('First coding pass. No application has been tested. Implement the complete selected foundation.')
    source = out / 'initial-working'
    keys = list(case_outcomes(json.loads((blank / 'playwright.json').read_text())))
    checkpoints = Checkpoints(out / 'checkpoints', frozen['tests_sha256'], keys)
    manifest_before = manifest(out / 'bundle')
    metadata = {'name': args.name, 'model': args.model, 'phase': 'mechanism',
        'image': subprocess.check_output(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True).strip(),
        'cap_cny': args.cap_cny, 'deadline_seconds': args.seconds, 'max_passes': args.passes, 'started': time.time(),
        'runtime_tests': frozen['tests_sha256'], 'source_sha256': frozen['requirements_sha256'],
        'compiler_trial': str(compiler), 'bundle_sha256': manifest_before,
        'holdout_input_to_coder': (frozen['tests_sha256'] == holdout['tests_sha256'] or
                                  bool(comparison and comparison['foundation_feedback_consumed']) or
                                  bool(continuation and continuation['foundation_feedback_consumed'])),
        'acceptance_origin': frozen.get('schema'),
        'coverage_claim': frozen.get('coverage_claim', 'generated internal tests, not official coverage'),
        'formal_upload_allowed': False, 'continuation': continuation, 'comparison': comparison}
    (out / 'manifest.json').write_text(json.dumps(metadata, indent=2))
    token = control('/trial', {'id': args.name, 'phase': 'mechanism', 'cap_cny': args.cap_cny, 'seconds': args.seconds})['token']
    deadline = time.monotonic() + args.seconds
    last, accepted, records = None, False, []
    print(f'Start {args.name}: max CNY{args.cap_cny} / {args.seconds}s / {args.passes} pass(es); serial only', flush=True)
    try:
        for number in range(1, args.passes+1):
            if deadline - time.monotonic() < 800:
                break
            if control('/status', {'read': True})['unresolved_cost_lock']:
                raise RuntimeError('uncertain upstream cost; no next model call')
            attempt = out / f'attempt-{number}'
            rc = coding_pass(out / 'bundle', source, acceptance, out / f'feedback-{number}.txt', attempt, token, 360, args.model)
            if manifest(out / 'bundle') != manifest_before:
                raise RuntimeError('frozen coding controller changed')
            working = attempt / 'pass/working'
            if not working.exists():
                records.append({'attempt': number, 'kernel_exit': rc, 'error': 'no working export'})
                break
            last = working
            evidence = attempt / 'runtime-evidence'
            verdict, proof = grade_application(working, acceptance / 'suite', evidence, frozen['expected'],
                                               min(850, max(1, deadline-time.monotonic()-300)), out / 'bundle/grader')
            decision = checkpoints.record('foundation', working, evidence, proof)
            records.append({'attempt': number, 'kernel_exit': rc, 'passed': verdict['passed'],
                            'total': verdict['total'], 'decision': decision})
            print(f'Pass {number}: internal {verdict["passed"]}/{verdict["total"]}; accepted={decision["accepted"]}; paused={decision["pause_module"]}', flush=True)
            if decision['accepted']:
                accepted = True
                break
            if decision['pause_module']:
                break
            source = out / f'resumed-working-{number}'
            checkpoints.restore_working('foundation', source)
            (out / f'feedback-{number+1}.txt').write_text(failure_feedback(evidence))
    finally:
        control('/close', {'id': args.name})
        budget = control('/status', {'read': True})
        (out / 'budget.json').write_text(json.dumps(budget, indent=2))
        metadata.update(finished=time.time(), passes=records, runtime_accepted=accepted,
            cost_upper_cny=sum(c['charged'] for c in budget['calls'] if c['trial']==args.name)/1e6)
        (out / 'manifest.json').write_text(json.dumps(metadata, indent=2))
    finalize_foundation(metadata, last, accepted, checkpoints, holdout_path, holdout, out, deadline)
    print(json.dumps({k: metadata.get(k) for k in ('foundation_gate', 'runtime_accepted','holdout','cold_delivery_gate','cost_upper_cny')}), flush=True)
    return 0 if metadata['foundation_gate'] else 1


def finalize_foundation(metadata, last, accepted, checkpoints, holdout_path, holdout, out, deadline):
    # Test source is never mounted in the coder. Visible failure feedback is
    # explicitly tracked; after it is used this is regression, not unseen data.
    metadata['foundation_evidence_kind'] = ('frozen_internal_regression' if metadata['holdout_input_to_coder']
                                            else 'previously_unseen_internal_holdout')
    if last is not None:
        independent, _ = grade_application(last, holdout_path, out / 'holdout-evidence', holdout['expected_count'],
                                           max(1, min(300, deadline-time.monotonic())), out / 'bundle/grader')
        metadata['holdout'] = {k: independent.get(k) for k in ('passed','total','gate','actual_restarts')}
        if accepted and independent['gate']:
            checkpoints.export_accepted(out / 'clean-delivery')
            cold, _ = grade_application(out / 'clean-delivery', holdout_path, out / 'cold-evidence', holdout['expected_count'],
                                        max(1, min(300, deadline-time.monotonic())), out / 'bundle/grader')
            metadata['cold_delivery_gate'] = cold['gate']
    metadata['foundation_gate'] = bool(accepted and metadata.get('holdout', {}).get('gate') and metadata.get('cold_delivery_gate'))
    prior = metadata.get('continuation') or {}
    gain = metadata.get('holdout', {}).get('passed', 0) > prior.get('previous_foundation_passed', 0)
    metadata['foundation_stagnant_rounds'] = (0 if gain or metadata['foundation_gate']
                                              else prior.get('foundation_stagnant_rounds', 0)+1)
    metadata['finished_with_validation'] = time.time()
    (out / 'manifest.json').write_text(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
