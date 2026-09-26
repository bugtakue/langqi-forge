"""Evidence-bound local comparison. Never merges local and official scores."""
import json
from pathlib import Path
import sqlite3

from run_trial import CACHE, ROOT

INFRASTRUCTURE = {
    'a-smoke--counter-1': 'EXDEV output-parent mount error; cost retained',
    'b-smoke--counter-2': 'Unix socket on macOS bind mount; zero model calls',
    'b-smoke--dice-1': 'Unix socket on macOS bind mount; zero model calls',
    'a-ticket-booking--ticket-booking-1': 'upstream response uncertain; exact user authorization permanently charges full bound; NOT a capability result',
}
REPLACEMENTS = {k:k+'-environment-retry' for k in INFRASTRUCTURE}


def main():
    config = json.loads((ROOT/'experiments/rebuild/campaign.json').read_text())
    db = sqlite3.connect(f'file:{CACHE}/gateway/budget.sqlite?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    calls = [dict(r) for r in db.execute('SELECT id,trial,status,charged,reserve,payload_sha FROM calls')]
    approvals = {r['call_id']:dict(r) for r in db.execute('SELECT call_id,reserve,payload_sha FROM worst_case_authorizations')}
    db.close()
    def cost_locked(call):
        approval = approvals.get(call['id'])
        allowed_unknown = (call['status']=='reserved' and approval
            and call['charged']==call['reserve']==approval['reserve'] and call['payload_sha']==approval['payload_sha'])
        return call['status']!='settled' and not allowed_unknown
    rows=[]
    for candidate in ('A','B'):
        for task, count in config['public_tasks'].items():
            for repeat in (1,2):
                name=f'{candidate.lower()}-{task}-{repeat}'
                name=REPLACEMENTS.get(name,name)
                folder=CACHE/'runs'/name
                item={'candidate':candidate,'task':task,'repeat':repeat,'run':name,'state':'not_run'}
                if (folder/'manifest.json').is_file():
                    m=json.loads((folder/'manifest.json').read_text())
                    c=[row for row in calls if row['trial']==name]
                    item.update(cost_uncached_upper_cny=sum(row['charged'] for row in c)/1e6,
                        requests=len(c),unsettled=any(row['status']!='settled' for row in c),
                        cost_locked=any(cost_locked(row) for row in c),
                        requirements_sha256=m['requirements_sha256'],tests_sha256=m['tests_sha256'])
                    if name in INFRASTRUCTURE:
                        item.update(state='infrastructure_unscorable',reason=INFRASTRUCTURE[name])
                    elif (folder/'evidence/verdict.json').is_file() and 'finished' in m:
                        v=json.loads((folder/'evidence/verdict.json').read_text())
                        clean=all(v.get(k) for k in ('source_unchanged','tests_unchanged','process_cleaned'))
                        item.update(state='scored',passed=v['passed'],total=v['total'],
                            qualified=bool(clean and not item['unsettled'] and v['total']==count
                                and v['passed']>=config['public_min_passes'][task]
                                and not v.get('skipped') and not v.get('flaky') and not v.get('errors')),
                            seconds=round(m['finished']-m['started'],3))
                    else:
                        item['state']='nonterminal'
                rows.append(item)
    qualifying=[]
    for candidate in ('A','B'):
        candidate_rows=[r for r in rows if r['candidate']==candidate]
        if all(r.get('qualified') for r in candidate_rows):qualifying.append(candidate)
    result={'evidence_kind':'public_source_tests_local_not_official_score','qualifying_candidates':qualifying,
        'selection_allowed':len(qualifying)>0 and all(r['state']=='scored' for r in rows),
        'charged_upper_with_unsettled_cny':sum(c['charged'] for c in calls)/1e6,
        'unsettled_count':sum(c['status']!='settled' for c in calls),
        'authorized_worst_case_count':len(approvals),
        'unresolved_cost_lock':any(cost_locked(c) for c in calls),
        'excluded_infrastructure':INFRASTRUCTURE,'rows':rows}
    path=CACHE/'comparison.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
