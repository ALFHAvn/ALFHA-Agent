# Step 37: simplified coding interface prototype

This is an **offline, review-only prototype**. No live model benchmark, model
switch, generated-code execution or source application is enabled. The interactive
agent and existing native-tool workflow retain their defaults and six-call budget.
A future live trial requires separate review and explicit authorization.

## Intermittent regression diagnosis

Step 36's original full-suite result remains **290/292 passed**, with one failure
and one error. Its preserved log is runs/step36_post_comparison_regression.log.

- test_validation_invalidated_after_write_or_external_edit indexed a missing
  validation field in a staging report.
- test_explicit_delete_only_affects_temporary_copy observed false review readiness.

The original underlying reports were removed by existing test teardown, so the
exact integrity decision/operation was not recorded. The earlier 2/2 targeted
passing rerun did not establish resolution. This stage ran **ten controlled
cycles, 20 test executions**, preserving any integrity rejection/workflow error
before teardown. All 20 passed; no rejection recurred. Evidence is in
runs/step37_regression_reproduction.json and its log.

These tests use real disposable Git/filesystem operations, mocked model responses
and mocked dependency readiness; neither calls Docker. There is no evidence
linking their failures to Docker startup, and no reproduced mechanism proving
filesystem timing, permissions, Git transport or concurrent modification as the
cause. The cause therefore remains **unresolved**. Neither passing repetitions
nor a passing full suite would retroactively fix that evidentiary gap.

The assertions now include the complete report when validation evidence is
missing or readiness unexpectedly fails. Checks still fail strictly; there is no
fallback validation field or forced readiness. The full-suite diagnostic runner
also captures relevant integrity decisions/workflow errors before cleanup. No
filesystem/security check was relaxed to make these tests pass.

## Offline historical proposal analysis

`python -m evaluations.analyze_proposals` reads saved Step 33, 35 and 36 reports,
records their SHA-256 hashes and writes runs/step37_proposal_analysis.json. It
never stages or dispatches a proposal. It parses complete raw JSON documents;
fences, prose and concatenated documents are not stripped or repaired. Decoded
calls are checked against saved exact authorization and initial file text.
Reads never change the simulated text. No generated Python is executed.

**14 model responses** were inspected. Counts below are decoded proposal/call
units, including native calls and objects in complete JSON arrays:

| Category | Units |
| --- | ---: |
| Valid single edit | 1 |
| Valid multiple-edit documents | 0 |
| Missing/nonmatching replacement text | 2 |
| Unauthorized filename/operation | 5 |
| Malformed proposal objects | 6 |
| Authorized inspection, not an edit | 18 |
| Authorized validation request, not an edit | 1 |

Separately, five whole responses contained malformed/ambiguous JSON or fenced/
concatenated proposals that could not be safely decoded as a complete document;
one was a non-actionable completion explanation. Do not add these response counts
to object counts as if they were the same unit. Four text responses mentioned
unsupported modify_file operations; their interior objects were not salvaged.

The one verifiable edit is coder 7B's Step 36 syntax-repair proposal: authorized
filename, exact matching old_text, and the requested corrected text. Its existence
shows an edit can be validated as data. It was not a native call and appeared
after its historical single recovery had already been used for a read. Thus it
was **not eligible for execution under the historical recovery state**. The
analysis executes zero proposals and grants no new recovery permission.

Step 33's array has two old_content placeholders that do not match either saved
file and one unauthorized non_existent.py edit. Step 35's first array has six
file-only objects without operation/argument schemas; its native response includes
four unauthorized reads. Step 36 adds repeated native reads, unsupported/fenced
proposals and the single exact edit above. No whole multiple-edit document is
safe as submitted. None has the prototype's new version/changes envelope, so
**zero historical documents are automatically accepted by the new protocol**.

## Explicit replacement protocol

`proposal_protocol.run_proposals(request, responses)` accepts an explicit task
request and one to six supplied response strings. A callable, live adapter,
model name, network operation or execution flag cannot turn it into a live run.
`proposal_schema(request)` returns a JSON schema with an exact filename enum,
version, operation and field constraints; generating a schema grants no authority.

Example data document:

```json
{
  "version": 1,
  "changes": [
    {
      "operation": "replace_text",
      "filename": "module.py",
      "old_text": "return old_value",
      "new_text": "return new_value"
    }
  ]
}
```

The request retains the existing explicit description/source_repository/
authorized_files/validation_requirements contract, optionally required_changed_files.
It requires static=true, docker_execution=false. This prototype supports existing
UTF-8 files with read+modify permission, plus read-only context files. Creation,
deletion and native-tool policy flags are rejected even if another workflow
supports them. Existing broader workflows are unchanged. Source contents are
read only under explicit read permission; no untracked user file is included in
context. A future live adapter/context presentation is not implemented here.

