# Step 41: preserved normalize_tags evaluation — approval pending

Preparation/preflight only. No preserved candidate has executed. The proposed
scope is exactly **three Docker-only jobs, 12 vectors per job, 36 vectors total**,
with no task retries, source application, generated-test execution or new model
generation. Explicit user approval is required before any of these jobs.

## Exact identities and policy decisions

| Origin | Original Step 38B attempt | Exact source SHA-256 |
| --- | --- | --- |
| qwen3:4b | 2 | `9619107e7cb8bdfcfdcd02f13e19190dfcc02706c15b73487ed8b73d2674a0c5` |
| qwen2.5-coder:3b-instruct-q4_K_M | 4 | `902a186ced6c570fdb2ddf74f5f4a34ec060394afc54723e644374596f82fbca` |
| qwen2.5-coder:7b-instruct-q4_K_M | 6 | `2ab54f18c286675de6822d9364d3bf455f78a917a9db253782d1574311277207` |

All three hashes match saved final candidate snapshots, successful staging-write
records and independent final per-file hashes. No code is reconstructed from a
proposal or diff. Exact strings, original requirements, original acceptance
criteria, vectors and policy decisions are in `runs/step41_review_plan.json`; generate
the same data-only plan with `python -m evaluations.prepare_normalize_evaluation`.
Missing or inconsistent evidence blocks preparation.

For all three: **default policy rejected; explicit scoped policy accepted**.
Acceptance means supported syntax/source identity, not functional correctness.
The generated `test_tag_utils.py` modules remain excluded from execution and
grading. Step 38B's historical 4/6 static score is unchanged.

## Job-scoped opt-in

`FunctionalHarness.run('step41_normalize_tags', source,
string_scope='step41-preserved-normalize-v1')` is the proposed trusted caller API.
Without that explicit argument the task lookup fails. Unknown scope values,
other task IDs, different function contracts or changed source bytes are rejected.
The public scope string is an explicit activation parameter, **not** execution
authorization. A saved report or plan is never an execution permit.

The host and Docker worker independently recompute the UTF-8 source hash and
require the exact three-value allowlist, function `normalize_tags`, parameter
`tags` and correct scope. The worker's optional scope field is allowed only for
the fixed Step 41 task. A shared contract check also rejects missing/null scope
on that task before compilation, even if the source uses no string operations.
No global addition of normalize_tags to STRIP_FUNCTIONS,
environment switch or persistent live flag is used. The default call remains
disabled before, between and after jobs.

The Step 40 rules remain intact: exact strip/lower names, zero arguments, direct
calls, at most one of each method per consecutive chain, no aliases, dynamic
lookup, reflection or unsafe nested receiver calls. The existing exact-str runtime
guard still dispatches trusted built-in methods inside Docker. No broader Python
subset or source transformation of the preserved files is introduced; the
existing trusted worker guard transformation remains part of execution.

The new fixed host profile, scope rules, worker and harness are bound into the
grading profile hash. The canonical five tasks/29 vectors and original fixtures
are unchanged. The twelve vectors exactly match the earlier Step 39 proposed
normalize_tags checks; no expected values are replaced.

## Exact vectors for each candidate

| # | Check | Input list | Expected output |
| --- | --- | --- | --- |
| 1 | Empty | `[]` | `[]` |
| 2 | Trim/lower | `["  RED ", "Blue  "]` | `["red", "blue"]` |
| 3 | Discard empty | `["", "   ", "\t"]` | `[]` |
| 4 | Ordered deduplication | `["Blue", " red ", "BLUE", "Red", "green"]` | `["blue", "red", "green"]` |
| 5 | Input preservation | `[" Blue ", "BLUE"]` | `["blue"]` |
| 6 | New list | `["red"]` | `["red"]` |
| 7 | All whitespace | `["", " ", "\t", "\n", "\r\n"]` | `[]` |
| 8 | Interspersed empties | `[" red ", "", "\t", "BLUE", " "]` | `["red", "blue"]` |
| 9 | First occurrence, not sorting | `["b", "a", "B", "c", "a"]` | `["b", "a", "c"]` |
| 10 | Repeated normalized strings | `["MiXeD", "mixed", " MIXED "]` | `["mixed"]` |
| 11 | Unicode whitespace | `["\u2003Red\u00a0", "\tBLUE\n"]` | `["red", "blue"]` |
| 12 | Preserve internal spaces | `["red blue", "Red Blue"]` | `["red blue"]` |

Escapes denote real control/Unicode characters in decoded input. Every vector
requires exact list/element types, ordered values, input unchanged against the
host's independent copy, and a fresh returned list distinct from the supplied
list (including empty input). The worker already reports a validated boolean
identity observation; the host grader now explicitly requires it for this fixed
profile. Only source, copied arguments, function metadata and the scope marker
enter the worker. Expected values and grading assertions remain on the host.

## Preflight and proposed execution lifecycle

Review includes the actual Step 40 24/24 expected reference outcomes and 11/11
real isolation results. They are historical evidence, never a current permit.
Step 41 performs fresh bounded Docker readiness, pinned-image/runtime preflight,
all eleven fail-fast real isolation probes and definitive post-probe inventory,
without invoking any candidate. Regressions use mocked execution only.

