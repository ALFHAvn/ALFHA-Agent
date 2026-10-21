# Read-only dependency preflight

This preflight is readiness evidence, not execution authorization, a model
attempt, or proof of container isolation. It never calls chat/generate/pull,
creates containers, starts services, installs software, changes settings or
runs candidate code. No previously completed evaluation is rerun.
This work consumes zero live attempts and does not expand the user's existing
six-attempt limit for Step 36. Missing models are not downloaded implicitly.

## Current evidence and historical limits

The metadata-only check for all three Step 36 tags found:

| Dependency | Actual result |
| --- | --- |
| Ollama loopback API | Passed |
| qwen3:4b metadata, native-tool capability and template | Passed |
| qwen2.5-coder:3b-instruct-q4_K_M | Failed: model_missing |
| qwen2.5-coder:7b-instruct-q4_K_M | Failed: model_missing |
| Local desktop-linux engine and existing required capabilities | Passed |
| Approved digest-pinned Linux/amd64 image | Passed |
| Combined readiness | Failed closed; no model request |

Bounded raw metadata and timestamps are retained in ignored
`evaluations/runs/step36_dependency_preflight_final.json`. These results describe that
instant, not uninterrupted service availability or behavioral isolation tests.
Each preflight invocation queries the model inventory once, without internal
retries. Three separate metadata-only development checks were made while the
deadline/incomplete-response handling was hardened; all found the same two
missing models. These were not live evaluation attempts or downloads.

A subsequent separate read-only `docker ps -a --filter name=alfha-eval-`
inventory timed out at its 3-second deadline, returning code 1, empty stdout/
stderr, complete pipe teardown and no output truncation. It was not retried.
The full tool result was transcribed into ignored
`runs/step36_container_inventory_timeout.json`, explicitly marked as recorded
after observation. Container inventory is unknown, not an empty passing result.
No containers were created in this milestone. The timeout does not identify
Docker startup, CLI latency, engine availability or another root cause, and
does not establish a cause for the historical verification anomaly. Live
evaluations remain unattempted; a future approved attempt requires fresh checks.

Step 33 received a real model response with six printed proposals. Step 35
received two model responses and six native calls: two authorized reads and
four unauthorized reads. Their saved errors are controller authorization
rejections, not startup/connection errors. Neither evaluation required Docker
execution. No saved evidence establishes dependency startup as their cause.

The Step 29 runtime boundary failure remains unresolved: the exact failed
operation/object was absent from the historical report. Later healthy metadata
cannot fill that gap. Step 29E's interruption has recorded Codex desktop/process
crash events, incomplete Ollama log coverage, and no established trigger; it
cannot be attributed to Ollama or Docker startup. See RUNTIME_DIAGNOSIS.md and
CRASH_RESILIENCE.md. Original reports are not rewritten or reclassified.

Verified unchanged SHA-256 evidence:
- Step 33 workflow: 267c44e796f90625901cffef44930022cc2a0ff8b7321eca0d863941a56c560c
- Step 35 workflow: e116c837f105d144f3eda33b955a6e704721e90ba97363aaa7c8913f2a57de59
- Interrupted Step 29E: 3d61fd95c711c19f18b121fb9619bc1a1b646ed5f1b9d8ca1897129c56a05ab8

## Usage and integration

Metadata only (exit 0 ready; exit 2 unavailable/incompatible):

```powershell
.venv\Scripts\python.exe -m evaluations.dependency_preflight --model qwen3:4b
```

Repeat `--model` for up to three distinct explicit tags to check a complete
comparison plan. The CLI prints JSON; it does not start an evaluation.

`coding_workflow.run_task` checks the selected model plus Docker/image before
creating staging or contacting the model, including when a caller supplies a
chat adapter. Tests explicitly mock readiness; supplying chat_fn does not bypass
preflight. A blocker returns a retained `preflight_failed` report with
`failure_domain=infrastructure`, zero model requests, zero budget use and no
staging. The functional benchmark CLI uses the same checks after its existing
explicit authorization switch and before claiming one-run authorization. Its
in-process harness still requires all existing isolation verification.

