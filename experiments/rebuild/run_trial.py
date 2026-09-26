"""One serialized, cost-reserved generation + independent cold browser grading.

Controller runs on host; candidate receives only its scoped gateway token and
has no external network, no control file, no organizer key, no writable tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / '.cache/ab-campaign'
IMAGE = 'factory26-ab:20260926'


def control(path, payload):
    token = (CACHE / 'gateway/control.token').read_text().strip()
    req = urllib.request.Request('http://127.0.0.1:18021' + path,
          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'X-Control': token})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def bind(source, target, writable=False):
    return ['--mount', f'type=bind,source={source},target={target}' + ('' if writable else ',readonly')]


def controller_fingerprint():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'experiments/rebuild').rglob('*.py'))}


def adapter():
    dest = CACHE / 'adapter'
    dest.mkdir(exist_ok=True)
    # Only our overlay is copied; original upstream remains untouched.
    for name in ('octos_adapter.py', 'verify_node.py'):
        shutil.copy2(ROOT / 'experiments/rebuild' / name, dest / name)
    for name in ('prompts', 'template', 'arc-policy.toml'):
        path = dest / name
        if not path.is_symlink(): path.symlink_to('/upstream/arc/' + name)
    return dest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', choices=['A', 'B'])
    parser.add_argument('task', choices=['smoke--counter', 'smoke--dice', 'ticket-booking--ticket-booking'])
    parser.add_argument('repeat', type=int, choices=[1, 2])
    parser.add_argument('--environment-retry', action='store_true', help='explicitly logged rerun after an infrastructure fault, never a best-of retry')
    args = parser.parse_args()
    config = json.loads((ROOT / 'experiments/rebuild/campaign.json').read_text())
    name = f'{args.candidate.lower()}-{args.task}-{args.repeat}'
    if args.environment_retry:
        name += '-environment-retry'
    out = CACHE / 'runs' / name
    out.mkdir(parents=True, exist_ok=False)  # Never silently repeat a billed trial.
    generated, evidence = out / 'generated', out / 'evidence'
    generated.mkdir(); evidence.mkdir(); (out / 'scratch').mkdir()
    upstream = CACHE / 'octos-upstream'
    task = upstream / 'arc/tasks' / args.task
    tests = upstream / 'arc/public-tests' / args.task
    checksums = {str(p.relative_to(tests)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tests.rglob('*') if p.is_file()}
    manifest = {'candidate': args.candidate, 'task': args.task, 'repeat': args.repeat,
                'config': config, 'tests_sha256': checksums,
                'controller_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'controller_sha256': controller_fingerprint(),
                'requirements_sha256': hashlib.sha256((task/'requirements.yaml').read_bytes()).hexdigest(),
                'image': subprocess.check_output(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], text=True).strip(),
                'started': time.time()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    token = control('/trial', {'id': name, 'phase': 'baseline', 'cap_cny': config['trial_cap_cny'],
                               'seconds': config['trial_deadline_seconds']})['token']
    # Docker --env NAME imports only these exact values. Never echo token or
    # supply the host environment wholesale. The upstream key is not here.
    env = dict(os.environ, OPENAI_API_KEY=token)
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-trial', '--network', 'factory26-ab-internal',
           '--memory', '3g', '--cpus', '2', '--shm-size', '512m', '--security-opt', 'no-new-privileges',
           '--cap-drop', 'ALL', '--env', 'OPENAI_API_KEY', '--env', 'OPENAI_BASE_URL=http://factory26-gateway:8021/v1',
           '--env', 'MODEL=glm-5.3-flash', '--env', 'PYTHONDONTWRITEBYTECODE=1',
           '--env', 'FACTORY26_MAX_OUTPUT_TOKENS=32768', '--env', 'FACTORY26_RUN_BROWSER_INTEGRATION=1']
    # A atomically promotes via a temporary sibling of output. Mount the
    # parent, not the output itself, so rename stays on one filesystem.
    cmd += bind(task, '/task') + bind(tests, '/public-tests') + bind(out, '/work', True)
    if args.candidate == 'A':
        cmd += bind(CACHE / 'baseline-a', '/agent')
        cmd += ['--workdir', '/agent', '--entrypoint', 'python', IMAGE,
                'main.py', '/task', '--output-dir', '/work/generated', '--web-port', '3000']
    else:
        cmd += bind(upstream, '/upstream') + bind(adapter(), '/adapter') + bind(CACHE / 'runtime', '/runtime')
        for key, value in {
            'OCTOS_BIN': '/runtime/octos', 'OCTOS_MODEL': 'glm-5.3-flash', 'OCTOS_PROVIDER': 'custom',
            'OCTOS_TIME_BUDGET': '780', 'OCTOS_NODE_TIME_BUDGET': '240', 'OCTOS_NODE_TIMEOUT': '420',
            'OCTOS_ARC_FINAL_RESERVE': '120', 'OCTOS_ARC_MIN_NODE_SECONDS': '60',
            'OCTOS_ARC_VERIFY_TIMEOUT': '300', 'OCTOS_REPAIR_ROUNDS': '2',
            'OCTOS_ARC_FINAL_REPAIRS': '1', 'OCTOS_ARC_LLM_TIMEOUT': '240',
            'OCTOS_ARC_NODE_MAX_TOKENS': '32768', 'OCTOS_MAX_ITERATIONS': '40',
            'OCTOS_ARC_INSTALL_PLAYWRIGHT': '0', 'OCTOS_ARC_PLAYWRIGHT_ROOT': '/opt/arcbench',
            'OCTOS_ARC_LOCAL_TESTS': '/public-tests', 'PYTHONPATH': '/adapter',
            'OCTOS_ARC_REPAIR_WINDOW': '240', 'OCTOS_ARC_PLAYWRIGHT_TIMEOUT': '180',
        }.items(): cmd += ['--env', key + '=' + value]
        cmd += ['--workdir', '/work/generated', '--entrypoint', 'python', IMAGE, '/adapter/octos_adapter.py',
                '/task', '--output-dir', '/work/generated', '--web-port', '3000']
    print(f'Start {name}: one trial, max CNY{config["trial_cap_cny"]}, {config["trial_deadline_seconds"]}s', flush=True)
    try:
        with (out / 'generation.log').open('w') as log:
            proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            try: rc = proc.wait(timeout=config['trial_deadline_seconds'])
            except subprocess.TimeoutExpired:
                subprocess.run(['docker', 'stop', '--time', '5', 'factory26-trial'], stdout=subprocess.DEVNULL)
                proc.wait(timeout=15); rc = 124
    finally:
        control('/close', {'id': name})
        (out / 'budget.json').write_text(json.dumps(control('/status', {'read': True}), indent=2))
    if controller_fingerprint() != manifest['controller_sha256']:
        raise RuntimeError('controller changed during generation; preserve evidence, do not score silently')
    grade = ['docker', 'run', '--rm', '--name', 'factory26-grade', '--network', 'none', '--memory', '2g',
             '--cpus', '2', '--shm-size', '512m', '--cap-drop', 'ALL',
             '--cap-add', 'CHOWN', '--cap-add', 'SETUID', '--cap-add', 'SETGID',
             '--cap-add', 'KILL', '--cap-add', 'DAC_OVERRIDE', '--security-opt', 'no-new-privileges']
    grade += bind(generated, '/generated') + bind(tests, '/public-tests') + bind(evidence, '/evidence', True)
    grade += bind(ROOT / 'experiments/rebuild', '/grader')
    grade += ['--entrypoint', 'python', IMAGE, '/grader/foundation_grade.py', '--public-suite',
              '--expected', str(config['public_tasks'][args.task])]
    graded = subprocess.run(grade, timeout=240, capture_output=True, text=True)
    from grade import manifest as evidence_manifest
    proof = json.loads(graded.stdout.strip().splitlines()[-1])['export_manifest']
    if evidence_manifest(evidence) != proof:
        raise RuntimeError('public grade export differs from private controller proof')
    (evidence / 'controller.log').write_text(graded.stdout + graded.stderr)
    manifest.update(generation_exit=rc, grading_exit=graded.returncode, finished=time.time())
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f'Completed {name}; evidence: {out}', flush=True)
    return graded.returncode


if __name__ == '__main__': raise SystemExit(main())
