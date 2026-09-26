# Controlled rebuild laboratory (not a submission)

This directory implements the local A/B and acceptance gates. It does **not**
replace the submitted runtime yet. Current state and authority live in
`docs/REBUILD_EXECUTION_2026-09-26.md`; stop if its cost lock is active.

## Frozen dependencies

- A: git archive of 804c4e8 at `.cache/ab-campaign/baseline-a`.
- B: Apache-2.0 upstream `https://github.com/octos-org/octos-arc`, commit
  561e03d6fa5f4606901f8694d21f2182cb73538b. License remains in the unmodified
  checkout `.cache/ab-campaign/octos-upstream`; no third-party source is copied
  into these overlay files. Any future vendor/package step must retain LICENSE
  and notices and identify changes.
- Official arc.17 binary at `.cache/ab-campaign/runtime/octos`; exact hash in
  `campaign.json`. Do not rely on the upstream stale arc.13 lock.
- Docker image `factory26-ab:20260926`, built from `Dockerfile`; native ARM
  Python/Node/Chromium with x86 Octos via existing Docker emulation. This is NOT
  a claim of official x86 browser parity. The two named prerequisite images
  are local runner images; a fresh machine requires those prerequisites first.
- Python controller: repository `.venv/bin/python`. SDK in image pinned
  `arcbench-runtime==0.1.0`; Playwright 1.54.0 at `/opt/arcbench`.

## Safe no-model commands (repository root)

```sh
.venv/bin/python -m unittest discover -s experiments/rebuild -p test_budget_gateway.py -v
.venv/bin/python experiments/rebuild/preflight.py
.venv/bin/python experiments/rebuild/test_sensitivity.py
.venv/bin/python experiments/rebuild/freeze_foundation.py
.venv/bin/python experiments/rebuild/summarize.py
```

The last two require the downloaded public YAMLs and existing ledger. The freeze
command refuses to overwrite changed tests. The sensitivity command uses an
explicit internal positive fixture plus six deliberate defects and never
calls a model. Its success is validator evidence, not candidate business quality.

## Billable commands — serialized baseline, original acceptance gates apply

`run_trial.py A|B task 1|2` creates one fresh trial; `run_matrix.py --stage
smoke|ticket` runs serially. Neither should run while an unresolved reservation
exists without a specific human-authorized full-cost exception. Do not manually mark a reservation settled, release it based on absence
from a bill, automatically retry, or use a personal key.

The local gateway accepts the organizer key through its loopback-only memory
handoff, not CLI arguments, shell history or source files. It publishes port
18021 on 127.0.0.1, routes only the fixed organizer completion endpoint, and
issues scoped per-trial tokens. Candidate containers have only the internal
`factory26-ab-internal` network; only the gateway has upstream egress. Control
state is never mounted into candidates. Require this topology before resuming.

Each request reserves uncached input/output maxima in persistent SQLite before
transmission. Incomplete usage or transport ambiguity locks all further calls.
Error metadata does not settle money. Formal platform bills still require a
separate verified import and aggregate ¥120 check before formal work is allowed.

One exact exception was explicitly approved by the user in
`authorizations/2026-09-26-db7578d7.json`. `authorize_worst_case.py` applied it to
the existing ledger: the entire bound is permanently counted, actual bill and
usage remain unknown, the original call is not rewritten as settled. This
local-only administration has no gateway endpoint and is not available to the
candidate. Every future uncertain call still locks. The live gateway has now
reloaded the append-only authorization after the user-approved Docker restart;
the ledger hash was unchanged. Never replace that ledger. Total ceiling ¥120.

## Evidence and test boundaries

`.cache/ab-campaign/runs/<trial>/` holds manifest, generation log, disposable
browser result, failure screenshot/trace, and budget snapshot. Proxy bodies in
`gateway/traces/` redact both upstream and scoped tokens (no headers). Early B
smoke requests predate full body capture; do not call those traces complete.
`comparison.json` excludes documented infrastructure failures and does not
select a winner until the whole prespecified matrix is evaluable.

Public practice tests come only from the pinned public upstream directories.
Official hidden tests and private submissions are never inputs. Self-authored
foundation tests remain internal evidence, even when frozen. Generated output
is copied for evaluation, not modified in place. Candidate implementations
cannot modify the mounted assertions or receive the process-restart control key.
All generated accounts/state belong to disposable grade copies.

Source tests, deliberate fault fixtures, keys, and experimental caches must not
enter the eventual submitted agent. The current submission allowlist excludes
this directory entirely. Do not package current main.py and describe it as the
new Octos-based implementation: engine selection and mechanism work are pending.

## Offline candidate mechanisms (not enabled in A/B)

`requirement_catalog.py <public-yaml> --output <fresh-json>` retains ancestor
contracts and expands inherited folder dependencies. `checkpoints.py` separates
working and accepted snapshots, checks source/test/report hashes against the
controller's trusted export proof, pauses after two no-gain attempts, and never
exports raw failed work when no accepted snapshot exists.

`replay_checkpoints.py <successful-sensitivity-run>` reuses real grader receipts
and then performs a fresh cold browser/restart run on the exported accepted
snapshot. `--state-only` is debugging only and explicitly leaves gate=false.
Neither module supplies prebuilt application answers or changes the A/B source.

The strengthened foundation grader runs generated build/server as UID 65534,
keeps tests/reports on the native private container filesystem, and checks
export hashes outside the container. The grader parent requires exactly CHOWN,
SETUID, SETGID, KILL, DAC_OVERRIDE capabilities after dropping all others;
generated child processes drop identity/capabilities and keep no-new-privileges.
No external network is needed. Do not rely on chmod on macOS bind mounts to
protect assertions or report files. The final deliberate-tamper and cold
delivery gates completed after the user-authorized Docker restart. See the
dated recovery record for exact evidence. `regrade_public.py` regraded all eight
existing smoke apps under the same isolation; every original result remained
unchanged. This is grader continuity, not eight new model generations.
