# Step 45: opt-in line-array replacements

## Evidence and scope

The three Step 42 and three Step 44 retained clamp responses were inspected
without staging or executing their proposals. In all six, both old_text targets
contain literal backslash+n sequences, zero actual newlines and zero exact source
matches; the replacement strings also contain literal backslash+n. Independent
JSON decoding agrees with the strict parser. The archive preserves those strings;
it does not establish the model's internal cause or independently audit raw HTTP
bytes. Read-only evidence is retained in ignored
`runs/step45_historical_analysis.json`. Existing responses and reports are intact.

A replacement-only new_lines field would not fix the nonmatching old_text target.
The extension therefore represents **both target and replacement** as line arrays.
It is a distinct document version and operation; it does not reinterpret version 1.
There were no live model requests or generated-code executions in this milestone.

## Exact schema and opt-in

Default calls to proposal_schema, proposal_messages, envelope, validate_changes
and run_proposals retain version 1 behavior. Explicit keyword
`allow_line_arrays=True` enables the extension; values other than booleans are
rejected. A model cannot enable it by printing a flag. Authorization and file
permissions remain in the separately validated task request.

Version 2 has exactly these fields:

```json
{
  "version": 2,
  "changes": [
    {
      "operation": "replace_lines",
      "filename": "clamp.py",
      "old_lines": ["def clamp(value, lower, upper):", "    return value", ""],
      "new_lines": [
        "def clamp(value, lower, upper):",
        "    if value < lower:",
        "        return lower",
        "    if value > upper:",
        "        return upper",
        "    return value",
        ""
      ]
    }
  ]
}
```

The complete machine-readable schema is returned by
`proposal_schema(request, allow_line_arrays=True)`: oneOf the unchanged version 1
schema and version 2 schema. Each branch forbids additional fields. The version 2
branch is also embedded verbatim in the proposed follow-up plan's second payload.

| Field | Rule |
| --- | --- |
| version | Integer 2, never boolean |
| changes | Nonempty array, at most six operations |
| operation | Exact string replace_lines |
| filename | Exact authorized existing read/modify path |
| old_lines | Nonempty string array; joined text must be nonempty |
| new_lines | String array; empty array is allowed |
| Each line | String without actual CR or LF; indentation and backslashes preserved |

The controller additionally enforces one change per filename, exactly one target
match, a real content change, existing UTF-8/text/file-size restrictions, source
integrity and the remaining operation budget. JSON schema alone is not the safety
boundary. All edits in a document must use its declared representation. Mixed
old_text/new_text/line fields, extra fields, unsupported operations, wrong types,
duplicate JSON keys, prose and trailing documents are rejected. A version 1
document cannot contain replace_lines; a version 2 document cannot contain
replace_text. Opted-in callers may still submit a separate version 1 document.

## Canonical newline rules

Join elements with exactly one LF between them, with no implicit final separator:

| Array | Exact decoded text |
| --- | --- |
| `["a", "b"]` | a, LF, b; no final LF |
| `["a", "b", ""]` | a, LF, b, LF |
| `["a", "", "b"]` | a, LF, LF, b |
| `["a", "", ""]` | a followed by two LFs |
| `[]` or `[""]` | Empty replacement text; invalid as an empty target |
| `["", ""]` | One LF |
| `["a\\nb"]` | Literal backslash+n inside one line, never a separator |

No trimming, indentation repair, unescaping, newline inference or CRLF conversion
occurs. Version 2 intentionally supports LF-separated targets only. A multi-line
CRLF target does not match an LF array and must use the unchanged exact string
protocol. Line arrays describe exact text fragments, not line numbers or a fuzzy
line editor. A fragment may match within a line; the same unique exact substring
semantics as version 1 apply. Empty replacement text removes the matched region,
not the file; file deletion remains unauthorized.

## Security and compatibility

