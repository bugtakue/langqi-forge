# Kernel foundation V2: real dispatch, incomplete app, new billing stop

## Current decision

**No next model call, no new formal upload.** A NEW unknown-cost call is locked:
`9a1ce726512ffb81c86be567376b9472`, reserved/charged conservatively ¥0.226807.
The previous user exception for `db7578d75f9900b512f400ae642ec87b` does NOT cover
this request. Keep the new row reserved with null usage until terminal billing
is verified or the user expressly authorizes this exact worst-case exception.
Do not release the reservation, infer a free error, recharge or change keys.

All experiments are closed; the gateway and all seven prior business containers
remain Up. No Docker re-restart, Xunji deployment, hidden-test access or GOSIM
final submission occurred. Goal remains active and NOT achieved.

## Source / process / independent results

Controller revision `3984f5b`, selected pinned Octos arc.17 and GLM 5.3 Flash.
Trial `.cache/ab-campaign/mechanism/github-foundation-kernel-v2`.
It has one actual dispatched pipeline and one coding pass, not the V1 no-op.
Pass ended after 299.183 seconds. The outer graph says success because its
failure-tolerant coding node reached Done; `implement` itself reported failure.
Neither graph success nor the model's prose is treated as acceptance.

Five source files retained: backend package/server, frontend package/index/style.
`frontend/src/index.html` references `app.js`, but that file does not exist.
The rendered root has no Sign in link. Independent results:

| Evidence | Pass / total | Skip / flaky | Meaning |
|---|---:|---:|---|
| Frozen runtime-generated suite | 0/11 | 0/0 | All fail at missing entry; no acceptance |
| Separate pre-frozen foundation holdout | 0/3 | 0/0 | Same missing entry; no foundation gate |

Both suites ran in disposable no-network/no-model-key containers, source/tests
remained unchanged and processes were cleaned. The original holdout was not
mounted into the compiler or coder. Zero actual restart was reached because
entry failed; do not describe these results as backend/session correctness tests.
The holdout was run offline after billing had stopped the coding loop; it was
not fed back to a model or used to edit/relax the runtime suite.

Working checkpoint (not accepted):
`666a1104c34e9c78c99b6977e9cf7341f98c3a04f5435500d831ca5c07c48278`.
Stagnant rounds = 1, accepted=false, no final delivery exported. The exact bytes
also exist under `resumed-working-1`, with `feedback-2.txt` containing actual
runtime failures. If later authorized, continue this source/checkpoint and
remaining budget; do not regenerate from the empty template or re-run V1.

Frozen generated test hashes:
- `contract.spec.ts`: ccfa2c9da17ef8a3ac9ab5e0358ee733e3fc643285ebc5e5e6c9068e41510a87
- `restart.ts`: 79cc6b2d9dc5597419710118250404cd0592a416805c93de4b96264014dd42bd

Trial manifest SHA256:
`13a65b0c867179cff059e1ef167d77195c8ebecafd4bbfc5c123276947d88411`.

## New upstream error and conservative cost

Eight successful responses plus one unresolved request. Error occurred at
2026-09-26 11:14:15 Beijing: HTTP 502, provider body is a generic OpenResty
Bad Gateway HTML page, no usage or provider request ID. Redacted request/error
bodies were saved before the failure was recorded. Error-body SHA256:
`515cfa2dbec5307889708b51a1dafc56571b5a72154329cbc7fb2a3633809fd0`.
This is evidence of an upstream/proxy error, not proof of zero charge or the
underlying provider's root cause.

- Trial upper cost: ¥0.343315, INCLUDING new unresolved ¥0.226807.
- Complete new campaign conservative upper cost: ¥2.512969.
- Organizer meter at **11:19:35 Beijing**, `https://meter.arc-bench.com/user`:
  balance **¥99.094982**, posted account-level usage **¥0.905018** from initial ¥100.
- Latest visible request: **11:13:34**, request ID
  `2026092611132014857896651231`; no later terminal usage row was visible.

Posted account-level charges cannot be assigned to this missing request or used
to clear its reservation. The upper cost is NOT the organizer's actual bill.
No score/rank improvement is claimed. Last formal verification remains the old
17/200, 6.55, #10/26 snapshot; this local run generated no formal result.

## Next safe step

Wait for terminal billing evidence or explicit user direction on this exact
¥0.226807 reservation. No repeated notification while this state is unchanged.
After authority is resolved, preserve the frozen tests, retained backend and
failure steps; resume a bounded frontend-completion/behavior-repair pass. Re-run
independent checks and clean export before any broader task or official run.
The native x86 compatibility gate, Sheet foundation, repeatability and formal
two-task result remain open. Completing the compiler/controller does not close
any of those gates.
