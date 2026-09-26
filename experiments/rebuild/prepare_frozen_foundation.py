"""Reuse an existing pre-app internal freeze; no model or test discovery.

This creates a deliberately narrow regression experiment, NOT full requirement
coverage or a new independent holdout. It never modifies the old frozen tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from grade import manifest
from run_trial import CACHE, IMAGE, ROOT, bind, control


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('catalog', type=Path)
    parser.add_argument('requirements', type=Path)
    parser.add_argument('--suite', choices=('github', 'sheet'), required=True)
    args = parser.parse_args()
    if not args.name.replace('-', '').isalnum():
        raise ValueError('simple experiment name required')
    status = control('/status', {'read': True})
    active = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    if status['unresolved_cost_lock'] or any(not t['closed'] for t in status['trials']) or any(
            n.startswith(('factory26-trial', 'factory26-grade', 'factory26-acceptance')) for n in active):
        raise RuntimeError('another trial/grade or unresolved call exists')
    code = ROOT / 'experiments/rebuild'
    original = code / 'foundation' / args.suite
    foundation = json.loads((CACHE / 'foundation-v1.json').read_text())['suites'][args.suite]
    catalog = json.loads(args.catalog.read_text())
    if (manifest(original) != foundation['tests_sha256'] or catalog['source_sha256'] !=
            foundation['requirement_source_sha256'] or hashlib.sha256(args.requirements.read_bytes()).hexdigest() != catalog['source_sha256']):
        raise RuntimeError('original source/foundation freeze differs')
    output = CACHE / 'mechanism' / args.name
    acceptance = output / 'result/acceptance'
    acceptance.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.catalog, acceptance / 'catalog.json')
    shutil.copytree(original, acceptance / 'suite')
    frozen = {'schema': 'preexisting-foundation-internal-regression-v1',
              'requirements_sha256': catalog['source_sha256'],
              'tests_sha256': foundation['tests_sha256'], 'expected': foundation['expected_count'],
              'evidence_kind': 'internal_not_official_tests',
              'coverage_claim': 'Foundation journeys only; not complete atomic/scenario coverage. Source is visible to coder, so this is regression, not unseen holdout.',
              'original_freeze_sha256': hashlib.sha256((CACHE / 'foundation-v1.json').read_bytes()).hexdigest(),
              'collection': foundation['collection']}
    (acceptance / 'frozen.json').write_text(json.dumps(frozen, indent=2))
    cmd = ['docker', 'run', '--rm', '--name', 'factory26-acceptance-check', '--network', 'none',
           '--memory', '1g', '--shm-size', '512m', '--cpus', '2', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges']
    cmd += bind(code / 'acceptance_sensitivity.py', '/checker/acceptance_sensitivity.py')
    cmd += bind(code / 'grade.py', '/checker/grade.py')
    cmd += bind(acceptance, '/frozen') + bind(output / 'result', '/result', True)
    cmd += ['--entrypoint', 'python', IMAGE, '/checker/acceptance_sensitivity.py', '/frozen', '--output', '/result/blank-control']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    (output / 'blank.log').write_text(result.stdout + result.stderr)
    print(result.stdout, flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
