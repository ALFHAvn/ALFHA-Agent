# Step 36: local model comparison plan (not yet authorized)

Starting commit: a3dc094. No new model download or live generation is authorized
by this document. The interactive agent and both existing default model values
remain qwen3:4b. No generated program or generated test will execute.

## Candidate selection

| Exact model tag | Parameters / quantization | Artifact size | Tool support | Practical tradeoff |
| --- | --- | --- | --- | --- |
| qwen3:4b | Installed 4.0B / Q4_K_M | 2,497,293,931 bytes locally | Local show confirms tools, completion, thinking | Baseline; not a coding-specific comparison candidate |
| qwen2.5-coder:3b-instruct-q4_K_M | 3.09B / Q4_K_M | Ollama lists 1.9 GB | Library advertises tools; installed tag/template must be verified | Most comfortable weight footprint; smaller capacity may limit reasoning |
| qwen2.5-coder:7b-instruct-q4_K_M | 7.62B / Q4_K_M | Ollama lists 4.7 GB | Library advertises tools; installed tag/template must be verified | More capacity, tight 6 GB VRAM headroom; CPU offload may slow generation |

Sources checked 2026-10-21:
- https://ollama.com/library/qwen2.5-coder:3b-instruct-q4_K_M
- https://ollama.com/library/qwen2.5-coder:7b-instruct-q4_K_M
- https://registry.ollama.com/library/qwen3-coder
- https://ollama.com/library/devstral-small-2/tags

These are local models without a paid API requirement. Artifact size is not peak
RAM or VRAM: context cache, runtime buffers, Windows and other applications need
additional memory. Actual fit/latency remain unmeasured. Load one model at a time;
16 GB RAM provides some offload headroom but is not a performance guarantee.
Qwen3-Coder 30B (19 GB weights) and Devstral Small 2 24B (15 GB Q4 weights)
are unsuitable first choices for this machine. The 3B coder page lists a Qwen
research license; the 7B page lists Apache 2.0. They are not identical licenses.
No model has been downloaded in this milestone; local inventory contains only
qwen3:4b, digest 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7.

## Fixed scenarios

A: disposable clean Git source containing only syntax_target.py, UTF-8/LF:

```python
def add_one(value)
    return value + 1
```

Exact description:

> Fix the missing colon after def add_one(value) in syntax_target.py. Preserve the function name, value parameter, and return value + 1 body. Use actual tools to inspect and edit the authorized file. Do not execute the module or tests. Only read/modify syntax_target.py. Six tool-call attempts total. Static checks only; finish with a concise summary.

Authorization: syntax_target.py = [read, modify]; required_changed_files contains
only that path. Independent acceptance requires the exact corrected source
`def add_one(value):\n    return value + 1\n`, successful AST parsing, a recorded
edit, unchanged source snapshot and successful staging discard. This exact text
criterion is intentionally narrow; it does not test functional correctness.

B: use the request description, two initial file texts and original static
acceptance criteria preserved in evaluations/runs/step35_preparation.json and
step33_preparation.json. Do not rewrite the description or examples. Create
fresh disposable fixture repositories with identical file bytes; only the
absolute source_repository path changes. Authorized files remain tag_utils.py
and test_tag_utils.py, each [read, modify], both required to change. Before any
live request compare fixture hashes and description/criteria with preserved
Step 33 evidence; absence or mismatch blocks execution. Original evidence and
source fixture repository remain untouched.

For BOTH scenarios and ALL models:
- Existing tools, exact argument schemas, filename enums and dispatcher.
- Six calls, including rejected calls and recovered proposals; no budget reset.
- tool_policy = {inspection_first: true, single_json_recovery: true}.
- Existing single corrective prompt and existing response bound; no task retry.
- validation_requirements = {static: true, docker_execution: false}.
- Same system/controller prompts and scenario description across models.
- Static text/AST checks only; no candidate imports, compilation execution,
  generated tests, Docker execution or source application.

## Proposed execution and approval scope

Before any approved attempt, run the read-only dependency preflight for all
three tags and preserve its report. Missing dependencies block the comparison;
do not install, start services, or infer authorization from readiness. Each task
also checks its selected model and Docker/image in the workflow before staging.
See DEPENDENCY_PREFLIGHT.md for bounds and infrastructure failure reporting.

