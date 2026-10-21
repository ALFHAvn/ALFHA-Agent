# Step 31: review-only multi-file tasks

`multi_file_tasks.MultiFileTask` extends Step 30's isolated Git staging handle.
It is a trusted host API, not a new model/interactive tool. It never applies
results to the source, runs a candidate program, or authorizes execution.

## Authorization and coordinated editing

Prepare with an explicit `authorized_files` list. Existing files must satisfy
the existing clean tracked-file and ownership checks. Absent files additionally
require `create_files`; deleting an existing file additionally requires
`delete_files`. Both permissions must be subsets of the file allowlist.
Neither permission is inferred from a model proposal or Git diff.

- `read_text(name)`: reads only an authorized regular text file in the temporary
  repository, checking ownership, Git identity and link boundaries again.
- `write_text(name, text)` / `write(name, utf8_bytes)`: edit or explicitly create
  authorized text files. The existing 1 MB limit remains. Binary policy is
  defined as valid UTF-8 without ASCII control bytes except tab/CR/LF. It is
  an encoding policy, not a universal binary-format detector.
- `delete(name)`: requires the distinct deletion permission. Direct filesystem
  deletion, creation, binary writes or unrelated files are rejected at inspection
  if they violate the permissions, even when they bypassed these helpers.
- Each operation rechecks the authorization and workspace boundaries. Failed
  operations are logged and leave earlier successful edits inspectable.

Traversal, absolute/drive/ADS paths, reserved/Git-control names, case aliases,
links, junctions and hard links retain Step 30's restrictions. Dirty unrelated
source files and untracked/ignored user files remain outside staging. Source
conflicts and stale state prevent review readiness and checkpoint creation.

## Validation and report semantics

`validate()` performs actual **non-executing** checks of the staged files:
UTF-8 text checks, AST parsing for `.py`, and JSON parsing for `.json`. Other
text types receive encoding checks only. Authorized absence has no source to
parse. These checks do not prove coordinated behavior, compilability, policy
acceptance by the Docker evaluator, or functional correctness. In particular,
AST parsing can accept a module-level return. Reports explicitly state
compilation/execution/functional tests **not_run**.

Validation results are bound to per-file statuses and content hashes. Any helper
write/deletion invalidates validation; direct edits invalidate the hash binding.
`checkpoint()` requires current successful static evidence; a Boolean alone
cannot claim validation. It creates only an owned temporary Git commit.
Failed checks can be corrected and rerun, with earlier failures still logged.

`report()` returns JSON-serializable evidence with:

- Authorized files and explicit creation/deletion permissions.
- Actual modified paths, per-file unchanged/modified/created/deleted status,
  content hashes and the combined Git diff from the temporary baseline.
- Source starting commit, current temporary checkpoint commit, stale state,
  actual validation checks/results and content binding.
- Successful, failed and rejected operations, including context-manager aborts.
- Integrity result and `ready_for_user_review`, which means current static
  checks passed for an inspectable nonempty change with unchanged source.
  It never means approval to apply or demonstrated functional correctness.

Integrity failures produce a rejected report with an error and any last safe
review; unsafe new content is not staged into a diff. Repeated failures do not
nest reports indefinitely. The report remains available on the in-memory handle
after `discard()` or context-manager cleanup; readiness then becomes false.

## Cleanup and limitations

Only the exact ALFHA-owned temporary repository is discarded. No source reset,
clean, overwrite, commit, push or application is implemented. Inspect/review
and static validation are not permission to apply. Any future application
workflow needs separate review and explicit user approval.

Reports and operation logs are in-memory evidence returned to a trusted caller;
they are not a crash-durable audit service. A caller must retain the returned
report before losing the handle. The existing manifest is descriptive and cannot
recreate ownership or authorization. A hard process death still requires manual
review of orphaned temporary repositories. No automatic adoption or deletion is
introduced. As in Step 30, snapshots are not an OS-level lock against a hostile
process running as the same user, and ignored file contents are not hashed.

The workspace contains only authorized files, not the full project's imports or
dependencies. There are no Python imports of candidate source, host execution,
new Docker permissions, functional-test claims, automatic task retries, or live
model requests. Interactive tools and the six-call budget remain unchanged.

## Actual verification

**235/235 regression tests passed**, including **20 new real-Git multi-file
tests**. These cover two/three-file coordinated changes, explicit creation and
deletion, unauthorized reads/writes, binary data, direct filesystem violations,
partial failures and corrections, content-bound validation, stale source,
untracked user files, traversal, actual Windows junction rejection, repeated
checks, cleanup and retained evidence after abort/discard. Candidate text was
never executed. No live Qwen3 benchmark or new Docker execution batch ran.
