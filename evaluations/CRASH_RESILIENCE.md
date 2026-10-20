# Step 29F: checkpoint integrity and interruption diagnosis

No live Qwen3 benchmark was run. Step 29E evidence remains unchanged, including
SHA-256 `3d61fd95c711c19f18b121fb9619bc1a1b646ed5f1b9d8ca1897129c56a05ab8`
for `runs/functional_live_20261020T184556886732Z.json`.

## Available crash evidence

Windows Application events (ID 1000) at **2026-10-21 01:49:04 Asia/Saigon** record:

| Application | Faulting module | Exception code |
|---|---|---|
| codex.exe | DNSAPI.dll | 0xc00000fd |
| ChatGPT.exe (Codex desktop package) | ntdll.dll | 0xc0000005 |

The raw messages, record IDs, and timestamps are separately retained in ignored
`runs/step29f_windows_events.json`. These identify crashes of the host tooling
during the interruption window. They do not establish the underlying trigger,
causality between the two crashes, or an Ollama/Docker/candidate fault. No crash
dump was analyzed. The targeted System restart-event query returned no matching
41/6008/1074 events in 01:40–02:00. The targeted Docker backend error/shutdown
search returned no matching lines in the immediate window; this is not proof
that Docker remained healthy. The available Ollama server.log ends at an earlier
10:23:43 request on October 20 and does not cover this invocation. Absence of
diagnostics is not a passing runtime verification.

## Persistence and state

The old writer already replaced a temporary file. The new writer serializes
first, writes a uniquely named sibling temporary file, flushes and fsyncs it,
closes it, then atomically replaces the destination. A failed write or replace
preserves the old checkpoint. Ordinary failures remove the temporary file;
abrupt termination may leave a temporary file, which inspection never promotes
or uses as evidence. Disk failure/power-loss durability of directory metadata
remains filesystem-dependent; this is not a guarantee against disk corruption.

Additive report fields preserve legacy `results`, counters, and statuses:

- `run_id`, process PID/creation identity, `checkpoint_utc`, increasing sequence.
- `task_states`: pending, running, completed, interrupted, plus generation/grading
  phase. Only a retained grading outcome makes a task completed.
- Separate `completed_results` and `in_progress_telemetry`, with completeness
  markers and explicit unknown outcomes. Legacy aggregate tool counters cover
  completed controller returns; partial counters remain under `progress`.
- Progress snapshots before requests, after responses, and after tool actions
  retain responses, candidate text, tool results, and observed counters. A model
  request still underway has no invented response. No extra model/tool calls are
  introduced. A grading interruption retains the candidate but no invented grade.

The original expected vectors, grading worker, Docker restrictions, image,
interactive controller, and six-call limit are unchanged. `checkpoints.py` is
included in protected source hashes. Checkpoint failures stop orchestration and
expire authorization; even if the final save also fails, no retry is authorized.

## Read-only inspection

```powershell
.venv\Scripts\python.exe -m evaluations.checkpoints evaluations/runs/REPORT.json
```

This standard-library-only entry point reads data and checks process identity.
It does not import the agent, contact Ollama/Docker, execute candidate source,
create a permit, write evidence, resume tasks, or retry anything. Even a matching
live owner cannot grant execution through this API. Dead/reused owner identity
identifies a stale active run; unavailable identity is explicitly unknown and
conservatively presents unfinished outcomes as interrupted. Legacy reports
without process identity cannot prove termination by themselves.

Inspection validates basic report structure and grade counts, recomputes recorded
completed totals, separates unknown outcomes, and removes overall scores for
incomplete evidence. It is not cryptographic authentication of arbitrary reports.
`vectors_not_run` retains compatibility and means no recorded execution; the new
`vectors_without_recorded_execution` makes that meaning explicit during recovery.
Unobserved execution during a crash is unknown, not an assertion failure.

Repeated inspection leaves original bytes unchanged. A saved active authorization
is descriptive historical data only. Every future live run still requires new
explicit human approval and the existing one-use permit and runtime verification.

## Verification

**184/184 regression tests passed**, including **21 new checkpoint/crash tests**.
Tests cover generation/grading interruptions, telemetry snapshots, stale and reused
PIDs, unknown liveness, missing outcomes, malformed/partial files, duplicate tasks,
expired permits, repeated inspection, serialization/fsync/replace failures, and
progress-save failure stopping before grading. A trusted test writer was actually
force-terminated at the replacement boundary; the previous complete file survived
and the leftover temporary file was ignored. Model and grading orchestration used
test doubles; no candidate program ran on Windows and no live benchmark occurred.
No new real Docker worker integration/probe batch was needed or run for these
persistence-only changes; historical probe results are not claimed as fresh tests.

Progress cannot recover responses not yet returned, vectors not yet checkpointed,
or lost filesystem writes. Frequent full report snapshots add serialization/I/O
overhead and duplicate some data for compatibility. They do not make a crashed
run resumable or justify automatic authorization.
