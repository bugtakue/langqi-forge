# Sheet acceptance V1 rejected before application generation

Two complete model responses, both retained. No frozen suite or app produced.
First: one case lacked two UI assertions. Second: only the five requested entry
atoms were covered, omitting eight declared dependency atoms. Cost upper bound
¥0.049584; campaign ¥4.353003; zero open trials and no unknown-cost gate.

The compiler had exposed `requested_ids` beside the expanded required `nodes`,
which the model treated as the real scope. New compiler input omits these
selection-control fields and explicitly lists ALL `mandatory_atomic_ids`;
correction feedback repeats the complete list rather than inviting correction
of only the first reported error. Catalog/source/dependency closure are retained
unchanged in the audit artifact. No requirements or assertions were dropped.

Also identified from the public CSV contracts: the original syntax surface
could not exercise file upload/download safely. Controller-owned `uploadCsv`
and `downloadCsv` helpers now move declared in-memory UTF-8 CSV through visible
UI controls, with a 512 KiB limit and no disk-path API. Generated tests still
cannot use Buffer, filesystem, setInputFiles, download paths or raw network.
The helper is frozen with each new suite; old GitHub tests remain unchanged.

Offline validation before the next paid call: 10 compiler/catalog checks pass;
3 real-browser utility controls pass (UTF-8/quotes/newline upload-download round
trip, upload path/size rejection, oversized-download rejection). These validate
the helper, NOT a Sheet application or official task.

Next serial experiment `sheet-acceptance-v2`: same public requirement hash,
GLM 5.3 Flash, five roots and full 13-atom closure, max ¥1/600s/two responses.
App and frozen Sheet foundation source remain absent from compiler inputs.
Require actual Playwright collection and blank-UI rejection before any coder.
V1 evidence stays under `.cache/ab-campaign/mechanism/sheet-acceptance-v1/`.
