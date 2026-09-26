"""Regrade existing generated apps after grader isolation changes; no model IO.

Original apps, tests and receipts stay untouched. A changed result invalidates
comparison continuity rather than silently choosing the better grade.
"""
import json
import subprocess
import time

from grade import manifest
from run_trial import CACHE, IMAGE, ROOT, bind


def main():
    comparison = json.loads((CACHE/'comparison.json').read_text())
    previous = [row for row in comparison['rows'] if row['state'] == 'scored']
    if not previous:
        raise RuntimeError('no completed public results to regrade')
    out = CACHE/'regrade-private'/str(int(time.time()))
    out.mkdir(parents=True)
    results = []
    for row in previous:
        source = CACHE/'runs'/row['run']/'generated'
        tests = CACHE/'octos-upstream/arc/public-tests'/row['task']
        if manifest(tests) != row['tests_sha256']:
            raise RuntimeError('public assertions changed from the original trial')
        evidence = out/row['run']
        evidence.mkdir()
        cmd = ['docker','run','--rm','--name','factory26-regrade','--network','none',
               '--memory','2g','--cpus','2','--shm-size','512m','--cap-drop','ALL',
               '--cap-add','CHOWN','--cap-add','SETUID','--cap-add','SETGID',
               '--cap-add','KILL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges']
        cmd += bind(source,'/generated') + bind(tests,'/public-tests')
        cmd += bind(evidence,'/evidence',True) + bind(ROOT/'experiments/rebuild','/grader')
        cmd += ['--entrypoint','python',IMAGE,'/grader/foundation_grade.py','--public-suite',
                '--expected',str(row['total'])]
        run = subprocess.run(cmd,capture_output=True,text=True,timeout=240)
        proof = json.loads(run.stdout.strip().splitlines()[-1])['export_manifest']
        if manifest(evidence) != proof:
            raise RuntimeError('public grade export differs from private controller proof')
        (evidence/'controller.log').write_text(run.stdout+run.stderr)
        verdict = json.loads((evidence/'verdict.json').read_text())
        clean = all(verdict.get(k) for k in ('source_unchanged','tests_unchanged','process_cleaned'))
        result = {'run':row['run'],'previous_passed':row['passed'],'passed':verdict['passed'],
                  'total':verdict['total'],'continuity':clean and verdict['passed']==row['passed']
                  and verdict['total']==row['total'],'grade_exit':run.returncode}
        results.append(result)
        print(json.dumps(result),flush=True)
    summary = {'kind':'public_grader_isolation_continuity_not_new_generation',
               'gate':all(r['continuity'] for r in results),'results':results}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),out,flush=True)
    return 0 if summary['gate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
