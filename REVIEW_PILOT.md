# Limited everyday-coding pilot: time-report formatter

## Scope for separate generation approval

One local Qwen3 4B response for the fixed request in `prepare_review_pilot.py`.
No retries, corrective requests, native tool calls, candidate execution, generated
test execution, source application, or default-model changes. The request uses the
existing version 2 `replace_lines` schema, exact-match/atomic batch validation,
six-operation budget, temperature 0, context 8192 and 180-second client timeout.
Resource gates, source fingerprints, file/link guards and staging cleanup remain
the existing `interactive_review.run_review` implementation. No new live runner
or execution permission is introduced.

The first-party project is `pilots/time_report`, a small work-log duration utility.
It is deliberately incomplete, not an existing private project or production
application. Preparation copies its three files into a new disposable source Git
repository. All proposed edits occur in a separate disposable staging workspace.
The source copy stays unchanged. This offers realistic maintenance practice
without needing private files or external downloads; it does not establish
performance on a larger existing codebase.

| File | Permission | Purpose |
| --- | --- | --- |
| `duration.py` | read, modify | Format integer elapsed seconds |
| `test_duration.py` | read, modify | Preserve baseline and add boundary tests |
| `README.md` | read only | Project contract/context |

No creation, deletion or other paths are permitted. Both Python files must change.

## Exact requested behavior and independent review checklist

For nonnegative integer seconds, `format_duration(seconds)` returns a string of
total minutes, a colon and exactly two second digits. Minutes never wrap at an
hour. Negative integers raise `ValueError`. Other input types are out of scope.
Preserve the signature, module purpose, import and existing `test_zero` unchanged.

Append `test_boundaries` with precisely these assertions, in order:

```python
assert format_duration(1) == "0:01"
assert format_duration(59) == "0:59"
assert format_duration(60) == "1:00"
assert format_duration(61) == "1:01"
assert format_duration(3600) == "60:00"
assert format_duration(3661) == "61:01"
```

Then append `test_negative`, calling `format_duration(-1)` in a try/except
`ValueError`, with an explicit failing assertion if it returns normally. No other
test code or imports. Static review must verify the exception check is meaningful,
not merely that a try statement exists.

Report separately: strict proposal validity, staged edits, both required paths
changed, AST parsing, preserved signature/test/import, all six assertions with
exact arguments/results/order, meaningful negative case, implementation source
inspection, readonly-file preservation, original source integrity and cleanup.
The existing controller's `ready_for_human_review` flag checks changes and static
validation; it does **not** automatically prove this natural-language checklist.
Any missing requirement means incomplete pilot task despite a valid proposal.
Functional correctness remains **not tested**. Do not run or import candidate files.

## Preparation and preserved review

Preparation only (no model calls, no candidate execution):

```powershell
.venv\Scripts\python.exe -B -m prepare_review_pilot
```

This creates a fresh source repository and a separate `plan.json`, prints their
paths, and verifies isolated inspection/cleanup. The plan retains exact request,
model messages/schema/options, fixture hashes and starting source state. It is
data with `generation_authorized=false`; opening it never grants authorization.
Retain the prepared source and plan through review. Re-preparation is not needed
to retry an unavailable dependency and does not authorize any live attempt.

Reopen an existing interactive report without contacting dependencies:

```powershell
.venv\Scripts\python.exe -B -m review_report "C:\exact\saved\report.json"
```

The viewer reads only that bounded report file and prints selected evidence as
escaped JSON. It follows no embedded source paths and restores no authorization.
It does not reverify historic source state, hashes, cleanup, validation or claimed
success. A report may be tampered with; displayed claims are not an approval token.

## Evidence and resource expectations

The pending live pilot preserves the one exact request/response, request count,
response duration, all rejected operations, diff, final file snapshots/hashes,
validation, independent checklist and final source/staging checks. Abort on missing
readiness or source/cleanup evidence; do not retry. Expire approval on completion
or abort. No Docker jobs are needed for static review.

Existing conservative preflight requires 4 GiB available RAM and 10 GiB commit
headroom before generation, then 2/4 GiB after response before staging. These are
readiness thresholds, not reserved resources. The previous single smoke response
took about 172 seconds; this is not a duration guarantee. Memory use can change
after a snapshot. Serialize with regressions and Docker work; never change system
settings, unload models or terminate applications automatically.

## Next decision

Only after explicit approval, run one prepared review attempt, then inspect its
complete contract manually. Use its evidence to prioritize review usability.
Source application stays disabled until the separate human-approval mechanism has
been reviewed; no application implementation is part of this pilot.

## Actual preparation verification

- **42/42 focused tests passed in 128.226 seconds**, including seven new pilot/viewer
  tests and the existing interactive/resource suite. Native regression readiness
  passed before loading tests; model responses and dependency checks were mocked.
- Preparation then verified real disposable Git inspection, unchanged source
  state, and staging discard. All three copied source hashes match the tracked
  fixtures. No `alfha-git-*` staging remains. The prepared source and plan are
  retained intentionally for the pending review.
- **Zero live model requests and zero candidate/test executions.** No full regression
  rerun is claimed for this additive preparation; the new tests are included in
  the existing resource-gated full regression runner for future runs.
- Ignored local evidence: `evaluations/runs/review_pilot_tests.log`,
  `review_pilot_test_readiness.json`, `everyday_review_pilot_preparation.json` (exact
  payload and source identity), and `everyday_review_pilot_closure.json`.
