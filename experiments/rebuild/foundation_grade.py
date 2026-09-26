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

from grade import manifest, run, summarize
from restart_control import AppProcess, RestartControl


def grade(work, tests, evidence, result, expected):
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'PLAYWRIGHT_BROWSERS_PATH')}
    env.update(PORT='3000', HOST='127.0.0.1', CI='1', E2E_BASE_URL='http://127.0.0.1:3000',
               NODE_PATH='/opt/arcbench/node_modules')
    if run(['npm', 'run', 'build'], work/'frontend', env, evidence/'build.log'):
        result['error'] = 'build failed'
        return
    suite = work/'suite'
    shutil.copytree(tests, suite)
    (suite/'node_modules').symlink_to('/opt/arcbench/node_modules', target_is_directory=True)
    config = suite/'playwright.config.cjs'
    config.write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts',timeout:60000,retries:0,workers:1,"
        "reporter:[['json']],outputDir:'/evidence/test-results',use:{headless:true,baseURL:process.env.E2E_BASE_URL,"
        "actionTimeout:10000,trace:'retain-on-failure',screenshot:'only-on-failure'}}")
    process = AppProcess(work/'backend', env, evidence/'server.log')
    try:
        process.start()
        with RestartControl(process) as control:
            test_env = dict(env, **control, PLAYWRIGHT_JSON_OUTPUT_NAME=str(evidence/'playwright.json'))
            rc = run(['/opt/arcbench/node_modules/.bin/playwright', 'test', '-c', str(config)],
                     suite, test_env, evidence/'playwright.log', seconds=max(90, expected*65))
            result['test_exit'] = rc
            report = evidence/'playwright.json'
            if report.is_file():
                result.update(summarize(json.loads(report.read_text())))
            result['gate'] = (rc == 0 and result['passed'] == expected and result['total'] == expected
                and not result.get('skipped') and not result.get('flaky') and not result.get('errors')
                and process.restarts > 0)
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        process.stop()
        result['actual_restarts'] = process.restarts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected', type=int, required=True)
    args = parser.parse_args()
    source, tests, evidence = Path('/generated'), Path('/public-tests'), Path('/evidence')
    before, tests_before = manifest(source), manifest(tests)
    result = {'evidence_kind': 'internal_foundation_not_official_score', 'gate': False,
              'passed': 0, 'total': args.expected, 'source_manifest': before, 'test_manifest': tests_before}
    evidence.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='foundation-grade-') as td:
            work = Path(td)
            for part in ('frontend', 'backend'):
                shutil.copytree(source/part, work/part, symlinks=False,
                               ignore=shutil.ignore_patterns('node_modules', '.git', 'dist'))
            grade(work, tests, evidence, result, args.expected)
    except Exception as exc:
        result['gate'], result['error'] = False, str(exc)
    result['source_unchanged'] = before == manifest(source)
    result['tests_unchanged'] = tests_before == manifest(tests)
    result['process_cleaned'] = not AppProcess.port_open()
    result['gate'] = bool(result['gate'] and all(result[k] for k in
        ('source_unchanged', 'tests_unchanged', 'process_cleaned')))
    (evidence/'verdict.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('manifest')}), flush=True)
    return 0 if result['gate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
