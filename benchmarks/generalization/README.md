# Blind generalization lane

The official qualifier intentionally rewards the two announced domains. This
separate lane asks a different question: can the submitted runtime encounter a
third, previously uncached product and make real workspace edits through its
bounded coding-agent route?

`change-control/requirements.yaml` is the only task material supplied to the
agent. The Playwright file remains outside the generated workspace and tests
dynamic input, validation, separation of duties, state transitions, and refresh
persistence. It is not part of the official 304-test score and must never be
reported as such.

The source tree never self-asserts that this proof passed. A dry run cannot
pass because the generic scaffold does not implement this domain; a production
result is published only in the same-revision `evidence-v2` branch after the
real model route and locked evaluator both pass.

Run it only from a clean commit with an OpenAI-compatible model configured:

```bash
export OPENAI_API_KEY='...'
export OPENAI_BASE_URL='https://your-gateway.example/v1'
export MODEL='your-model'

.venv/bin/python -m benchmarks.run_generalization \
  --agent-root /tmp/unpacked-exact-submission-bundle \
  --output-dir /tmp/langqi-unseen-change-control
```

The runner locks both inputs by SHA-256, requires the generic bounded coding
route with at least one real edit loop, starts the generated application with a
secret-free environment, executes five hidden browser checks using the pinned
Playwright runtime, verifies source immutability, and appends the result to the
run's sealed trace. `--agent-root` lets the proof execute the exact unpacked zip
rather than trusting the surrounding development checkout. A failure is
retained and never represented as a pass.
