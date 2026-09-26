"""Real offline browser mutation gate, not model generation or official score."""
import json
import shutil
import subprocess
import time

from run_trial import CACHE, IMAGE, ROOT, bind
from grade import manifest


def main():
    out=CACHE/'sensitivity'/str(int(time.time()))
    out.mkdir(parents=True)
    code=ROOT/'experiments/rebuild'
    results={}
    for defect in ('healthy','blank','200-only','session-loss','overwrite-db','volatile','tamper'):
        fixture=out/defect/'source'; evidence=out/defect/'evidence'
        evidence.mkdir(parents=True)
        shutil.copytree(code/'sensitivity/fixture',fixture)
        (fixture/'backend/variant.txt').write_text(defect)
        cmd=['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--shm-size','512m',
             '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','SETUID','--cap-add','SETGID',
             '--cap-add','KILL','--cap-add','DAC_OVERRIDE',
             '--security-opt','no-new-privileges']
        cmd+=bind(fixture,'/generated')+bind(code/'sensitivity/suite','/public-tests')
        cmd+=bind(evidence,'/evidence',True)+bind(code,'/grader')
        cmd+=['--entrypoint','python',IMAGE,'/grader/foundation_grade.py','--expected','1']
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
        proof=json.loads(p.stdout.strip().splitlines()[-1])['export_manifest']
        if manifest(evidence)!=proof:
            raise RuntimeError('exported evidence differs from isolated grader stdout proof')
        (evidence/'controller.log').write_text(p.stdout+p.stderr)
        v=json.loads((evidence/'verdict.json').read_text())
        results[defect]={'gate':v['gate'],'passed':v['passed'],'restarts':v.get('actual_restarts',0),
            'source_unchanged':v['source_unchanged'],'tests_unchanged':v['tests_unchanged'],
            'process_cleaned':v['process_cleaned'],'exit':p.returncode}
        results[defect]['isolated_export_verified']=True
        if defect=='tamper':
            log=(evidence/'server.log').read_text()
            results[defect]['writes_denied']=log.count('TAMPER_DENIED')==2 and 'TAMPER_SUCCEEDED' not in log
        print(defect,results[defect],flush=True)
        if defect=='healthy' and not v['gate']:
            raise RuntimeError('positive control failed; do not count rejected faults as evidence')
    passed=results['healthy']['gate'] and all(not r['gate'] for k,r in results.items() if k!='healthy')
    passed=bool(passed and all(all(r[k] for k in ('source_unchanged','tests_unchanged','process_cleaned')) for r in results.values()))
    passed=bool(passed and results['tamper']['writes_denied'])
    summary={'gate':passed,'kind':'internal_validator_sensitivity_not_application_quality','results':results}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),out,flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
