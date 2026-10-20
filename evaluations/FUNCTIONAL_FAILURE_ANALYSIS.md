# Step 29C: evidence-based functional failure analysis

Analyzed benchmark: evaluations/runs/functional_live_20261020T171451704939Z.json,
run on implementation 915ccc1 and documented in 2f6a914. Report SHA-256:
4b4a3ca7142bedd0c4901ac3f3d5ec0c565c08d358179a879b689bcb684582b6.
The report is ignored by Git and was not changed, replayed against a live model,
or rescored. Its result remains 2/5 tasks, 16/23 executed vectors, six unexecuted.
All references below use zero-based report indices.

## Attribution

| Task | Observable model mistake | Controller contribution | Intentional restriction | Budget role |
|---|---|---|---|---|
| clamp | Two reads; final edit printed as JSON instead of native invocation | Empty earlier response consumed the sole recovery opportunity; valid later proposal was ignored | Strict JSON parser/filename/argument checks did not reject the final proposal | Only 2/6 calls used; four remained |
| palindrome | Replacement lost indentation on its second line; used unsupported filter | AST-only syntax success was insufficient feedback; stored after-edit policy failures were not sent to model | Top-level statement and unsupported-call rejection correctly prevented execution | 3/6 calls used; three remained |
| unique_order | Double-escaped newlines in both edits; repeated reads; incomplete printed proposal | Generic exact-match feedback did not identify escaped-text mismatch; no confirmed editing-engine defect | Exact-match edits and strict proposal envelope correctly rejected attempts | All 6 used: three reads, two failed edits, one syntax check |

The final candidate source is retained for all three tasks. For clamp and
unique_order it is identical to the starter, matching unchanged hashes and zero
successful edits. Palindrome has one successful text edit but no executed vectors.
Successful edits count changed bytes, not verified repairs.

## clamp: correct proposal never applied

Retained actual candidate, /results/1/candidate_source:

```python
def clamp(value, lower, upper):
    return min(value, lower)
```

This selects the smaller of value/lower and ignores upper. Host-graded failures:

| Vector index | Arguments (value, lower, upper) | Actual | Expected |
|---|---|---|---|
| 0 | (5, 0, 10) | 0 | 5 |
| 1 | (-1, 0, 10) | -1 | 0 |
| 2 | (11, 0, 10) | 0 | 10 |
| 4 | (10, 0, 10) | 0 | 10 |
| 6 | (-5, -10, -2) | -10 | -5 |

Vectors 3 and 5 passed. No argument mutation or runtime error was reported.

The response sequence in /results/1/model_responses is read (index 0), empty
content/no tool calls (1), another read (2), then a complete strict JSON edit (3).
The final proposal names edit_workspace_file and supplies exactly filename,
old_text and new_text, replacing the return with max(min(value, upper), lower).
Its reporting validation_error is null. /results/1/recoveries instead records a
parse failure for the earlier empty response. The old controller set recovery_used
before parsing, so no later recovery was attempted. No edit was dispatched or
rejected for the valid final proposal. This is a confirmed recovery-accounting
defect in addition to the model's failure to invoke its tool interface.

The proposal expresses the appropriate interval operation. That is source-level
evidence, not an execution result: its vectors were never run in the benchmark.

## palindrome: malformed candidate, correctly blocked

Retained actual candidate, /results/2/candidate_source:

```python
def is_palindrome(text):
    cleaned = ''.join(filter(str.isalnum, text.lower()))
return cleaned == cleaned[::-1]
```

The exact edit matched an unindented substring inside an indented line. The
original four spaces therefore prefix only the first replacement line; the model
supplied no indentation for the following return. Literal replacement behaved as
specified; automatic indentation would reinterpret the requested edit.

The top-level return violates the single-function contract. filter is outside
PURE_CALLS. After-edit and final policy checks both failed. The function count is
one: "Nested/extra functions are unsupported" is a misleading secondary diagnostic
because validate_source sets its selected function to None when extra module
statements exist. It is not evidence of a second helper function.

AST parsing and the native syntax tool reported success. ast.parse does not check
all compiler context rules, including return outside a function. No compilation
result for this particular candidate exists: policy validation blocked the worker
first. The report's syntax_valid field means AST parse success, not compilability.
The controller stored the failed static checks but sent the model only the edit
success and parser-only Syntax OK tool results. The model then claimed no further
calls were required. This is a feedback/design limitation; the independent grader
and isolation policy did not falsely pass the candidate.

**No palindrome vectors failed assertions: all six were unexecuted.** Canonical
inputs/expected outcomes were empty string -> True; !!! -> True;
A man, a plan, a canal: Panama! -> True; race a car -> False; 0P -> False;
12-21 -> True. Each corresponding worker result is not_run. Their hypothetical
outcomes must not be inferred from the recorded source.

## unique_order: repairs described, literal edits rejected

Retained actual candidate, /results/3/candidate_source:

```python
def unique_order(numbers):
    return sorted(set(numbers))
```

This removes duplicates but sorts them instead of retaining first-appearance order.

| Vector index | Input list | Actual | Expected |
|---|---|---|---|
| 1 | [3, 1, 3, 2, 1] | [1, 2, 3] | [3, 1, 2] |
| 4 | [4, 2, 9] | [2, 4, 9] | [4, 2, 9] |

