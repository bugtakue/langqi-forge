"""Internal foundation gate, not public-reference-validated or official scoring.

Only the test process receives the restart control credential. Application runs
in a disposable copy without model credentials, original source/tests read-only.
At least one actual process restart and every frozen test must pass.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import uuid

from grade import manifest, run, summarize
from restart_control import AppProcess, RestartControl

APP_UID = 65534


def prepare_app_identity(work, evidence):
    # Only disposable app copies are writable by generated build/server code.
    # Root-owned tests, report paths, restart controller and grading code are not.
    work.chmod(0o755)
    evidence.chmod(0o700)
    for part in ('frontend', 'backend'):
        root = work/part
        for path in [root, *root.rglob('*')]:
            if path.is_symlink():
                raise RuntimeError('application symlinks cannot cross the grader boundary')
            os.chown(path, APP_UID, APP_UID)


def build_app(work, env, evidence):
    with (evidence/'build.log').open('w') as log:
        try:
            return subprocess.run(['npm','run','build'],cwd=work/'frontend',env=env,
                user=APP_UID,group=APP_UID,extra_groups=[],stdout=log,stderr=subprocess.STDOUT,timeout=90).returncode
        except subprocess.TimeoutExpired:
            return 124


def grade(work, tests, evidence, result, expected, public_suite=False):
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'PLAYWRIGHT_BROWSERS_PATH')}
    env.update(PORT='3000', HOST='127.0.0.1', CI='1', E2E_BASE_URL='http://127.0.0.1:3000',
               NODE_PATH='/opt/arcbench/node_modules')
    prepare_app_identity(work,evidence)
    if build_app(work,env,evidence):
        result['error'] = 'build failed'
        return
    suite = work/'suite'
    shutil.copytree(tests, suite)
    suite.chmod(0o700)
    (suite/'node_modules').symlink_to('/opt/arcbench/node_modules', target_is_directory=True)
    config = suite/'playwright.config.cjs'
    timeout = 10000 if public_suite else 60000
    config.write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts',timeout:"+str(timeout)+",retries:0,workers:1,"
        "reporter:[['json']],outputDir:process.env.E2E_RESULTS_DIR,use:{headless:true,baseURL:process.env.E2E_BASE_URL,"
        "actionTimeout:10000,trace:'retain-on-failure',screenshot:'only-on-failure'}}")
    process = AppProcess(work/'backend', env, evidence/'server.log', identity=APP_UID)
    try:
        process.start()
        with RestartControl(process) as control:
            test_env = dict(env, **control, PLAYWRIGHT_JSON_OUTPUT_NAME=str(evidence/'playwright.json'),
                            E2E_RESULTS_DIR=str(evidence/'test-results'))
            rc = run(['/opt/arcbench/node_modules/.bin/playwright', 'test', '-c', str(config)],
                     suite, test_env, evidence/'playwright.log', seconds=180 if public_suite else max(90, expected*65))
            result['test_exit'] = rc
            report = evidence/'playwright.json'
            if report.is_file():
                result.update(summarize(json.loads(report.read_text())))
            result['gate'] = (rc == 0 and result['passed'] == expected and result['total'] == expected
                and not result.get('skipped') and not result.get('flaky') and not result.get('errors')
                and (public_suite or process.restarts > 0))
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        process.stop()
        result['actual_restarts'] = process.restarts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected', type=int, required=True)
    parser.add_argument('--public-suite', action='store_true',
                        help='explicit public practice tests; retain original 10s/180s timeouts, no added restart requirement')
    args = parser.parse_args()
    source, tests, exported = Path('/generated'), Path('/public-tests'), Path('/evidence')
    # Native Linux filesystem enforces UID isolation. macOS bind mounts can
    # ignore guest chmod; never trust them as the scoring security boundary.
    private = tempfile.TemporaryDirectory(prefix='private-grade-evidence-')
    evidence = Path(private.name)
    before, tests_before = manifest(source), manifest(tests)
    kind = 'public_source_tests_local_not_official_score' if args.public_suite else 'internal_foundation_not_official_score'
    result = {'evidence_kind': kind, 'run_id':str(uuid.uuid4()), 'gate': False,
              'passed': 0, 'total': args.expected, 'source_manifest': before, 'test_manifest': tests_before}
    evidence.mkdir(exist_ok=True)
    evidence.chmod(0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='foundation-grade-') as td:
            work = Path(td)
            for part in ('frontend', 'backend'):
                if any(p.is_symlink() for p in (source/part).rglob('*')):
                    raise RuntimeError('source contains symlink; reject before copying')
                shutil.copytree(source/part, work/part, symlinks=False,
                               ignore=shutil.ignore_patterns('node_modules', '.git', 'dist'))
            grade(work, tests, evidence, result, args.expected, public_suite=args.public_suite)
    except Exception as exc:
        result['gate'], result['error'] = False, str(exc)
    result['source_unchanged'] = before == manifest(source)
    result['tests_unchanged'] = tests_before == manifest(tests)
    result['process_cleaned'] = not AppProcess.port_open()
    result['gate'] = bool(result['gate'] and all(result[k] for k in
        ('source_unchanged', 'tests_unchanged', 'process_cleaned')))
    (evidence/'verdict.json').write_text(json.dumps(result, indent=2))
    proof = manifest(evidence)
    exported.mkdir(exist_ok=True)
    shutil.copytree(evidence,exported,dirs_exist_ok=True)
    # Only the root controller's stdout carries this proof. Generated build and
    # app stdout are redirected to logs; parent checks after container exit.
    print(json.dumps({**{k:v for k,v in result.items() if not k.endswith('manifest')},
                      'export_manifest':proof}), flush=True)
    private.cleanup()
    return 0 if result['gate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
