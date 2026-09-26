# Sheet foundation: observed failure repaired, clean replay passed

Trial `sheet-foundation-refresh-blocker-v1`, controller f9da141, DeepSeek V4 Flash,
one coding pass. Source checkpoint
`5c7f0bd4432c89be2c7c744a336e62564b5e261084ef9bc77dce1025da639d65`.

The independent runtime suite passed 2/2, the repeated foundation suite passed
2/2, and the clean-delivery cold suite passed 2/2. Each executed one real process
restart, with zero skips/flaky results and unchanged source/tests. All test
processes were cleaned up. Frozen test hashes remain
`f54ba9652bd30196dd382a07d958ad4c312cfe160356f4523ebe912d0df259f9`
(workspace.spec.ts) and
`8f32844eeccf61873b8830ae60ff5cefacc8ffac5a1a89c0d32479c0224aac3b`
(restart.ts).

The coder changed only two asset URLs in frontend/src/index.html, anchoring
app.css and app.js at the root. Five other source files stayed byte-identical.
This fixed the documented deep-link refresh failure; app data and assertions
were not changed. Explicit human diagnostic feedback was used and recorded.
This is NOT an autonomous from-blank success, unseen holdout, complete 13-atom
coverage or new official score. Evidence is under
`.cache/ab-campaign/mechanism/sheet-foundation-refresh-blocker-v1/`.

This trial's uncached upper cost was ¥0.977946; campaign conservative total
¥8.323356, no open trial or unresolved-cost lock at completion. Official best
remains the previously verified 17/200, 6.55, rank 10; no new official upload.

## Next: reproducibility instead of another hand-guided repair

Freeze one generic coder revision that treats nested-route reload as a fresh
entry and requires assets/saved state to survive it. It contains no task IDs,
app source, predefined data, selectors or test answers. Starting ONLY from the
unchanged upstream blank template, run `sheet-foundation-fresh-v1-1` then
`sheet-foundation-fresh-v1-2` serially, identical DeepSeek model, coder/kernel,
public catalog, frozen tests, ≤¥5/1800s/3 passes per run. No old implementation
or manual feedback enters either first pass. Failed source and actual browser
feedback can be retained within each run; two no-gain rounds still pause.
Both repeats count, not the better one. No additional manual rescue is part of
this experiment. Any failure leaves reproducibility unproven.

The local per-trial cap is raised from ¥3 to ¥5 to avoid the previously observed
maximum-request reservation blocking a useful second pass. The mechanism ¥20
and campaign ¥120 caps remain enforced by the gateway; neither cap is raised.
No formal evaluation is authorized by this local result. Full-task generation,
final-candidate public-practice repeats, packaging and official gates remain.
