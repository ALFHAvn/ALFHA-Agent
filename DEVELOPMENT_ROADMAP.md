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

The workflow is a guarded pilot; wider readiness is **unverified**. Historical
version 2 success does not establish reliability of this interactive integration.
Static validation does not establish functional correctness.

## Ordered next work

1. Complete one fresh, explicitly approved disposable smoke request when resource
   readiness passes. Reuse the fixed smoke fixtures, one response, six operations,
   no retries or candidate execution. Inspect the exact test contract and diff.
2. Improve review usability from that evidence: show incomplete requirements,
   retain readable reports and distinguish proposal validity from task completion.
   Use deterministic tests before considering another live sample.
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
