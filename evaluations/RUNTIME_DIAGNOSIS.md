# Step 29A: runtime verification diagnosis

Live functional evaluation is disabled in both the benchmark API and CLI. There
is no command-line override. It requires a separate reviewed change before a
fresh live benchmark; this diagnosis never calls Ollama or retries a model task.
The generic backend execute() and legacy static CLI remain disabled too.

## Historical evidence and scope of the unknown

The retained consolidated report is
evaluations/runs/functional_live_20261020T163242781596Z_consolidated.json.
Its exact terminal error is "RuntimeError: Execution verification lost after
grading". The failed boundary verification object was not recorded. The earlier
11-probe report and successful worker observations cannot fill that gap.

clamp's actual container inspection had no policy errors. It exited with code 0,
was not OOM-killed, and had independent removal/absence evidence. Its functional
result was 7/7. The subsequent failing boundary did not inspect this already
removed container: it checked the local Docker context, engine, pinned image,
runtime identity, transport/policy source hashes and probe-runner source hash.

The relevant path is:

1. benchmark_functional.verify_boundary calls backend.verify().
2. verify deep-copies the in-process probe evidence and calls transport.preflight.
3. preflight uses bounded Docker CLI metadata commands for context, info and image.
4. It checks required isolation capabilities and compares the resulting identity
   and source hashes with the in-process baseline.
5. Any exception/mismatch invalidates verification; the benchmark stops.

Container execution separately follows preflight, fixed create arguments,
effective inspection/policy/command/environment validation **before start**,
bounded attach, state/exit consistency checks, then forced removal and absence
verification in finally. Timeout/output/I/O failures also trigger a kill. Failed
cleanup poisons the transport, preventing further execution.

The historical failure could be a metadata transport/inspection failure or an
identity mismatch. Its exact operation/field and underlying cause remain
unresolved. The evidence does not establish a container inspection race, changed
security configuration or host compromise. Later successful metadata checks
cannot retroactively turn that failed verification into a pass.

Historical Docker Desktop host/VM API logs were also examined. They show
completed info/image requests before clamp's grade was recorded at
16:37:50.833957 UTC. No engine API request appears in the selected logs during
the final boundary's 0.234-second window ending 16:37:51.067777 UTC. This narrows
the observed timeline but does not identify a failed CLI operation: local context
inspection does not contact the engine, and a client can fail before an engine
request. The CLI's missing result prevents a definitive attribution. Narrow raw
log extracts and source hashes are retained in ignored
evaluations/runs/step29a_historical_log_evidence.json.

## Validated diagnostic improvements

Previously the Docker command audit retained only operation, return code,
timeout and truncation flags. Metadata exceptions discarded stdout, incomplete
I/O details and exact arguments. Identity mismatches gave no field-level diff.
This reporting deficiency is reproduced deterministically; it is distinct from
the unknown cause of the historical verification failure.

The audit now retains bounded stdout/stderr, operation arguments, exit status,
timing and I/O errors/unfinished threads. Candidate input programs are not copied
into command arguments/audit. Every verification reports the observed identity,
typed field differences, probe source hash and the raw metadata commands from
that verification. Expected identity evidence is never replaced with observed
values. Saved reports are never loaded as execution permits.
Internal worker verification rejection now carries the original report across
exception boundaries. The harness preserves blocked, preflight and postflight
verification objects instead of replacing them with generic messages.

Failures distinguish metadata timeouts, incomplete I/O, output limits, CLI errors,
malformed JSON, invalid schemas/missing evidence, policy mismatches, identity
mismatches, source mismatches and unverified cleanup. Container policy errors
retain the actual inspected document and failed settings. Missing exit-state
evidence cannot become normal completion. Duplicate fields and non-finite JSON
metadata are rejected rather than interpreted ambiguously.

No inspection retry was added: the missing historical evidence does not justify
one. There are no execution retries. The existing bounded cleanup attempts remain
in place. Network, non-root identity, capabilities, seccomp, CPU/memory/PID limits,
timeout, scratch/output limits, mount restrictions and pinned image are unchanged.

## Controlled reproduction command

    .venv\Scripts\python.exe -m evaluations.diagnose_runtime --cycles 20

It reruns all 11 real mandatory probes, then alternates three fixed trusted
programs: print(6 * 7), exit(7), and a sleep exceeding the existing wall timeout.
There are no caller-supplied programs, image overrides, Docker flags or model
requests. Every cycle records before/after verification, raw Docker commands,
container inspection, execution/state and cleanup evidence. It stops at the first
unexpected result. A final independent query must establish that no evaluation
containers remain; existing unrelated containers are never removed.

JSON reports are atomically checkpointed under ignored evaluations/runs/.
Repeated successful checks demonstrate only the observed lifecycles. They do
not establish the cause of an earlier unrecorded failure or authorize live use.

## Actual results

- **131/131 regression tests passed**: the 112-test baseline plus one live-disable
  test and 18 deterministic diagnosis tests. They cover raw I/O evidence loss,
  exact identity field changes, missing evidence versus explicit policy mismatch,
  timeout/truncation/CLI failures, duplicate/non-finite metadata, spawn exceptions,
  incomplete inspections/states, blocked start, cleanup poisoning, internal
  rejection/postflight evidence and controlled-runner failure paths.
- First controlled batch: **20/20 cycles**, **40/40 boundary checks**, fresh
  **11/11 isolation probes**. Report:
  evaluations/runs/runtime_diagnosis_20261020T165122419441Z.json.
- After preserving internal worker/harness rejection reports, the final code was
  tested in a second fresh batch: **20/20 cycles**, **40/40 boundary checks** and
  **11/11 isolation probes**. Report:
  evaluations/runs/runtime_diagnosis_20261020T165554591132Z.json.
- Across both batches: 14 normal exits, 14 controlled exit-code-7 cases and 12
  wall-timeout cases. All had verified cleanup. All 80 recorded boundary checks
  matched; no boundary metadata transport failure was observed.
- Each batch's final container query was empty. A separate final Docker query
  also found no evaluation containers. No model requests were made; the live CLI
  was checked and refused to run. Original benchmark reports were preserved.

The confirmed defect addressed here is lost diagnostic evidence, including
internal rejection paths. **The original intermittent failure's root cause is
still unresolved.** No inspection retry, weakened requirement or inferred success
was introduced. Successful trusted cycles do not reproduce all timing conditions
of the historical model run, and cannot establish that the intermittent failure
is fixed. Live evaluation remains disabled pending a separate review; do not
resume or rescore the interrupted benchmark from these results.

Full regression command:

    .venv\Scripts\python.exe -m unittest -q test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport test_functional_worker test_functional_benchmark test_runtime_diagnosis
