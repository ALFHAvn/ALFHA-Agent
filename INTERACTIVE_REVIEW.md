# Step 47A: interactive structured review

Start from the project virtual environment:

```powershell
.venv\Scripts\python.exe -B main.py --review
```

Enter the absolute Git repository root, the development request, exact relative
files to read/modify (one per line, blank ends selection), then optional additional
read-only files. ALFHA displays the exact authorization and requires `yes` before
requesting one local Qwen3 proposal. Cancellation/EOF does not contact the model.
The existing command without `--review` retains its legacy behavior and tools.
The default model remains qwen3:4b. Review mode has no application or execution API.
Unknown or extra command-line flags now stop with usage text, so a misspecified
review invocation cannot fall back into the legacy tool workflow.

## Scope and behavior

- Existing tracked, clean, authorized UTF-8 text files only. Dirty unrelated user
  files stay in the source. Creation, deletion, ignored/Git-control paths, traversal,
  links, read permission omissions and ambiguous authorization fail closed.
- Controller inspection reads only the authorized files through existing isolated
  Git staging. Context includes read-only files, but the response schema exposes
  only explicitly mutable filenames. Inspection staging is discarded before the
  model request; a second isolated workspace stages the proposed edits.
- One loopback Ollama request, with a 180-second transport timeout, context 8192
  and temperature 0. No native tools, recovery, corrective generation, retries,
  default-model switch or remotely configured OLLAMA_HOST is used.
  The generation client disables proxy-environment routing and HTTP redirects.
- Exactly one raw version 2 replace_lines document. Legacy version 1 is rejected
  even though the reusable opt-in parser supports it. Existing JSON uniqueness,
  response size limit, line joining, exact target matching, six-operation budget
  and batch prevalidation are reused unchanged. Serialized request context is also
  capped at 65,536 bytes; larger tasks must be scoped explicitly, not truncated.
- Source snapshots are checked around inspection and generation and by the staging
  system. A changed source invalidates the proposal. New files in ignored source
  directories can also invalidate its inventory; `-B` avoids creating Python caches
  during this workflow. The guard is deliberately not weakened for such changes.
- Existing static validation and the combined diff are displayed. Reports identify
  missing required file changes, rejected operations, errors and incomplete work.
  Arbitrary natural-language requirements are **not** proven by these static checks.
  Validation does not establish compilation or functional correctness.
- All edits stay in disposable staging. The original repository is never updated.
  Batch argument validation occurs before writes; writes are not an OS filesystem
  transaction. A runtime write failure may leave partial staging evidence, which
  the existing owned-workspace cleanup handles without touching the source.
- Staging is discarded automatically, with complete proposed final file text,
  hashes, diff, request, response and diagnostics retained in an external temporary
  report directory. Review that report after the console closes. If cleanup cannot
  be verified, readiness is false and the report says so. Report inspection grants
  no generation, resume, application or candidate-execution authority.

## Resource readiness and serialization

Step 46 established that severe host pressure existed before the failed regression
run: Event 2004 reported 99.1% commit use, with the resident Ollama runner and WSL
among the largest consumers. Disk cleanup is not a memory-readiness check.

The new Windows preflight uses GetPerformanceInfo and a Toolhelp process census.
It samples three times, 0.2 seconds apart. Missing, inconsistent or unsupported
evidence fails closed. Thresholds are conservative pilot policy, not empirically
proven universal resource requirements:

| Phase | Minimum available physical RAM | Minimum commit headroom |
| --- | ---: | ---: |
| Before generation, including fresh check after inspection | 4 GiB | 10 GiB |
| Full regressions; post-response safety check before staging | 2 GiB | 4 GiB |

Failures report the required headroom and suggest waiting or voluntarily closing
optional applications. Nothing changes the pagefile, stops processes, unloads a
model, starts a privileged service or adjusts security settings. Even passing
samples do not reserve memory or prove sustained stability. Pressure after the
response prevents staging; the exact response remains preserved.

A nonblocking named Windows session mutex coordinates this review mode, real
DockerTransport executions and the resource-gated regression runner. A conservative
process census also rejects other Python/PyPy/pytest/ALFHA jobs (excluding this
process and its launcher ancestry). Busy, abandoned or unavailable locks fail
closed. Real Docker executions retain all existing isolation checks and options;
mock command runners used by deterministic tests perform no Docker work.

Use the full trusted suite through:

```powershell
.venv\Scripts\python.exe -B -m regression_check
```

The runner checks resources before loading/running tests, then holds the workload
lock for the suite. It includes the existing 476 tests plus the new review tests;
it does not run live benchmarks or candidate programs. Direct unittest commands
and third-party applications can ignore cooperative locking: users must not start
them alongside ALFHA work. A process can also start after a census. These controls
reduce overlap; they cannot guarantee global stability or control unrelated apps.

Static review checks Ollama API/model metadata without contacting Docker, avoiding
an unnecessary WSL wake-up. Existing dependency checks still require Docker by
default. No functional evaluation gate, image, task fixture, execution policy or
Docker restriction was relaxed. Existing live functional execution remains disabled.

