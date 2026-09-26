# Next mechanism experiment — after completed baseline selection

Authority: approved rebuild plan; selection `experiments/rebuild/selection.json`.
Selected full-system baseline B, pinned Octos arc.17; keep GLM 5.3 Flash and
organizer gateway unchanged. A remains frozen. No new formal upload is allowed.
The 12-trial baseline is finished, so controller editing may resume. Do not rerun
session 76257 or any completed baseline directory. Phase cap remains ¥20 for
mechanism work and ¥120 combined new spending; baseline conservative spend is
¥2.110234. The one original unknown-cost exception stays charged permanently.

## Concrete experiment, not extra features

1. Compile behavior acceptance from the explicit runtime public requirements
   BEFORE writing application code. Preserve root and ancestor descriptions,
   scenarios, exact accessible names, public seeds and inherited dependencies.
   Freeze source/test/case-ID hashes. Do not discover test directories or load
   any official hidden tests. Map tests explicitly to requirement IDs (upstream's
   period-oriented filename regex is not a reliable map for hyphenated IDs).
2. Retain the selected execution kernel and one serial coding worker. The
   private grader owns behavior verdicts; implementation never deletes, changes
   or softens assertions. Failed work is checkpointed and resumed within its
   module. Two checks with no new passing behavior pause that module. An
   independent module starts from accepted state, while failed state is retained
   separately; a later merge must preserve passing regressions. Never fall back
   to raw failed working files when exporting.
3. Test success, rejection, reload, process restart and permission boundaries in
   disposable copies. Promote only independently accepted code, rerun accepted
   behavior after changes, export without test users/state, and cold-test the
   export again. Self-authored/generated tests remain internal evidence.

The baseline B2 repeated smoke-script writes despite NO PROGRESS warnings. The
new coding contract should explicitly hand execution to the verifier and bound
coding turns; it should not ask the coding worker to write ad hoc tests it cannot
execute. Do not assume a prompt change alone fixes the loop: measure repeated
no-op writes, cost, wall time and independent pass count in the new candidate.

## Foundation evaluation separation

`foundation-v1.json` and the existing 3 GitHub / 2 Sheet browser tests are already
frozen before foundation implementation. Keep those independent of the runtime
acceptance compiler and final holdout judge; no candidate has passed them yet.
Do not feed their source to the runtime test compiler as if it were public
requirements, or replace them with an easier generated suite.

The GitHub foundation requirements have a dependency closure of 5 atoms. The
Sheet foundation list has a declared closure of 13 atoms, including import/
export, range selection, paste, validation, filtering and rename. The existing
fanout order places Create Blank Workbook late. Therefore preserve the declared
dependencies, but do not silently claim the 5 requested entry workflows are a
5-atom complete task, or let low-fanout creation/persistence go unbuilt while
spending the budget on advanced modules. Grouping/prioritization must derive
from runtime public contracts, not ship hardcoded app solutions.

First verify a fresh generated GitHub foundation and Sheet foundation against
the frozen holdout cases, with no manual app fixes. Then rerun Counter, Dice and
Ticket twice on the complete new candidate to establish no public-practice
regression and compare the worse repeat/cost against B. If two controlled
revisions yield no repeatable improvement, stop that route and present evidence;
do not burn reserve on unreasoned reruns or change models at the same time.

Source review/unit checks are not foundation acceptance. Native x86 compatibility
also remains open after the failed local emulation probe; see its separate record.
No formal trial until all required gates pass, budget metering is enforceable,
and the official active-run list is checked again at action time.

## First compiler-only trial (registered before calling the model)

`github-acceptance-v1`: GLM 5.3 Flash, mechanism budget, maximum ¥1 / 600s.
Input is the official public GitHub YAML, selecting REQ-1-1-1, REQ-1-1-2,
REQ-1-2, REQ-2-1-2, REQ-3-2-1 with all transitive prerequisites/ancestors.
No application or foundation holdout is mounted; only six explicitly named
compiler files, the public source, output directory and scoped gateway token.
At most two model responses: the second only corrects schema/syntax/collection,
before any app exists. No transport retry or relaxed test assertions.

