# Step 42 — structured coding reliability preparation

This is a preparation-only benchmark. Neither this document, its JSON plan nor
an offline assessment grants permission to contact a model or execute a candidate.
The interactive agent, qwen3:4b default, six-operation limit, existing functional
fixtures, string scope, Docker policy and source-application permissions are unchanged.

## Exact proposed attempts

Use only installed `qwen3:4b`. Twelve fresh, separately approved generation
attempts, in this fixed order:

| Round / seed | Attempt order |
| --- | --- |
| 1 / 42 | syntax, even_sum, bounds, stable_unique |
| 2 / 43 | syntax, even_sum, bounds, stable_unique |
| 3 / 44 | syntax, even_sum, bounds, stable_unique |

Each attempt starts from pristine byte-identical fixtures in its own disposable
Git source and isolated editing workspace. No candidate or response is reused.
One raw JSON response, temperature 0, context 8192, no thinking override, no native
tools, no corrective prompts, no text salvage, no retries. At most six operations;
one exact replacement per authorized existing file. Validate the entire batch
before any write. Strict duplicate-key/field/type/path/match/size checks remain
those of `proposal_protocol`. Runtime staging failures preserve partial evidence.
Transport errors consume the attempt and are reported separately from model
proposal failures. Infrastructure, integrity or cleanup failure aborts the run;
unknown inventory never means clean. An interrupted run is not resumed.

`step42_plan.json` contains all twelve exact Ollama payloads, schemas, initial
file bytes/hashes, host acceptance contracts and functional vectors. Reproduce
it offline with `python -m evaluations.structured_reliability`. The module has
no network/model adapter, candidate execution call or authorization switch.

## Tasks and independent acceptance

| Task | Exact authorized files (read/modify only) | Static acceptance | Docker profile / vectors |
| --- | --- | --- | --- |
| syntax | add_one.py | Exact missing-colon repair; preserve signature/body/newline | step39_add_one / 6 |
| even_sum | sum_even.py | Module changed, AST parses, signature preserved | sum_even / 5 |
| bounds | clamp.py, test_clamp.py | Both changed, module signature/AST, complete required test AST | clamp / 7 |
| stable_unique | unique_order.py, test_unique_order.py | Both changed, module signature/AST, complete required test AST | unique_order / 5 |

Numeric requirements include negatives, zero, empty input, inclusive boundaries,
equal bounds, duplicates, order, fresh-list identity and input preservation.
The host uses existing independently defined fixed vectors, not generated tests.
Original canonical tasks/29 vectors are not modified. All exact expected values
are reviewable in the plan. Only requirements and initial authorized source text
enter prompts; host reference implementations and grading data do not.

Test-file acceptance compares the entire AST with the explicitly requested test
contract: formatting may differ, but removed assertions, shadowing, skip markers
or extra top-level code fail. These generated files are never imported or run.
Module structural acceptance intentionally does not judge algorithm semantics.
A changed, parseable but incorrect function may pass static criteria and must be
reported as functionally unknown until independently graded. This separates
interface/editing reliability from functional correctness rather than guessing it.

## Proposed Docker execution scope — requires separate explicit authorization

Maximum twelve jobs, one final retained implementation module per generation
attempt, against its fixed profile: 23 vectors per round, **69 total**. Only
policy-accepted, hash-recorded final sources may run. Rejected or missing sources
have unexecuted vectors, not invented failures or successes. No reference source
substitution or reconstruction from a diff. No generated test modules execute.
No new string policy or general Python support is required or enabled.

Use only the existing pinned image and host grader. Fresh 11 mandatory isolation
probes and current profile/image/runtime identity must pass before any candidate;
verify runtime and cleanup on each job. Stop on missing, inconsistent or failed
isolation evidence. Do not retry failed checks or jobs. Expected answers remain
host-side. Record raw observations, policy decisions, compilation, timeout,
runtime/transport/protocol errors and per-vector host grades independently.
This preparation provides a reviewed scope, not a newly enabled live runner.
The approved-stage orchestration must bind retained candidate hashes and runtime
results to exact attempt IDs before executing; no saved plan/report is a permit.

