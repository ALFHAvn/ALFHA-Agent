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

## Approved Step 44 live retest — 2026-10-23

Exactly six fresh generation requests completed in the approved order at commit
5672f8f, without retries, corrective requests, proposal repairs or unattempted
cases. Every payload matched the fixed plan. Relative to its paired Step 42
payload, only the system message changed; original user strings/options/seeds,
JSON schemas, fixtures, per-file permissions and acceptance criteria were retained.
Model identity matched the retained baseline. Bounded read-only Docker readiness,
pinned Linux image metadata and each definitive mandatory inventory passed.
No behavioral probes, candidate containers, generated Python or tests ran.

| Task | Round 1 | Round 2 | Round 3 | New complete static | Paired Step 42 |
| --- | --- | --- | --- | --- | --- |
| bounds | Rejected; 149.985 s | Rejected; 173.875 s | Rejected; 173.657 s | 0/3 | 0/3 |
| stable_unique | Pass; 161.859 s | Pass; 164.328 s | Pass; 163.875 s | 3/3 | 0/3 |

**Complete static task success: 3/6 (50%), versus paired baseline 0/6.**
All three deduplication proposals were valid, staged both required files and
passed implementation static checks and the full generated-test AST contract,
including `assert result is not values`. All three clamping proposals again
contained literal backslash+n old_text with zero exact matches. Whole-batch
validation staged neither file. Their final implementation/test checks failed
because required changes were absent; missing test diagnostics are a consequence
of edit rejection, not proof that the unapplied proposed tests were defective.

Across six attempts: three contextually valid proposals, three rejected proposals,
six staged edits, six rejected declared operations and twelve charged operations
(two per attempt, within six-operation budget). No unauthorized paths/operations,
malformed JSON, native calls, recovery calls, transport errors, safety/integrity
failures or cleanup failures were observed. Response durations averaged 164.597 s
versus 100.125 s in the six paired historical attempts. This is an observed latency
difference, not a demonstrated prompt-caused effect or peak resource measurement.
Full response envelopes and returned Ollama duration/token metadata are retained.

## Exact repeats and candidate provenance

New raw response content had three distinct strings. The deduplication contents
were identical in all three rounds (SHA-256
`476235a5e75322d4684f792ad1c84b128a0d5bb298d245b1d23ed79bc7b54c08`).
Clamping rounds 2 and 3 matched exactly (SHA-256
`84791703bd525c74a33303050b36e0b5ed9b38354efb6ce1f5d63928dd28c4e8`);
round 1 differed. No new content exactly matched any of the six historical
baseline contents. Comparisons concern response content, not changing transport
timestamps/duration metadata. Recurring failure diagnostics were preserved once
per attempt, separately from exact-content duplication. Different seeds do not
make these repeated outputs independent evidence.

Actual final staging snapshots and full per-file hashes are retained for every
attempt. Deduplication implementation bytes match the corresponding historical
Step 42 implementation (`c7fec2319dc636218ddca64a330630cd9879d71700c252cf95b5813da7a00271`),
but the generated tests changed to comply with the identity contract (new test
hash `1f9c1e19769fcf1264f18cd3392f27383d99909631b1a1458e6fd8f246502c9b`).
No historical functional result is credited as a new execution: all Step 44
functional statuses remain not_run. The three unchanged clamp snapshots are
preserved as rejected/no-edit outcomes, never reconstructed from proposals.

Full evidence: ignored `runs/step44_live_results.json`, per-attempt response and
candidate JSON snapshots, and `runs/step44_paired_comparison.json`. Historical
reports remain separate and unchanged. The parent live record proves actual
invocations; nested assess_attempt reports correctly label their own operation
as supplied-data validation, not another model call.

## Recommendation from actual outcomes

**Defer interactive everyday-workflow integration.** Retain the isolated,
review-only experimental workflow and address recurring multiline representation
failures before reconsidering a pilot. The observed test-contract improvement
is useful, but clamping still completed 0/3 with zero edits and half of this small
trial failed. Accepted implementation hashes repeat historical code; no new
functional correctness or general reliability is established. The payload
intervention was controlled as planned, but this small correlated trial does not
prove causal attribution to Step 43 instructions.

No interactive integration, automatic source application, default-model change
or execution permission was implemented. Future generation or functional jobs
require a new reviewed scope and separate explicit approval.

Paired metric comparison (Step 42 focused baseline -> Step 44): contextually
valid proposals **3/6 -> 3/6**; actual staged edits **6 -> 6**; rejected literal-
newline batches **3 -> 3**; incorrect identity assertions in staged dedup tests
**3 -> 0**; complete static tasks **0/6 -> 3/6**. Thus the measured gain is in
required test-contract fidelity; edit acceptance did not increase in this trial.

## Final verification

The full post-attempt regression suite passed **452/452** tests in 491.488 s.
These trusted regression tests made zero live model calls and performed no
Docker candidate execution. Final closure independently confirmed expired
generation authorization, default live execution disabled, unchanged plan and
validator hashes, unchanged historical evidence, source repositories and
fixtures, and verified all six retained candidate snapshot sets. No ALFHA staging
workspaces remained. Bounded read-only Docker readiness and the separate
mandatory container inventory succeeded; the final inventory contained zero
containers. There were zero candidate execution jobs. Complete closure evidence
is retained in ignored `runs/step44_live_closure.json`, with regression evidence
in `runs/step44_post_live_regression_evidence.json` and its full log.
