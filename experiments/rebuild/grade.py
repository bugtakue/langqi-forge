"""Independent cold-start public suite grader. Executes only in disposable container.

Mount /generated and /public-tests readonly; /evidence is the only writable host
mount. No model credentials or internet. JSON test verdict, never prose PASS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time


def manifest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()
            and not {'.git', 'node_modules'} & set(p.relative_to(root).parts)}


def run(argv, cwd, env, log, seconds=90):
    with log.open('w') as stream:
        try:
            return subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                                  stderr=subprocess.STDOUT, timeout=seconds).returncode
        except subprocess.TimeoutExpired:
            return 124


def summarize(report):
    stats = report.get('stats', {})
    expected = int(stats.get('expected', 0))
    failed = int(stats.get('unexpected', 0))
    skipped = int(stats.get('skipped', 0))
    flaky = int(stats.get('flaky', 0))
    return {'passed': expected, 'failed': failed, 'skipped': skipped, 'flaky': flaky,
            'total': expected + failed + skipped + flaky, 'errors': report.get('errors', [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected', type=int, required=True)
    args = parser.parse_args()
    source, tests, evidence = Path('/generated'), Path('/public-tests'), Path('/evidence')
    before, tests_before = manifest(source), manifest(tests)
    result = {'evidence_kind': 'public_source_tests_local_not_official_score',
              'source_manifest': before, 'test_manifest': tests_before,
              'passed': 0, 'total': args.expected, 'gate': False}
    evidence.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='independent-grade-') as td:
        work = Path(td)
        for part in ('frontend', 'backend'):
            if not (source / part).is_dir():
                result['error'] = 'missing application directories'
                break
            shutil.copytree(source / part, work / part, symlinks=False,
                            ignore=shutil.ignore_patterns('node_modules', '.git', 'dist'))
        else:
            grade_app(work, tests, evidence, result, args.expected)
    result['source_unchanged'] = before == manifest(source)
    result['tests_unchanged'] = tests_before == manifest(tests)
    with socket.socket() as probe:
        result['process_cleaned'] = probe.connect_ex(('127.0.0.1', 3000)) != 0
    result['gate'] = bool(result['gate'] and result['source_unchanged'] and result['tests_unchanged'] and result['process_cleaned'])
    (evidence / 'verdict.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if not k.endswith('manifest')}), flush=True)
    return 0 if result['gate'] else 1


def grade_app(work, tests, evidence, result, expected):
    env = dict(os.environ, PORT='3000', HOST='127.0.0.1', CI='1', E2E_BASE_URL='http://127.0.0.1:3000',
               NODE_PATH='/opt/arcbench/node_modules', PLAYWRIGHT_JSON_OUTPUT_NAME=str(evidence / 'playwright.json'))
    if run(['npm', 'run', 'build'], work / 'frontend', env, evidence / 'build.log'):
        result['error'] = 'build failed'
        return
    suite = work / 'suite'
    shutil.copytree(tests, suite)
    (suite / 'node_modules').symlink_to('/opt/arcbench/node_modules', target_is_directory=True)
    config = suite / 'playwright.config.cjs'
    config.write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts',timeout:10000,retries:0,workers:1,"
                      "reporter:[['json']],outputDir:'/evidence/test-results',use:{headless:true,baseURL:process.env.E2E_BASE_URL,trace:'retain-on-failure',screenshot:'only-on-failure'}}")
    with (evidence / 'server.log').open('w') as stream:
        server = subprocess.Popen(['npm', 'run', 'start'], cwd=work / 'backend', env=env,
                                  stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            ready = False
            for _ in range(80):
                with socket.socket() as probe:
                    ready = probe.connect_ex(('127.0.0.1', 3000)) == 0
                if ready or server.poll() is not None: break
                time.sleep(.25)
            if not ready:
                result['error'] = 'server failed to bind 3000'
                return
            rc = run(['/opt/arcbench/node_modules/.bin/playwright', 'test', '-c', str(config)], suite, env,
                     evidence / 'playwright.log', seconds=180)
            result['test_exit'] = rc
            report = evidence / 'playwright.json'
            if report.is_file():
                result.update(summarize(json.loads(report.read_text())))
            result['gate'] = (rc == 0 and result['total'] == expected and result['passed'] == expected
                              and not result.get('skipped') and not result.get('flaky') and not result.get('errors'))
        finally:
            try:
                os.killpg(server.pid, signal.SIGTERM)
                server.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(server.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                server.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
