# Step 29E: interrupted controlled comparison

Exactly one explicitly approved invocation was started from commit `0273fee`:

```powershell
.venv\Scripts\python.exe -m evaluations.benchmark_functional --authorize-once
```

The user reported an unexpected crash. The original process was subsequently
absent in an elevated Win32_Process query and its exec session no longer existed.
The benchmark was not resumed, repeated, or authorized persistently.

## Retained results

| Task | Retained outcome | Passed/executed vectors |
|---|---|---|
| sum_even | Passed | 5/5 |
| clamp | Generating at last checkpoint; result unknown | None recorded |
| palindrome | Not attempted | None |
| unique_order | Not attempted | None |
| count_words | Not attempted | None |

One of two started tasks has a completed passing result. There is **no overall
five-task score**. Five of five recorded executed vectors passed; 24 of the 29
planned vectors have no recorded execution. In-progress clamp activity was not
checkpointed, so it cannot be represented as known zero calls or failures.

Retained telemetry: four model requests, two native calls (read and successful
edit), zero recovered calls, zero rejected dispatched calls, zero invalid JSON
proposals, one controller retry prompt, and one successful edit. These are partial
checkpoint totals, not complete totals for the terminated process. The completed
task used two of six tool calls. No agent-initiated syntax check was recorded.

After the edit, the model received AST passed, compilation not run (Docker-only),
policy accepted, empty diagnostics, and functional tests not run. No failed tool
action or corrective diagnostic was recorded for this task, so the run provides
no evidence about whether the model corrected behavior after actionable errors.
The independently graded final candidate passed AST parsing, Docker compilation,
policy validation, container execution, and all five functional vectors.

## Security and final verification

Preflight regressions: **163/163 passed**. Standalone mandatory real Docker
probes: **11/11 passed**. The approved invocation also passed its fresh eleven
probes. All four retained outer verification boundaries were accepted (before
model, before grading, after grading for sum_even; before model for clamp).
No isolation failure is recorded. The historical verification failure remains
unexplained; this interrupted run does not resolve it.

After the crash the Docker Linux pipe was unavailable. The existing Docker
Desktop application was restarted solely to inspect cleanup. The subsequent
desktop-linux container query for `alfha.execution=security-probe` succeeded with
no containers returned. No new candidate execution occurred during recovery.
The crash's cause and any uncheckpointed activity remain unknown.

The process-local authorization expired through process termination. Its final
`finally` checkpoint was not observed: the original saved report still says
`running` and `active`. These stale data do not constitute an authorization and
were preserved unchanged. The separate interruption record documents effective
expiry without inventing a normal completion/expiry event. Default CLI execution
was actually tested and returned BLOCKED. Post-interruption regressions:
**163/163 passed**; benchmark-looking lines in those tests use test doubles and
are not additional live runs.

## Evidence and comparison

Complete retained checkpoint (ignored, not committed):
`runs/functional_live_20261020T184556886732Z.json`.
SHA-256: `3d61fd95c711c19f18b121fb9619bc1a1b646ed5f1b9d8ca1897129c56a05ab8`.
Separate recovery observations:
`runs/functional_live_20261020T184556886732Z_interruption.json`.
Standalone preflight evidence:
`runs/isolation_20261020T184100909781Z.json`.

The previous complete benchmark passed 2/5 tasks and 16/23 executed vectors,
with six vectors unexecuted. Both runs passed sum_even 5/5. This partial run
cannot establish an improvement, regression, or causal effect from Step 29D.
A fresh full comparison requires separate explicit approval; none was retried.
Interactive code, fixtures, six-call budget, and Docker restrictions were unchanged.
