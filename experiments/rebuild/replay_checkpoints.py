"""No-model integration proof using real independent browser receipts.

Does not modify any original receipt/fixture, does not infer official quality.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from checkpoints import Checkpoints, application_manifest, case_outcomes
from grade import manifest
from run_trial import CACHE, ROOT, IMAGE, bind


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('sensitivity_run',type=Path)
    parser.add_argument('--state-only',action='store_true',help='debug checkpoint semantics only; NEVER a cold-delivery release gate')
    args=parser.parse_args()
    samples=args.sensitivity_run.resolve()
    if not args.state_only and not json.loads((samples/'summary.json').read_text())['gate']:
        raise RuntimeError('need successful real sensitivity test, not fabricated PASS')
    out=CACHE/'checkpoint-replay'/str(int(time.time()));out.mkdir(parents=True)
    healthy=samples/'healthy'
    receipt=json.loads((healthy/'evidence/verdict.json').read_text())
    report=json.loads((healthy/'evidence/playwright.json').read_text())
    contract=receipt['test_manifest']; cases=list(case_outcomes(report))
    store=Checkpoints(out/'controller',contract,cases)
    def record(target,sample):
        log=(sample/'evidence/controller.log').read_text()
        proof=json.loads(next(line for line in log.splitlines() if line.startswith('{"evidence_kind"')))['export_manifest']
        return target.record('foundation',sample/'source',sample/'evidence',proof)
    first=record(store,healthy)
    assert first['accepted']
    assert record(store,healthy)==first
    assert len(store.history())==1  # identical receipt is not another attempt
    for defect in ('overwrite-db','volatile'):
        sample=samples/defect
        before=application_manifest(sample/'source')
        decision=record(store,sample)
        assert not decision['accepted']
        assert application_manifest(sample/'source')==before
    assert decision['pause_module'] and decision['stagnant_rounds']==2
    store.restore_working('foundation',out/'resumed-working')
    assert (out/'resumed-working/backend/variant.txt').read_text()=='volatile'
    chosen=store.export_accepted(out/'delivery')
    assert chosen['snapshot']==first['snapshot']
    assert (out/'delivery/backend/variant.txt').read_text()=='healthy'
    assert not list((out/'delivery').rglob('db.json'))  # test accounts never shipped
    failed=Checkpoints(out/'failure-only',contract,cases)
    record(failed,samples/'volatile')
    try:failed.export_accepted(out/'must-not-exist')
    except ValueError:pass
    else:raise AssertionError('unverified working tree escaped as a delivery')
    assert not (out/'must-not-exist').exists()
    try:Checkpoints(out/'controller',{'changed.spec.ts':'different'},cases)
    except ValueError:pass
    else:raise AssertionError('frozen tests changed silently')
    if args.state_only:
        summary={'gate':False,'kind':'checkpoint_state_logic_only_not_release_acceptance',
            'checkpoint_logic_passed':True,'failed_work_preserved':True,'pause_after_two_no_gain':True,
            'only_accepted_exported':True,'no_test_accounts_exported':True,'cold_delivery_browser_gate':None,
            'no_accepted_fallback_rejected':True,'frozen_suite_change_rejected':True,'idempotent_receipts':True}
        (out/'summary.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps(summary),out)
        return
    # Actual fresh build/browser/restart after export, never just a hash PASS.
    evidence=out/'cold-delivery-evidence';evidence.mkdir()
    code=ROOT/'experiments/rebuild'
    cmd=['docker','run','--rm','--network','none','--memory','1g','--cpus','2','--shm-size','512m',
         '--cap-drop','ALL','--cap-add','CHOWN','--cap-add','SETUID','--cap-add','SETGID',
         '--cap-add','KILL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges']
    cmd+=bind(out/'delivery','/generated')+bind(code/'sensitivity/suite','/public-tests')
    cmd+=bind(evidence,'/evidence',True)+bind(code,'/grader')
    cmd+=['--entrypoint','python',IMAGE,'/grader/foundation_grade.py','--expected','1']
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=100)
    proof=json.loads(result.stdout.strip().splitlines()[-1])['export_manifest']
    assert manifest(evidence)==proof
    (evidence/'controller.log').write_text(result.stdout+result.stderr)
    verdict=json.loads((evidence/'verdict.json').read_text())
    assert result.returncode==0 and verdict['gate'] and verdict['actual_restarts']>=1
    summary={'gate':True,'kind':'internal_checkpoint_integration_not_candidate_score',
        'source_sensitivity_run':str(samples),'failed_work_preserved':True,'pause_after_two_no_gain':True,
        'only_accepted_exported':True,'no_test_accounts_exported':True,'cold_delivery_browser_gate':True,
        'no_accepted_fallback_rejected':True,'frozen_suite_change_rejected':True,'idempotent_receipts':True}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),out)


if __name__=='__main__':main()
