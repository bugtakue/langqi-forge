# Foundation repair V3 — verified progress, not a formal score

## Outcome

Serial trial `github-foundation-repair-v3` is finished. Frozen runtime acceptance
improved from 0/11 to 6/11 and then **11/11**. The separate, previously unseen
internal foundation suite is **2/3**. No official upload or new official score.

| Receipt | Passed / total | Skips / flaky | Actual app restarts |
| --- | ---: | ---: | ---: |
| Frozen runtime suite | 11/11 | 0/0 | 5 |
| Separate foundation suite | 2/3 | 0/0 | 1 |

Both receipts confirm unchanged source/tests and cleaned processes. Runtime
receipt SHA256 `cb80b4a3a1125e7cc32feff9d772c038715f8df21f875ab6d1127862b0f7ba7f`;
foundation receipt `88c5f48f48695cac12ce1a440e8ad6dba565c20c00f8b915ed5346cd319b6ab8`.
Artifacts: `.cache/ab-campaign/mechanism/github-foundation-repair-v3/`.
Accepted-for-runtime-only checkpoint:
`92b0abe0571c10229e5b42b9c730d03d71ed5fb959313e08c7d1336b04f6d569` (6 source files).
`foundation_gate=false`; no clean delivery or cold-delivery pass claimed.

## Remaining failure and interpretation

The registration/login/reload/restart/logout/relogin foundation journey stops
after restart when `getByText(username, exact=true)` matches BOTH the Account menu
button and its menu-user text. This is a strict-locator ambiguity, NOT evidence
that authentication or session persistence failed. The other two foundation
cases pass. The public account contract requires visible current-user identity
and uniquely named Account menu / Sign out controls; it does not explicitly
forbid repeating non-control username text. Do not retroactively call this a
proven product correctness defect or silently relax the frozen assertion.

Next useful action: have the implementation agent eliminate the ambiguous
presentation while preserving the public identity/menu contract and all 11
runtime assertions, then repeat all three foundation cases and cold delivery.
If any foundation failure feedback is supplied to a future coder, that suite is
no longer an unseen holdout for that candidate; label it frozen internal
regression. Do not claim renewed holdout/generalization evidence. Never pass
official hidden tests or change frozen assertions to manufacture a pass.

V3 is a `manifest.json` controller run, unlike the older resume controller's
`result.json` + `resume-plan.json` format. The next continuation needs to handle
that exact format and runtime-accepted/foundation-failed state; do not blindly
invoke the old continuation reader or reset from the initial template. Preserve
the last checkpoint, prior passed set and no-gain history. A single bounded
repair is warranted by the observed 6→11 improvement, not a new empty full run.

## Cost and user direction

User: “费用别管那么多，重要的是成绩啊！！！！！” Within the unchanged
¥120 campaign cap and organizer credits only, subsequent ended requests with a
known fully reserved maximum are recorded at that full maximum and continued
without another small-cost question. This does not permit parallel/in-flight
retries, unpriced calls, unknown maximum liability, personal keys or recharge.

V3 conservative cost ¥0.918282, campaign total ¥4.238474. Includes request
`7a4e778b4508e8eebac29f7ec4922a9c` reserved ¥0.284613; its upstream request ended
with RemoteDisconnected after the model process stopped. The exact full charge
was retained via an append-only authorization; actual usage stays unknown.
Ledger freshly shows zero open trials and no unresolved-cost gate. Do not
mistake these upper bounds for organizer-posted actual billing.

Earlier controller mistakes remain archived: 90s dispatch timeout; a 600s
invocation rejected by the frozen 360s CLI before any model call (zero cost);
then a single corrected entry produced 6/11. They are not excluded expenses or
claimed business passes. Candidate bundles/tests were frozen per attempt.

Goal remains active. Sheet foundation, repeat generation, native x86 parity,
clean delivery, complete tasks and official same-snapshot top3 are still open.
