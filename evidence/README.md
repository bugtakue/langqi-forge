# Current evidence map

All current evidence below is bound to source revision
`d0474d789c583b3c0d0dfbd133c4af8df270cfed` and deterministic submission ZIP
SHA-256 `a897cb3ed11833bfd76bf3a9f80ff930a49d9b30714a5f1fc87c14d510444869`.

| Lane | Result | Purpose |
|---|---:|---|
| [`v2/`](v2/) | 304/304, 0 skipped, 0 flaky | Exact dual-domain Bailian/Qwen production evidence plus an independent verifier |
| [`generalization/`](generalization/) | 5/5 twice, distinct generated source | Same-ZIP unknown-domain bounded coding-agent evidence |
| [`linux-official-runner/`](linux-official-runner/) | 101/101, post-install source unchanged | Official ARC-Bench Linux/arm64 packaging and protocol compatibility |
| [`../judge/`](../judge/) | 90-second summary | Human-readable view derived from the sealed v2 artifacts |

Verify the strict dual-domain bundle from the repository root:

```bash
.venv/bin/python -m factory26_harness.verify_evidence evidence/v2
```

These artifacts prove the stated runs against their locked public or withheld-during-generation tests. They do not claim hidden-test success, Top 20 placement, or an award.
