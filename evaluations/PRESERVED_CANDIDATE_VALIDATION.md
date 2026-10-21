# Step 39: preserved-candidate functional validation preparation

**No candidate execution is authorized or performed.** Three add_one snapshots
are prepared for a separately approved Docker-only run; all normalize_tags
snapshots remain blocked. The historical Step 38B static score of
4/6 is unchanged; a policy rejection is not a functional test failure.

## Evidence provenance

`python -m evaluations.prepare_candidate_validation` reads the original completed
Step 38B run and the six independent staging reports. It requires actual final
file snapshots, exact agreement between the saved records, successful-write
hashes and final per-file hashes. It never reconstructs code from proposed edits
or diffs. Missing or inconsistent snapshots fail preparation.

All six implementation snapshots and three associated generated test snapshots
were preserved and verified. Exact source strings, hashes, proposed checks and
policy diagnostics are retained in `runs/step39_preparation_review.json`. The original
run and staging records are read only and hash-linked. No candidate modules are
imported, compiled or executed. Generated test files are evidence only and are
excluded from any proposed execution scope or trusted grading decisions.

## Exact implementations

All three syntax candidates have the same bytes, SHA-256
`eb03dcb53008b66099f4a3324d5335b3cf0a3e93fefc7836afbb6a9eb88cfbdd`:

```python
def add_one(value):
    return value + 1
```

Qwen3 normalize_tags, SHA-256
`9619107e7cb8bdfcfdcd02f13e19190dfcc02706c15b73487ed8b73d2674a0c5`:

```python
def normalize_tags(tags):
    result = []
    for tag in tags:
        cleaned = tag.strip().lower()
        if cleaned:
            if cleaned not in result:
                result.append(cleaned)
    return result
```

Coder 3B normalize_tags, SHA-256
`902a186ced6c570fdb2ddf74f5f4a34ec060394afc54723e644374596f82fbca`:

```python
def normalize_tags(tags):
    normalized = set()
    for tag in tags:
        tag = tag.strip().lower()
        if tag:
            normalized.add(tag)
    return list(normalized)
```

Coder 7B normalize_tags, SHA-256
`2ab54f18c286675de6822d9364d3bf455f78a917a9db253782d1574311277207`:

```python
def normalize_tags(tags):
    return [tag.strip().lower() for tag in tags if tag.strip()]
```

Code blocks illustrate the implementations; the report's exact source strings
and hashes are authoritative for whitespace/final-newline identity. No extracted,
rewritten, relabeled or reconstructed variant is proposed as the original.

## Proposed deterministic checks

Each add_one snapshot has six proposed vectors:
`0 -> 1`, `1 -> 2`, `-1 -> 0`, `41 -> 42`, `-8 -> -7`,
`1000000 -> 1000001`. Require exact integer type/value and unchanged arguments.

Each normalize_tags snapshot has these twelve proposed vectors:

| Check | Input list | Expected result |
| --- | --- | --- |
| Empty | `[]` | `[]` |
| Trim/lower | `["  RED ", "Blue  "]` | `["red", "blue"]` |
| Original empties | `["", "   ", "\t"]` | `[]` |
| Original ordered deduplication | `["Blue", " red ", "BLUE", "Red", "green"]` | `["blue", "red", "green"]` |
| Original input preservation | `[" Blue ", "BLUE"]` | `["blue"]` |
| Original new-list requirement | `["red"]` | `["red"]` |
| All whitespace | `["", " ", "\t", "\n", "\r\n"]` | `[]` |
| Empty values between tags | `[" red ", "", "\t", "BLUE", " "]` | `["red", "blue"]` |
| First occurrence, not sorting | `["b", "a", "B", "c", "a"]` | `["b", "a", "c"]` |
| Repeated normalized values | `["MiXeD", "mixed", " MIXED "]` | `["mixed"]` |
| Unicode whitespace | `["\u2003Red\u00a0", "\tBLUE\n"]` | `["red", "blue"]` |
| Internal spaces retained | `["red blue", "Red Blue"]` | `["red blue"]` |

Escapes above represent actual tab/newline/Unicode characters in the JSON plan.
Every normalize_tags vector additionally requires exact list/element types,
order and values, unchanged input against an independent deep copy, and output
list identity distinct from the input, including empty input. The twelve vectors
are new Step 39 check data, not modifications to the original benchmark fixtures,
acceptance criteria or canonical five-task/29-vector suite.

