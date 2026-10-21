# Step 38B: six approved structured-editing attempts

The six original Step 38 requests ran once each from `a9983d7`, after fresh
dependency/model-identity checks and the bounded Docker readiness gate. The
original plan hash was
`ee3b12b2244f78d662f73f8b5a419a1e55adbef94d1d929b87cdcc63518376e0`.
Fixtures, JSON schemas, task requirements and acceptance criteria were unchanged.
No corrective generation, task retry, code/test execution or source application
occurred. The default model and interactive controller were unchanged.

## Actual results

| Model | Syntax task | Two-file task | Static completion | Response seconds A / B |
| --- | --- | --- | --- | --- |
| qwen3:4b | Complete | Complete | 2/2 | 67.985 / 116.110 |
| qwen2.5-coder:3b-instruct-q4_K_M | Complete | Incomplete | 1/2 | 11.109 / 4.016 |
| qwen2.5-coder:7b-instruct-q4_K_M | Complete | Incomplete | 1/2 | 13.672 / 13.938 |

All **6/6 proposals** passed strict JSON and contextual edit validation. All
**9 authorized edits** were staged, changing all **9 required file slots**.
Every syntax task exactly matched the original expected source. All **9/9 file
slots passed AST parsing**. Static task completion was **4/6**. This is not a
functional test score: candidate programs and generated tests were never run;
compilation and functional correctness were not verified.

Each syntax attempt used **1/6 operations**; each two-file attempt used **2/6**.
Total operation use was **9/36**, averaging **1.5 per attempt**. There were zero
native calls, recovered calls, malformed/invalid proposals, rejected operations,
or unauthorized actions. Native calls are absent by design in this protocol.
Both two-file failures resulted from submitted code/test content, not edit
dispatch or budget exhaustion. Static review readiness alone did not grant task
completion: all staged results were inspectable, including the two failures.

## Independent static assessment

The retained final files were inspected directly, without importing them.
AST parsing and AST comparison corroborated structure, signatures and retained
tests; manual inspection determined requirement coverage. The JSON assessment
records each original acceptance group and finer criteria. It is a snapshot
assessment of these saved outputs, not a general automated correctness grader.

- **Qwen3 B:** builds a fresh ordered result list, normalizes with `strip().lower()`,
  discards empty values and appends only unseen normalized strings. It preserves
  the input and original signature. The existing test is retained, and all four
  named tests contain the requested examples/assertions, including a real tab and
  an independent input copy. All original static criteria are met.
- **Coder 3B B:** collects strings into a set and returns `list(normalized)`.
  This provides no first-occurrence order guarantee. It removes
  `test_returns_new_list`. Its input-preservation test also asserts that the
  result is `["blue", "blue"]`, contradicting the required deduplication.
  Both the implementation and test-preservation acceptance groups fail.
- **Coder 7B B:** returns a normalizing/filtering list comprehension with no
  deduplication. Repeated normalized tags remain. It preserves the original test
  and includes the four requested test structures/examples, but the normalization
  acceptance group fails because duplicate removal is absent.

The submitted tests expose intended behavior, not executed evidence that the
implementation satisfies it. No functional failures/pass counts are inferred.

## Timing, resources and security evidence

Response time totals **226.830 seconds**. These are sequential end-to-end chat
times, including loading where applicable; they are not steady-state throughput
measurements. Complete Ollama duration/token metadata is retained.

Post-response `/api/ps` samples reported context 8192 for each model:

| Model | Resident bytes | VRAM bytes |
| --- | ---: | ---: |
| Qwen3 4B | 3,877,571,133 | 3,877,571,133 |
| Coder 3B | 2,411,577,999 | 2,411,577,999 |
| Coder 7B | 5,409,058,322 | 4,270,619,360 |

These are residency snapshots, not peak RAM/VRAM use or utilization. No extra
generation or unload requests were made for telemetry.

The initial fresh Docker readiness and final inventory passed. Every attempt's
source snapshot matched before/after staging, its owned staging was discarded,
and its separate mandatory post-attempt inventory passed with zero containers.
No infrastructure, source-integrity, inventory or isolation-verification failure
was recorded. No containers or candidate execution were needed for this static
evaluation; runtime isolation probes were not rerun and are not claimed as new
security evidence. Authorization expired when the sixth attempt completed;
persistent live execution remains disabled.

## Comparison and evidence

Step 36's native-tool comparison completed **0/2 tasks for each model**, with no
successful edits. This trial completed 2/2, 1/2 and 1/2 statically, and every
model performed the authorized edits. It demonstrates successful proposal-to-edit
dispatch in these six attempts. It does not establish repeatable reliability or
prove that the protocol alone caused the difference: the interface, supplied
source context, constrained JSON format and response policy differ from Step 36.
In particular, the host supplied readable source contents here, so inspection
did not consume operation slots as native reads did in Step 36.
One attempt per model/task is too small to support a general model ranking or
software-development competence claim. The default model remains Qwen3 4B.

Complete evidence is retained under ignored `evaluations/runs/`:

- `step38b_live_started.json`: exclusive no-restart invocation marker.
- `step38b_live_comparison.json`: original checkpointed run, exact payloads,
  full responses (including available thinking), telemetry, source snapshots,
  staging reports, diffs, errors and per-attempt inventories.
- `step38b_01_A_response.json` through `step38b_06_B_response.json`, and matching
  staging reports: independent per-attempt copies.
- `step38b_evaluation.json`: complete embedded live evidence plus per-criterion
  independent static assessments, aggregate metrics and comparison limitations.

The historical blocked Step 38 report and earlier evidence were preserved. No
generated report or temporary fixture is committed.

## Final closure

The complete trusted regression suite passed **342/342 tests** in **377.155
seconds**, with no captured failures/errors. Its service/model execution is
mocked; benchmark-like unit-test log messages are not extra live attempts.
Afterward, the original Step 33 source snapshot and all six disposable source
snapshots still matched. All owned editing staging workspaces were absent.
The six unchanged read-only source-fixture copies remain retained as evidence;
they were never editing targets in the original repository.

A final bounded readiness cycle and its separate mandatory inventory passed,
definitively confirming zero containers. Complete closure and regression evidence
is included in `step38b_evaluation.json`, with `step38b_completion.json` and
`step38b_full_regression_evidence.json` as separate records. The original live
checkpoint report is preserved unchanged and hash-linked from the assessment.
Authorization remains expired, default functional live execution remains disabled,
and no future generation is authorized by the report or exclusive run marker.

The older runtime isolation anomaly and intermittent historical staging failures
are not explained or resolved by this passing suite. Further performance or
functional execution measurements require separate review and authorization.
