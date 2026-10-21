# Step 38A: bounded Docker readiness and definitive inventory

Readiness does not authorize generation or execution. The Step 38 comparison
remains blocked/expired and is not resumed. A future comparison needs fresh
review and authorization, including approval of this revised readiness gate.

## Confirmed mechanism

`runs/step38_initial_inventory.json` records a three-second process timeout with
empty stdout/stderr and exit code 1. `bounded_command` starts its timer when
launching the CLI; the budget includes API negotiation, Resource Saver wake-up
and engine response, not only listing containers. Its bounded process/pipe
teardown can add time after that command budget.

Local Docker logs now establish the Step 38 mechanism:

- 12:23:01.8766897 UTC: the container API request changed idle to busy and started
  the VM after about four hours of idle time.
- 12:23:06.8749471 UTC: engine running after **4.988 seconds**.
- 12:23:07.0159883 UTC: the original `containers/json?all=1&size=1` request was
  logged with context canceled, after the controller had timed out the CLI.

Excerpts, source log filenames and SHA-256 hashes are preserved in
`runs/step38a_log_evidence.json`. The original Step 38 evidence is unchanged.
This evidence does not explain the separate historical isolation-verification
anomaly or intermittent Git staging tests.

## Readiness and inventory are separate phases

`evaluations/docker_readiness.py` adds a data-only, read-only gate:

1. Poll the fixed Linux context with
   `docker --context desktop-linux ps -a --no-trunc --size --format "{{json .}}"`.
   Default overall readiness budget: **20 seconds**, configurable from 1 to 60.
   Per-command budget: at most three seconds or the remaining readiness time.
   Poll interval: 0.5 seconds; absolute ceiling: 40 polls. Late success after the
   readiness deadline does not pass. Transport teardown is separately bounded.
2. After service readiness, perform exactly one final inventory using the
   original `ps -a --no-trunc --format "{{json .}}"` command and three-second
   command budget. There is no retry of this final check.
3. Require successful transport and complete, unambiguous JSON rows with full
   IDs, names, image, state and labels. Duplicate identities, malformed data,
   truncated/incomplete capture, stderr or transport failure block readiness.
   ALFHA-named/labeled containers require cleanup; this checker never removes
   them. Other valid containers are recorded and preserved.

Polling failures are retained as readiness telemetry, never relabeled as passed
inventory or isolation evidence. A timed-out final inventory remains **unknown**,
including when its stdout is empty. A successful empty inventory requires a
successful, complete final command. No container creation, service management,
image download or Docker configuration changes occur. Desktop itself can wake
its VM in response to the read-only query.

The explicit `--size` readiness request matters: an initial controlled prototype
used quiet `ps`, which returned in 0.234 seconds while the engine was asleep.
The logs show that request was served by the idle cache. The subsequent JSON
inventory woke the VM, needed about 4.37 seconds, and timed out. This failed
prototype check is preserved in `runs/step38a_controlled_readiness.json`, not
overwritten. The corrected implementation uses the engine-dependent size path
for polling. Unit tests assert this path; cached metadata or quiet IDs cannot
satisfy the readiness phase.

## Invocation and compatibility

Standalone Docker-only check:

```powershell
.venv\Scripts\python.exe -m evaluations.docker_readiness --readiness-timeout 20
```

Combined evaluation preflight, with readiness/inventory first and the existing
Ollama/model/Linux engine/pinned-image metadata checks afterward:

```powershell
.venv\Scripts\python.exe -m evaluations.dependency_preflight --verify-docker-inventory --readiness-timeout 20 --model qwen3:4b --model qwen2.5-coder:3b-instruct-q4_K_M --model qwen2.5-coder:7b-instruct-q4_K_M
```

Both return structured duration, poll count, per-command raw results and final
status; exit nonzero on failure. `isolation_verified` and `execution_authorized`
remain false. The legacy metadata-only preflight API/default CLI remains
compatible and does **not** imply container inventory was verified. Interactive
agent behavior is unchanged. Future evaluation orchestration must explicitly use
the combined gate and check its result before generation. No old benchmark or
approval mechanism is silently migrated. Runtime isolation verification and
post-execution cleanup keep their existing requirements and are never retried
by this code.

## Verification and limits

Fifteen deterministic tests cover delayed wake-up, deadline exhaustion, late
success, single final-inventory timeout, malformed/duplicate/partial evidence,
owned containers, configuration bounds, transport exceptions, and CLI gating.
The corrected controlled combined check passed: one readiness poll in **0.266
seconds**, final inventory verified empty, Docker phase **0.500 seconds**; all
three required models and pinned-image metadata also passed. Evidence is in
`runs/step38a_corrected_readiness.json`. This was a warm-engine observation,
not by itself evidence of a real cold wake-up succeeding under the new gate.

After the full regression suite, a second corrected controlled cycle handled a
real Resource Saver wake-up. Logs show idle-to-busy at 12:42:26.5557069 UTC and
the engine running after **4.368 seconds**. Readiness took **4.781 seconds**, with
two polls (first timed out, second passed). The separate final inventory passed
once and definitively returned an empty list; total Docker phase **5.031 seconds**.
All three model/image metadata checks also passed. Evidence:
`runs/step38a_final_readiness.json` and `runs/step38a_final_log_evidence.json`.
Only startup readiness was polled; no failed final inventory or isolation check
was automatically retried. This is one observed cold-wake success, not proof of
readiness under all failures, races or future Docker versions.

The initial targeted sandbox run had five filesystem permission errors (Git init
and atomic report replacement), with no assertion failures. With the required
disposable-repository/report permissions, the 37-test targeted suite passed.
The additional engine-path regression then passed in the 15-test readiness suite.
These test invocations use fake services; no model generation or candidate
execution takes place.

The complete trusted regression suite passed **342/342 tests** in **370.311
seconds**, including the fifteen new readiness tests. Full diagnostic evidence
and log: `runs/step38a_full_regression_evidence.json` and its companion log.
No live benchmark or candidate code ran. The approved image, Docker execution
policy, task fixtures, model default and six-operation budget are unchanged.
Legacy metadata-only callers still require explicit integration of the combined
gate; it is not a substitute for runtime isolation or final cleanup checks.