Defined total: **54 vector checks** (18 add_one, 36 normalize_tags), currently
**zero executed**. Only the **18 add_one checks** are proposed for execution
approval; the 36 normalize_tags checks remain unexecuted under current policy.
Expected values, identity assertions and grades must stay on
the host. Only exact candidate source and copied arguments may reach the worker.
Candidate-generated tests never become the host oracle.

## Execution compatibility blockers

| Candidates | Language policy | Existing harness task registration | Current execution scope |
| --- | --- | --- | --- |
| Three add_one snapshots | Accepted by non-executing policy validation | New fixed profile | Pending explicit approval and fresh verification |
| Three normalize_tags snapshots | Rejected | Not registered | Blocked |

The unchanged validator reports `Unsupported attribute: strip` and `Unsupported
call target` for every normalize_tags snapshot. `PURE_METHODS` includes `lower`
but not `strip`. No source rewrite, allowed-method addition, policy exception or
misleading mapping to another task is implemented. This is an intentional
restricted-language limitation; it does not establish whether a candidate is
functionally correct or incorrect.

Originally the `FunctionalHarness.run` and `make_request` entry points resolved
only the five canonical task IDs. This preparation adds exactly one separate,
fixed trusted profile, `step39_add_one`, via `preserved_tasks.py`. Its six explicit
vectors are deep-copied, and the existing grading profile hash now covers that
module. No original task/fixture changes and no arbitrary task registration API
are introduced. The unchanged worker and host grader can therefore evaluate the
add_one snapshots after approval and fresh verification. normalize_tags remains
unregistered and policy-rejected.
Furthermore, the current host grader requires new-list identity specifically for
`unique_order`; a future normalize_tags profile needs an explicit reviewed host
identity assertion. Relabeling normalize_tags as unique_order is not an acceptable
way to gain execution or grading coverage.

No execution adapter or permission flag is enabled by preparation or saved
reports. The registered add_one profile still fails closed without current
in-process isolation/profile verification. Approval cannot override the
normalize_tags compatibility failures. No generated-code execution approval is
being consumed. The strip-using candidates must remain unexecuted under the
current policy. Any proposed language-profile expansion would require its own
security review and is outside this implementation.

## Required future execution review

Only preserved exact hashes may be considered. Any supported future scope must
state which snapshots/vectors will execute and which remain policy rejected.
Fresh bounded readiness, definitive inventory and all eleven real isolation
probes must pass before any candidate job; saved historical reports are not
permits. Retain the pinned image, non-root/network-none/read-only restrictions,
CPU/memory/PID/output limits, per-task timeout, identity/profile checks and forced
cleanup. Stop immediately on mandatory verification failure; do not retry it.
Do not enable live model generation, source application or persistent execution.

The concrete approval request is **three Docker-only worker jobs**, one per
preserved add_one snapshot (attempts 1, 3 and 5, shared exact source hash above),
six fixed vectors per job, **18 vectors total**, with no job retries. First run
the existing eleven trusted isolation probes once under the pinned policy;
execute no candidates unless all mandatory evidence passes. Do not execute any
normalize_tags candidate or generated test module. Preserve per-vector host
grades, runtime/verification errors and cleanup evidence, and stop on mandatory
isolation failure. This approval scope does not include a new model request.

The historical Step 38B results are not altered by this preparation. No functional
success rate or vector result is claimed from static inspection or policy checks.

## Preparation verification

The final complete suite passed **353/353 regression tests** in **411.570
seconds**, including eleven new preparation/profile tests. The 32-test targeted
preparation/worker suite also passed. Five additional synthetic host-grading
checks passed, covering valid frames, boolean-versus-integer mismatch, changed
arguments, runtime-error frames and the fixed-profile harness flow. These use
test doubles and are not functional results from executing the candidates.

The earlier preparation-only full suite passed 349 tests before the fixed-profile
integration; its evidence is retained separately. A Windows console encoding
error during initial plan printing was fixed by ASCII-escaped JSON output;
decoded candidate bytes and checks are unchanged.

Final read-only readiness/inventory verification passed with zero containers.
No temporary Git editing staging remained; original source and Step 38B report
hashes still matched. Evidence: `runs/step39_preparation_completion.json`,
`runs/step39_review_regression_evidence.json`, and
`runs/step39_mock_grading_checks.json`. Generated reports remain uncommitted.
No real worker integration, isolation probes or candidate execution occurred.
The modified grading profile requires fresh verification after approval; prior
historical security reports cannot authorize this new profile.
