# Read-only project storage audit — 2026-10-23

Root: `E:\Project\ALFHA-Agent`. Measurement followed the approved two-request
Step 45 comparison, its regression tests and final staging checks.

**Approximately 405.9 MiB (425.6 decimal MB), 2,469 files.** The largest component
is historical evaluation evidence, not the virtual environment or Git history.
Sizes are point-in-time file lengths; overlapping parent/child rows must not be
added together. New audit reports and subsequent documentation add small amounts
after the measurement.

| Directory / category | Size | Treatment |
| --- | ---: | --- |
| evaluations | 376.24 MiB | Source, fixtures, plans, caches and reports |
| evaluations/runs (inside evaluations) | about 375.3 MiB | Preserve historical reports, exact model outputs, candidate snapshots, isolation evidence and failure diagnostics |
| .venv | 27.81 MiB | Current working runtime; conditionally rebuildable, not an immediate cleanup target |
| .venv/Lib/site-packages/pip (inside .venv) | 13.17 MiB | Runtime tooling and its caches, not all disposable |
| .venv/Lib/site-packages/pydantic_core | 5.68 MiB | Installed dependency; preserve |
| .git | 0.77 MiB | Essential history, refs and repository metadata; preserve |
| root __pycache__ | 0.63 MiB | Regenerable bytecode; included in the cache estimate below |
| workspace | 0.011 MiB | Existing workspace/user data; preserve |
| All source-backed bytecode caches (nested within categories above) | 11.33 MiB | Conservative cleanup candidates only after explicit approval |
| ALFHA-prefixed directories under Windows Temp, outside project | 0.86 MiB across 72 directories | Retained sources/reports and other temporary evidence; prefix alone is not deletion authority |
| Remaining alfha-git staging | None | Confirmed after regression completion |

## Largest files

Paths below are relative to the stated root. The full absolute-path inventory is
in the retained JSON audit.

| File | Size |
| --- | ---: |
| evaluations/runs/worker_integration_20261020T183113077401Z.json | 81.60 MiB |
| evaluations/runs/worker_integration_20261020T182612272721Z.json | 81.59 MiB |
| evaluations/runs/step40_reference_integration.json | 62.96 MiB |
| evaluations/runs/functional_live_20261020T171451704939Z.json | 36.07 MiB |
| evaluations/runs/step42_functional_results.json | 32.02 MiB |
| evaluations/runs/step39_functional_summary.json | 9.96 MiB |
| evaluations/runs/step41_functional_results.json | 9.84 MiB |
| evaluations/runs/step39_functional_results.json | 9.81 MiB |
| evaluations/runs/functional_live_20261020T184556886732Z.json | 8.28 MiB |
| .venv/Lib/site-packages/pydantic_core/_pydantic_core.cp312-win_amd64.pyd | 5.29 MiB |

The first three alone occupy about 226.2 MiB. Different filenames and similar
sizes do not establish redundant evidence or byte-identical duplicates. No
reports were deleted, deduplicated, rewritten, compressed or relocated. Historical
live results and runtime evidence cannot be recreated identically by rerunning a
benchmark. Ignored/untracked status is not evidence that a file is disposable.

## Conservative cleanup proposal — requires separate approval

1. Keep all source code, fixtures, plans, workspace data, Git history, candidate
   snapshots, raw responses, evaluation reports and failure evidence.
2. After approval, remove only the **807 enumerated .pyc files** whose standard
   cache names map to existing .py sources and whose current link count is one.
   Recheck the exact paths, source availability, link count and cache identity
   immediately before deletion. Stop if the inventory no longer agrees. Preserve
   any uncertain or sourceless bytecode. Do not delete whole parent directories.
3. Estimated recoverable file bytes: **11,881,051 bytes, about 11.33 MiB**. Of this,
   about 10.35 MiB is inside .venv, 0.63 MiB is root bytecode and 0.35 MiB is under
   evaluations. This is roughly 2.8% of the project. Bytecode will regenerate and
   may temporarily slow the next startup. Actual free-space gain is approximate.
4. Do not remove .venv as a shortcut. No tracked requirements/lock manifest was
   found. A future approved rebuild would first need a verified dependency and
   Python-version inventory and a recovery plan. Its 27.81 MiB overlaps the cache
   estimate; it is not additional immediate safe recovery.
5. Larger savings would require a separately reviewed evidence-retention/archive
   plan with verified backups and unchanged decompressed hashes before removing
   any local copy. No archive/compression ratio was measured or assumed, so no
   additional recoverable-space estimate is claimed. Keep all evidence in place
   for now, including external Temp sources and reports referenced by old records.

No cleanup, Git maintenance, software changes, security changes or source
application was performed. In particular, no git gc, git clean, deletion,
compression or relocation ran. The observed regression-time virtual-memory issue
is separate from this disk inventory; deleting bytecode is not presented as its
fix.

## Measurement evidence and limitations

Authoritative inventory: ignored `runs/step45_storage_verified_audit.json`.
It includes directory totals, 35 largest files, individual cache eligibility,
absolute paths and external Temp measurements. Scans used read-only filesystem
metadata and Windows GetCompressedFileSizeW, with no reparse/junction traversal.
The verified scan reported zero read/allocation errors, no skipped reparse paths,
and no active staging. Logical and OS-reported allocation totals agreed. Inode
deduplication found no shared file identities in the project.

The first scan's logical directory/file sizes were valid, but Windows DirEntry
metadata returned zero link/inode values, making its cache-eligibility/unique-file
fields unsuitable. A separate os.stat-based scan corrected those fields; the
first report was preserved unchanged. Use the verified report for cleanup review.
No existing measured file was rewritten by either scan; each wrote a new report
after reading the tree. Current process/system changes can affect later sizes.

Global Ollama models, Docker virtual disks, global pip caches and unrelated Temp
data are outside this project's measured total and were not recursively audited.
The ALFHA-prefixed Temp inventory is an identification aid, not ownership proof.
