# Step 29B: proposed single-run authorization

Status: **one explicitly approved benchmark completed**, using commit 915ccc1.
The one-run permit expired. Default API/CLI execution remains disabled. Another
run requires separate approval. The historical verification failure remains
unresolved and did not recur in this run.

Only after approval, the exact operator command is:

    .venv\Scripts\python.exe -m evaluations.benchmark_functional --authorize-once

Without that flag the CLI exits before contacting Ollama. The API requires a
OneRunAuthorization instance; LIVE_EVALUATION_ENABLED remains False and cannot
be used as a blanket authorization. The flag is an operator acknowledgement of
the separately obtained human approval, not a cryptographic approval service.
The model cannot access the host-side CLI, permit object or grading API.

The explicit invocation creates one in-memory permit, with a random run ID. It
binds to one harness instance, the current protected source hashes, qwen3:4b, the
fixed six-call budget, the approved digest-pinned Docker backend, and fingerprints
of the original five task specifications/29 vectors and all starter fixtures.
Each task must occur in canonical order, once for model generation and once for
independent grading. Unknown/repeated tasks, altered fixtures, a changed budget,
changed code or a different backend/image invalidate the permit.

The benchmark still reruns all mandatory security probes in process, checks
verification before model generation, before grading and after grading, and
inherits the worker's verification before/after each execution. Saved reports
never authorize execution. No Docker policy, resource limit, task fixture,
interactive-agent permission, model default or recovery schema is changed.

The permit is consumed by one run and marked expired in finally on success,
abort, interruption or reporting failure. Process termination destroys it too.
There is no authorization file, environment switch, resumable report, persistent
enablement, task retry or automatic inspection retry. A second invocation needs
another explicit approval. Controller retry prompts within the existing six-call
workflow remain unchanged and are reported separately from task retries.

Isolation rejection, missing evidence, model/controller errors and runtime,
serialization, timeout or grading-integrity errors stop the suite. Ordinary
wrong return values or static policy rejection fail the task without retry.
The original full verification evidence and partial results are checkpointed.
Incomplete suites have no overall five-task score.

Pre-approval validation: **138/138 regressions passed**, including seven new
authorization tests for expiry/reuse, bound task/fixture/image scope, duplicate
or out-of-order use, cross-harness use, controller/runtime failures and reporting
failure. Model and transport calls in these tests are test doubles.

Fresh real mandatory security checks: **11/11 passed**, recorded in ignored
evaluations/runs/isolation_20261020T170846061753Z.json. They confirmed the local
Linux engine and approved Python image; they did not execute model-generated code.

## Actual authorized results

Exactly one invocation of the command above was made after the user's explicit
approval. No task was rerun, and no previous successful result was reused.
Complete ignored JSON report:
evaluations/runs/functional_live_20261020T171451704939Z.json.

| Task | Outcome | Passed/executed vectors | Native calls | Successful edits |
|---|---|---|---|---|
| sum_even | Passed | 5/5 | 2 | 1 |
| clamp | Failed; starter unchanged | 2/7 | 2 | 0 |
| palindrome | Static policy rejection | 0 executed; 6 not run | 3 | 1 |
| unique_order | Failed; starter unchanged | 3/5 | 6 | 0 |
| count_words | Passed | 6/6 | 3 | 1 |

**2/5 attempted tasks passed (40%)**. **16/23 executed vectors passed**. All five
tasks were attempted; no tasks remain unattempted. Six of the 29 planned vectors
were not executed because palindrome's candidate was rejected before execution.
They are not presented as executed assertion failures.

Telemetry: 25 model requests, 16 requested/dispatched native tool calls, zero
recovered JSON calls, three failed native tool actions, one invalid JSON proposal,
five established controller retry prompts, and three successful edits. Average
tool use was 3.2 calls/task; the largest was six. There were no task retries,
isolation retries or rejected oversized tool-call batches.

clamp read its source twice and later printed a valid edit proposal without using
the actual tool interface. The single recovery opportunity had already been
consumed on an earlier non-JSON response, so this later proposal was not applied.
unique_order's two edit attempts used literal backslash-n text that did not match
the real newlines, correctly producing "Text not found" without changing files.
count_words initially supplied content instead of old_text/new_text; this action
was rejected, then a subsequent valid edit produced the passing final candidate.

palindrome's edit placed a return statement at module scope and used unsupported
filter/call structure. It was rejected by the existing static policy and was
never executed. An interim commentary described an extra helper function; the
retained candidate confirms the actual issues above. No fixture/profile was
changed to admit this candidate.

The controller reported five successful final AST parses and two agent-initiated
syntax checks. These counters retain their existing meanings: ast.parse can
accept a module-level return even though compilation would reject it. Thus these
are **not five independently established compilable programs**. The policy
rejection and Docker-only trusted grading remain decisive. Syntax alone does
not establish functional correctness.

All four executed candidate jobs exited normally with validated observations and
verified removal. There were no candidate runtime errors, execution timeouts,
malformed grading streams or failed cleanup. All **15/15** outer verification
boundaries passed; full current verification evidence is retained, along with
the worker's verification and raw container/cleanup evidence. The run's fresh
mandatory probes passed **11/11**. No isolation anomaly was recorded; this does
not explain or resolve the historical intermittent failure.

Final authorization state is expired (run ID cd7fd85c277a4c51ada502149a94d5e1),
with persistent=False. LIVE_EVALUATION_ENABLED remains False and the default CLI
was checked and refused execution. An independent final Docker query found no
evaluation containers. Protected implementation/fixture hashes were unchanged
throughout the run, and **138/138 post-run regressions passed**. Those regression
tests use test doubles and did not invoke an additional live model benchmark.

No implementation changes were made after the approved run. This is one small,
fixed pure-function benchmark, not evidence of general development competence.
The remaining reliability issues are applied tool use, exact editing arguments
and generating code within the established function profile. Addressing them
requires a separate milestone, not alteration or repetition of this benchmark.
