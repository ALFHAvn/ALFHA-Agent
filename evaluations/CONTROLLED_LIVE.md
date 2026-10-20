# Step 29B: proposed single-run authorization

Status: preflight complete; **awaiting explicit human approval**. No live model
benchmark has run in this milestone. The default API/CLI gate remains disabled.
The unexplained historical verification failure remains unresolved.

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

After approval and the one live attempt, the final review must confirm expiration,
default CLI rejection, no remaining evaluation containers, full regressions, and
record actual benchmark outcomes. This document must then be updated with those
results; preflight evidence is not a functional benchmark score.
