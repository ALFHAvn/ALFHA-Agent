# Step 43 — structured edit feedback and test-contract diagnostics

No live model request, preserved-proposal staging replay, candidate execution or
Docker job is authorized or performed in this milestone. Mocked response tests
use disposable Git repositories. Existing interactive tools, qwen3:4b default,
six-operation budget, file permissions, task fixtures, expected results, Docker
policy and source-application restrictions remain unchanged.

## Evidence: confirmed versus inferred

`python -m evaluations.analyze_step42_contracts` reads saved Step 42 responses,
recorded request contexts, candidate snapshots and their hashes. It never stages
or executes historical proposals. Local output is retained under ignored
`runs/step43_failure_analysis.json`; original Step 42 evidence is not rewritten.

All three bounds responses already contain double-escaped newlines in the earliest
retained `message.content`. Parsing the saved response archive reproduces the
same content as the consolidated report; serialization round-trip preserves it.
Independent `json.loads` and the strict controller parser agree that each old_text
contains literal backslash+n and zero actual newlines. Neither old_text matches
its corresponding real multiline fixture. The controller correctly rejects the
whole batch before writes. This is not a controller JSON-decoding defect or an
archive-induced change. The original instruction already required newline escapes
to decode to real newlines, but gave no concrete contrasting examples.

Generation escape confusion is supported by the output and retained auxiliary
text explicitly discussing doubled escaping. Exact internal causation remains
unproven: auxiliary model text is self-report, and no raw HTTP bytes are retained
to independently audit the model-server/SDK boundary. Copying the JSON-escaped
source display rather than decoded text is a plausible contributing factor,
not a demonstrated causal effect of prompt formatting.

For all three stable_unique attempts, the exact recorded request explicitly
requires `assert result is not values`. The final staged test instead has
`assert result != values`; AST operator is NotEq rather than IsNot. The contract
validator correctly rejected it. The implementation and test files are separate
artifacts: passing implementation vectors did not make the test assertion valid.
The observable failure is operator substitution; its internal reasoning cause
is unknown. This was not omission of the identity requirement from the prompt.

The approved benchmark allowed one response and no corrective call. Rejections
and post-edit static validation happened after that response; no validation
feedback was delivered to Qwen3. Feedback could not correct the same attempt.
This milestone makes diagnostics available as data; it adds no correction loop,
retry, model call or additional operation allowance.

## Versioned future proposal instructions

`proposal_protocol.proposal_messages(request, contents)` produces messages as data
only. It validates the existing explicit request/schema, accepts exactly the
readable authorized files and includes a required-files checklist. It explains:

- Decode supplied source strings before copying; serialize the response once.
- JSON `"first\nsecond"` represents one real newline; JSON `"first\\nsecond"`
  represents literal backslash+n. No controller repair is assumed.
- Preserve indentation, trailing newlines, exact filenames and unique old_text.
- Preserve required assertion operators, variables and order: `is not` checks
  identity, while `!=` checks unequal values.
- One raw version/changes object, six operations, one replacement per file,
  atomic batch prevalidation, no creation/deletion/execution or automatic retry.

The legacy SYSTEM constant and frozen Step 38/42 request plans are unchanged.
A future reviewed plan must explicitly use this new message builder; it is not
silently substituted into historical payloads or the interactive agent. Behavioral
improvement remains unmeasured until a separately approved live retest.

## Actionable exact-edit diagnostics

Exact equality and match counts still determine edit acceptance. Diagnostic
`ProposalValidationError` remains a SafetyError subclass, so existing callers
still catch rejection. It adds structured data to rejected staging events:
`code`, `filename`, `field`, `match_count`, `literal_backslash_n`,
`actual_newline_count` and `message`. Existing `error` text remains present.

For the observed failure, feedback names the file and old_text, reports zero
matches and literal backslash+n, and explains encoding once. No old_text or
new_text is transformed, decoded again, repaired, applied partially or retried.
Literal escapes that actually occur in source and match exactly once remain
valid. Multiple matches produce `ambiguous_replacement` and require a larger
unique context; the controller never picks a location.

## Separate static, contract and functional outcomes

Existing `checks`, `completed`, `static_task_completed` and functional fields
remain compatible. Static reports now also include:

- `implementation_static`: module parse/change/signature/exact-repair checks.
  This explicitly leaves functional correctness `not_tested`.
- `generated_test_contract`: passed/failed/not_required plus diagnostics.
- `diagnostics`: missing/unchanged required files, parse failures and contract
  defects, including precise expected/observed assertions and function names.
- Assessment `feedback`: rejected-proposal and static diagnostics combined,
  with `feedback_delivered_to_model=False`.

Example: `test_unique_order.py / test_input: Require assert result is not values;
found assert result != values. Use is not for object identity; != compares values
and does not prove a fresh object.` Missing assertions and functions and wrong
assertion order receive distinct codes. Extra code, changed assignments/imports,
decorators, duplicate functions or equivalent-but-unrequested test forms still
fail the original full test-AST equality rule. Diagnostics do not become a new,
weaker acceptance path. Functional worker/grader and all hidden vectors are
unchanged, and generated tests are never executed on Windows.

## Verification

Twenty-five new deterministic tests cover multiline and literal escapes,
legitimate matching escape text, ambiguous matches, assertion operators/order,
missing/duplicate/async tests, extra code, partial two-file edits, full compliance,
whole-batch rejection, authorization, source preservation, cleanup, frozen plan
compatibility and inconsistent provenance. Live clients and candidate execution
are blocked in new tests. The data-only historical analysis verifies all six
failure records without replaying their proposals. Full-suite evidence is stored
locally under `runs/step43_*`.

Actual verification: **25/25 new targeted tests passed** in 24.147 seconds;
**433/433 full regressions passed** in 509.290 seconds. Final offline closure
verified all twelve historical snapshots and unchanged static decisions, original
source repositories, frozen Step 38/42 plans, execution profile and provenance
report hashes, with no remaining temporary editing staging. No live requests,
Docker probes/jobs, generated code or generated tests ran. Evidence is preserved
in `runs/step43_targeted_tests.log`, `step43_regression_evidence.json`, its log,
`step43_failure_analysis.json` and `step43_closure.json`.

Future live generation or functional execution requires a new reviewed scope and
separate explicit user approval. No live-performance improvement is claimed.
