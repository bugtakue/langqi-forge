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

## Next action, unchanged experimental design

A repeat2 is running in the same serial matrix (host exec session 76257), then
B repeat2. No official upload/run was launched. Finish both
repeats before kernel selection. The common improvement to test later is
independent acceptance that starts from each required user entry and preserves
the required locator contract; do not patch a prebuilt Ticket answer into the
agent or relax public assertions. Independent tests must not conceal ambiguous
entry actions by automatically choosing `.first()` or by bypassing navigation.
