# Step 25 evaluation controller

Run the authorized test suite:

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller

Run the live local model benchmark (Ollama must be running):

    .venv\Scripts\python.exe evaluations/evaluate_agent.py

The controller copies each case into an owned TemporaryDirectory and loads a private
instance of the trusted main module. It never changes main.WORKSPACE. Only exact
read_workspace_file, edit_workspace_file, and check_python_syntax argument schemas
are allowed, and filename must equal the current case basename. Initially valid
files cannot be edited. Existing atomic editing and unique-match checks are reused.

One JSON edit proposal may be recovered per initially invalid case. Only a complete
JSON object with exactly name and arguments is accepted, optionally fenced with
```json. Duplicate keys, extra prose, extra fields, unsupported tools, and argument
coercion are rejected. Recovery shares the six-call budget with real calls. Invalid
parsed proposals consume a call; rejected JSON parsing consumes the recovery attempt.

Every successful edit receives an independent AST syntax check; a final independent
check runs even after budget exhaustion or a model exception. The report preserves
agent verification separately from controller verification, records call origins,
recovery outcomes, successful edits, and verification stages. Passing requires final
valid syntax, no controller/model error, and a successful modifying edit for an
initially invalid case; initially valid cases must remain byte-identical. Controller
verification can satisfy this syntax benchmark without an agent verification call.
This benchmark does not measure functional correctness. Generated cases are never
executed or imported. The interactive controller in main.py is unchanged.

Validation: 20 tests passed (10 original, 10 controller tests, with 17 invalid proposal
subcases). Initial sandbox test run hit Windows access-denied errors during atomic
replacement in temporary directories; approved execution outside the sandbox passed.
No new live Ollama score is claimed by these deterministic regression tests.

## Step 26 reliability benchmark

Run `.venv\Scripts\python.exe evaluations/benchmark_reliability.py` from the
project root. This calls the unchanged Step 25 controller for the existing three
cases, sequentially, five times. Ollama must be running with qwen3:4b installed.
It adds no model options, timeout, transport retry, or prompt changes. Each attempt
gets a fresh disposable workspace and the existing six-call budget.

The timestamped consolidated JSON under evaluations/runs is checkpointed after
every attempt. It contains all controller fields, raw Ollama responses (including
thinking and tool arguments), elapsed times, retries, and per-case/overall rates.
Reports and local server logs are ignored by Git.

`tool_calls` and `average_model_tool_calls` count dispatched native requests plus
parsed JSON recovery calls, including calls rejected by validation. They are the
budget units used by Step 25. Native requested counts also include unexecuted
over-budget batches. Native dispatched counts and recovered JSON counts are
recorded separately. Model requests count chat requests, including failed requests.
Controller AST checks consume none of that model tool budget.

Retry prompts count additional controller system prompts actually sent to Ollama.
Rejected recovery attempts include ordinary prose that Step 25 tries to parse;
this alone does not indicate a fake JSON tool proposal. JSON proposal observations
flag text containing JSON name/arguments/filename/old_text/new_text keys or a JSON fence; validation errors
are retained with response indexes. Unique-match/edit errors remain in the tool
trace and invalid-dispatched-call counts. Raw responses allow review of proposals
that fall outside this deliberately simple reporting heuristic. These telemetry
checks do not dispatch calls or change controller decisions.

The Step 26 live run completed all 15 attempts: 12 passed (80%). Indentation:
4/5, parenthesis: 3/5, valid code: 5/5. Repetition scores: 3/3, 2/3, 2/3,
3/3, 2/3. Average budgeted calls: 2.67 (38 native calls plus 2 JSON recovery
dispatches across 15 attempts); native-only average: 2.53. One recovery edited
successfully; the other failed its exact text match. Both agent and final controller
verification passed in 12 attempts. There were 7 successful edits, 7 retry prompts,
6 rejected dispatched calls, and 5 structurally invalid JSON proposal responses.
All 15 final AST results are retained. Total case duration was about 22.7 minutes.

Failures were repetition 2 parenthesis (unsupported JSON and text function-call
wrappers; no tools executed), repetition 3 parenthesis (hallucinated search text,
literal newline escapes, and missing filename; all six calls used), and repetition
5 indentation (bare edit argument JSON after reading; no edit executed). The
largest observed reliability problem remains translating a repair into a real,
correctly formed tool call with exact matching edit text. These are syntax-only
results, not functional correctness results.

The local Ollama server was initially stopped and was started before measurement.
No model/controller settings changed between attempts and none were rerun. Bare
argument proposal telemetry was recomputed from saved responses after completion;
this changed reporting classification only. Pre-run: 20 tests passed. Post-run:
25 tests passed, including the original 20 and five reporting tests. The generated
JSON is intentionally untracked under evaluations/runs.

## Step 27 functional tasks

See [FUNCTIONAL.md](FUNCTIONAL.md) for the five-task, 29-vector framework,
non-executing validation command, isolation gate, report semantics and full test
command. Existing syntax evaluations remain unchanged.

## Step 28 execution interface

See [EXECUTION_SETUP.md](EXECUTION_SETUP.md) for the fail-closed backend interface,
Windows/WSL/Docker findings, manual installation instructions and required runtime
security tests. No candidate execution or live functional benchmark is enabled.

## Step 28C controlled Docker transport

See [DOCKER_TRANSPORT.md](DOCKER_TRANSPORT.md) for the pinned image, real transport,
actual behavioral security probes and tests. Run explicit controlled verification
with `python -m evaluations.verify_docker_isolation`. The live gate stays closed.

## Step 28D offline functional worker

See [FUNCTIONAL_WORKER.md](FUNCTIONAL_WORKER.md) for the restricted worker, structured
protocol, host grading, per-vector results and offline Docker integration command.
The live model gate remains closed.
