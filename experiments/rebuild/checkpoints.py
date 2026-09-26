"""Host-owned working/accepted checkpoints bound to independent test evidence.

Controller store and receipt directory MUST be outside the candidate's writable
mount. No model-provided PASS or count is accepted. Not enabled in frozen A/B.
"""
import hashlib
import json
from pathlib import Path
import shutil

from grade import manifest


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def application_manifest(root):
    for part in ('frontend','backend'):
        if not (root/part).is_dir() or any(p.is_symlink() for p in (root/part).rglob('*')):
            raise ValueError('application parts must be real directories without symlinks')
    return {k:v for k,v in manifest(root).items()
            if k.startswith(('frontend/','backend/')) and 'dist' not in Path(k).parts}


def case_outcomes(report):
    outcomes={}
    def walk(suite):
        for spec in suite.get('specs',[]):
            for test in spec.get('tests',[]):
                key=json.dumps([spec['file'],spec['line'],spec['title'],test.get('projectName','')],ensure_ascii=False)
                if key in outcomes:raise ValueError('duplicate test case')
                results=test.get('results',[])
                outcomes[key]=(test.get('expectedStatus')=='passed' and test.get('status')=='expected'
                    and len(results)==1 and results[0].get('status')=='passed'
                    and results[0].get('retry',0)==0 and not results[0].get('errors'))
        for child in suite.get('suites',[]):walk(child)
    for suite in report.get('suites',[]):walk(suite)
    return outcomes


class Checkpoints:
    def __init__(self, root: Path, tests_sha256: dict, case_keys: list):
        self.root=root.resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        if not tests_sha256 or not case_keys or len(set(case_keys))!=len(case_keys):
            raise ValueError('nonempty frozen tests and unique case keys required')
        self.contract={'tests_sha256':tests_sha256,'case_keys':sorted(case_keys)}
        path=self.root/'frozen.json'
        if path.exists():
            if json.loads(path.read_text())!=self.contract:raise ValueError('frozen acceptance changed')
        else:
            with path.open('x') as stream:json.dump(self.contract,stream,indent=2)
        (self.root/'attempts').mkdir(exist_ok=True)
        (self.root/'snapshots').mkdir(exist_ok=True)

    def snapshot(self, work, hashes):
        key=digest(hashes)
        destination=self.root/'snapshots'/key
        if not destination.exists():
            destination.mkdir()
            for part in ('frontend','backend'):
                shutil.copytree(work/part,destination/part,
                    ignore=shutil.ignore_patterns('node_modules','dist','.git'))
        if application_manifest(destination)!=hashes:
            raise ValueError('snapshot changed or copy incomplete; refusing promotion')
        return key

    def history(self):
        return [json.loads(p.read_text()) for p in sorted((self.root/'attempts').glob('*.json'))]

    def validated_evidence(self, work: Path, evidence: Path, trusted_export_manifest: dict):
        work,evidence=work.resolve(),evidence.resolve()
        if self.root==work or self.root in work.parents or work in self.root.parents:
            raise ValueError('controller store must not overlap candidate workspace')
        if evidence==work or work in evidence.parents:
            raise ValueError('candidate cannot own its acceptance receipt')
        names=['verdict.json']+(['playwright.json'] if 'playwright.json' in trusted_export_manifest else [])
        for name in names:
            actual=hashlib.sha256((evidence/name).read_bytes()).hexdigest()
            if trusted_export_manifest.get(name)!=actual:
                raise ValueError('receipt differs from trusted controller export proof')
        verdict=json.loads((evidence/'verdict.json').read_text())
        report=(json.loads((evidence/'playwright.json').read_text()) if 'playwright.json' in names
                else {'suites':[],'errors':['independent grader produced no behavior report']})
        hashes=application_manifest(work)
        scored_hashes={k:v for k,v in verdict.get('source_manifest',{}).items()
                      if k.startswith(('frontend/','backend/')) and 'dist' not in Path(k).parts}
        if hashes!=scored_hashes:raise ValueError('code changed since independent grading')
        if verdict.get('test_manifest')!=self.contract['tests_sha256']:
            raise ValueError('tests differ from frozen acceptance')
        if not all(verdict.get(k) for k in ('source_unchanged','tests_unchanged','process_cleaned')):
            raise ValueError('incomplete or dirty grading receipt')
        outcomes=case_outcomes(report)
        if set(outcomes)-set(self.contract['case_keys']):
            raise ValueError('extra test cases outside frozen acceptance')
        missing=set(self.contract['case_keys'])-set(outcomes)
        passed=sorted(k for k,v in outcomes.items() if v)
        complete=bool(passed and not missing and len(passed)==len(outcomes) and verdict.get('gate')
                      and verdict.get('test_exit')==0 and not report.get('errors'))
        return hashes, verdict, report, passed, complete

    def record(self, module, work: Path, evidence: Path, trusted_export_manifest: dict):
        hashes, verdict, report, passed, complete = self.validated_evidence(work,evidence,trusted_export_manifest)
        identity=digest({'module':module,'code':hashes,'verdict':verdict,'report':report})
        history=self.history()
        for previous in history:
            if previous['receipt_id']==identity:return previous  # no double-counted attempts
        local=[p for p in history if p['module']==module]
        seen={k for p in local for k in p['passed_cases']}
        gain=set(passed)-seen
        stagnant=0 if gain or complete else (local[-1]['stagnant_rounds'] if local else 0)+1
        snapshot=self.snapshot(work,hashes)  # failures are retained, not rolled back
        decision={'schema':'independent-checkpoint-v1','module':module,'receipt_id':identity,
            'snapshot':snapshot,'passed_cases':passed,'new_passed_cases':sorted(gain),
            'stagnant_rounds':stagnant,'pause_module':not complete and stagnant>=2,
            'accepted':complete,'evidence_kind':verdict.get('evidence_kind'),
            'source_manifest':hashes,'frozen_contract_sha256':digest(self.contract)}
        path=self.root/'attempts'/f'{len(history)+1:06d}-{identity}.json'
        with path.open('x') as stream:json.dump(decision,stream,indent=2)
        return decision

    def export_accepted(self, destination: Path):
        accepted=[p for p in self.history() if p['accepted']]
        if not accepted:raise ValueError('no accepted state; never fall back to failed working files')
        selected=accepted[-1]
        return self.export_record(selected,destination)

    def restore_working(self, module, destination: Path):
        attempts=[p for p in self.history() if p['module']==module]
        if not attempts:raise ValueError('no working checkpoint for this module')
        return self.export_record(attempts[-1],destination)

    def export_record(self, selected, destination):
        source=self.root/'snapshots'/selected['snapshot']
        if application_manifest(source)!=selected['source_manifest']:
            raise ValueError('accepted snapshot corrupted')
        # Destination must be fresh; never destructively replace a user's app.
        shutil.copytree(source,destination)
        if application_manifest(destination)!=selected['source_manifest']:
            raise ValueError('export hash mismatch')
        return selected
