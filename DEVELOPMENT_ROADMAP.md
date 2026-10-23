# ALFHA development roadmap

Updated 2026-10-23 after the autonomous-development mandate.

## Evidence and immediate priority

Review-only interactive version 2 editing is implemented at `435592f`. Its first
authorized smoke invocation stopped in resource preflight with **zero model
requests**: available physical RAM 4,005,052,416 bytes (3.73 GiB), commit headroom
10,667,978,752 bytes (9.94 GiB). Required minima remain 4 and 10 GiB. This is an
infrastructure rejection, not evidence of model or editing performance. No retry
was made. Authorization expired on abort. The disposable source remained unchanged;
no staging workspace was created. The source fixture and report are retained.

Evidence: `evaluations/runs/step47a_smoke_result.json` and the exclusive
`step47a_smoke_consumed.json` claim. These local reports are intentionally ignored
by Git. Existing Step 46 diagnostics remain untouched.

After two further separately authorized preflight rejections, a fresh attempt
approved after the owner closed applications passed readiness and completed one
Qwen3 response in 171.875 seconds. Both authorized files changed, using 2/6
operations, with no rejected edits. Both ASTs parse, the signature is preserved,
and the generated test AST matches the exact expected contract. The clamp branch
structure implements the requested comparisons on inspection; no candidate code
or tests ran. This is one static smoke success, not measured functional correctness
or repeatable reliability.

Exact response, final snapshots/hashes, diff and preflight evidence are preserved
in `evaluations/runs/step47a_smoke_retry3_result.json`. Closure evidence confirms
authorization expired, original fixture bytes match, no staging remains and live
functional execution remains disabled. Earlier failed invocations remain intact.

The workflow is suitable for a limited human-reviewed pilot with explicit file
selection and resource gating. Wider readiness is **unverified**. Static validation
does not establish functional correctness, and source application stays unavailable.

## Ordered next work

1. Completed: one explicitly approved disposable smoke response with exact test
   contract and diff inspection. No further live request is authorized.
2. Improve review usability from that evidence: show incomplete requirements,
   retain readable reports and distinguish proposal validity from task completion.
   Offline report reopening is now implemented without generation or restored
   authority. The first-party time-report pilot is prepared in `REVIEW_PILOT.md`,
   with two mutable Python files, read-only context and an independent checklist.
   Live generation remains pending separate approval. Use deterministic tests
   before considering another live sample.
3. Prepare a human-approval design for applying reviewed changes. Keep the current
   implementation review-only until that design receives separate review.
4. Introduce controlled functional verification only for supported tasks with
   separate candidate-execution approval and fresh mandatory Docker verification.
5. Consider project context and reusable skills after everyday editing is useful;
   defer autonomous self-modification.

## Proposed application approval design — not implemented

A future approval must identify the source repository, starting commit and complete
source snapshot, exact authorized paths, before/after content hashes, combined diff,
validation evidence, and a review identifier. It must bind to those exact bytes and
expire on any source change, proposal change, cancellation or use. Loading a report
must never recreate authority. Declining approval must leave all source files intact.

Before implementation, review concurrent-write protection, dirty/untracked/ignored
file preservation, partial-write recovery, and durable audit evidence. A Git commit
match alone is insufficient to detect uncommitted changes. A simple check-then-copy
has a race and is not an acceptable application design. No source-write or apply
command is authorized or supplied by this roadmap.

## Execution boundaries

Routine development, deterministic tests and local commits continue autonomously
within the current session. Live generation, candidate execution, real-project
application, system changes, downloads and remote publication require their stated
separate approvals. No automatic retry, background continuation, model-default
change, budget increase or security-policy relaxation is planned.
