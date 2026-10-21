# Step 36: approved local coding model comparison

All six approved task attempts finished. **0/6 tasks met static acceptance;
0/9 required file slots changed.** No task was retried. No generated program or
generated test executed; functional correctness remains untested.

## Downloads and identity

Only the two approved tags were downloaded. Ollama reported digest verification
and successful manifest installation for both. Local inventory/show metadata:

| Model | Artifact bytes | Quantization | Full installed manifest digest |
| --- | ---: | --- | --- |
| qwen3:4b (unchanged baseline) | 2497293931 | Q4_K_M | 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7 |
| qwen2.5-coder:3b-instruct-q4_K_M | 1929912626 | Q4_K_M | f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225 |
| qwen2.5-coder:7b-instruct-q4_K_M | 4683087561 | Q4_K_M | dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364 |

All three advertise completion/tools and have tool-aware templates. Qwen3 also
advertises thinking; both coders advertise insert. Capability metadata did not
predict successful native tool use by the coder models in these tasks.
The read-only local version endpoint reported Ollama 0.40.6; Docker reported
Desktop 4.96.0 and Linux Engine 29.9.1.

The first download monitor encountered a null progress counter and stopped.
Its failed journal was retained; the monitor was corrected and downloads resumed
with a separate journal. A local report reader also needed explicit UTF-8 for
model-template text; that failed before dependency/model checks. Neither issue
was a model coding attempt or a model failure.

## Docker inventory diagnosis

The original three-second inventory timeout was reproduced during read-only
diagnosis. Version, context and info succeeded, but the first filtered inventory
query timed out. Subsequent explicit diagnostic queries completed in about
0.25 seconds and returned no containers. One comparison query had a ten-second
diagnostic limit but finished in 0.25 seconds: the actual readiness/cleanup
limits remained three seconds throughout, with no internal retry added.

Docker Desktop logs supply a mechanism for the earlier inventory failure:
- At 04:23:35.064702400 UTC, a containers/json request changed Resource Saver
  from idle to busy and started its VM.
- The engine reached running at 04:23:39.724118500 UTC; VM-start completion was
  logged at 04:23:39.728492900, about 4.66 seconds after the request.
- At 04:28:39.904024600 UTC the five-minute idle timer expired. The engine stopped
  at 04:28:40.462076700, overlapping this stage's reproduced inventory timeout.

These observations support Resource Saver wake-up/shutdown transitions as the
inventory timeout mechanism. Cached metadata availability is not proof that an
engine-dependent inventory request can finish within three seconds. They do
**not** resolve the separate historical Step 29 isolation-verification anomaly.
No Docker/WSL/service/security setting was changed or explicit start command
issued. Docker's own read-only-request-triggered VM resume is visible in its logs.

## Readiness and fixed conditions

All three models passed fresh required metadata checks before live generation.
Docker Linux/amd64, cgroup v2, resource capabilities, builtin seccomp and the
approved pinned image passed existing validation. An independent, successful
unfiltered all-container inventory confirmed no containers before launch.

Pinned image remained:
`python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d`.
No containers or candidate execution were needed for this static comparison.

The tracked step36_plan.json remained unchanged. Scenario A was the single
missing-colon edit; B reused the original description, fixture bytes, per-file
authorization and acceptance criteria from Steps 33/35. Every attempt used fresh
isolated Git staging, inspection_first=true, single_json_recovery=true, the same
tools/authorization, six-call budget, one bounded corrective prompt, and
num_ctx=8192, temperature=0, seed=36, stream=false. The local SDK adapter used
a uniform 180-second HTTP timeout; no request timed out.

Automatic approval review rejected a proposed extra generation-API unload call
before its command executed. No attempt began from that rejected invocation.
The revised runner made only approved chat requests; no unload/generate request
or residency-setting change was made. Ollama managed residency normally and
samples were recorded. There was only one model in each post-response sample.
An exclusive launch marker and retained output prevent automatic restart.

## Actual task results

A = syntax repair; B = original two-file normalize_tags task. Malformed proposals
are counted by **model response**, not by counting objects inside rejected text.
Calls below are dispatched native/recovered calls; rejected text consumes no
model tool-call budget.

| Model | Scenario | Changed / required | Native | Recovered | Budget | Malformed proposal responses | Corrective prompts | Candidate AST | Wall seconds |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- | ---: |
| qwen3:4b | A | 0/1 | 6 | 0 | 6/6 | 0 | 0 | Fails | 91.81 |
| qwen3:4b | B | 0/2 | 6 | 0 | 6/6 | 0 | 0 | Both pass | 56.55 |
| coder 3B | A | 0/1 | 0 | 0 | 0/6 | 2 | 1 | Fails | 43.00 |
| coder 3B | B | 0/2 | 0 | 0 | 0/6 | 1 | 1 | Both pass | 11.16 |
| coder 7B | A | 0/1 | 0 | 1 | 1/6 | 0 | 1 | Fails | 20.30 |
| coder 7B | B | 0/2 | 0 | 0 | 0/6 | 2 | 1 | Both pass | 31.64 |

Each model completed **0/2 tasks**. Total: 11 model requests within six task
attempts, 12 native calls, one successful recovered read, 13/36 tool-call slots
used (mean 2.17/attempt), zero successful edits, zero rejected dispatched actions
and zero unauthorized dispatched calls. Five malformed proposal responses were
not executed. Two additional valid single proposals in 7B A were not dispatched
because its one recovery had already been consumed. Four corrective prompts were
issued across the coder attempts. No infrastructure/runtime failure occurred
during any of the six live tasks.

