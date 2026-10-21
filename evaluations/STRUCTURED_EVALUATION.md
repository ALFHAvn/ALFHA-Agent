# Step 38: structured-editing comparison — approval pending

Preparation only. No live generation is authorized by this document or the plan
file. The interactive controller, default model, Docker policy, and source
application restrictions are unchanged. Generated programs and tests will not run.

## Exact requests and controller

`step38_plan.json` contains all six complete Ollama chat payloads, including the
exact system/user messages and JSON schemas. Reproduce it offline with
`python -m evaluations.prepare_structured`. This command prints data only; it has
no generation adapter, execution capability, or approval switch.

Order, matching Step 36: Qwen3 4B A/B, Qwen2.5-Coder 3B Q4_K_M A/B,
Qwen2.5-Coder 7B Q4_K_M A/B. One fresh response per attempt; six attempts total.
Each uses temperature 0, seed 36, context 8192, stream false, and a 180-second
HTTP client timeout (not a hard process wall-time limit). No native tools,
corrective prompts, automatic retries, text
salvage, or separate recovery calls. Thinking is not explicitly overridden.
The installed models are not changed or downloaded.

The payload's `format` is the strict `proposal_schema` for that scenario. Only
`{"version":1,"changes":[...]}` is accepted. Each change contains exactly
`operation: "replace_text"`, `filename`, `old_text`, and `new_text`. Paths are an
exact enum. One replacement per file; up to six operations, no creation/deletion.
The controller independently validates JSON, duplicate keys, fields, types, paths,
text size, authorization and exactly one old-text match. JSON-schema constrained
generation is an aid, never an authorization boundary. No Markdown stripping,
implicit newline repair or arbitrary prose interpretation is allowed.

The host supplies the full initial contents of the explicitly readable files.
The original requirement paragraphs and examples are preserved verbatim. Only
the obsolete instructions to use native tools and finish with a summary are
replaced. Unlike Step 36, inspection does not consume model operations; report
that difference explicitly. All three models receive identical payloads except
the model identifier. Host acceptance criteria and expected repaired source are
not included in model context.

## Tasks and acceptance

A reuses exactly the missing-colon `syntax_target.py` fixture from
`step36_plan.json`. Only read/modify that file. Completion requires the exact
original expected source, AST success, unchanged source, and retained evidence.

B reuses exactly the Step 33/35 `tag_utils.py` and `test_tag_utils.py` fixtures,
requirements and five acceptance groups recorded in the plan. Only read/modify
these two files. Both must change. Independently inspect normalization, stable
deduplication, empty removal, input preservation, signature preservation, the
existing test, and all four requested tests with their original examples.
AST success and review readiness alone do not establish task completion.
Manual static inspection must mark uncertain criteria unknown rather than pass.
Compilation, test execution and functional correctness remain untested.

## Required run gate and lifecycle (after separate approval)

Before consuming an attempt, verify the approved plan hash, clean project tree,
the preserved source snapshots and exact fixture bytes. Run the existing bounded
read-only dependency preflight for all three installed model tags, including
their identities, and the Docker Linux/pinned-image metadata checks. Also require
a separate successful three-second all-container inventory with no ALFHA-owned
staging/execution containers. Docker metadata alone is insufficient: Resource
Saver previously delayed inventory. Missing/unknown inventory blocks the run;
do not reinterpret it as empty or retry it automatically. No service starts,
downloads, generated-code execution or Docker behavior probes are authorized.

Create disposable sources from the retained exact fixture bytes using existing
trusted Git helpers. Record source snapshots before generation. Send only the
approved payload once. Preserve the raw response and transport errors before
parsing. Recheck the source snapshot after generation and before calling the
offline `run_proposals` staging API; abort on any mismatch. This closes the gap
between the prompt's source text and staging's later snapshot. A failed transport
request is recorded as an attempted invocation, not silently repeated.

Feed at most that one raw response to `run_proposals`. It validates the entire
batch before writing any edit. Invalid envelopes cost one operation; declared
changes consume the remaining operation budget even when rejected. Over-budget
batches are rejected whole, never partially dispatched. Rejected prevalidation
must leave staging unchanged. Runtime write failures can leave partial temporary
edits; preserve them as failures and discard only the owned staging workspace.
No source apply API exists. No external validators, candidate imports or tests.

Retain full JSON evidence after success, rejection, interruption and cleanup:
payload/plan hash, run/attempt identity, timestamps, response, validation errors,
source snapshots, staging trace, final file text, diff and independent assessment.
Do not resume an interrupted generation. Fail closed and stop the trial on an
infrastructure/integrity/cleanup failure; report unattempted tasks separately.
Report normal invalid proposals as task failures and continue only within the
approved six-attempt ceiling. Authorization ends on completion or abort.

## Metrics and comparison

- Valid document: complete JSON passes envelope, six-operation cap and every
  contextual edit check. Schema-shaped but nonmatching/unauthorized is invalid.
- Proposed operations: declared array length when available; report malformed
  envelope separately. Budget consumed follows the existing controller rules.
- Unauthorized operations: exact-path/operation permission violations; retain
  errors and distinguish from malformed fields and nonmatching replacements.
- Applied edits: successful staging writes, separately from valid proposals.
  Count actual changed files and required files from final diff, not model claims.
- Static outcomes: per-file AST, individual original acceptance decisions,
  review readiness, complete/incomplete/unknown. Functional correctness untested.
- Transport/resource outcomes: wall time, Ollama duration/token fields if
  returned, read-only post-request `/api/ps` residency if available (not peak
  resource use); optional telemetry failure is reported as unavailable.
- Integrity: source snapshots equal, owned staging discarded, final container
  inventory known/clean. Preserve unknowns and errors, never infer a clean state.

Compare each model's A/B static completion, actual edits, changed files, rejected
proposals and elapsed time with Step 36's 0/2 tasks and zero edits for each model.
Native tool calls are zero by design here; structured operations are a different
metric. The format, supplied context and response policy differ from Step 36.
One attempt per cell cannot establish repeatable reliability or identify whether
model size, interface or task complexity caused a difference.

## Preparation evidence

The generated plan is tracked for review. Local fixture/source verification and
full regression results are retained under ignored `runs/step38_*` files.
No historical evaluation is replayed or modified. The two historical intermittent
staging test failures and the older runtime-verification anomaly remain
unresolved unless independently reproduced and explained.

Preparation result: **327/327 regression tests passed** in 401.831 seconds,
including seven new data-only preparation tests. No failures or errors were
captured. The retained Step 33 source snapshot and both file hashes matched
exactly. The tracked plan matches the offline builder. No live generation or
candidate execution occurred. These passing tests do not resolve the historical
intermittent failures or measure model performance.
