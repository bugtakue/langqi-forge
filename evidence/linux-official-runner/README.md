# Official runner compatibility proof

The exact submission ZIP was unpacked and executed by the ARC-Bench runner from repository revision `4c61da1f7b153ea0522164132f262cab98985910` in its Linux/arm64 image (`sha256:5b89e3028e52578913e44a784b4b507fb03857bfb91f8ef1eb0a12bc2290c062`).

Result: 101/101 GitHub GUI tests actually executed with four workers, 0 skipped, 0 flaky, 0 unexpected, and a runner score of 100.0. Chromium preflight passed under Node `v20.19.3`. The sealed application source SHA-256 remained `6dc5f1b9c36ae6856c61619426080b1c7a958e8dd1cc540e3dc6e211c1b654b7` after the runner's dependency-install and test phases, and the run envelope still verified afterward.

This lane intentionally used a local OpenAI-compatible planner protocol fixture. It proves archive layout, entrypoint, environment contract, model tool-call protocol, Linux runtime, build, startup, and official runner test compatibility; it is not production-model evidence. The real Bailian/Qwen evidence is in [`../v2/`](../v2/). See [`proof.json`](proof.json) for hashes and the precise claim boundary.
