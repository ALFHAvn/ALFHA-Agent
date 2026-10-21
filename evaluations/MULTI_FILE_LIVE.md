# Step 33: first live integrated two-file attempt

Exactly one live coding attempt was explicitly approved and run from `a7578cd`
using the unchanged `coding_workflow.run_task` API and local `qwen3:4b`.
There was no task retry, recovery execution, source application, generated-code
execution, or Docker execution. A separate exclusive attempt-start marker prevents
accidental re-invocation of the live-attempt driver. The approval has been consumed;
another attempt requires new explicit approval.

## Prepared task and acceptance

The disposable source repository contained `tag_utils.py` with
`normalize_tags(tags): return list(tags)` and `test_tag_utils.py` with one
existing unittest method, `test_returns_new_list`. Both fixture files were marked
read-only before taking the source snapshot. Model tools could only read/modify
these two files in a separate isolated Git workspace. They had no source-writing,
creation, deletion, Git, or execution permission. Budget: six tool-call attempts.

The requirement was to trim/lowercase tags, discard normalized empty values,
deduplicate in first-occurrence order, return a new list and leave input unchanged.
The test file had to retain its existing test and add four named tests with the
precise examples preserved in `runs/step33_preparation.json`.

| Static acceptance criterion | Actual outcome |
|---|---|
| Both required files changed | **Not met:** neither changed |
| Both final files parse as Python AST | Met for the two **unchanged fixtures** |
| Preserve `normalize_tags(tags)` signature | Met; original signature retained |
| Requested normalization changes present | **Not met:** function still only returns `list(tags)` |
| Existing `test_returns_new_list` retained | Met; file unchanged |
| Four requested tests added | **Not met:** all four absent |
| No unauthorized executed modifications | Met; no tool actions executed |
| Original source snapshot unchanged | Met; full Step 30 snapshot compared equal |
| Owned staging discarded | Met; workflow reported cleanup, independent temp-directory query found no remaining `alfha-git-*` directories |
| Diff and trace preserved | Met; both are empty because no actions occurred |

**Overall coding outcome: failed.** There is no functional score or functional
correctness claim. Neither fixture nor any proposed Python/test program was
executed. Independent inspection used retained text, hashes, AST parsing and
source Git/filesystem fingerprints only.

## Exact failure mechanism

One model request returned ordinary assistant content containing a JSON array of
six proposals. Native `tool_calls` was absent. The workflow correctly did not
interpret that text as executable tool instructions; no JSON recovery is enabled.

- Native requested/dispatched calls: **0**.
- Recovered calls: **0**. Executed rejected actions: **0**.
- Tool budget consumed: **0/6**, not exhausted.
- Successful edits: **0**. Changed files: **0/2**. Combined diff: empty.
- Printed proposals: **6** (two reads, two intended edits, validation, and an
  edit to unauthorized `non_existent.py`). These are not counted as tool calls.

Both printed edits supplied the literal `old_content` as old_text. Neither
starting file contains it. The printed test replacement has a comment-only test
body and fails standalone AST parsing with an expected-indented-block error.
Its proposed test names/examples also depart from the requested contract. The
last printed proposal names an unauthorized file and has an empty old_text.
These are **data-only observations of unexecuted proposals**, not actual rejected
dispatcher actions or claims that an applied candidate failed tests.

The model never received real file contents or dispatcher feedback because it
never requested a native tool. `workflow.status=completed` means the assistant
exchange ended; `ready_for_human_review=false`, the incomplete-work field, empty
diff and unchanged per-file statuses correctly distinguish that from coding
success. There was no isolation or execution-policy failure; no execution was
requested or authorized. This single attempt does not measure general reliability.

## Evidence and verification

All raw artifacts are ignored and were not committed:

- `runs/step33_preparation.json`: original request, fixture texts and source snapshot.
- `runs/step33_attempt_started.json`: exclusive single-attempt marker.
- `runs/step33_workflow_report.json`: complete model output, tool trace, diff,
  static checks, source starting commit and staging cleanup result. A byte-identical
  copy remains at the workflow's reported OS temporary report path.
  SHA-256: `267c44e796f90625901cffef44930022cc2a0ff8b7321eca0d863941a56c560c`.
- `runs/step33_evaluation.json`: independent acceptance results, actual unchanged
  candidate texts, hashes, model metadata, and separate printed-proposal analysis.
- `runs/step33_regression.log`: post-attempt regression output.

The starting fixture commit was `dd896db030e3c4bc7d49b12a9b61fbd53991b382`.
No source fixture, index, configuration, reference or existing commit was changed.
The ALFHA framework and controller were not modified for this attempt.
**252/252 existing regressions passed after the attempt.** Model/transport activity
printed by these trusted tests uses test doubles and is not another live model
attempt or execution of the Step 33 test file. The final post-regression source
snapshot still matched, and no staging directories remained. The independent
report retains an interim observation of a transient regression workspace and
the final empty-directory check, rather than classifying the test workspace as
a live-attempt cleanup failure.

The immediate reliability problem is native tool-interface use. A future reviewed
milestone could test a bounded reminder after an actionless proposal while keeping
the six-call budget, or improve native-tool prompting with deterministic tests.
Executing arbitrary printed JSON, fuzzy replacements, granting extra file rights,
or silently rerunning this attempt would not be justified by this evidence.
