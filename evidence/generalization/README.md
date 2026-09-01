# Same-revision unseen-domain proof

The exact submission ZIP was run twice against the Change Control task. The task has no cached domain kernel, so the planner had to route both requirements to the bounded coding agent. The five evaluator checks were kept outside the agent workspace during generation.

| Run | GUI | Coding turns | Model requests | Manual interventions | Generated source SHA-256 |
|---|---:|---:|---:|---:|---|
| A | 5/5 | 12 | 13 | 0 | `e45d6a16ac669a9f234a1bd8d41e764e8f955eaf217d038e4b6d2eff0e70d43c` |
| B | 5/5 | 8 | 9 | 0 | `af01387c67f3f776c553c813d8cbc791b8e7df3fcd65f46524093c2b865ce6f1` |

Both used Alibaba Cloud Bailian `qwen3-coder-plus`, produced different seven-file applications, and finished with zero skipped, flaky, or unexpected tests. See [`summary.json`](summary.json) for the cross-run binding and each run's `proof.json`, exact generated source, planner contract, compiled plan, harness report, and run envelope.

Local absolute paths in Playwright reports and production traces were replaced with explicit placeholders before publication. Each `transformation.json` records both source and public hashes; sanitized traces were re-sealed after replacement. This lane is independent generalization evidence, not part of the official 304-test score.
