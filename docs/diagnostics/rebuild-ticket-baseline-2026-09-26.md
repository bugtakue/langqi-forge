# Ticket baseline — independent public results, not official scoring

Frozen A=804c4e8, B=Octos 561e03d6/arc.17. Model glm-5.3-flash,
cap ¥1.50 and 900s per independent generation. Controller b1d011e; private
low-UID grader, original public assertions and 10s-per-test timeout unchanged.
Do not edit the running controller or any generated app to improve this table.

## A repeat 1: valid technical replacement of the interrupted request

Run: `a-ticket-booking--ticket-booking-1-environment-retry`.
Generation exit=0; independent grading exit=1; **0/10**.
12 normal responses, 202667 prompt tokens, 10224 completion tokens; conservative
uncached cost **¥0.190766**, not a provider invoice. Total generation+grading
manifest duration 422.515 seconds. Source/tests unchanged and processes cleaned.
The earlier infrastructure-interrupted original run remains excluded and its
full authorized unknown-cost reservation is still permanently counted.

All ten cases failed at the SAME initial homepage action, before form fields or
business assertions ran. The public helper `support/e2e.ts:46-48` starts at home
and clicks `a[href="/register"]`. Generated `frontend/src/app.js:30` and `:53`
render that link twice, so Playwright rejects the ambiguous locator. The test
results consistently report both elements. The login route also has duplicated
entry markup, but the executed failures here are the registration entry only.

The agent's internal trace seq71 claimed both requirements completed and
`AUDIT PASS`; seq75 replayed its own capsule successfully. Those probes entered
the registration page directly and did not exercise the public entry action.
This demonstrates a false-positive internal acceptance gap, not a provider
outage. It does NOT prove every underlying account/session behavior is broken,
nor prove removing one duplicate would pass the other assertions.

Evidence under `.cache/ab-campaign/runs/<run>/`:
`manifest.json`, `generation.log`, `evidence/verdict.json`,
`evidence/playwright.json`, failure screenshots/traces, trusted controller export
hash proof, and original `generated/`. No result was hand-corrected.

## B repeat 1: independent 10/10

Run: `b-ticket-booking--ticket-booking-1`. Generation exit=0, independent
grading exit=0, **10/10**, no skipped/flaky/error cases. Source/tests unchanged,
processes cleaned, trusted export proof verified. 32 settled model responses,
291147 prompt tokens and 11436 completion tokens; conservative uncached cost
**¥0.264947**, not the upstream agent's differently denominated cost summary
and not a provider invoice. Manifest duration 464.904 seconds. The controller
commit is `50f0987` (docs-only successor); its Python hash map is identical to
the A1 map frozen at `b1d011e`.

The pipeline log shows registration and login each using a failed check followed
by repair and a new check, then the full suite. This is evidence that feedback
was exercised, not yet proof of performance without public practice tests.
B's explicit public-test access differs from A's native DSL probes; this is the
registered full-system comparison, not an isolated kernel effect.

## A repeat 2: independent 5/10, below the 9/10 threshold

Run: `a-ticket-booking--ticket-booking-2`. Generation exit=0, grading exit=1,
**5/10**; no skipped/flaky/error cases, source/tests unchanged, processes cleaned.
20 normal responses, 307608 prompt tokens and 10461 completion tokens;
conservative uncached cost **¥0.275386**, duration 367.440 seconds.

Three negative registration and two invalid-login cases pass. The registration
success case first fails to find the exact section text `账户信息`; four other
cases fail in their registration/setup step looking for the exact signed-in
username. Those failures do not establish whether later duplicate or valid-login
assertions would pass. Internal seq118 again claims `AUDIT PASS`, seq122 accepts
its self-selected capsule; the independent result remains 5/10. A's two Ticket
results are therefore 0/10 and 5/10, both below the predeclared threshold.

The four saved failure-page snapshots show `当前用户：<the test username>`.
`frontend/src/app.js:68` renders the prefix and username in one span. The test
requires exact text equal to the username, so this is a demonstrated presentation
contract mismatch; it is not evidence that registration created no account.
The internal probe accepted the prefixed string and therefore missed the mismatch.

## B repeat 2: independent 10/10; baseline selected

Run: `b-ticket-booking--ticket-booking-2`. Generation and grading exit=0;
**10/10**, zero skipped/flaky/error cases, source/tests unchanged, processes
cleaned. 68 settled responses, 993212 prompt tokens, 17980 completion tokens;
conservative uncached **¥0.844944**, duration 787.891 seconds.

The first coding node repeatedly rewrote smoke scripts despite NO PROGRESS
tool warnings, then handed off to acceptance. Registration was repaired before
login and the full-suite check. This inefficiency is retained, not erased by
the final pass. It motivates a bounded coding-to-acceptance handoff, not more
agents or a claim of zero-shot reliability.

The serial matrix/session 76257 has **finished**. No trial/grading containers or
open ledger trials remain. No new call failures; the sole raw reserved row is
the original exact user-authorized ¥0.174823 unknown-cost exception. The current
unresolved-cost lock is false. All 12 prespecified valid trials are scored.
`summarize.py` selects **B only**, with total conservative campaign cost
**¥2.110234**, including all excluded infrastructure costs and the exception.
Immutable comparison: `rebuild-baseline-complete-2026-09-26.json`; explicit
decision: `experiments/rebuild/selection.json`. A is not developed further.

Meter sync 10:25:52 Beijing: balance **¥99.213048**, posted total **¥0.786952**
from the original gift. This is an account-level observed bill, not per-trial
allocation. The unknown original call remains conservatively retained.

## Next action after selection

No official upload/run was launched. The common improvement to test next is
independent acceptance that starts from each required user entry and preserves
the required locator contract; do not patch a prebuilt Ticket answer into the
agent or relax public assertions. Independent tests must not conceal ambiguous
entry actions by automatically choosing `.first()` or by bypassing navigation.

## Official/meter boundary, 2026-09-26 10:09–10:12 Beijing

Meter overview at its visible sync time 10:09:11: balance **¥99.547259**, so
**¥0.452741** has actually been posted against the original ¥100 practice
gift. This is a mid-matrix snapshot (A2 was still active), NOT final trial cost.
It does not resolve the original uncertain request; its authorized ¥0.174823
remains permanently charged to the conservative campaign ledger.

Refreshed official Hackathon leaderboard with All tasks / All models: bugtakue
still **10/26, 6.55, 8.5% (17/200), ¥25.0273**, from the old Pro snapshot.
Third place remains 29.17 (29.5%, ¥24.9800); first place is now 55.37 (52.0%,
¥22.2067). The official Running page shows **0 active runs**. These UI facts
were checked live, not inferred from local model calls or cached standings.
No official snapshot/upload/run was created.
