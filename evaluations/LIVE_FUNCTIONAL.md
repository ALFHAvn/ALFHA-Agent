# Step 29: single-pass live functional benchmark

**Step 29A status:** live evaluation is disabled pending a separate review of
the unresolved runtime-verification failure. The API and CLI reject live runs
before accessing Ollama. See [runtime diagnosis](RUNTIME_DIAGNOSIS.md). The
description and results below document the historical Step 29 implementation/run.

Run the explicit, gated benchmark from the project root:

    .venv\Scripts\python.exe -m evaluations.benchmark_functional

This command calls the installed qwen3:4b model, using the existing functional
controller unchanged. It attempts each of the five canonical tasks once, with
the existing six-tool-call budget, recovery rules and model defaults. Controller
retry prompts are recorded; tasks are never automatically rerun. The model gets
read/edit/syntax tools only. It receives neither expected results nor functional
grading feedback. Its prompt prohibits executing files; independent grading
happens after its final candidate is collected.

The existing static CLI and generic backend execute() remain blocked. This
dedicated entry point uses the Step 28D worker API, with fresh in-process evidence
from all 11 mandatory isolation probes before any model request. The approved
digest-pinned image must already be installed; there is no automatic image pull.
Policy, transport, worker protocol, trusted grading and all 29 vectors are
unchanged. Candidate code is parsed on the host and executed only in restricted
Docker containers. Expected results, reports and canonical fixtures stay on the
host, outside the candidate tool workspace and container.

Reports are atomically checkpointed to ignored evaluations/runs/functional_live_*.json,
including an in-progress record before each model attempt. No report is silently
resumed. The report retains final candidate text as data, model responses, call
traces, recoveries/rejections, retries, edits, separate agent/controller syntax
verification, worker observations and host per-vector grades. Nested worker
model_invoked=False means the grader itself makes no model requests; the outer
task records actual model invocation. Candidate files live in disposable
directories; generated reports and source are not committed.
Verification results at each boundary include their exact reason, and remaining
unattempted tasks are listed explicitly. The CLI pins Ollama to localhost rather
than inheriting a remote OLLAMA_HOST. Interruptions retain a partial checkpoint.

Task success requires all its vectors to pass the existing host grading rules.
Policy rejections fail the task without running its vectors. Ordinary incorrect
values, runtime exceptions and timeouts are recorded without retry. Execution or
grading-integrity failures stop the suite, retain partial results and leave the
overall success rate null. vectors_executed counts validated completed result
frames, not merely planned tests. Not-run vectors are reported separately.

Hashes before/after cover the interactive controller, syntax evaluator, functional
controller, policy, worker, harness, transport and fixtures. Runtime identity is
rechecked between tasks and by the harness before/after execution. The existing
forced removal and independent absence verification apply to every container.

Regression command (no real model/candidate execution):

    .venv\Scripts\python.exe -m unittest -q test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport test_functional_worker test_functional_benchmark

The small fixed suite measures these five pure-function tasks, not general
software-development competence. The restricted AST/built-in profile remains
deliberately narrow; broadening it requires a separate integrity review. Passing
the probes is evidence for the tested configuration and behavior, not proof
against every container or Python vulnerability.

## First actual run: incomplete, stopped safely

Local report: evaluations/runs/functional_live_20261020T163242781596Z.json.
Consolidated evidence, including explicit not-attempted rows for all remaining
tasks and post-run diagnostics:
evaluations/runs/functional_live_20261020T163242781596Z_consolidated.json.
Model: qwen3:4b, Q4_K_M, digest
359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7.
Ollama was confirmed at http://127.0.0.1:11434. The installed service was started;
no image/model download, policy change or software installation was needed.
Docker Linux engine 29.9.1 and the approved image were verified by fresh probes.

| Task | Functional result | Passed/executed vectors | Model tool calls |
|---|---|---|---|
| sum_even | Failed; starter unchanged | 2/5 | 1 |
| clamp | Passed | 7/7 | 3 |
| palindrome | Not attempted | 0 executed; 6 planned | — |
| unique_order | Not attempted | 0 executed; 5 planned | — |
| count_words | Not attempted | 0 executed; 6 planned | — |

Observed: **1/2 attempted tasks passed**, **9/12 executed vectors passed**.
The full suite contains 29 vectors; **17 were not run**. The report correctly
leaves overall five-task success rate null. This is not a completed five-task
benchmark, and unexecuted vectors are not presented as tested failures.

The two attempts used four native tool calls, no recovered JSON calls, no invalid
dispatched calls, two invalid JSON proposals, two controller retry prompts, eight
model requests and one successful edit. Average tool calls: 2 per attempted task.
Both final sources passed independent syntax verification; only clamp received
agent-initiated syntax verification. Both candidate executions exited normally,
had validated grading streams and verified container removal; there were no
candidate runtime errors, timeouts or malformed grading results in these attempts.

sum_even read its source but proposed a plain object containing filename,
old_text and new_text, without the required name/arguments wrapper. It was
classified as an invalid proposal and never executed. The controller's single
recovery opportunity had already been consumed by an earlier non-JSON response;
even if attempted, the final object would fail the existing strict schema.
No edit occurred; the
unchanged starter passed only empty-list and all-even vectors. This shows the
remaining model tool-use problem: describing a correct repair does not apply it.

Immediately after clamp's successful independent grading, an additional runtime
verification returned an unacceptable result. The runner stopped with
"Execution verification lost after grading" before requesting the third task.
The original version did not persist that particular verification object, so its
precise cause is **unknown**. No host compromise or changed identity is established
by this generic failure. The validated grades remain partial observations.

Follow-up diagnostic report: evaluations/runs/step29_postrun_diagnostics.json.
Twenty read-only Docker metadata checks matched the recorded identity, with no
transport failures. An independent container query returned no evaluation
containers. These later checks neither explain the earlier failure nor authorize
resuming the interrupted suite. The original benchmark report was preserved;
no task was retried and no remaining task was run after verification failed.

Post-run reporting improvements retain the full verification object at each
boundary, explicitly enumerate unattempted tasks and pin the CLI's model endpoint
to localhost (matching the endpoint independently verified for the actual run).
They were regression-tested without another live benchmark.

Next milestone: investigate the intermittent metadata/verification failure using
the new boundary evidence, then authorize a fresh complete single-pass benchmark.
Keep isolation fail-closed and address model tool-call reliability separately;
do not broaden recovery schemas based on this one failure.

Final validation: **112/112 regression tests passed** (101 existing plus 11 new
orchestration tests). The fresh real isolation checks passed **11/11** before the
model ran. The baseline 19 worker integration checks were not rerun in this
milestone; the two live candidates were actually graded through Docker. Protected
source/fixture hashes were unchanged throughout the live attempt.