The extension converts validated line arrays to strings in pure prevalidation,
then uses the existing exact-match, allowlist and atomic batch validation path.
The original response remains in the audit event; final file bytes, hashes, diff,
charged operations, rejections and cleanup evidence remain inspectable. Opted-in
reports identify explicit-replacements-v1+lines-v2. Legacy report shape and
protocol identifier remain unchanged when disabled.

Every declared edit consumes the existing operation budget even if its batch is
rejected; malformed envelopes consume one slot. Batch arguments are checked before
any write. As before, file writes are not an OS transaction: a filesystem failure
can leave partial edits inside owned staging, recorded and discarded on failure.
No source application or execution authority is added. The interactive agent,
default model, six-operation cap, Docker policy and frozen benchmark plans are
unchanged. Historical benchmark entry points do not opt in. Their recorded
implementation hashes remain historical evidence; any future live plan needs
fresh review against the new implementation hashes.

This is a representation change, not a sandbox or proof of functional correctness.
It may avoid newline-encoding confusion but can still produce incorrect lines,
nonmatching targets, bad code or incomplete contracts. No live reliability gain
has been measured.

The new JSON schema has not been sent to Ollama in this milestone. Its grammar
conversion support and the model's ability to emit this representation remain
unverified; a future adapter must fail closed on schema/transport errors rather
than remove constraints or fall back silently.

## Deterministic verification

The new tests use mocked/model-free data and disposable real Git staging. They
cover multiline replacements, blank lines, absent and multiple trailing LFs,
empty targets/replacements, malformed arrays, embedded CR/LF, literal backslashes,
legacy behavior, explicit boolean opt-in, wrong versions, mixed fields/batches,
duplicate targets, missing/ambiguous matches, unauthorized/read-only paths,
atomic batch rejection, retained diffs, cleanup and six-operation exhaustion.
Source snapshots are checked before/after real staging tests. No candidate is
imported, executed or used as an executable test.

Actual results on 2026-10-23: **24/24 new tests passed** in the targeted run;
the complete current regression suite passed **476/476** in 697.548 seconds.
No live model or Docker candidate execution ran. Final closure verified unchanged
Step 42/44 reports and frozen plans, all retained original source repositories,
disabled default live execution, and no remaining ALFHA staging workspaces. The
follow-up plan's schema, prompt and implementation hash agree with the new code;
both generation and candidate execution remain unauthorized. Ignored evidence:
`runs/step45_targeted.log`, `runs/step45_regression.log`,
`runs/step45_regression_evidence.json`, `runs/step45_closure.json`.

## Proposed follow-up: not authorized

`step45_followup_plan.json` contains two exact proposed Qwen3 4B requests:

1. One legacy version 1 clamp attempt using the original Step 44 round 1 request.
2. One version 2 line-array attempt with the same user message, fixtures,
   acceptance criteria, permissions and generation options (seed 42,
   temperature 0, context 8192). Only system instructions and representation
   schema differ. Require the declared response version; no fallback or repair.

This is a small protocol comparison, not an estimate of reliable success rate.
Each slot permits one request, at most six operations, no corrective request or
retry, and isolated review-only staging. Record full requests/responses, timing,
validity, actual edits, newline behavior, implementation and test-contract checks,
diffs and exact candidate snapshots/hashes separately. Use bounded dependency
preflight and definitive inventory before generation; fail closed on missing
evidence and stop on integrity or infrastructure failure. Verify source snapshots
and staging cleanup; authorization must expire after completion or abort.

No generated code or tests would run. No Docker functional jobs are proposed.
Expected resources: the existing local Qwen3 4B model, two sequential requests with
the existing 180-second response timeout and small disposable Git fixtures. Prior
focused responses averaged 164.6 seconds; that is an observation, not a runtime
guarantee. There is no live runner in this preparation. Separate approval of the
final commit and fixed requests is required before either generation request.

## Approved two-request comparison — 2026-10-23

