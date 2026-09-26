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
