"""Reproducible no-model environment gate; records real runs, no skip credit."""
import json
from pathlib import Path
import subprocess
import time

from run_trial import CACHE, IMAGE, ROOT, bind


def main():
    out = CACHE / 'preflight' / str(int(time.time()))
    out.mkdir(parents=True)
    common = ['docker', 'run', '--rm', '--network', 'none', '--memory', '2g', '--cpus', '2', '--shm-size', '512m',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges']
    browser = common + bind(CACHE/'baseline-a', '/agent') + ['--env', 'FACTORY26_RUN_BROWSER_INTEGRATION=1',
              '--workdir', '/agent', '--entrypoint', 'python', IMAGE, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_browser_probe.py', '-v']
    kernel_code = '''from arcbench_agent_runtime import AgentRuntime
import tempfile,sys,os
from pathlib import Path
sys.path.insert(0,'/upstream/arc')
from octos_stdio import OctosStdioSession
p=Path(tempfile.mkdtemp());r=AgentRuntime.from_env(project_dir=str(p))
assert hasattr(r.traceability,'init_store') and hasattr(r.traceability,'init_db') and hasattr(r.git,'add_all')
s=OctosStdioSession('/runtime/octos',p,dict(os.environ,OPENAI_API_KEY='unused-local-no-model'),p/'state')
try:
 s.bootstrap_profile('custom','glm-5.3-flash','http://127.0.0.1:9/v1','OPENAI_API_KEY',timeout=30)
 s.open();print('SDK and kernel startup: OK, no model calls')
finally:s.close()
'''
    kernel = common + bind(CACHE/'octos-upstream', '/upstream') + bind(CACHE/'runtime', '/runtime') + ['--entrypoint','python',IMAGE,'-c',kernel_code]
    results = {}
    for name, cmd in [('browser', browser), ('kernel', kernel)]:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        (out/f'{name}.log').write_text(res.stdout+res.stderr)
        results[name] = {'exit': res.returncode, 'no_skips': 'skipped=' not in res.stdout+res.stderr}
        print(name, results[name], flush=True)
    grade = common + bind(CACHE/'octos-upstream/arc/template','/generated') + bind(CACHE/'octos-upstream/arc/public-tests/smoke--counter','/public-tests') + bind(out,'/evidence',True) + bind(ROOT/'experiments/rebuild','/grader') + ['--entrypoint','python',IMAGE,'/grader/grade.py','--expected','1']
    res = subprocess.run(grade, capture_output=True,text=True,timeout=120)
    (out/'negative-grader.log').write_text(res.stdout+res.stderr)
    verdict = json.loads((out/'verdict.json').read_text())
    results['empty_page_rejected'] = verdict.get('passed') == 0 and verdict.get('test_exit') != 0 and not verdict['gate']
    results['gate'] = all(r['exit']==0 and r['no_skips'] for r in (results['browser'],results['kernel'])) and results['empty_page_rejected']
    (out/'environment.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results), out, flush=True)
    return 0 if results['gate'] else 1


if __name__=='__main__': raise SystemExit(main())
