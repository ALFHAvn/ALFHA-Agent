# Step 38 live comparison: blocked before generation

The user authorized the six prepared attempts at commit `2801a68`. The mandatory
readiness gate failed on 2026-10-21, before any model-generation request.

The existing three-second read-only preflight passed Ollama API availability,
all three installed model identities/capabilities, Docker Linux engine metadata,
and the approved digest-pinned image. Evidence: `runs/step38_live_preflight.json`.

The separate engine-dependent all-container inventory command was:

```text
docker --context desktop-linux ps -a --no-trunc --format "{{json .}}"
```

It timed out at 3.0 seconds, returned exit code 1, and produced empty stdout and
stderr. Capture was not truncated and no I/O threads remained unfinished. Full
arguments and transport evidence are in `runs/step38_initial_inventory.json`,
embedded in `runs/step38_live_comparison.json`.

Empty output from this timed-out command is **not** evidence that the inventory
was empty. Container cleanup status is unknown. The inventory check was not
retried, no service was started, and no timeout or security requirement changed.
Docker Resource Saver caused a previous readiness delay, but no current evidence
establishes the cause of this timeout. Passing metadata does not override it.

| Model | Syntax repair | Two-file task |
| --- | --- | --- |
| qwen3:4b | Not attempted | Not attempted |
| qwen2.5-coder:3b-instruct-q4_K_M | Not attempted | Not attempted |
| qwen2.5-coder:7b-instruct-q4_K_M | Not attempted | Not attempted |

Attempts consumed: **0/6**. There were no proposals, generation timings, model
tool calls, staging edits, or task outcomes. The comparison score is unavailable;
these are not six failed coding attempts. Step 36's historical 0/2 tasks per
model remains the only completed three-model comparison. No conclusion about
structured-editing model performance can be drawn.

The retained original source snapshot matched exactly, and no `alfha-git-*`
staging directories remained when the blocked-run report was saved. This run
created no candidate staging or execution containers. Generated programs and
tests did not execute. Interactive/default-model settings and source repositories
were unchanged. Authorization ended on the blocked invocation; no persistent live
execution was enabled. A future invocation needs fresh explicit authorization
and a successful unchanged readiness gate.

The complete blocked report and regression evidence remain under ignored
`evaluations/runs/`; they are not committed. No historical evidence was modified.

After the blocked gate, **327/327 trusted regression tests passed** in 383.365
seconds. The suite used mocked model/Docker execution; its benchmark-like log
messages are not live attempts. No failures or errors were captured. The original
source snapshot still matched after regression testing, and no temporary
`alfha-git-*` staging directories remained. Container inventory was not repeated
and remains unknown. No passing test resolves the historical runtime-verification
anomaly or the historical intermittent staging failures.
