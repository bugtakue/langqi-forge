"""No-model suite collection + immutable test manifest before implementation."""
import hashlib
import json
import subprocess

from grade import manifest
from run_trial import CACHE, ROOT, IMAGE, bind

SOURCES = {'github':'bdc17d23265a6b1948aec150e69d0b2accfa37db4c569305c97be7ff7f3b0b8f',
           'sheet':'9cddf67be50748106289ed158648629a6c50c30a490d0eda5bd570c557440b96'}


def main():
    code=ROOT/'experiments/rebuild'
    frozen={'suite_version':'foundation-v1','evidence_kind':'internal_not_official_tests','suites':{}}
    for kind, expected in [('github',3),('sheet',2)]:
        source=CACHE/f'official-public/hackathon--{kind}/requirements.yaml'
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=SOURCES[kind]:raise RuntimeError('public source changed; require independent review')
        script="""import pathlib,shutil,subprocess,tempfile
p=pathlib.Path(tempfile.mkdtemp());shutil.copytree('/suite',p/'suite')
(p/'suite/node_modules').symlink_to('/opt/arcbench/node_modules')
(p/'suite/playwright.config.cjs').write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts'}")
raise SystemExit(subprocess.call(['/opt/arcbench/node_modules/.bin/playwright','test','--list','-c',str(p/'suite/playwright.config.cjs')],cwd=p/'suite'))
"""
        cmd=['docker','run','--rm','--network','none','--cap-drop','ALL','--security-opt','no-new-privileges']
        cmd+=bind(code/f'foundation/{kind}','/suite')+['--entrypoint','python',IMAGE,'-c',script]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        if proc.returncode or f'Total: {expected} tests' not in proc.stdout:
            raise RuntimeError('suite cannot collect cleanly: '+proc.stdout+proc.stderr)
        frozen['suites'][kind]={'requirement_source_sha256':digest,'tests_sha256':manifest(code/f'foundation/{kind}'),
                              'expected_count':expected,'collection':proc.stdout}
    path=CACHE/'foundation-v1.json'
    if path.exists() and json.loads(path.read_text())!=frozen:
        raise RuntimeError('frozen suite differs; never overwrite it to match a candidate')
    if not path.exists():path.write_text(json.dumps(frozen,indent=2))
    print('Collected and frozen foundation-v1, NOT application acceptance:',path)


if __name__=='__main__':main()