Only exactly version and changes are accepted at the root. Version must be the
integer 1. Every change has exactly operation, filename, old_text and new_text,
all strings; the only operation is replace_text. Filename must match explicit
authorization exactly. Unknown fields, aliases such as content/modify_file,
traversal, case variants, duplicate JSON keys, NaN, fences, trailing prose,
non-UTF-8 data and oversized responses are rejected. Response input is bounded
to 64 KiB; the existing per-file size/control-byte checks remain in force.

old_text must be nonempty, differ from new_text and match exactly once. Literal
backslash-n is not silently converted into a newline. Duplicate filenames within
one batch are rejected: sequential/overlapping edits are ambiguous. Distinct
explicitly authorized files can be edited in the same document.

**Every change is prevalidated before any file write.** If any entry is invalid,
the entire batch writes nothing. This is validation atomicity, not an OS filesystem
transaction. An I/O failure or interruption after a valid batch starts can leave
partial changes in the owned temporary workspace. Such outcomes are marked
failed/interrupted, never ready; the partial diff/evidence is retained and only
that owned staging workspace is discarded. Source files are never rolled back,
reset, cleaned or overwritten.

## Budget and reporting

The prototype has a fixed six-operation budget. Each declared batch entry costs
one slot, including entries in a rejected batch. An invalid envelope costs one
slot. A batch larger than the remaining budget stages nothing and exhausts the
remaining slots; it is not split or silently retried. At most six response
strings can be supplied. There is no budget refund, automatic model correction,
benchmark retry or expansion of the old single-proposal recovery mechanism.

The model-facing proposal protocol is deliberately different from native tools;
it is not bolted onto legacy recovery. Grouping does not grant six edits per
call: six individual operations is the task maximum. The original native-tool
six-call accounting is untouched. Later live comparisons would need a reviewed
context/prompt design, not a claim that offline operation counts are identical
to native read/edit turns.

Reports preserve task/authorization, original contents, raw response events,
accepted/rejected operations and charges, starting/checkpoint commits, combined
diff, per-file status/AST validation, actual final contents, failures, required
missing changes and cleanup. They are atomically retained in a separate
alfha-proposal-report-* directory after staging discard. Saved reports cannot
resume a task, recreate ownership or authorize execution/application.

Source freshness, links/junctions/hardlinks, staging ownership and unexpected
changes use the existing Git safety layer. Actual final contents must also match
the replacements accepted by this controller, including read-only context files.
Unexpected staging edits are not adopted. A review-ready flag requires all
required files changed, source freshness and current successful static evidence.
Static AST/JSON/text validation is not compilation or functional correctness.
Same-user hostile races and underlying filesystem/power-loss limitations are not
solved by an in-process prototype; no stronger OS sandbox claim is made.

## Deterministic verification

Tests use supplied strings and disposable real Git repositories, never live
models. They cover valid one/two/three-file replacements, exact schema enums,
unknown fields/types/operations/paths, missing/nonmatching/ambiguous text, literal
newline escapes, duplicate targets, invalid later entries in a batch, exhausted
budgets, static failures, incomplete tasks, untracked user data, hardlinks, stale
source, unexpected staging changes, interruption, partial write failure and
retained reports/diffs after cleanup. Classifier tests prove analysis does not
call the staging writer and does not salvage fenced or ambiguous documents.

This validates controller behavior on mocked data only. It establishes neither
better live model reliability nor functional coding competence. The historical
regression causes remain unresolved pending a captured reproduction. Keep the
default model and live-execution gates unchanged; review this interface before
considering any new live trial.

## Actual final results

**320/320 regression tests passed in 361.230 seconds**, including **28 new tests**
(25 protocol/schema cases and 3 analysis cases). The full run captured zero
integrity rejections or workflow errors in the two historical test cases. This
is evidence for the current run, not proof that their intermittent causes are
resolved. The preserved Step 36 failed full-suite log remains unchanged.

- runs/step37_full_regression.log and step37_full_regression_evidence.json:
  full suite and pre-cleanup diagnostic capture.
- runs/step37_regression_reproduction.json: ten controlled cycles / 20 passes.
- runs/step37_proposal_analysis.json: full classification and historical input hashes.
- runs/step37_prototype_example.json: retained mocked two-file combined diff,
  two charged operations, successful static validation, unchanged source and
  discarded staging. Only the owned source fixture/evidence were created.
- runs/step37_completion.json: consolidated actual results and restrictions.

Historical input hashes were rechecked unchanged. No live model requests,
Docker execution, candidate imports/programs/tests or source application ran.
The existing default model, interactive agent, six-call budget, Docker policy,
execution gates and evaluation fixtures are unchanged. Reports remain ignored;
the prototype, classifier, deterministic tests and this documentation are committed.
