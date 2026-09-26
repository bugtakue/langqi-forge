# Stop broad re-exploration; one focused-repair candidate

The closed `sheet-foundation-fresh-v1-1-resume-1` remains 0/2 and paused after
its second no-gain receipt. It spent ¥0.625962 (first generation plus resume
¥4.178046). The application hash stayed
`221ee2bfc4cfa62845043b147b4490e8860d864117113cdce834db3b58d1fae6`.
All nine requests settled; eight worker responses used only list_dir/read_file,
then a local maximum-request reservation denial stopped coding. There was no
implemented repair to judge. This is not an organizer-balance failure.

Request-body audit exposed a concrete orchestration issue: the worker's direct
user task was only `Code task: ... --seed /source / Working source copied; not
verified`. Actual error evidence was buried at the end of the large system
contract. Its system instruction also told every pass to begin by exploring
manifests/entry files. Worker message histories restarted during the failed
episode. The pinned public source contains an additional M8.9 recovery path;
`max_retries=0` alone must not be described as proof of no internal recovery.
Outer deadline and gateway limits did still bound the run. No binary was edited.

## New decision, not another unchanged retry

`sheet-focused-repair-v1`, ≤¥3/900s/one coding pass, same DeepSeek model, exact
retained source, frozen tests/grader, kernel binary and public catalog. The
explicit coder revision changes only generic seed-task placement and prompt:

- Fixed seed stdout supplies real verifier feedback and file inventory as the
  worker's direct task. No application patch/answer is supplied.
- A repair first reads the failing file and necessary helpers, rather than
  re-discovering all directories or implementing unrelated features.
- Server logs are bounded untrusted data; assertions and acceptance remain
  controller-owned. Old source, counters, receipts and frozen bundles stay.

This is the one reviewed reconsideration of this paused lineage; source/model
tests are unchanged, and --refresh-coder records exact before/after hashes.
The earlier deep-link repair was a different lineage and is not overwritten.
No repeated reconsideration of this lineage is allowed. If this cannot pass,
stop and do not spend on the second fresh generation or another manual rescue.
Current campaign upper cost before this candidate: ¥12.501402; all calls
terminal, no other trial/grader, no official upload. The ¥20 mechanism and ¥120
campaign limits remain unchanged. This is an internal experiment, not ranking.
