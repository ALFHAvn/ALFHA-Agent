# Step 32: integrated review-only coding workflow

`coding_workflow.run_task(request, chat_fn=...)` connects the isolated multi-file
staging API to local `qwen3:4b`. Omit `chat_fn` to explicitly use Ollama at
`http://127.0.0.1:11434`; a remote `OLLAMA_HOST` is never inherited. Importing the
module starts nothing. This milestone was tested with injected model responses
only: no live model coding run or benchmark was performed.

## Request contract

All four fields are required; unknown fields and ambiguous operation scopes are
rejected before contacting a model:

```json
{
  "description": "Coordinate the configuration values in the two modules.",
  "source_repository": "E:/explicitly-authorized/project",
  "authorized_files": {
    "settings.py": ["read", "modify"],
    "client.py": ["read", "modify"],
    "new_config.json": ["create", "read"]
  },
  "validation_requirements": {"static": true, "docker_execution": false}
}
```

The caller must have authorized that root and those operations. Existing clean
tracked files can receive read/modify/delete permissions. Absent files require
explicit create permission. There is no wildcard authorization, inherited
directory permission, overwrite-through-create, or implicit delete permission.
The source-root, dirty-file, untracked/ignored-file, alias, link and ownership
protections of Steps 30/31 remain in force. No source file/ref/index/config is
written by the workflow.

## Controller and tools

The model receives the task, explicit authorization, and registered read_file,
edit_file, create_file, delete_file and validate_files interfaces. Every call
passes strict host-side name, argument-key, string-type, path and operation
checks. Edits use a nonempty exact old_text with exactly one match. Rejections
return specific feedback and can be corrected within the same budget. Source
freshness and staging integrity are checked repeatedly.

There are **six native tool-call attempts total**, including rejected calls and
model-requested validation. A batch larger than the remaining budget is rejected
in full and recorded separately; none of it is dispatched. Exhaustion produces
an incomplete/budget_exhausted result rather than an invented completion. The
existing interactive controller and its tools/budget are unchanged.

Printed JSON, code fences and prose are never dispatched. There is no recovery
parser in this workflow: existing evaluation-specific recovery does not grant
multi-file authority. Calls requesting execution, Git operations, source apply
or unsupported tools are rejected. Model response text is untrusted; a claim of
success is not evidence of an edit or functional correctness.

## Validation, review and evidence

At the end, including partial/interrupted runs, the host runs the existing
non-executing static checks. Actual text/AST/JSON results are recorded per file.
AST parsing is not compilation. Compilation, functional execution and functional
tests remain not_run. No model-generated Python executes on Windows.

Only a completed model exchange with a changed, intact, source-fresh candidate
and current successful static evidence is marked ready_for_human_review. That
means ready to inspect the retained artifact, not semantically correct, accepted,
or authorized to apply. A temporary-only Git checkpoint is made for that artifact.
Readiness does not establish that every semantic part of the request was met.

The complete JSON report includes the task, per-path operations, source starting
commit, model requests/responses, attempted calls and budget use, accepted changes,
rejected calls/batches, partial edits, errors/incomplete work, final per-file
statuses/validation, combined diff and temporary checkpoint identity. Zero JSON
recoveries are explicit. Model interrupts and transport failures do not restart
the task or silently retry the model.

Reports are atomically checkpointed in a separate owned OS temporary directory
named `alfha-coding-report-*`; `report_path` identifies the retained `report.json`.
Evidence precedes model requests, tool dispatch and cleanup. Pending flags mean
an operation/response was not observed to finish, not a successful result.
The developer can inspect the returned report or read its JSON after the staging
workspace has been discarded. Keep/move desired reports through an explicitly
authorized host workflow: OS temporary storage is not permanent archival storage.
Report data cannot recreate an ownership handle, resume a task or grant execution.

The staging workspace is discarded after completion or handled failure; the
separate evidence directory is retained. Cleanup refusal/errors are reported,
not hidden or bypassed. A process kill may leave an orphan staging directory or
a pending checkpoint; no automatic adoption, execution or deletion is introduced.
Existing filesystem/atomic-replace and same-user concurrency limitations remain.

## Execution boundary

Only `static=true, docker_execution=false` is supported here. Explicit Docker
requests are rejected before a model call. The verified Docker worker currently
supports fixed single-function evaluation tasks, not arbitrary multi-file
projects. This workflow does not reinterpret that policy or broaden it.
There is no persistent execution toggle or source-application path. Future
execution/project application integration needs separate review and authorization.

## Actual tests

**252/252 regression tests passed**, including **17 new orchestration tests**
using mocked model responses and real disposable Git repositories. Tests cover
two/three-file coding, explicit creation/deletion, read versus modify permissions,
invalid calls and correction, malformed native calls, literal newline errors,
printed JSON, interrupts and transport failure, static validation failure, stale
source, budget exhaustion and whole-batch rejection, source preservation, cleanup
and the retained JSON report. No real model, live benchmark or new Docker worker
batch was run in this milestone.
