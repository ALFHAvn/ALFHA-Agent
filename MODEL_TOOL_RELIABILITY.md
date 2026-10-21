# Step 34: model-to-tool investigation and controls

No live generation/evaluation or candidate execution was performed in this
milestone. Step 33 raw evidence and source fixtures remain unchanged. New
metadata was obtained with the read-only Ollama `show` API, not `chat`.

## Confirmed findings

1. Step 33's `message.tool_calls` was absent. Its content was valid JSON: a
   six-object array, not a native tool batch or malformed JSON. Several proposals
   could not be applied (placeholder old_text, unauthorized path, empty old_text);
   the printed test replacement also failed standalone AST parsing.
2. Installed Ollama Python SDK **0.6.3** accepts the supplied dictionary function
   schemas. The installed Qwen3 template advertises `completion`, `tools` and
   `thinking`; it requests function-call JSON inside `<tool_call>` tags. Step 33's
   bare array lacks that native format. The server returned a normal response to
   the tool-bearing request; the adapter did not remove a structured native call.
   An in-memory HTTP transport test confirms SDK schema serialization and native
   response roundtripping without contacting a model.
3. The integrated request used model/messages/tools with default non-streaming
   behavior. It did not force JSON `format` or alter `think`/options. The installed
   model template contains the JSON function-call example; the host prompt did
   not ask for a raw JSON plan. Why Qwen3 ignored the required format remains
   unknown; this evidence does not establish prompt causality.
4. A separate adapter defect was confirmed: the SDK drops `name` from outgoing
   tool-result messages and preserves `tool_name`. The integrated workflow now
   sends `tool_name`. This cannot explain Step 33's first response, since no tool
   result was sent in that attempt.
5. The unchanged interactive controller also calls Ollama with schemas and reads
   native `.message.tool_calls`. It already has a bounded request for real tool
   use after actionless output and edit-focused recovery mode. Its tool-result
   dictionaries still use the legacy name key. It was inspected, not modified.
   The integrated workflow previously ended on any text-only response, even a
   plan; it now distinguishes text proposals, empty responses and completion.

Raw installed-template/capability evidence is ignored at
`evaluations/runs/step34_model_template.json`. Step 33's preserved raw-report
SHA-256 remains `267c44e796f90625901cffef44930022cc2a0ff8b7321eca0d863941a56c560c`.

## Deterministic controls

- Tools and filename enums are restricted to the request's authorized operations.
  Every action is independently checked on the host; schema hints grant no rights.
- Optional `tool_policy` requires exactly two Boolean values:
  `inspection_first` and `single_json_recovery`. Both default false to preserve
  native edit compatibility. With inspection-first enabled, only read_file is
  offered/accepted until all readable modification/deletion targets have been
  read successfully. The phase restriction applies to native and recovered calls.
- Empty/actionless or proposal-only output gets at most **one corrective prompt**
  within the existing eight-response bound. It does not start a new task or reset
  the six-call budget. Subsequent unresolved actionless output is incomplete.
- All mutable authorized paths are required to change by default. A caller may
  narrow this completion requirement through explicit `required_changed_files`,
  a unique list of authorized mutable paths. It cannot authorize a new path or
  operation. A summary cannot mark missing required edits as complete.
- Native tool errors identify expected/missing/unexpected arguments and exact
  match counts, with no fuzzy editing, newline rewriting or automatic coercion.

## Explicit single-object recovery

Recovery is **off by default**. A trusted task request must explicitly opt in;
the model cannot change the policy. When enabled, at most one parsed proposal
may enter dispatch, including a proposal subsequently rejected by authorization.

The accepted textual envelope is one raw JSON object with exactly `name` and
`arguments`. Arrays (even one-item arrays), duplicate keys, nonstandard constants,
fences, prose wrappers, trailing content, and extra envelope fields are rejected.
No first-item selection or splitting of a printed plan is performed.

Only read_file or edit_file can be recovered. A recovered edit requires a prior
successful authorized read of that file, correct string arguments and exactly
one nonempty old_text match. It passes the same visibility/phase, per-file
operation, source freshness, ownership, link, text and size checks as native
calls. Recovery cannot create/delete files, validate, execute, call Git, apply
changes or exceed original permissions. Unsupported native actions are also
rejected.

Each recovered attempt consumes one of the same **six tool-call attempts**;
rejected attempts count too. Native batches larger than remaining capacity remain
rejected in full. Text parsing errors consume no tool dispatch but have only the
one bounded correction prompt. Native requested counts, dispatch attempts,
recovery attempts/successes, origins and textual observations are reported
separately. No text proposal is labeled an executed action without acceptance.

## Validation and compatibility

The new behavior is confined to the integrated workflow and helper. The
interactive agent, source Git protections, Docker policy, fixtures, execution
gates, local model defaults and six-call limit are unchanged. `stream=False` is
explicit; format/think/options remain unspecified. No arbitrary candidate program
or generated test executes during parsing, recovery, staging or validation.

Existing request shapes remain accepted. Compatibility changes are stricter
completion coverage (supply required_changed_files if some authorized mutable
files are optional), one bounded text correction, filtered tool visibility, and
correct SDK tool-result metadata. Static validation still cannot establish
compilability, semantics or functional correctness.

**267/267 regression tests passed**, including **15 new protocol/SDK tests**.
The full output is preserved in ignored `evaluations/runs/step34_regression.log`.
New tests cover
proper native calls, installed SDK wire format, single recovery, arrays/malformed
JSON/duplicates/fences, explicit authority, wrong/missing arguments, nonmatching
edits, empty responses, phase restrictions, native-plus-recovered budget use,
incomplete multi-file work and named tool feedback in real disposable Git repos.

These are deterministic safety/control improvements. Their effect on Qwen3's
actual success rate is unmeasured. A separately approved live attempt is needed;
the Step 33 failure was neither rerun nor retrospectively repaired.