Vectors 0, 2 and 3 passed. Input and new-result-list assertions passed; order was
the observed defect. /results/3/trace/1 and /trace/2 contain literal backslash+n
characters in old_text instead of the actual newline. The supplied new_text also
contains literal escaped newline sequences. These were string-valued, correctly
named arguments, so schema validation passed. Exact text matching then correctly
returned "Text not found. File unchanged." twice. Adding leading spaces in the
second attempt did not repair the newline mismatch. The first old_text need not
include indentation to match a substring; missing spaces alone do not explain
that first rejection. Automatically unescaping would also risk indentation errors
or changing text intended to contain literal escape sequences.

The single invalid-proposal metric refers to /results/3/model_responses/4: prose
surrounding a JSON code block containing only old_text/new_text. The whole response
is not JSON, and the embedded object lacks name, arguments and filename. The
strict parser correctly refused it; it was not a failed native tool invocation.
The model's visible explanation incorrectly described double-escaped sequences
as exact newlines. Subsequent reads and a syntax check consumed the remaining
budget without changing the starter. No seventh-call behavior is observed, so
increasing the budget cannot be claimed to have fixed this case.

## Three failed tool actions and edit accounting

| Report location | Action | Rejection layer | Assessment |
|---|---|---|---|
| /results/3/trace/1 | unique_order edit | Exact-text match | Correct rejection; literal escaped newline |
| /results/3/trace/2 | unique_order edit | Exact-text match | Correct rejection; same mismatch remains |
| /results/4/trace/1 | count_words edit using filename/content | Argument schema | Correct rejection; required filename/old_text/new_text |

count_words later supplied a valid edit and passed 6/6, showing that feedback can
lead to recovery within the unchanged budget. The three successful edits were
sum_even, palindrome and count_words. There were zero recovered calls. The valid
unapplied clamp proposal and invalid unique_order prose/fragment are distinct
observations. The failed empty-response recovery is not another malformed JSON
proposal in that reporting metric.

## Ranked improvements

| Priority | Improvement | Expected impact | Risk and boundaries |
|---|---|---|---|
| 1, implemented | Consume the single JSON recovery only after strict parsing succeeds | Addresses the exact clamp accounting defect | Low; same parser, dispatch validation, one recovered call and six-call/response limits |
| 2, proposed | Bounded evaluator feedback for failed edits: show escaped-text mismatch and the exact required schema | Addresses the two newline failures and content-argument mistake | Low/moderate prompt change; no automatic unescaping, indentation repair or extra file access |
| 3, proposed | Send existing after-edit contract/policy diagnostics to the model within the tool interaction | Exposes palindrome's actual structural failure while calls remain | Moderate controller-feedback change; preserve policy, don't feed expected outputs or grant execution tools |
| 4, proposed | Clarify pure-function profile and multiline edit examples in evaluator-only prompting | Reduce unsupported filter/top-level code and escaping mistakes | Low/moderate; use allowed comprehensions/methods, no whitelist expansion |
| 5, proposed | Distinguish AST-parsed, policy-valid, compiled-in-Docker and functionally-passed reporting; improve misleading diagnostics | Prevent false confidence from Syntax OK | Low for reporting; compiler checks, if added, must stay Docker-only and fail closed |
| 6, proposed | Explicitly track no successful edit and remaining budget; discourage redundant reads and reserve a final check | Better allocation of unique_order's six calls | Moderate control-flow effect; no larger budget, forced edits or extra retries |

These expected impacts are hypotheses except for the deterministic accounting
replay. None is a measured new Qwen3 success rate. Broader feedback/prompt changes
should be reviewed and tested separately before another explicitly authorized run.

## Implemented fix and verification

Only evaluate_functional.one_functional_case recovery accounting changed:
recovery_used is now set after parse_proposal succeeds and before dispatch.
Empty/prose/malformed responses remain rejected and recorded, but cannot consume
a recovered tool invocation that never occurred. A parsed proposal with an
unauthorized filename or invalid arguments still consumes the single dispatch
opportunity and is rejected. No substring extraction, coercion, newline decoding,
fuzzy matching or additional model retry was introduced.

Six new deterministic regressions cover the recorded clamp pattern, malformed
then valid proposals, rejected unauthorized proposals retaining the one-dispatch
limit, sixth-call recovery with no budget overrun, literal escaped-newline
rejection, and the exact palindrome source remaining policy rejected. The clamp
replay supplies synthetic continuation replies for verification: it produces one
edit and syntax check in four calls, with no candidate execution and no functional
pass claim. It does not claim what the real model would have replied next.

**144/144 regressions passed** (138 existing plus six new). No new live Qwen3
benchmark or real Docker candidate execution was run in Step 29C. Interactive
main.py, syntax evaluator, budget, fixtures/vectors, policy, worker, grader and
Docker transport remain unchanged. Default live execution is False; the previous
permit remains expired. The historical runtime-verification failure remains
unresolved; this analysis supplies no new evidence about its cause.

Full regression command:

    .venv\Scripts\python.exe -m unittest -q test_agent test_evaluation_controller test_benchmark_reporting test_functional_evaluation test_execution_backend test_docker_transport test_functional_worker test_functional_benchmark test_runtime_diagnosis