Offline compiler/catalog checks passed 8/8 with real Playwright collection,
including forbidden imports/calls, fake constant assertions, undeclared test
registration and inherited dependency coverage. After generation a separate
no-network/no-key container must execute the frozen suite against an HTTP-200
empty page: every case must fail with zero skips. This negative control is
necessary but not proof of business correctness. Foundation holdouts remain
frozen and untouched. No new formal upload or score is produced by this trial.

### V1 result and justified compiler revision

V1 ended before freeze/app generation: both complete model responses rejected
by coverage classification, cost upper bound ¥0.036540 (21,731 input / 6,841
output tokens), no unknown-cost call. The generator supplied successful
create/restart journeys as `persistence`; the validator only counted `positive`
and its first correction failed to name missing IDs. Neither label proves
acceptance, and duplicating journeys to satisfy labels wastes evaluation time.
Inspection also found an impossible email assertion computing `unused-` plus
the current input value; it was never accepted or used to score an app.

V2 counts a successful persistence journey toward positive coverage, requires
actual restart, identifies missing IDs explicitly, and rejects awaited UI reads
inside expected assertion values. Prompt requires saved pre-action input values
and exact literal UI locators. Existing foundation holdouts are unchanged; no
frozen suite has been edited. Offline compiler/catalog checks: 9/9.

Register `github-acceptance-v2`, same source/model/selection/cap ¥1/600s, same
two-response maximum, before any application generation. This is one explained
compiler revision, not a retry to select a better application score. Preserve
both original V1 responses, rejections and charges. If V2 still cannot produce
valid acceptance, diagnose it before any further model call.

### V2 compiler result / first kernel-foundation experiment

V2 completed with one response: 11 frozen cases, all collected; all 11 reject
the reachable empty page, zero skipped/flaky/report errors, tests unchanged and
server cleaned. Upper cost ¥0.019094; combined baseline + compiler upper cost
¥2.165868, no open trial or new billing error. Frozen source:
`.cache/ab-campaign/mechanism/github-acceptance-v2/result/acceptance`.
This validates execution and a negative control only. It is NOT official test
equivalence, and its incomplete coverage is still judged by the unseen holdout.

Register `github-foundation-kernel-v1`: same GLM/model kernel, ≤¥3 / 1800s,
at most three serial coding passes. Each pass has one bounded codergen node
(20 iterations / ≤315s within 360s graph); only file read/write/edit/search.
No model-owned shell, test execution, test edits or test-generated verdicts.
The fixed seed node restores failed WORKING source. Independent private browser
receipts drive checkpoints; two no-gain rounds pause the module; only fully
accepted state can be exported. The previous B smoke-script loop is explicitly
disallowed. No node-count expansion of the global deadline.

Coder mounts only explicit pinned upstream glue/license, candidate glue/prompt,
kernel, working source, frozen generated tests and previous actual failure steps.
Foundation holdout, budget ledger/control credential and personal keys are not
mounted. Grader mounts only three trusted code files, no model network/key;
original test source is behind a root-only parent, proved unreadable by app UID.
The private-grader healthy control passed with actual restart and unchanged
source/tests (`private-grader-check/1790391759`). Kernel/compiler/catalog checks
12/12. One final separate 3-case foundation holdout is NOT fed back during this
coding loop. Passing it plus clean cold export is required to claim this one
foundation gate; full task/Sheet/official/x86 gates remain open.

### Kernel V1 dispatch failure, no application score

V1 made exactly one completed dispatch request (4,722 input / 3 output tokens,
¥0.003786 upper cost). The model replied `ok` with no tool call; both the event
trace and the exact own pipeline-run directory inventory confirmed no launch.
The local idle container was stopped after this evidence; nothing was uploaded,
no application was generated, and no foundation/holdout score was produced.
This is an orchestration failure, not a 0/11 application result.

V2 restores the explicit upstream-style dispatch instruction and checks actual
tool/run evidence. Only when a completed, error-free reply made ZERO tool calls
can one corrective dispatch instruction follow. An observed tool call, existing
run or transport error forbids redispatch. Two no-op replies fail immediately,
not after a full coding timeout. Four kernel controller tests pass, including
no duplicate launch after observed action or transport failure.

Register `github-foundation-kernel-v2` with the same frozen V2 acceptance,
model/kernel/source, ≤¥3/1800s and unchanged coding/holdout/checkpoint rules.
Do not rerun V1 or quietly rename its result as application quality.
