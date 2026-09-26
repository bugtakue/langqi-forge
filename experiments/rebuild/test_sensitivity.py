"""Real offline browser mutation gate, not model generation or official score."""
import json
import shutil
import subprocess
import time

from run_trial import CACHE, IMAGE, ROOT, bind


def main():
    out=CACHE/'sensitivity'/str(int(time.time()))
    out.mkdir(parents=True)
    code=ROOT/'experiments/rebuild'
    results={}
    for defect in ('healthy','blank','200-only','session-loss','overwrite-db','volatile'):
        fixture=out/defect/'source'; evidence=out/defect/'evidence'
        evidence.mkdir(parents=True)
        shutil.copytree(code/'sensitivity/fixture',fixture)
        (fixture/'backend/variant.txt').write_text(defect)
        cmd=['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--shm-size','512m',
             '--cap-drop','ALL','--security-opt','no-new-privileges']
        cmd+=bind(fixture,'/generated')+bind(code/'sensitivity/suite','/public-tests')
        cmd+=bind(evidence,'/evidence',True)+bind(code,'/grader')
        cmd+=['--entrypoint','python',IMAGE,'/grader/foundation_grade.py','--expected','1']
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
        (evidence/'controller.log').write_text(p.stdout+p.stderr)
        v=json.loads((evidence/'verdict.json').read_text())
        results[defect]={'gate':v['gate'],'passed':v['passed'],'restarts':v.get('actual_restarts',0),
            'source_unchanged':v['source_unchanged'],'tests_unchanged':v['tests_unchanged'],
            'process_cleaned':v['process_cleaned'],'exit':p.returncode}
        print(defect,results[defect],flush=True)
    passed=results['healthy']['gate'] and all(not r['gate'] for k,r in results.items() if k!='healthy')
    passed=bool(passed and all(all(r[k] for k in ('source_unchanged','tests_unchanged','process_cleaned')) for r in results.values()))
    summary={'gate':passed,'kind':'internal_validator_sensitivity_not_application_quality','results':results}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),out,flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
