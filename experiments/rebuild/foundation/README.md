# Internal foundation acceptance, NOT official scoring

Authored from the publicly downloadable requirement ZIP on 2026-09-26, before
any foundation candidate is generated. No official hidden tests are used.

Source ZIP SHA256: `9884f23ea10c3dfeee170d1eed57966c8fce9a5ce18a0ac43b3d7942eba8c414`.
GitHub YAML: `bdc17d23265a6b1948aec150e69d0b2accfa37db4c569305c97be7ff7f3b0b8f`.
Sheet YAML: `9cddf67be50748106289ed158648629a6c50c30a490d0eda5bd570c557440b96`.

- GitHub: REQ-1-1-1, REQ-1-1-2, REQ-1-2, REQ-2-1-2, REQ-3-2-1, and the
  root/ancestor contracts (exact accessible names, server persistence, access).
- Sheet: REQ-1-1-1, REQ-1-2-1, REQ-2-1-1, REQ-2-1-2, REQ-3-1-1, plus
  ancestor contracts (ARIA grid/cell/tab and selection names).

The v1 subset now includes grader-owned process restart (including signed-out
session revocation after restart). `freeze_foundation.py` checks test collection
and freezes exact source/test hashes before any foundation generation. This is
NOT application acceptance: no candidate has run these business tests yet.

The separate generic `sensitivity/` fixture passed a real browser positive
control and rejected blank, 200-only, session-loss, response-overwrites-database,
and volatile-storage faults. It proves those validator pathways can fail, NOT
that the GitHub/Sheet business assertions are complete or correct. There is no publicly verified reference product
for these self-authored tests; they remain internal evidence. Do not weaken
assertions in response to a candidate's failure. A test correction requires an
independent public-spec reason, a new suite version, and both candidates rerun.