The user separately authorized the two fixed requests at e9044b7. Both were sent
once, in legacy-then-line-array order, without retries, corrective requests,
schema changes, automatic repairs or candidate execution. Read-only Docker
readiness, pinned-image metadata, exact baseline Qwen3 identity and mandatory
inventory passed before generation and after both attempts. Source snapshots
remained unchanged; owned staging was discarded; one-time authorization expired.

| Result | Legacy version 1 | Line-array version 2 |
| --- | --- | --- |
| Response time | 157.406 s | 154.312 s |
| JSON syntactically valid | Yes | Yes |
| Contextually valid proposal | No | Yes |
| Charged operations | 2/6 | 2/6 |
| Accepted edits / rejected operations | 0 / 2 | 2 / 0 |
| Required files changed | 0/2 | 2/2 |
| Implementation static requirements | Fail: unchanged module | Pass |
| Exact generated-test AST contract | Fail: unchanged tests | Pass |
| Complete static task | Fail | Pass |
| Functional execution | Not run | Not run |

The legacy output again encoded literal backslash+n in all four old_text/new_text
fields, with no actual newlines and zero target matches. Whole-batch validation
wrote nothing. Its missing-test diagnostics describe unchanged final staging,
not an independent judgment about the unapplied replacement proposal.
Its raw content exactly repeated Step 44 round 1; the new invocation and response
envelope are retained separately. The new version 2 content matched no Step 44
response exactly.

The version 2 output contained two replace_lines operations, valid arrays without
embedded CR/LF or literal backslash+n, and final empty elements. Both joined
targets matched once. The final module retained its signature and used explicit
below/above/interior branches. The final test AST exactly matched the unchanged
contract: existing import/test_inside and all five test_edges assertions in order.
Independent response/snapshot analysis confirmed archive agreement and hashes:

- clamp.py: `b048cd32a37f44104fbb4b54d31578bb00c7bb723ca2a6f0a865a81bef29e731`
- test_clamp.py: `040e046b52155dfacb1bc5eb8d0cb8f24b71383ca651a611a909241712a21e59`

The server returned a version 2 response under the submitted schema; this is not
proof of every server-side grammar constraint. Controller-side validation remained
the safety boundary. Across both attempts there were no unauthorized operations,
native calls, recovery calls or recorded infrastructure/integrity failures.
No generated Python or generated tests ran, including inside Docker. Neither the
implementation nor the default model/interactive controller was changed.

This pair supports further controlled study of line arrays, not a reliability or
causality claim. Keep the format opt-in and review-only; functional execution of
the preserved candidate requires a separately approved scope.

Complete ignored evidence: `runs/step45_live_results.json`, separate exact response
and candidate snapshot JSON files, and `runs/step45_live_comparison.json`.

Final checks confirmed expired authorization, live execution and line arrays
disabled by default, unchanged source repositories/fixtures and historical
evidence, verified candidate hashes, zero staging workspaces and a definitive
empty Docker container inventory. No controller, default-model, policy or fixture
change was made for this comparison.

The first post-comparison regression run encountered one assertion failure and
three errors before interruption. Git launch errors explicitly reported Windows
error 1455 (paging file too small); the shell also reported OutOfMemoryException
and exited, leaving its test child waiting without CPU progress. The stalled
owned test process was stopped after identity verification. Its partial evidence
was preserved, not replaced or counted as a completed suite. The assertion's
precise cause is not established by the retained traceback, and a root cause for
the transient host resource problem remains unresolved. No system settings or
services were changed.

A fresh full deterministic run with direct file logging passed **476/476** in
697.691 seconds, including the tests affected in the interrupted run. This is not
proof that the resource issue was fixed. No model attempts were repeated.
Evidence: `runs/step45_live_post_regression_interrupted_evidence.json`,
`runs/step45_host_resource_evidence.json`,
`runs/step45_live_post_regression_rerun.log`,
`runs/step45_live_post_regression_rerun_evidence.json`, and
`runs/step45_live_closure.json`. Storage was then measured separately without
cleanup; see [STORAGE_AUDIT.md](STORAGE_AUDIT.md).