The initial preflight script stopped before Docker activity on a static plan
comparison: an empty proposed host-mount tuple became a JSON list. The builder
now returns stable JSON data. Only the proposed plan representation is normalized;
runtime verification evidence is never normalized to make it pass. The original
diagnostic is retained as `runs/step41_preflight_serialization_error.log`.

After separate approval, verify the committed plan/profile/hashes again, recheck
readiness and run fresh in-process probes before any candidate job. Each job gets
one disposable container under the unchanged pinned image and restrictions:
network none, non-root, read-only root, dropped capabilities, no-new-privileges,
required seccomp, no host mounts/credentials/socket, 256 MiB, one CPU/CPU-second,
16 PIDs, 1 MiB bounded scratch, two-second worker timeout and 64 KiB output cap.
No expected result is sent to the candidate.

Save full responses, per-vector host comparisons, policy/compilation/runtime
status, before/after verification, source/profile hashes and cleanup evidence.
Do not retry failed jobs. Stop immediately on mandatory isolation/runtime
verification failure; keep unexecuted vectors distinct from failed assertions.
Expire authorization on completion or abort, leave the default scope off, verify
absence of owned containers, and run regressions. Do not resume an interrupted
invocation or reuse previous successes.

No functional result is claimed in preflight. In particular, unordered-set output
can vary between processes; the approved one-shot run must record its actual
values rather than rerun to obtain a preferred ordering. Passing these fixed
vectors would not establish general coding reliability or a general proof of
the normalization algorithm.

## Actual preparation results

The final full trusted suite passed **386/386 tests** in **468.284 seconds**,
including sixteen new scope/protocol/host-grading tests. The targeted suite
passed **61/61**. The initial full run passed 384 tests before the two final
missing-scope tests; its separate log is retained. During the tightening, one
mock fixture needed to retain its test-only hash patch through bootstrap
validation; that intermediate failure log is also preserved, not converted into
execution evidence.

The final-version preflight passed **11/11 fresh mandatory real probes**, verified
the approved digest-pinned image and runtime, and confirmed a definitive empty
post-probe inventory. The final read-only closure again confirmed zero containers,
no temporary Git editing staging, unchanged original source and preserved model
evidence, and default-disabled scope. **No candidate job or model request ran.**

Review artifacts under ignored `evaluations/runs/`:

- `step41_review_plan.json`: exact source strings/hashes, original requirements,
  fixed expected vectors, policy decisions and proposed three-job scope.
- `step41_review_preflight.json`: final-profile fresh probes and raw command audit.
- `step41_review_regression_evidence.json`: full final regression outcome.
- `step41_preflight_completion.json`: plan hash, final provenance/default-scope
  checks and definitive cleanup inventory.

The scoped candidate worker path has unit/mock protocol coverage; real candidate
compilation, invocation and vector grades remain pending approval. Preflight
verification does not persist an execution permit; the approved invocation must
recheck current readiness and in-process isolation/profile identity. Saved
reports cannot resume execution. Interactive code, default model, six-call
budget, original task fixtures, image/security restrictions and source-application
permissions remain unchanged. Historical unrelated runtime and staging anomalies
are not explained by this passing preflight.

## Approved Step 41 execution — 2026-10-22

The separately approved one-shot invocation completed all three preserved jobs,
with no retries or new model requests. Fresh bounded readiness, the pinned image,
all 11 mandatory real isolation probes, and pre/post-job runtime verification
passed. All 36 vectors executed exclusively through the existing Docker worker.

| Preserved candidate | Functional vectors | Entire candidate |
| --- | --- | --- |
| qwen3:4b | 12/12 | Passed |
| qwen2.5-coder:3b-instruct-q4_K_M | 7/12 | Failed |
| qwen2.5-coder:7b-instruct-q4_K_M | 7/12 | Failed |

Total: 26/36 vectors, one of three candidates passed all required vectors;
zero unexecuted vectors. All three passed scoped policy and Docker compilation.
No policy rejection, runtime error, timeout, transport error or isolation failure
was recorded. Every executed vector preserved its input and returned a fresh list.

Coder 3B uses a set and failed ordered results on one-based vectors 2, 4, 8, 9
and 11. Its actual order was retained without rerunning or changing the hash seed.
Coder 7B omits deduplication and failed vectors 4, 5, 9, 10 and 12.
These are functional assertion failures, not infrastructure failures.
Qwen3 satisfied all twelve fixed checks; this small preserved sample does not
establish general coding reliability. Historical static results remain unchanged.

Complete source identities, fixed expected values, raw worker frames, host-side
per-vector decisions, probe evidence, runtime checks, cleanup and authorization
expiry are preserved in ignored `runs/step41_functional_results.json`.
The in-process authorization expired in the invocation's finally block, and its
probe capability was invalidated. Default scoped task lookup remains disabled.
The immediate final mandatory inventory was verified and empty. No candidate,
expected output, original fixture, Docker restriction or source repository changed.

Post-execution validation: **386/386 regressions passed** in 534.781 seconds.
`runs/step41_post_execution_regression.json` and its log retain the actual suite
results. `runs/step41_execution_closure.json` confirms expired authorization,
default-disabled scope, unchanged approved plan/snapshots and original source,
no temporary editing staging, and a fresh definitive empty Docker inventory.
Only documentation changed in this completion stage; complete generated reports
remain local under ignored runs storage.
