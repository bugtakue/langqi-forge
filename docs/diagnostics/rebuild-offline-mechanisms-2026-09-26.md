# Rebuild continuation: offline mechanisms, no model spend

## Scope and outcome

Frozen A/B remains unchanged. No model call, formal upload, official evaluation,
production change, personal key use, or Docker daemon restart in this continuation.
Billing remains unresolved: meter synchronized 09:01:27 Beijing, balance 99.838926,
latest successful bill still 08:43:00; reserved call `db7578d75f9900b512f400ae642ec87b`
is not released. An explicit user choice has been requested: keep waiting for
organizer reconciliation, or exceptionally account the full reserved ¥0.174823
as spent while retaining unknown actual cost. No answer was treated as approval.

The user subsequently explicitly chose “按最坏费用全额记账后继续”. The exact
call now has an append-only worst-case authorization in the existing SQLite
ledger; the full ¥0.174823 remains charged, original reserved status and unknown
usage are preserved. Total conservative occupation stays ¥0.534191. No actual
provider settlement is claimed. Authorization is exact-call/payload/amount,
cannot be edited/deleted, does not release budget, and does not authorize the
next unknown request. All 13 gateway regressions pass. The old gateway process
has not reloaded the new source yet; no new billable trial has started.

The user also asked this task to consult the existing task named “循济因果”. A
read-only coordination question was sent to thread
`019ea4f3-03f4-7dc2-be91-e2b8ccbcb301` about container ownership, dependencies
and maintenance windows. It expressly excludes restart/stop/deployment actions.

## Runtime requirements: fixed candidate module, not yet selected engine

`experiments/rebuild/requirement_catalog.py` accepts only the explicitly supplied
public runtime tree. It retains all ancestor descriptions/scenarios, expands
folder dependencies, refuses unknown IDs/duplicate IDs/cycles, and orders ready
prerequisites by downstream reach (document order breaks ties). No application
code or competition IDs are embedded in the module. Four structural regressions
pass; the actual downloaded GitHub 47 and Sheet 24 atoms compile successfully.

Artifacts: `.cache/ab-campaign/contracts-v1/{github,sheet}.json`, bound to the
original public YAML SHA256 values. GitHub has 39 atomic nodes inheriting at
least one dependency from a folder. Max ancestor+node contract text is 11,798
characters for GitHub and 16,406 for Sheet: these are NOT silently truncated.
These counts demonstrate preservation, not behavior passed or better scores.
Coherent foundation-flow generation still needs the billable controlled trial.

## Checkpoints: independently scored source, failed work preserved

`checkpoints.py` keeps controller-owned immutable content-addressed snapshots
outside the candidate mount. It binds both source and frozen tests to independent
grader receipts and the trusted export hash proof; checks actual per-case
results, not model prose or summary counts; and makes repeat receipt processing
idempotent. Builds without behavior evidence can be retained but never accepted.
Two consecutive attempts without a newly passed case pause that module. Failed
work is restored from the latest working snapshot; delivery only exports an
accepted snapshot into a fresh directory, with no raw-working-tree fallback.

Actual existing browser receipts were replayed: healthy accepted, response-
overwrite and volatile-storage failures retained, second no-progress failure
paused, working restore stayed volatile, export stayed healthy and contained no
test database. Changed frozen suites and no-accepted fallback were rejected.

Evidence: `.cache/ab-campaign/checkpoint-replay/1790385570/summary.json`.
This was `--state-only`; **gate=false**, cold-delivery re-run is still pending.
It is not a complete release gate or candidate business score.

## Validator isolation: discovered vulnerability and incomplete final gate

The first low-UID test proved copied test assertions were protected, but the
macOS host evidence bind mount still allowed a UID-65534 app to overwrite
`/evidence/playwright.json`, despite chmod 0700. This is a real defect in relying
on host-mount permissions as the boundary, not a passing security result.
See `.cache/ab-campaign/sensitivity/1790385050/tamper/evidence/server.log`.

Current source moves all scoring into a root-private native-container temporary
directory. Build/server run as UID 65534 without model credentials or restart
tokens. The controller exports evidence and prints its SHA256 manifest to its
own stdout; the outer host checks the exact export after container exit. App
stdout goes only to a log file. This protects against an app forging the host
export after grading. It still needs the final deliberate-tamper validation.

At `.cache/ab-campaign/sensitivity/1790385188/`, the new isolation version
completed healthy + blank/200-only/session-loss/overwrite/volatile cases with
expected results and verified export hashes. The last tamper container never
started, so the complete seven-case gate is **not passed**. Initial local
permission-transition runs (1790384773 and following) are setup failures, not
application or fault-detection successes; all reports are retained.

## Local runtime blocker and cleanup

Docker Desktop accepted container creation but did not start processes. The
tamper container `c3ded85c1248` and independent `/bin/true` health probe
`a4e4f9594e57cf5f5a0b86890106ecd83e15fbc5ec5d568ded6d9f95f5fc20ea`
both showed Status=created, Running=false, Pid=0, StartedAt=zero; events contained
create/attach but no start. This is not a browser test failure or a model score.

Only those two confirmed never-started disposable test containers were removed.
The initial SIGTERM did not actually stop their host Docker CLI processes; a
subsequent exact-PID check found them still present. Their verified CLI parent/
child PIDs 93727/93804 and 94057/94121, plus this task's blocked read-only
`docker ps` PIDs 94957/95025, were then killed with SIGKILL. These are client
processes, not the daemon or other containers. Host evidence/source remains.
Other user containers and the budget gateway were untouched. Do not restart
Docker Desktop without coordinating with the user: unrelated services are live.
The gateway's loopback `/health` still returned ready=true after Docker list
queries stopped responding. No fresh container was started to bypass the fault.

## Resume order

1. Keep the explicit exact-call full-cost authorization and persistent ledger.
   After runtime recovery, reload the gateway source and verify the new policy,
   fixed upstream, internal-only candidate network and memory-only key handoff.
2. Coordinate Docker startup recovery; do not stop unrelated services without
   user authorization. Run the positive control + all six defects;
   use `replay_checkpoints.py <successful-sensitivity-run>` without state-only,
   and require its fresh build/browser/process-restart delivery verification.
3. Complete the prespecified Ticket A/B matrix before choosing an engine.
4. Integrate the candidate modules only after selection, keep test generation
   independent/frozen, then execute the actual foundation behavior experiments.
5. Formal submission still requires every original gate, the shared ¥120 budget,
   and a fresh no-active-run check. No new official score is claimed here.