## Proposed next live smoke test — not authorized

The exact proposed scope is recorded in `evaluations/step47a_smoke_plan.json`.
After review of the committed implementation, authorize at most one Qwen3 4B
generation response for a small disposable two-file task, with explicit read/modify
paths, required file changes, the existing version 2 schema and six-operation cap.
Perform fresh resource/dependency checks, keep all other ALFHA workloads idle, and
stop on unavailable evidence or a source/cleanup failure. Preserve exact payload,
response, rejected operations, diff, final source strings/hashes and resource samples.
No retry, corrective request, generated-code/test execution or source application.
Runtime tests of a preserved candidate would require another separate authorization.

No live smoke test or candidate execution is authorized by installing this code.
Future interaction by the human through the explicit CLI confirmation is a new
coding request; it is not permission for this development session to generate.

## Actual verification — 2026-10-23

- Resource-gated full suite: **504/504 passed**, 801.196 seconds. This included
  the existing 476 regressions and 28 new deterministic tests.
- Final focused suite: **34/34 passed**, 103.084 seconds, after the final CLI
  routing, root-authorization ordering and loopback-client changes. This reran
  all interactive/resource tests and added six focused checks. The complete
  updated runner now enumerates 510 distinct tests; a 510-test full run is not
  claimed. The unchanged underlying suites passed in the 504-test run.
- An initial 24-test targeted run had one mock fixture error (missing SDK message
  role); the fixture was corrected and the failure log retained.
- No live generation, generated-code/test execution, Docker integration jobs,
  model unloads or system/security configuration changes occurred. Docker-related
  regression output is from deterministic test doubles, not fresh isolation probes.
- Final read-only check passed with about 5.7 GiB available RAM and 12.3 GiB commit
  headroom. This is a later observation, not a stability guarantee or authorization.
- No owned alfha-git staging remained. Tested production source hashes matched.
  Seven preserved Step 46 evidence-file hashes were verified unchanged. The live
  functional benchmark gate remains false; original task fixtures and all Docker
  restriction values remain unchanged.

Ignored evidence: `evaluations/runs/step47a_targeted.log`,
`step47a_regression.log`, `step47a_regression_evidence.json`,
`step47a_final_focused.log`, `step47a_final_focused_evidence.json`, and
`step47a_closure.json`. Mock task sources are checked before/after each test;
production task reports are external and retained after staging discard.

Remaining limits: Windows-only readiness/exclusion, cooperative session locking,
conservative thresholds, no continuous reservation/cancellation on changing memory,
existing clean tracked files only, static validation only, no live measurement of
this interactive adapter, and no source-application feature. CLI transport timeout
is the SDK timeout, not proof of a strict whole-request wall deadline. The Step 46
resource incident is not claimed permanently fixed.

## Authorized smoke preflight and follow-up

The autonomous-development mandate authorized the prepared one-response smoke
scope. Its 2026-10-23 invocation aborted **before generation**: available RAM was
3.73 GiB and commit headroom 9.94 GiB, below the unchanged 4/10 GiB thresholds.
Zero model requests, edits, candidate executions or Docker jobs occurred. No
staging workspace was created; the fresh disposable source remained unchanged.
The source fixture and reports were retained. Authorization expired on abort;
the invocation was not retried. This leaves interactive coding usefulness untested.

Local evidence is `evaluations/runs/step47a_smoke_result.json`, with an exclusive
`step47a_smoke_consumed.json` invocation claim. A fresh smoke attempt requires new
explicit approval; a later passing resource snapshot does not resume this run.

Readiness errors now include observed RAM and commit headroom alongside required
values. **10/10 resource regression tests passed** under the regression readiness
gate and workload lock, including the new numeric-diagnostic test. No new full
suite run is claimed for this diagnostic-only follow-up. Historical full/focused
results above remain separate evidence. See `DEVELOPMENT_ROADMAP.md` for priorities
and the proposed, unimplemented source-application approval design.

### Fresh approved smoke completed after resource availability improved

A later, separately approved attempt passed the unchanged preflight and completed
one Qwen3 response in **171.875 seconds**. Its strict version 2 proposal staged two
authorized changes using **2/6 operations**, with zero rejected changes. Both files
passed AST parsing, the clamp signature was preserved, and the generated test AST
matched the expected five-assertion edge contract. The implementation uses explicit
below/above/interior branches consistent with the request on source inspection.
The test source omits a cosmetic blank line before `test_edges`; AST comparison
ignores formatting and the original assertions remain intact.

No generated Python or tests executed. No functional pass is claimed. The source
fixture bytes remained unchanged, no temporary staging remains, and authorization
expired. Full evidence and candidate hashes are in the ignored local report
`evaluations/runs/step47a_smoke_retry3_result.json`, with final inventory evidence
in `step47a_smoke_retry3_closure.json`. No regressions were rerun for this live
smoke/documentation-only update; existing test evidence above remains distinct.

Recommendation: limited review-only pilot with explicit files and human inspection;
one successful response does not establish general or repeatable coding reliability.