Unchanged limits per disposable container: 256 MiB memory/no extra swap, one CPU,
one CPU-second, 16 PIDs, two-second worker deadline, 1 MiB scratch, 64 KiB shared
output. Network none, non-root, read-only root, all capabilities dropped,
no-new-privileges, required seccomp, no host mounts/socket/credentials.
At most one job runs at once. GPU is used only by Ollama, not candidate containers.
The model previously fit the 6 GB GPU; actual residency is measured, not assumed.
Generation has a 180-second HTTP client timeout per attempt (up to 36 minutes
of client waiting across twelve attempts, not a hard process-wide deadline).
Candidate worker deadlines total at most 24 seconds; Docker/probe overhead is
additional and platform-dependent. No downloads, service starts or setting changes.

## Reporting, persistence and analysis

`assess_response(task_id, disposable_source, raw_response)` accepts data only,
verifies exact fixture bytes, uses existing isolated staging and writes an atomic
assessment next to the complete retained staging report. It retains full response,
accepted/rejected operations, budget, final sources/hashes, combined diff, static
checks, source snapshot equality, cleanup, assessment elapsed time and explicit
functional-not-run fields. It never executes or imports candidate code.
Model-response time is null here: the future approved live caller must measure
it separately rather than confusing editing time with generation time.

The live-stage report must checkpoint response/transport failure before parsing,
and retain pending/running/completed/interrupted task states using existing
crash-safe infrastructure. Authorization must expire on completion or abort;
checkpoint loading cannot recreate it. Use bounded dependency readiness and a
separate definitive clean inventory before consuming attempts, and final inventory.
Do not run a live trial just to validate preparation.

`summarize` rejects duplicate, unknown and mismatched attempt IDs. It reports
static success rates over known static outcomes, attempted/unattempted counts, and per-task rates. Interrupted outcomes remain explicitly unknown and are excluded from the known-outcome rate.
Functional success has a separate denominator (executed vectors and fully graded
tasks), with policy-rejected/unexecuted vectors retained. No functional rate is
computed from static reports. Future functional reporting must use actual host
grades; it cannot accept model claims as outcomes.

Three rounds give three observations per task, not strong statistical evidence.
Temperature zero may repeat outputs; different seeds do not guarantee independent
samples. Report numerator/denominator and per-round outcomes, avoid causal claims,
and do not compare these varied tasks directly to Step 38B's two-task percentage.

## Preparation validation

Deterministic tests cover stable plans, strict schemas, repeated payloads, fixed
vectors, static false positives distinguished from semantics, missing/invalid
files, incorrect test contracts, partial summaries, duplicate attempts and actual
one/two-file staging with supplied responses. Rejected unauthorized, nonmatching,
malformed and over-budget batches cannot edit files. No live model generation,
candidate code, generated tests or Docker execution is performed by these tests.


Preparation validation: **408/408 regressions passed** in 541.492 seconds,
including 22 new Step 42 tests. The first targeted run found a missing-fixture
exception diagnostic; it failed closed before staging and was fixed to return
SafetyError with the missing filename. Its focused check passed. The earlier
full run loaded before that fix retains its one error separately; the corrected
full run has zero failures/errors. Failure evidence was not overwritten.

Final plan/builder equality, unchanged original Step 33 source snapshot, and no
remaining temporary editing staging were confirmed. No live requests, candidate
jobs, generated-test execution, downloads or Docker execution occurred in this
preparation. Live readiness/security checks remain required after approval.
Reports are local under ignored `runs/step42_*`; only fixtures, plan, offline
reporting implementation, deterministic tests and this document are committed.

## Approved generation trial — 2026-10-23

Exactly twelve fresh requests ran under the separately approved c43a446 plan.
All completed; zero requests were retried and zero cases were unattempted.
Bounded Docker readiness, pinned-image/Linux metadata, model identity and each
mandatory inventory passed. These were read-only dependency checks, not fresh
behavioral isolation probes or permission to execute code. No Docker worker,
generated module or generated test ran. The authorization expired on completion.

