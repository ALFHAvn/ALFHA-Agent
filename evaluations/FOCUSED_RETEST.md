# Step 44 — focused structured-editing retest, approval pending

Preparation only. No live generation, candidate execution or generated-test
execution has run or is authorized by this file. `step44_plan.json` is the exact
six-request review artifact; reproduce it offline with
`python -m evaluations.prepare_focused_retest` from the project root.
No live client, execution backend invocation or authorization switch is provided.

## Exact generation scope and order

Only installed `qwen3:4b`, at most six new generation requests, one response each:

| New attempt ID | Historical pair | Seed | Authorized existing files |
| --- | --- | --- | --- |
| step44-r1-bounds | r1-bounds | 42 | clamp.py, test_clamp.py |
| step44-r1-stable_unique | r1-stable_unique | 42 | unique_order.py, test_unique_order.py |
| step44-r2-bounds | r2-bounds | 43 | clamp.py, test_clamp.py |
| step44-r2-stable_unique | r2-stable_unique | 43 | unique_order.py, test_unique_order.py |
| step44-r3-bounds | r3-bounds | 44 | clamp.py, test_clamp.py |
| step44-r3-stable_unique | r3-stable_unique | 44 | unique_order.py, test_unique_order.py |

Every file has exactly read/modify permission; no creation, deletion, traversal,
links or other paths. Both files must change. Use a fresh disposable source and
isolated staging workspace per attempt. No application to any source repository.
The original task descriptions, fixture bytes, expected test ASTs, signatures and
acceptance criteria are copied unchanged from the tracked Step 42 plan.

Temperature 0, context 8192, stream false, original seeds and no thinking override.
Strict version/changes JSON schema is identical as JSON data to each
paired original schema. No native tools, prose recovery, newline transformations,
corrective prompts or task retries. At most six charged operations per attempt,
one exact replacement per file; invalid batches validate wholly before writes.
The 180-second HTTP client timeout is unchanged (not a hard process-wide deadline).
Six requests permit at most 18 minutes of client waiting plus local/Ollama/Git
and readiness overhead. Peak CPU/RAM/VRAM will not be inferred from model size;
record returned Ollama durations/tokens and optional read-only residency if
available, clearly separate from measured wall time. No downloads/model changes.

## Single intended prompt intervention

Prompt version: `step43-structured-instructions-v1`.
Request version: `step44-focused-v1`.

Use the **system message** returned by Step 43's `proposal_messages`. Preserve
the paired Step 42 **user message byte-for-byte**. The helper's additional
required-files user checklist is intentionally not included: it would introduce
another prompt difference. Model, options, schema and all other payload fields
are exactly the paired originals. No new functional grading data enters prompts.

The new system text gives contrasting JSON newline examples, explains copying
decoded source/encoding once, and requires exact identity assertion operators.
Its full text and every final user message appear in each plan payload, together
with system/user/schema/request hashes, historical payload hashes, instruction
builder hash, and unchanged validation-controller source hashes. Prompt/version
metadata alone grants no execution or generation permission.

Step 43 diagnostics are recorded but not returned in a corrective model call.
This keeps one response/no retry and avoids introducing a feedback-loop effect
alongside the prompt intervention. Default model and interactive controller stay
unchanged. The historical Step 42 request plan and outcomes are not rewritten.

## Independent outcomes and exact duplication

`assess_attempt` accepts a supplied response as offline data only. It reuses the
existing byte-checked disposable Git workflow and strict controller, retaining
raw content, applied changes, failed operations, final file hashes, combined diff,
full diagnostic feedback, source integrity and cleanup evidence. Its origin is
explicitly `supplied_offline_data`, never falsely labeled a live request.
A later approved live caller must independently save actual request events,
complete response envelopes, response times and generation metadata before parsing.

Record decoded old/new actual newline counts and literal backslash-n presence
per file. Presence alone does not reject legitimate exact text; original unique
match rules decide acceptance. No double-decoding, repair or salvage is permitted.

Measure separately:

