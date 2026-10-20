# Step 28D: offline worker and trusted host grading

The five existing tasks and 29 vectors are unchanged. This milestone adds an
explicit offline API and reviewed integration cases, without calling Ollama or
enabling live evaluation. DockerExecutionBackend.execute and --live remain blocked.
The interactive agent, syntax evaluator and six-call model budget are unchanged.

## Boundary and supported language

functional_harness.py runs on the host. It retains expected outcomes, builds
requests, validates observations and computes assertions/scores. Expected values,
grading code, reports, fixtures, credentials and host paths are never sent/mounted
into the container. The candidate has no way through its tool interface to change
the request or Docker options.

functional_worker.py is read as text, never imported or called on Windows. A
trusted bootstrap carries an escaped JSON literal over bounded stdin. It repeats
the existing AST validation and compiles/executes source only inside Docker.
A platform/UID/container guard rejects accidental invocation on Windows.

Candidates are limited to the existing pure-function AST profile. Each vector
gets fresh function globals and copied JSON arguments. Candidate globals contain
only approved pure built-ins, not worker functions/modules/locals or the request.
Full built-ins are not supplied: sum=eval raises NameError. Imports, introspection,
dunder access, decorators, print and dynamic execution remain unsupported. See
[Python exec namespaces](https://docs.python.org/3.12/library/functions.html#exec).

The whitelist is not claimed as a general Python sandbox. The profile, isolated
namespace, plain-data inputs and verified Docker restrictions are used together.
This is not an arbitrary-Python execution service. The observation stream is
validated, not cryptographically authenticated. Expanding the language profile
requires reviewing grading integrity as well as kernel isolation.

## Protocol v1

Input fields are exactly version, request_id, task_id, function, parameters, source
and vectors. request_id is UUID hex. Each vector contains only args, copied from
the canonical manifest; expected results/assertions are excluded. The worker plus
escaped request must fit the existing 100,000-byte input cap. Candidate quotes
cannot escape the payload literal.

Output is strictly ordered newline-delimited JSON:

1. start with matching version/request_id/task_id.
2. vector_start with sequential integer index.
3. vector_result with index/status/value/args_after/new_list/error.
4. Repeat starts/results, then end with the exact count.

Result status is returned, runtime_error or result_error. Compilation failure emits
a terminal job_error after the header. The host rejects unknown/duplicate fields,
bool-as-index/version, non-finite JSON, bad ordering/counts, mismatched job IDs,
missing frames, extra stdout and any stderr. No passed/score/expected fields from
the worker are accepted. Results must be plain JSON, depth <=16, <=4096 structural
nodes, strings <=4096 UTF-8 bytes and integers <=4096 bits. Objects, sets, tuples,
generators and cycles cannot be successful observations. No pickle/eval is used
to interpret results on the host.

Only the host compares exact types/values, unchanged arguments and the new-list
identity requirement for unique_order. Printed grading claims never become grades.

## Lifecycle and reporting

FunctionalHarness.prepare() explicitly reruns all 11 real isolation checks.
run(task_id, source) refuses execution without current in-process verification and
an unchanged profile hash covering harness, worker, policy, manifest and fixtures.
Runtime/image/policy/transport identity is checked before/after each job. Persisted
reports are evidence, never permits. No auto-pull or live enablement flag is added.

Each whole task uses one fresh container and the unchanged limits: 2 seconds wall,
1 second CPU, 256 MiB/no extra swap, 16 PIDs, bounded scratch and 64 KiB shared
stdout/stderr. Budgets are not multiplied per vector. Existing metadata/cleanup
deadlines remain separate; all errors inherit forced removal/absence checking.
There are no project, fixture, socket or credential mounts.

grade_candidate_offline(task_id, source, harness) bridges results to the existing
assessment fields, preserving vectors/assertions. Reports distinguish static
syntax/policy, candidate/function changes, execution, vector results and scores.
Statuses distinguish blocked, policy_rejected, passed, failed, runtime_error,
result_error, timeout, malformed_result, unexpected_output, output_limit and
execution_error. CPU/resource termination records its actual exit status; it is
not mislabeled as a wall timeout. executed counts complete result frames;
attempted counts starts. Interrupted/later vectors are marked interrupted/not_run.
Only validated complete observations receive credit. Failed cleanup or malformed
output produces no score. Otherwise score is passed_count/planned.

## Reproduce checks

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport test_functional_worker

Run explicit offline Docker integration (fresh isolation checks run first):

    .venv\Scripts\python.exe -m evaluations.verify_functional_worker

Integration covers five correct references/all 29 vectors, incorrect returns,
exceptions, a loop requiring actual started/termination evidence, input mutation,
grading-print rejection, an eval alias, unsupported return types, compile errors,
forged frames, extra stdout/stderr, after-end claims, wall timeout and output flood.
Corrupted wire programs are trusted diagnostics run inside Docker; they go through
the same host validator. Reports are checkpointed under ignored
evaluations/runs/worker_integration_*.json.

Step 28D actual validation: **101/101 regressions passed** (80 existing plus 21 new),
**19/19 isolated integration checks passed**, all **29/29 reference vectors passed**,
and fresh **11/11 isolation probes passed**. Final local report:
worker_integration_20261020T161934596628Z.json. An independent Docker query found no
remaining ALFHA controlled-execution containers. These are reviewed reference and
failure fixtures, not Qwen3 performance results. No model request was made.

These are finite tests, not proof of general functional correctness or immunity to
runtime/kernel vulnerabilities. Live Qwen3 evaluation remains a separate milestone.
