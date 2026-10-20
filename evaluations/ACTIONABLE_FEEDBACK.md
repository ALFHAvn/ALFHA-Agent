# Step 29D: actionable evaluation feedback and verification stages

The interactive agent, six-call budget, syntax evaluator, five fixtures/29 vectors,
Docker transport and fixed isolation limits are unchanged. No live Qwen3 run is
part of this milestone. Default live execution remains disabled.

## Tool feedback

Only the functional evaluation dispatcher enriches responses. The original strict
argument validator still decides which calls may reach the registered tools.
Missing/unexpected/non-string arguments are diagnosed without coercion:

    Error: Invalid tool arguments. Missing: old_text, new_text; Unexpected: "content". Required string fields: filename, old_text, new_text. No action performed.

Exact-match editing still requires one occurrence. Zero matches retain the
original error prefix and advise copying exact authorized file text. A detected
literal backslash+n in an unmatched replacement receives a targeted explanation:

    Literal backslash+n detected; this is not an actual newline. Do not double-escape JSON newlines. No automatic conversion was made.

Multiple matches advise adding surrounding context to identify one occurrence.
Consecutive failed edits are counted in the feedback, which recommends correcting
the arguments/match. No automatic unescaping, indentation repair, fuzzy matching,
extra read-tool call or extra model retry is introduced. Every dispatched action, including
rejected ones, still consumes the existing tool budget.

After a successful edit, and after an authorized syntax check, bounded JSON
feedback reports AST parsing, policy acceptance/rejection, current diagnostics,
and that compilation/functionality have not been checked by those tools. It
contains no vectors, expected outputs or grading results. Source-derived messages
are quoted as untrusted data. The full host-side diagnostics remain in the report.

For the recorded palindrome failure, feedback now names the top-level return and
unsupported filter call. A single function plus a top-level statement no longer
produces the misleading extra-function message. Actual nested/extra functions
remain rejected. The accepted AST/call/method sets and acceptance conditions are
unchanged; these are diagnostic changes, not an expanded Python subset.

## Reporting compatibility

Existing syntax_valid and verified_by_agent retain their AST-parser meanings.
Existing passed, score, status, functional_tests and policy fields retain their
semantics. Trace entries add raw_result for the original registered-tool or
argument-validator response; result contains the enriched feedback seen by the
model. Consumers comparing result to an exact old string should use raw_result
or the existing explicit verification booleans instead. Success/error prefixes
remain compatible with controller accounting.

Assessments and graded results add verification_stages:

| Stage | Meaning |
|---|---|
| ast_parsing | Host AST-only parsing passed/failed; no candidate bytecode compilation or invocation |
| compilation | Observed Docker compilation passed/failed, or explicitly not_run/unknown/not_observed |
| policy | Existing restricted Python contract/subset accepted/rejected |
| docker_execution | Container execution/transport evidence; candidate_invocation_attempted is based on validated worker vector-start frames |
| functional_tests | Independent host grading of observed vectors; not_run and not_observed are distinct |

passed=None means no positive/negative conclusion is established. A malformed or
missing stream cannot establish that a candidate never executed. A verification
failure cannot establish compilation success. docker_execution.passed refers to
container completion/exit/cleanup/stream metadata, not correct return values; a
wrong candidate can complete normally and fail functional assertions.

The existing functional worker protocol is unchanged. Its job_error is emitted
only from its compilation exception handler, so compilation failures add
failure_kind=compilation_error while preserving legacy status=execution_error.
Reaching a validated vector_start establishes that this trusted worker previously
completed compilation; it does not prove successful candidate return. Raw streams
and transport/verification evidence remain available.

## Compilation without execution

An explicit trusted API is available after fresh in-process security preparation:

    worker = FunctionalHarness()
    verification = worker.prepare()
    diagnostic = worker.compile_only(task_id, source)

This is not a model tool, a new CLI execution flag, or an automatic check attached
to every edit. The model's file/parse tools do not call it. Without this explicit
Docker evidence, compilation remains not_run in their feedback/reports.

The host reads compilation_worker.py as text and escapes its source request as a
JSON literal. The worker verifies Linux/container/non-root identity and only
calls compile(source, '<candidate>', 'exec'); it never executes the compiled
object, imports the candidate, calls its function, or writes candidate bytecode.
Only the verified pinned backend can run it, using unchanged network/mount,
CPU/memory/PID, root filesystem, scratch, output and timeout/cleanup restrictions.
Both runtime identity and the compiler/profile source hashes are checked.

Policy-rejected source may be compiled for diagnosis, but compile_only has no
candidate-invocation or vector path. In contrast, FunctionalHarness.run still
rejects that source before candidate execution. A successful compile does not
override policy, authorize execution, or count as a functional pass.

Compiler observations require an exact schema, matching job/task/version,
bounded output, empty stderr, valid exit/timeout metadata, current verification
and confirmed cleanup. Unknown fields, booleans masquerading as exit/version
integers, malformed/extra output or incomplete evidence fail closed. There is no
new inspection retry or execution retry.

## Verification

The 19 new deterministic tests cover missing/wrong arguments, corrected calls,
literal newlines, repeated failures, ambiguous matches, actual policy feedback,
top-level return versus extra functions, parser/compiler separation, invalid
compiler schemas, verification loss, legacy compile-error reporting, functional
failures after successful compilation, and missing evidence. They use test doubles
and never invoke generated candidate code on the host.

Full regression command:

    .venv\Scripts\python.exe -m unittest -q test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport test_functional_worker test_functional_benchmark test_runtime_diagnosis test_actionable_feedback

Controlled real Docker integration command, with fresh 11-probe verification:

    .venv\Scripts\python.exe -m evaluations.verify_functional_worker

It retains the 19 existing integration checks and adds six compile-only cases:
valid source, top-level return, break outside a loop, parse error, unsupported
filter, and a module-level raise that must never run. These distinguish policy
rejection from compilation failure without granting rejected source execution.

The historical functional benchmark remains 2/5. These tests do not establish
improved Qwen3 performance; measurement requires a separately approved live run.
The earlier intermittent runtime-verification failure remains unresolved.

Final actual results: **163/163 regressions passed**, **25/25 controlled Docker
integration checks passed**, **29/29 reference vectors passed**, and fresh
**11/11 mandatory isolation probes passed**. Final integration evidence is saved
under ignored evaluations/runs/worker_integration_20261020T183113077401Z.json.
An independent final Docker query found no evaluation containers. Live execution
remains disabled. The earlier development integration pass also passed 25/25;
the named final report validates the final stage-reporting implementation.