- Complete original static task acceptance: both actual required changes, all
  original module/test criteria, source integrity and confirmed staging cleanup.
- Implementation static checks versus exact generated-test contract compliance.
- Proposal validity, charged operations, successful writes, actual changed files,
  multiline representation, elapsed model/staging time and rejection patterns.
- Functional correctness: **not tested**. No generated module or test executes.

`summarize_attempts` reports complete-static outcomes by task and round, attempts,
unattempted/unknown outcomes, and JSON/edit metrics separately. A valid proposal
or correct-looking implementation cannot hide a missing test or wrong operator.

`duplication_report` compares exact raw content without trimming or
semantic normalization. Report duplicate groups among new responses separately
from exact matches to historical responses. Never count old responses as new
attempts or reuse old acceptance outcomes. Missing responses remain unknown,
not duplicate empty placeholders. Recurring diagnostic codes count each attempt
once, even when multiple fields raise the same code. Duplicate attempt IDs,
historical IDs in new slots, mismatched tasks/rounds and invalid outcomes fail
report validation. Small samples and repeated outputs limit interpretation.

Historical paired baseline: zero of six complete static tasks. Three clamp
batches had literal-newline mismatches; three dedup test contracts used `!=` in
place of required `is not`. Reference evidence remains in local ignored
`runs/step42_live_results.json`, snapshots and Step 43 provenance analysis.
Historical functional successes are not reused as new retest results.

## Required lifecycle after separate approval

Before consuming any attempt, verify approved commit/plan/prompt/controller
hashes, exact original fixtures and source snapshots, Ollama API/model identity,
Linux Docker engine and pinned image metadata, bounded read-only readiness and
a separate definitive mandatory all-container inventory. Unknown/failed inventory
blocks generation. Never interpret a timeout as an empty list. No auto-install,
service start, security change or container execution is needed for this trial.

Checkpoint pending/running/completed/interrupted states with atomic writes;
record a generation invocation before sending it and save the full response or
transport error before assessment. Failure to transport a request consumes that
slot and aborts on infrastructure failure; never silently repeat it. Recheck
source identity before staging. Ordinary rejected proposals are task failures,
not authorization to retry. Stop immediately on required infrastructure, integrity
or cleanup failure and preserve partial/unknown outcomes without restarting.

Expire generation authorization on completion or abort; saved checkpoints cannot
extend it. Verify unchanged source fixtures, retained candidate hashes and source
snapshots, discarded owned staging, final definitive container inventory and
regressions. No destructive Git operation or source application exists.
Future functional checks require retained candidate/hash review and separate
explicit Docker execution approval; none are requested in this generation scope.

## Recommendation after the retest

Do not decide readiness from preparation tests or JSON validity. After the live
trial, report all six complete-static outcomes, recurring failures, exact output
duplication, authorization/source integrity and diagnostic quality. Compare paired
cases with the 0/6 focused historical baseline without claiming causality from
three correlated attempts per task.

Any authorization/isolation/integrity failure blocks integration. Recurrent edit
or test-contract failures require further work before everyday integration.
Even full static success can support at most considering an opt-in, human-reviewed
pilot with inspectable diffs and explicit file permissions; it does not establish
functional correctness. Candidate execution and any actual interactive integration
require their own reviewed scope and approval. No integration is implemented here.


## Actual preparation validation

**19/19 new targeted tests passed** in 19.970 seconds. The complete trusted suite
passed **452/452 tests** in 544.700 seconds, including Step 43's deterministic
newline and assertion-operator diagnostics. Final offline closure confirmed the
plan matches its builder, unchanged historical responses/original fixture bytes,
unchanged validator source hashes and source snapshots, and no temporary editing
staging. **Zero live generation requests and zero candidate jobs executed.**

Local ignored evidence: `runs/step44_targeted_tests.log`,
`runs/step44_regression_evidence.json`, `runs/step44_regression.log`, and
`runs/step44_preparation_closure.json`. These are preparation results, not a
coding benchmark outcome or permission to consume attempts. Separate explicit
approval of the fixed six requests is still required.