The Step 36 plan requires this all-model preflight before its first attempt,
then the workflow performs fresh selected-model preflight per task. A saved
passing report is not accepted as authorization or a cached health guarantee.
Preflight failure does not silently replace, retry, or increase approved task
attempts. Preserve any partial report and stop for operator review.

Report separation:
- `dependency_preflight`: required dependencies, per-check statuses, timestamps,
  model digests/capabilities/template, Docker raw metadata audit and failure data.
- `failure_domain=infrastructure`: preflight blocker or later recognized model
  transport/API failure. `model_request_failure` retains exception type/message.
- `failure_domain=model_adapter`: other exceptions raised by a supplied adapter;
  these are not assumed to prove an Ollama outage.
- `failure_domain=model_tool_use_or_completion`: rejected tool actions or an
  incomplete/exhausted model exchange, with the original trace retained.
- Static validation and source integrity remain in the existing review fields.
  A domain identifies an observed failure layer, not a definitive root cause;
  rejected calls can occur in an otherwise completed exchange.

Unknown generation outcomes remain unknown after a connection loss. No request
is retried and no tool budget is refunded. Required dependency failures never
enter model-failure scores as if a completed attempt had produced bad code.
Aggregate comparisons must present not-started/partial rows separately.

## Bounds and fail-closed behavior

Ollama uses fixed http://127.0.0.1:11434, no inherited proxy/OLLAMA_HOST, and no
redirect following. Only GET /api/tags and POST /api/show are allowed. Each
request shares one 3-second deadline across connection, headers and body,
including repeated socket reads from slowly arriving responses. Metadata
is limited to 1 MiB, with duplicate JSON keys, non-finite numbers, invalid
schemas, truncated HTTP bodies, missing digests and incompatible tool/template evidence rejected.
No inference is performed to test model loading or tool competence.

Docker uses the existing transport's context/engine/image policy validation:
local Linux endpoint, Linux/amd64, cgroup v2, CPU/memory/swap/PID controls,
builtin seccomp, exact approved digest and safe image configuration. The wrapper
allows only the three fixed read-only metadata commands, limits each subprocess
to 3 seconds and preserves bounded stdout/stderr, status and I/O diagnostics.
The existing transport adds bounded process/pipe teardown (up to 2 seconds for
process wait and up to three 1-second thread joins). No readiness retries occur.
Missing image evidence is distinct from a ready engine; unreadable engine
metadata leaves image readiness not_checked, never passed.

Metadata readiness does not prove memory/process/network isolation behavior or
that the next request will succeed. Existing mandatory isolation probes and
per-container effective policy/identity verification remain unchanged. A later
mismatch still stops execution. No Docker restrictions, interactive controller,
six-call budget, fixtures, default model or execution gates were weakened.

## Regression coverage

Deterministic tests cover API refusal/timeouts, absent models, malformed and
ambiguous metadata, output/deadline limits, missing Docker, daemon failures,
Windows/remote engines, unsupported capabilities, missing/wrong image, exact
read-only CLI operations, no retries, workflow blocking before staging, retained
zero-attempt reports, later model connection loss, authorization rejections and
functional CLI blockers before authorization or model-client creation.


## Final validation

292/292 trusted regression tests passed in 276.223 seconds, including all 23
new preflight tests. The final log is ignored
`evaluations/runs/step36_preflight_regression_final.log`; the final targeted
23-test log is `evaluations/runs/dependency_preflight_tests.log`. All model and
Docker execution paths in those tests use test doubles; real Git tests use
owned disposable repositories. No live model attempt, candidate program/test,
image download, behavioral isolation probe or source application was run.

The original Step 33/35 source snapshot and recorded workflow-report hashes were
rechecked unchanged. No service, privilege, security-setting or model-default
change was made. The separate real container-inventory timeout remains a
recorded infrastructure failure with unknown inventory, not a passing check.
