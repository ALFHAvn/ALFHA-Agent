# Step 27: functional evaluation framework

For Step 28D's offline worker and actual host grading, see
[FUNCTIONAL_WORKER.md](FUNCTIONAL_WORKER.md). Live Qwen3 evaluation is still disabled.

See [DOCKER_TRANSPORT.md](DOCKER_TRANSPORT.md) for the later Step 28C controlled
Docker transport and actual isolation probes. Live functional evaluation remains
disabled in this stage.

Step 28 adds a disabled backend interface and evaluator integration. See
[EXECUTION_SETUP.md](EXECUTION_SETUP.md) for actual prerequisite findings, manual
installation instructions and the remaining runtime verification work. The
non-executing behavior below remains the production default.

This stage defines behavior tasks and an evaluation controller, but **does not
execute fixture or candidate Python**. Functional correctness remains unmeasured
until an execution backend is implemented and its isolation verified.

## Tasks

The trusted functional_cases/tasks.json contains five instructions, exact function
signatures, and 29 JSON input/output vectors. Each starter is syntax-valid with a
logic bug. This directory is separate from syntax cases/ and normal workspace/.

| Task | Required behavior | Vectors |
| --- | --- | ---: |
| sum_even | Sum even integers, including negatives; empty returns zero | 5 |
| clamp | Clamp an integer to an inclusive interval | 7 |
| palindrome | Ignore case and ASCII non-alphanumeric characters | 6 |
| unique_order | Deduplicate integers in first-appearance order | 5 |
| count_words | Count case-sensitive whitespace-separated tokens | 6 |

Future execution must compare value and type, verify unchanged arguments, and check
that unique_order returns a new list. Vectors are data, not Python snippets. The
model cannot read/edit the manifest: only its current candidate is authorized.

## Non-executing mode

Run from the project root:

    .venv\Scripts\python.exe -m evaluations.evaluate_functional

This validates the five starters and writes a new timestamped report under
evaluations/runs/functional_static_*.json. It makes no model requests. Existing
syntax/reliability reports are untouched. --live writes a blocked report and exits
with code 2 before any model request. There is no unsafe execution override.

The programmatic one_functional_case(task_id, chat_fn=...) controller is exercised
with explicitly injected offline model test doubles. It copies one starter into an
owned TemporaryDirectory and loads the trusted main module privately. It never
imports candidate code. Only read/edit/syntax tools are exposed. Functional tasks
authorize editing syntax-valid starters; the syntax controller is unchanged.
The six-call budget, complete-batch rejection, bounded response iterations, exact
filename/argument checks, unique-match atomic edits and one strict JSON recovery
are retained. Recovery dispatches consume the same budget as native calls.

Reports separate text change and target-function AST change from confirmed
behavior; agent syntax checks from controller checks after edits and at completion;
native requests/dispatched calls from JSON recoveries; invalid calls/proposals,
retry prompts actually sent, budget use and remaining budget. Raw model responses,
candidate source and before/after hashes are retained for injected-controller tests.
Functional tests have status not_run, executed=0 and passed=null. Overall pass and
requested-change confirmation remain null. A changed function is only a candidate
change; it cannot confirm behavior without functional tests.

Static validation checks signatures and conservatively rejects imports, file,
network, process and dynamic calls, dunder access, top-level actions, decorators,
defaults, annotations and unsupported constructs. Source bytes/AST nodes are bounded.
**This policy is diagnostic, not a sandbox or proof of correctness.** Passing code
is never run. syntax_valid denotes AST parsing, consistent with the existing tools,
not successful compilation/execution. Comments alone do not change the target AST.

## Execution limitation

Step 27 inspection found no Docker/Podman on PATH; wsl --status reported WSL is not
installed. No verified backend with network denial and resource limits was available.
Temporary directories, subprocess timeouts, Python isolated mode, AST inspection,
and the development shell sandbox do not establish the required execution controls.

isolation_status() always reports verified=false and execution_enabled=false.
Discovery is evidence only: installing Docker later cannot enable execution.
No execution controls are claimed as enforced. Generated code, including malicious
regression candidates, is only read, edited, hashed and parsed. No live Qwen3
functional benchmark has run; no functional success rate may be claimed.

## Validation and next milestone

Run all regression tests:

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation

Step 27 validation: all 45 tests passed (25 existing plus 20 new). The static CLI
also completed: five starters parsed, zero functional tests executed, no functional
success rate reported. No live Qwen3 functional benchmark was run.

Next implement and verify a disposable execution backend. A proposed initial policy
is non-root Linux, no network/host secrets/broad host mounts, an immutable trusted
harness, read-only candidate, bounded scratch space, 256 MiB memory, one CPU with
one second CPU time, two seconds wall time, 16 processes and 64 KiB captured output.
These are future requirements, not active limits. The parent must bound output
while reading, kill the entire process tree and clean up after timeouts/crashes.
The model must not control the harness or execution command.

Before opening the live gate, trusted adversarial probes must demonstrate network
denial, host-file isolation, blocked process escapes, memory/CPU/process/output
limits and timeout cleanup. Verify the harness against trusted correct/incorrect
references before scoring model outputs. Runtime availability alone is insufficient.