| Task | Round 1 | Round 2 | Round 3 | Static completion |
| --- | --- | --- | --- | --- |
| syntax | Pass | Pass | Pass | 3/3 |
| even_sum | Pass | Pass | Pass | 3/3 |
| bounds | Rejected batch | Rejected batch | Rejected batch | 0/3 |
| stable_unique | Test contract failed | Test contract failed | Test contract failed | 0/3 |

Static total: **6/12 (50%)**. All twelve responses were parseable JSON documents;
nine proposals passed contextual authorization/exact-edit validation and three
were rejected. Eighteen operations were declared and charged (never more than
two per attempt); twelve edits actually staged and six operations were rejected.
No unauthorized paths/operations, native calls, recovery calls, transport errors
or safety/infrastructure failures were observed. Exact full responses, thinking
and timing metadata, accepted/rejected operations, per-file AST checks, combined
diffs, final file text/hashes and source snapshots remain in ignored run reports.

All three bounds responses decoded to replacement strings containing literal
backslash-n sequences rather than newline characters. Both old-text strings had
zero matches. Whole-batch validation correctly staged neither file; no text was
repaired automatically and the unexecuted replacement proposals were not promoted
to candidates. All three stable_unique responses changed both files and passed
AST/signature checks but used `assert result != values` instead of the requested
`assert result is not values`. Unequal contents do not test object identity.
The original test contract was retained and all three were marked incomplete.

The same module hashes repeated across seeds 42/43/44. This is a small correlated
sample with task-specific outcomes, not evidence of general coding reliability.
Static completion does not prove functional correctness. These four varied tasks
are not directly comparable to the historical two-task Step 38B percentage.

## Retained candidates and proposed separate functional approval

`runs/step42_candidate_execution_review.json` contains exact final sources,
full hashes, per-origin snapshots, host vectors and policy decisions. It is data,
not a permit. Nine staged module candidates are accepted by the current unchanged
restricted policy; no string scope is requested. Their three distinct SHA-256s are:

| Task / origins | Exact module SHA-256 | Jobs / vectors |
| --- | --- | --- |
| syntax, rounds 1–3 | `eb03dcb53008b66099f4a3324d5335b3cf0a3e93fefc7836afbb6a9eb88cfbdd` | 3 / 18 |
| even_sum, rounds 1–3 | `e3493c685415619db281dea7561ef574c2e00abe1db30c8f229afce28400dc47` | 3 / 15 |
| stable_unique, rounds 1–3 | `c7fec2319dc636218ddca64a330630cd9879d71700c252cf95b5813da7a00271` | 3 / 15 |

Proposed scope: **nine Docker-only jobs, 48 fixed vectors**, one job per retained
origin, not one per unique hash. Failed static test-file contracts remain failed;
functional grading would concern only preserved implementation modules. The three
unchanged clamp modules and their 21 original planned vectors are excluded from
this proposed execution scope. Their unchanged snapshots are still retained.
No candidate is reconstructed from proposed text or diffs. No repairs, new model
requests, generated test execution, policy expansion or source application.

Separate explicit authorization is required. Before any such jobs, re-verify
hashes/profile/image and all eleven fresh mandatory behavioral probes; stop on
any missing or failed isolation evidence, never retry jobs or failed checks.
Keep all existing container restrictions, timeouts, limits and host-side grading.
Default live candidate execution stays disabled. Full functional results remain
unknown; no vectors have executed in this generation-only trial.

Review evidence: `runs/step42_live_results.json`, `step42_live_analysis.json`,
`step42_failure_details.json`, per-attempt response/candidate JSON snapshots and
`step42_candidate_execution_review.json`. These generated reports remain local
and ignored by Git; the documentation records the actual outcome.

Post-trial validation: **408/408 trusted regressions passed** in 558.169 seconds.
`runs/step42_post_live_regression_evidence.json` and its log preserve actual
results. `runs/step42_live_closure.json` verifies generation authorization expired,
all twelve final snapshots/hashes, unchanged plan/functional profile and original
source repositories, no temporary editing staging, and a fresh verified empty
container inventory. Candidate jobs executed: **zero**. Default candidate
execution/source application remain disabled; no interactive/default-model,
fixture, controller, operation-budget or Docker-policy implementation changed.
The proposed nine-job review is still pending separate approval. Only these
validated results and the scope/hash table are committed in this completion.