Every reconstructed final file matched both its initial fixture and the final
review SHA-256. Each A fixture remained syntactically invalid. Each B fixture
retained normalize_tags(tags), return list(tags), and test_returns_new_list;
normalization logic and all four required added tests were absent. Thus passing
AST checks on B are baseline validity, not successful coding or functional proof.
All combined diffs are empty. Criteria and traces remain separately recorded.

## Confirmed failure mechanisms

Qwen3 returned six native reads in one response for each task. A read the same
file six times; B read each file three times. All were authorized and executed.
The budget expired without an edit or another model turn. This confirms the
native adapter can dispatch calls, while action selection and inspection-phase
batching failed to advance the task. It does not prove a particular prompt phrase
caused the repeated reads.

Coder 3B printed fenced JSON, including unsupported modify_file/content proposals.
In B it then claimed completion without any applied changes. These were not
native calls or eligible single-object recovery; no edits occurred.

Coder 7B A printed a raw valid read object, which used its single allowed recovery.
Its next raw edit object contained the exact requested corrected source, but
was not a native call and the recovery grant was already consumed. Corrective
feedback elicited another printed read instead of a native edit. In B it printed
concatenated multiple proposals, unsupported modify_file calls and a completion
claim, then repeated them after correction. The strict rejection was intentional;
there was no authorization expansion or ambiguous multi-proposal execution.

The simple task failed for all three models, so task complexity alone does not
explain these outcomes. The immediate bottleneck is reliable conversion of model
intent into authorized edits, through different action-selection/protocol failure
patterns. These six observations cannot isolate causal percentages or establish
repeatable model reliability. Algorithmic competence was not functionally tested.

## Resource observations and recommendation

| Model | Ollama-reported loaded size | Ollama-reported VRAM | Context |
| --- | ---: | ---: | ---: |
| qwen3:4b | 3.88 GB | 3.88 GB | 8192 |
| coder 3B | 2.41 GB | 2.41 GB | 8192 |
| coder 7B | 5.41 GB | 4.27 GB | 8192 |

These are post-response samples, not peaks, process working-set measurements or
proof of full-GPU placement. The 7B size/VRAM difference is consistent with
partial offload. Cold loads, caching, generated token counts, thinking behavior,
model templates and fixed run order confound latency comparisons. Artifact size
is distinct from loaded size. No nvidia-smi peak or CPU-usage series was measured.

Keep qwen3:4b as the unchanged default pending better evidence. Neither coder
completed an edit, so this trial supports neither a model switch nor a planning/
coding split. Prioritize a separately reviewed, tightly scoped native-call
protocol test and clearer phase/action guidance: avoid consuming a whole budget
on duplicate inspection reads, retain exact authorization, and provide feedback
that distinguishes printed proposals from executed actions. Do not loosen the
recovery cap or execute multiple proposals merely to improve scores.

Also review an engine-dependent inventory liveness check alongside metadata in
future dependency preflight work: Resource Saver can make cached metadata look
healthy during transitions. Do not silently raise limits, retry isolation failures
or change Resource Saver settings. Any further live coding attempt needs a new
explicit authorization; all six approved attempts are consumed.

## Evidence and cleanup

Ignored JSON evidence under evaluations/runs/:
- step36_downloads.json: failed monitor journal; step36_downloads_resume.json:
  successful approved download progress/completion.
- step36_inventory_diagnosis.json, step36_docker_log_diagnosis.json and
  step36_resource_saver_evidence.json: complete bounded command/log evidence.
- step36_models_verified.json: exact inventory, show metadata and templates.
- step36_comparison_readiness.json and step36_launch_readiness.json: passing
  dependency and empty-inventory checks before generation.
- step36_live_started.json: exclusive consumed launch marker.
- step36_live_comparison.json and six numbered workflow reports: complete requests,
  responses, tool traces, source snapshots, diffs and resource samples.
- step36_evaluation.json: independent per-criterion review and consolidated scores.

Every source snapshot remained unchanged and every owned staging workspace was
discarded. All six post-task three-second container inventory checks passed with
empty output and exit code 0. No image/container execution, generated-code/test
execution or source application occurred. The default live-functional gate remains
false; the interactive controller/model, six-call budget, Docker restrictions
and tracked fixtures/plan remain unchanged. Only documentation is committed.

## Post-comparison regression results and unresolved limitation

The full existing suite ran 292 tests in 275.802 seconds: **290 passed, one failed
and one errored**. It must not be described as 292/292 passed.

- test_multi_file_tasks.MultiFileTests.test_validation_invalidated_after_write_or_external_edit:
  KeyError for a missing validation report field.
- test_coding_workflow.WorkflowTests.test_explicit_delete_only_affects_temporary_copy:
  ready_for_human_review was false instead of the expected true.

A diagnostic run of only those two existing tests passed 2/2 in 8.480 seconds.
It instrumented integrity-rejection reports and workflow errors before teardown;
neither failure recurred and no such error was captured. The original underlying
integrity decision/report was not retained by the existing test teardown, so its
exact cause is unknown. A passing diagnostic run does not erase the failed full
run or establish that the issue is fixed. No safety check was relaxed, no source
implementation was changed, and no live evaluation was repeated.

Logs: runs/step36_post_comparison_regression.log,
runs/step36_regression_diagnosis.log and runs/step36_regression_diagnosis.json.
The consolidated assessment retains both outcomes. These Git-staging regression
uncertainties are separate from the successful source/cleanup checks in all six
actual live attempts and from the Docker Resource Saver evidence.
