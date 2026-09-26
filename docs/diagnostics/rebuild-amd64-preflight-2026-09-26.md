# Local amd64 compatibility probe — failed, no model calls

After the full baseline matrix ended, ran the existing no-model preflight with
only its image parameter changed to the fixed local amd64 image
`sha256:87becc16d33b67315951888c1439e174fc15a4f7b3e51ebff8607b085744fcec`.
Source, browser tests and assertions were unchanged; no other trial was active.
Evidence: `.cache/ab-campaign/preflight/1790389773/`.

- Browser suite: 10 pass, 3 errors, 0 skips. Each real Chromium integration case
  reaches browser launch but exits in the local QEMU emulation. The logs include
  `/proc/self/maps` parsing failures, `inotify_init ... Function not implemented`,
  and `qemu: uncaught target signal 5`; one also reports SIGSEGV/SIGABRT. This is
  not a demonstrated application assertion failure or proof the official native
  x86 runner is broken.
- SDK/kernel check: `ModuleNotFoundError: No module named arcbench_agent_runtime`.
  The bare local amd64 image lacks the SDK dependency. The selected runtime's
  eventual requirements must pin the SDK explicitly; the successful native
  comparison image already installs `arcbench-runtime==0.1.0`.
- Empty template is rejected, but that alone is not a functioning-browser gate.
- Overall `gate=false`. No model calls, no official run/upload, no hidden test
  access. All probe containers ended; the only factory26 service left is the
  budget gateway. The 7 unrelated pre-existing business containers remain Up.

Do not rerun this same QEMU/Chromium configuration or count the 3 errors as
skipped/pass. Native ARM's 13/13 result and the completed A/B outcomes remain
valid local evidence, not x86 parity. Native x86 compatibility remains a separate
release gate. Continue the authorized source/behavior work locally; do not change
Docker's global emulator settings, use Xunji production, or provision paid cloud
infrastructure without the corresponding authorization.
