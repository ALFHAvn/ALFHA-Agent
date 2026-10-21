# Step 39: approved add_one functional evaluation

Exactly the three approved preserved add_one snapshots ran, once each, inside
the restricted Docker worker. No new model generation, normalize_tags execution,
generated-test execution, source application or Windows candidate execution
occurred. Preserved code and the six fixed expected outcomes were unchanged.

## Actual functional results

| Candidate origin | Policy | Compiled inside Docker | Functional vectors | Exit | Worker seconds |
| --- | --- | --- | --- | --- | --- |
| qwen3:4b, Step 38B attempt 1 | Accepted | Passed | 6/6 | 0 | 0.437 |
| Coder 3B, Step 38B attempt 3 | Accepted | Passed | 6/6 | 0 | 0.454 |
| Coder 7B, Step 38B attempt 5 | Accepted | Passed | 6/6 | 0 | 0.468 |

Per-vector observed results were identical for all three candidates:

| Input | Host expected | Actual for each candidate | Exact type/value | Arguments unchanged |
| --- | --- | --- | --- | --- |
| 0 | 1 | 1 | Passed | Passed |
| 1 | 2 | 2 | Passed | Passed |
| -1 | 0 | 0 | Passed | Passed |
| 41 | 42 | 42 | Passed | Passed |
| -8 | -7 | -7 | Passed | Passed |
| 1000000 | 1000001 | 1000001 | Passed | Passed |

Total: **3/3 approved candidates passed; 18/18 vectors passed**. There were no
runtime errors, timeouts, malformed outputs, truncated/incomplete captures or
nonzero candidate exit statuses. Expected values and grading decisions stayed
outside the candidate namespace/container request. Host grading required exact
integer types/values and unchanged arguments. Worker timings are execution
observations, not model generation speed or a model performance comparison.

All three implementations have the same preserved source SHA-256:
`eb03dcb53008b66099f4a3324d5335b3cf0a3e93fefc7836afbb6a9eb88cfbdd`.
These are three independently isolated executions of identical simple code,
not evidence of three different correct algorithms or general coding competence.

## Excluded candidates and interpretation

The three normalize_tags implementations were not sent to a worker, compiled,
executed or altered. Their non-executing policy decisions remain rejected for
`Unsupported attribute: strip` and `Unsupported call target`. They were outside
the approved execution scope; their 36 proposed checks remain unexecuted and
receive no functional pass/fail score. The Python subset was not expanded.

Step 38B's **4/6 static completions** remains unchanged. Its three syntax-task
static passes now have functional evidence for the six integer vectors. Its
normalize_tags static assessments still have no functional execution evidence.
This run cannot confirm or refute their functional correctness and does not
produce an overall six-task functional score.

## Fresh isolation and cleanup evidence

All **11/11 fresh mandatory probes passed before the first candidate job**:
normal calculation, wall timeout, network denial, host-file denial, memory limit,
CPU limit, process limit, read-only/non-root controls, bounded output, rejection
of unsafe configuration, and cleanup. Each probe retains actual observations,
container inspections, command results and absence checks, not merely accepted
Docker flags. All candidate jobs retain matched runtime identity before/after,
successful container inspection and worker transport evidence.

The pinned Python image and fixed execution policy were unchanged: non-root
65534:65534, network none, read-only root, all capabilities dropped,
no-new-privileges, required seccomp, no host mounts/credentials/socket,
256 MiB/no extra swap, one CPU/one CPU-second, 16 PIDs, bounded 1 MiB scratch,
two-second worker wall timeout and 64 KiB shared output cap.

Each candidate container was forcibly removed by the existing lifecycle and
independently confirmed absent. Every post-job inventory and the immediate final
inventory passed, showing zero containers. No mandatory probe, runtime identity,
isolation, protocol or cleanup failure occurred. Authorization expired on
completion; persistent live execution remains disabled.

## Fail-fast implementation

Inspection before execution found that the existing probe runner recorded probe
failures and continued collecting later checks. To enforce the user's immediate
stop requirement, `run_security_probes`, the backend and harness preparation now
accept an explicit `stop_on_failure` option and checkpoint callback. This run
used `stop_on_failure=True`. A failed probe stops before the next probe; later
checks remain not_run. Transport failures retain their original structured
failure objects and raw command audit. A checkpoint write failure propagates;
it cannot permit candidate execution.

Probe assertions, restrictions, image and time/resource budgets are unchanged.
Legacy default call signatures retain their prior behavior; execution still
requires every mandatory probe to pass. No failure is converted into a pass,
and no retry mechanism is added. The changed probe source/profile was freshly
verified during this run; historical reports were not used as permits.

Before the run, **60 targeted tests passed**, including four new fake-transport
tests for immediate stop, full failure preservation, stop after an earlier pass,
and failure to checkpoint before dispatch. These tests made no Docker calls.

## Preserved evidence

Generated reports remain ignored/uncommitted under `evaluations/runs/`:

- `step39_functional_results.json`: complete checkpointed run, fresh probes,
  per-job source, policy, verification, stdout/stderr, vector grades and cleanup.
- `step39_isolation_checkpoint.json`: probe-by-probe raw evidence and audit.
- `step39_job_1.json`, `step39_job_2.json`, `step39_job_3.json`: individual results.
- `step39_execution_started.json`: exclusive marker preventing restart/retry.
- `step39_functional_results.log`: actual probe/job progression.

The Step 38B and Step 39 preparation evidence is preserved. Only implementation,
tests and documentation are eligible for commit; no model code or generated
report is committed.

## Final closure

The complete trusted regression suite passed **357/357 tests** in **416.412
seconds**, including the four new fail-fast tests. Unit-test model/service calls
are test doubles, not additional candidate runs. Final closure reverified the
preserved source bytes, fixed expected vectors, original source snapshot and
grading profile. No temporary Git editing staging remained. A fresh read-only
readiness check and separate final mandatory inventory passed, definitively
confirming zero containers after regression testing.

The original execution report remains unchanged. `step39_functional_summary.json`
embeds it with final closure/regression results; `step39_execution_completion.json`
and `step39_execution_regression_evidence.json` retain separate records.
Authorization is expired, no persistent execution flag is enabled, and future
candidate jobs require fresh approval. Default model, interactive controller,
six-operation budget, original fixtures and source permissions are unchanged.
The older unrelated runtime-verification anomaly remains unexplained; passing
checks in this run do not establish its historical cause.
