"""One cost-reserved compiler experiment; no app or holdout data mounted."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from grade import manifest
from run_trial import CACHE, IMAGE, ROOT, bind, control

FILES = ('acceptance_compiler.py', 'acceptance_syntax.cjs', 'runtime_restart.ts', 'runtime_io.ts',
         'requirement_catalog.py', 'grade.py', 'prompts/acceptance.md')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('requirements', type=Path)
    parser.add_argument('--include', action='append', required=True)
    args = parser.parse_args()
    if not args.name.replace('-', '').isalnum():
        raise ValueError('experiment name must be alphanumeric/hyphen')
    status = control('/status', {'read': True})
    if status['unresolved_cost_lock'] or any(not t['closed'] for t in status['trials']):
        raise RuntimeError('an unresolved or active trial exists; no parallel call')
    containers = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    if any(n.startswith(('factory26-trial', 'factory26-grade', 'factory26-acceptance')) for n in containers):
        raise RuntimeError('experiment or grader already active')
    out = CACHE / 'mechanism' / args.name
    out.mkdir(parents=True, exist_ok=False)
    adapter = out / 'compiler'
    for name in FILES:
        destination = adapter / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'experiments/rebuild' / name, destination)
    (out / 'task').mkdir()
    shutil.copy2(args.requirements, out / 'task/requirements.yaml')
    metadata = {'kind': 'runtime_acceptance_compilation_not_app_generation',
        'trial': args.name, 'phase': 'mechanism', 'cap_cny': 1.0, 'deadline_seconds': 600,
        'model': 'glm-5.3-flash', 'included': args.include, 'compiler_sha256': manifest(adapter),
        'source_sha256': manifest(out / 'task'), 'started_at': time.time(),
        'app_input': False, 'holdout_input': False, 'image': subprocess.check_output(
            ['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True).strip()}
    (out / 'manifest.json').write_text(json.dumps(metadata, indent=2))
    (out / 'result').mkdir()
    token = control('/trial', {'id': args.name, 'phase': 'mechanism', 'cap_cny': 1.0, 'seconds': 600})['token']
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-acceptance', '--network', 'factory26-ab-internal',
        '--memory', '1g', '--cpus', '2', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--env', 'OPENAI_API_KEY', '--env', 'OPENAI_BASE_URL=http://factory26-gateway:8021/v1',
        '--env', 'PYTHONDONTWRITEBYTECODE=1']
    cmd += bind(adapter, '/compiler') + bind(out / 'task', '/task') + bind(out / 'result', '/result', True)
    cmd += ['--entrypoint', 'python', IMAGE, '/compiler/acceptance_compiler.py',
            '/task/requirements.yaml', '--output', '/result/acceptance']
    for nid in args.include:
        cmd += ['--include', nid]
    print(f'Start {args.name}: max CNY1.00 / 600s; public requirements only', flush=True)
    try:
        with (out / 'compile.log').open('w') as log:
            proc = subprocess.Popen(cmd, env=dict(os.environ, OPENAI_API_KEY=token), stdout=log, stderr=subprocess.STDOUT)
            try:
                rc = proc.wait(timeout=600)
            except subprocess.TimeoutExpired:
                subprocess.run(['docker', 'stop', '--time', '5', 'factory26-acceptance'], capture_output=True)
                proc.wait(timeout=15)
                rc = 124
    finally:
        control('/close', {'id': args.name})
        (out / 'budget.json').write_text(json.dumps(control('/status', {'read': True}), indent=2))
    metadata.update(exit=rc, finished_at=time.time())
    (out / 'manifest.json').write_text(json.dumps(metadata, indent=2))
    if manifest(adapter) != metadata['compiler_sha256']:
        raise RuntimeError('compiler changed during run')
    if rc:
        print(f'Compiler failed; evidence preserved: {out}', flush=True)
        return rc
    # No organizer or scoped key, gateway network, app, or holdout reaches this check.
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-acceptance-check', '--network', 'none',
           '--memory', '1g', '--shm-size', '512m', '--cpus', '2', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges']
    cmd += bind(ROOT / 'experiments/rebuild/acceptance_sensitivity.py', '/checker/acceptance_sensitivity.py')
    cmd += bind(adapter / 'grade.py', '/checker/grade.py')
    cmd += bind(out / 'result/acceptance', '/frozen') + bind(out / 'result', '/result', True)
    cmd += ['--entrypoint', 'python', IMAGE, '/checker/acceptance_sensitivity.py', '/frozen', '--output', '/result/blank-control']
    checked = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    (out / 'blank.log').write_text(checked.stdout + checked.stderr)
    print(checked.stdout[-1500:], flush=True)
    print(f'Compiler and blank-control evidence: {out}', flush=True)
    return checked.returncode


if __name__ == '__main__':
    raise SystemExit(main())