Approval is required separately for downloading the two exact candidate tags
(approximately 6.6 GB combined listed artifacts) and for six live attempts:
qwen3 A, qwen3 B, coder 3B A, coder 3B B, coder 7B A, coder 7B B, in that order.
Each is fresh staging and one task attempt. No warm-up generation, replacement
model, silent retry or extra calibration attempt. A transport/runtime interruption
is preserved as partial evidence, never replaced with a fresh attempt.

After approved downloads, inspect local model metadata and tool templates without
generation. Record full installed digests, quantization, capabilities, Ollama
version and server settings. Missing native tools or incompatible templates block
that candidate; do not silently substitute a text-only adapter. Reconfirm approval
if any exact tag or plan needs changing.

The workflow now accepts an explicit model keyword for only these three tags,
records that tag, and passes it unchanged to chat. It does not pull models or
create an authorization gate. Calling run_task remains a live request when no
mock is injected: do not invoke it without the separate user approval.

Use the same comparison-only chat adapter options for every model: num_ctx=8192,
temperature=0, seed=36, stream=false. Do not modify workflow/interactive defaults.
Retain model templates, stop tokens and architecture-specific defaults; record
these differences and thinking behavior as confounders. No per-model prompt or
controller tuning. Context overflow is an observed failure, not permission to
increase context. The fixed order and single sample cannot establish causality.

## Evidence and independent review

Before each attempt save a unique launch marker, exact request, source snapshot,
fixture hashes, model digest and settings under ignored evaluations/runs/.
Archive the complete retained workflow report after each attempt, including
responses, native and recovered calls, rejected batches/actions, text proposal
classifications, successful edits, corrective prompts, budget and combined diff.
Keep in-progress/unknown outcomes distinct from completed ones. Do not resume
from a saved report or reuse historical successful results.

Reconstruct candidate text from initial fixtures plus accepted exact edits;
match final per-file hashes in the review report. Independently inspect every
original criterion for B, including prescribed tests and no input mutation.
Record criterion true/false/unknown with evidence; AST validity alone never proves
normalization semantics, test effectiveness or functional correctness.

Comparison table columns: model/digest, scenario, authorized files changed,
criteria met and static task completion, native calls, recovered calls, invalid
text proposals, rejected/unauthorized actions, successful edits, budget, AST
results, workflow status, cleanup and source snapshot equality. Report functional
correctness as not tested. Preserve full evidence even for zero edits.

Record wall time plus response total_duration/load_duration/prompt_eval_count/
eval_count where supplied. Sample Ollama ps RAM/VRAM and nvidia-smi only when
available; label observations as samples, not proven peaks. Mark unavailable
measurements unknown. Loading/offload/order/thinking differences affect latency.

After each attempt confirm source unchanged and owned staging discarded. Stop
on protection/cleanup failures; do not automatically delete unknown directories.
Run the established regression suite afterward and archive its actual log.
Reports and temporary fixtures are not committed. Only validated infrastructure
and documentation changes are committed.

## Current findings and recommendation

Step 33 had printed multi-proposal JSON and zero dispatched calls. Step 35
produced native calls but spent its six-call budget on two authorized and four
unauthorized reads, with no edits. Thus the adapter can receive native calls;
these traces do not isolate whether model choice or task complexity dominates.
Controller protections correctly rejected unauthorized reads. Single-proposal
recovery cannot safely execute either response's multi-proposal arrays.

Keep qwen3:4b as the unchanged default pending measurement. Test the 3B coder
first as the resource-conservative alternative, with 7B as the capacity contrast.
Do not recommend a permanent switch or planning/coding split from unmeasured
performance. Future controller work should follow specific traces, especially
budget wasted on unauthorized batches; do not weaken rejection or refund calls.
Even six completed attempts provide descriptive results, not repeatable reliability
or proof of general software-development competence.

## Validation in this milestone

269/269 trusted regressions passed in 269.639 seconds, including two new tests
for selected-tag routing, accurate model reporting, unchanged default, identical
mocked requests across all three tags, source preservation, staging cleanup and
rejection of unsupported model values before staging/chat. No live model
request, download, generated program/test execution or fresh Docker security
probe occurred. Runtime benchmark results and resource measurements remain
pending approval. The regression log is evaluations/runs/step36_regression.log.

## Approved execution results

The subsequently approved six-attempt comparison is complete. See
[LOCAL_MODEL_RESULTS.md](LOCAL_MODEL_RESULTS.md) for exact downloads, Resource
Saver diagnosis, all six failures, independent static assessment and retained
JSON evidence. All six authorized attempts are consumed; this historical plan
and its pending status are not permission to rerun them.
