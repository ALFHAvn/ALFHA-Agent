# Step 30: isolated Git checkpoints and safe discard

`git_checkpoints.py` is a trusted host-side API, separate from the interactive
ALFHA controller and its six tools/six-call budget. It does not call Ollama or
execute candidate programs. Live functional evaluation remains disabled by
default. Docker policy, execution validation, and evaluation fixtures are unchanged.

## Workflow

1. Explicitly authorize a list of relative file paths and the exact repository
   root. The source must have an existing HEAD commit.
2. `GitCheckpoint.prepare(root, files)` creates an independent temporary Git
   repository **outside the project**, containing only the authorized starting
   files. It neither clones the project nor registers a source Git worktree.
   It has no remote, no copied project Git configuration/hooks, and uses its own
   `codex/isolated-task` branch and temporary commit identity.
3. `write(path, bytes)` stages authorized, bounded file contents. `inspect()`
   returns the starting source commit, owned checkpoint commit, modified paths,
   source conflict status, and a reviewable diff including new files.
4. A trusted caller may attest independent validation with
   `checkpoint(validation_passed=True)`. This creates a commit **only in the
   temporary repository**. The Boolean is an external validation attestation,
   not a validation engine or a claim that tests ran. Failed validation makes
   the task rejected; it must be discarded.
5. `discard()` deletes only the exact ALFHA-owned temporary root. The context
   manager also discards on normal exit or an exception. Rollback means
   discarding the temporary changes, never resetting the source.

There is **no apply, accept, restore, push, reset, clean, merge, or source-commit
API**. No CLI or interactive-agent tool was added. An inspectable or validated
diff does not authorize application. Any future project application workflow
requires separate review, explicit user approval, and fresh conflict validation.

## Safety rules

| Data or boundary | Protection |
|---|---|
| Dirty authorized files | Reject staged changes, conflicts, missing tracked files, and working content changes. Preserve all bytes/index entries. CRLF checkout representation is permitted without normalizing source bytes. |
| Dirty files elsewhere | May coexist; never copied or written. Tracked/untracked fingerprints and Git metadata detect source changes before and after a temporary checkpoint. |
| Existing untracked authorized paths | Reject adoption, including staged new files. New files are allowed only at explicitly authorized absent paths. |
| Ignored files | Never copied or written. Paths matching repository ignore rules are rejected, including absent ignored destinations. Inventory changes invalidate snapshots. |
| Existing source history/config | Source Git commands are read-only plumbing; no primary commits, ref changes, index refreshes, configuration writes, hooks, filters, or history rewriting. |
| Paths | Exact relative POSIX names; reject traversal, absolute/drive/ADS paths, Git-control names, Windows reserved names, case duplicates, and file/parent collisions. Resolve aliases and reject links, junctions, reparse points and hard links on write paths. |
| Concurrent source edits | Compare source HEAD, refs, index/config/HEAD hashes, tracked/untracked fingerprints and ignored inventory. Stale checkpoints cannot be validated. Source changes are never overwritten. |
| Temporary repository tampering | Reject changed Git configuration, changed HEAD, unauthorized files, links and hard links. Saved manifests cannot reconstruct an ownership handle or grant permissions. |
| Rollback | Verify in-memory ownership, marker, absolute root identity and non-linked ancestry; reject linked contents before deleting only that owned root. Repeated discard is harmless. |

Git subprocesses use argument arrays, timeouts, no shell, disabled hooks/signing/
fsmonitor and external diff/text conversion, no inherited `GIT_*` repository or
index overrides, and no global/system configuration. These are per-command
overrides; no user's configuration is changed. Source plumbing avoids invoking
repository-defined content filters. The isolated repository contains no copied
`.gitattributes`, Git hooks or credentials. The per-file write limit is 1 MB.

## Limits

- This is staging and review infrastructure, not an execution sandbox. Do not
  run candidate code here. Existing verified Docker execution remains the only
  candidate execution mechanism.
- Only explicitly authorized regular file contents are materialized. This is
  not a full project checkout or full dependency/test environment. Symlinks,
  submodules, dirty authorized files and Git-control files are unsupported.
- Ignored file contents are intentionally not read or hashed. Changes to bytes
  of an existing ignored file alone need not invalidate a snapshot, but no
  operation writes or applies results to ignored files. Global ignore settings
  are not inherited; existing untracked files are rejected regardless.
- Conflict snapshots are not an OS-level transaction or a lock against an
  adversarial process running as the same Windows user. Checks detect observed
  changes; they do not prevent changes after inspection. Automatic application
  remains unavailable, so these snapshots cannot authorize overwriting work.
- Abrupt process death can leave an owned temporary repository. There is no
  automatic adoption, resume, or orphan deletion based on a saved manifest.
  Such remnants require manual inspection; metadata is descriptive only.
- Review output contains untrusted candidate text and must not be executed.
  Temporary commits and manifests are local artifacts, not committed to the
  source project or cryptographic attestations of validation.

## Actual validation

**215/215 regression tests passed**, including **31 new real-Git tests** in
disposable repositories. Tests cover clean/dirty/staged work, untracked and
ignored data, absent new files, unauthorized paths, stale HEAD/refs/index/file
changes, preparation/checkpoint races, rejected validation, abort/discard,
ownership/config/history tampering, an actual Windows junction and hard link,
Git environment isolation, source content-filter avoidance, and cleanup after
initialization failure. Candidate text was never executed. No live benchmark ran.
