# Docker runtime/storage blocker — read-only diagnosis

## Current evidence

This continuation made no model call, official upload, container creation,
Docker restart, filesystem repair, volume deletion or production change.

- The existing Docker Unix socket was present. Both `/_ping` and
  `/containers/json?all=true` returned no bytes before their explicit five-second
  timeouts. This is an observation failure, not proof that every container stopped.
- The existing gateway loopback health endpoint still returned `ready: true`.
  SQLite has zero open trials and one unknown-cost reserved call; its exact user
  authorization retains all 174823 micro-CNY. No fresh billable work is active.
- The consulted “循济因果” turn remains completed with no readable assistant items;
  it has not provided maintenance approval or container-ownership evidence.

## Specific failure found in host-accessible VM logs

At 2026-09-26 01:22 UTC (09:22 Beijing):

- `Data/log/vm/dockerd.log:2843` reported a container-state write failing with
  `read-only file system`; later network-store writes failed the same way.
- `dockerd.log:2867` reported an `input/output error` while cleaning up an existing
  container. These messages are daemon/storage errors, not browser test failures.
- `Data/log/vm/containerd.log:3737-3748` reported `fatal error: fault`, SIGBUS and
  `panic during panic`.
- The Docker backend subsequently logged repeated VM ping/stats timeouts and
  inability to inject events. It did not regain a readable daemon API here.

The log paths are under
`/Users/zerongliu/Library/Containers/com.docker.docker/`.
Raw logs stay outside Git; only these non-secret diagnostic facts are recorded.

Docker's configured data file is `/Volumes/Xunji SSD/Docker/data/Docker.raw`
(63,999,836,160 logical bytes; last metadata write observed 09:21).
The mounted host APFS USB volume reports Media Read-Only=No and Volume
Read-Only=No, with about 800 GiB available. SMART is not supported through the
reported interface. This rules out a currently full host volume, but does NOT
prove disk health or distinguish a virtual-filesystem fault from a transient
USB/storage fault. No repair or active-image copying was attempted.

## Required next action

Recovery verified after the authorized restart: old Docker processes exited,
the installed app relaunched, and the daemon API was serving at 01:42 UTC.
Seven previously running business containers automatically returned to Up;
Redis subsequently reported healthy. Previously exited fuguai/xunji development
containers were not started. A disposable no-network container successfully
wrote a temporary file, exited and was auto-removed.

The existing gateway restarted with updated mounted source. Its original ledger
SHA256 stayed `f8d2831eaa7697d3a46f709282ef37b31d7207b64104e39767b6df0136d0e383`.
The same organizer key was reloaded through the loopback-only form; ready=true,
authorization count=1, open trials=0, cost lock=false, conservative occupation
¥0.534191. Network internal=true. Meter at 09:45:19 still showed ¥99.838926.

Recovery gates (all no-model):

- Full seven-sample sensitivity passed: `.cache/ab-campaign/sensitivity/1790387037/summary.json`.
- Checkpoint replay INCLUDING cold delivery passed: `.cache/ab-campaign/checkpoint-replay/1790387166/summary.json`.
- Browser/kernel/SDK no-skip environment passed: `.cache/ab-campaign/preflight/1790387183/environment.json`.
- Private low-UID public grader regraded all eight original apps with unchanged
  scores A=2/4, B=4/4: `.cache/ab-campaign/regrade-private/1790387221/summary.json`.
  Public assertions and original 10s-test/180s-suite timeouts remain unchanged.

These prove recovered local execution, not hardware health, a new generated
application or an official score. All original source/receipts remain untouched.

The following approval/start observations precede the verified recovery above:

Update: the user explicitly replied “允许你重启”. Docker Desktop's native
Troubleshoot → Restart button was clicked once; its UI changed to Engine
stopping with Restart disabled. No Clean/Purge, factory reset, disk repair or
data removal was selected. The original organizer key remains only in browser
automation memory for the same authorized local handoff after restart. Recovery
is not yet verified; do not start a second restart merely because polling times out.

Before that approval, the user had not approved the Docker Desktop restart.
That action can interrupt unrelated local containers and erase the gateway's
memory-only credential, so do not infer permission from the general goal.
Do not use factory reset, prune, remove Docker.raw, remount storage writable,
or run filesystem repair to work around this blocker.

After explicit maintenance permission or user-restored runtime: verify the same
daemon and a disposable startup, preserve the budget ledger, reload gateway
source/key through the memory-only handoff, finish the existing offline gates,
then resume the prespecified Ticket A/B comparison serially. A restart alone is
not evidence that storage or the application is healthy.

Previous goal turn classification: progress (code/checkpoint work, exact budget
authorization and documented coordination). Current turn: new diagnostic
evidence, but the Docker recovery/authorization blocker remains. No new official
score and no top-three completion claim.
