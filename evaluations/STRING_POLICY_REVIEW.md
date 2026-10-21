# Step 40: restricted string-operation review

No preserved model-generated candidate or generated test module is executed in
this milestone. No live model call, default-model change, interactive-controller
change, source application or persistent execution enablement is introduced.

## Findings and scope

All three preserved normalize_tags implementations use `strip`, which was absent
from the method allowlist. `lower` was already present, but the old AST rule
checked only its attribute name; it did not restrict arguments or verify receiver
types. AST acceptance is not a runtime type guarantee or an isolation boundary.

This implementation makes `strip()` available **only** in two fixed trusted
review function profiles, `review_strip(value)` and `review_chain(value)`.
`review_lower(value)` tests the already-supported lower operation. Their fixed
host vectors are stored separately in `preserved_tasks.py`; the original five
tasks and 29 vectors are unchanged. The preserved normalize_tags profile is not
registered or added to this scope and remains policy-rejected.

## Syntax restrictions

- Only the literal attribute names `strip` and `lower` participate in the new
  string rules. Both require direct calls with zero positional/keyword arguments;
  star arguments and unbound `str.strip(value)` calls are rejected.
- Extracting or aliasing a string method is rejected, even if the alias is an
  otherwise permitted built-in name. No dynamic method selection is added.
- Single calls and the two distinct-method chains `strip().lower()` and
  `lower().strip()` are permitted. Repetition or more than two methods is rejected.
- Receivers must be names, subscripts, string literals, or those permitted chains.
  Obvious non-string literals/container expressions are rejected. Nested receiver
  calls such as `str(value).lower()` or `value.get("x").strip()` are rejected.
- Imports, classes, reflection, dynamic attribute lookup, dunder access, files,
  network/process/dynamic execution calls and unsupported attributes retain their
  existing rejections. Other existing method families are not expanded.

`string_policy.py` implements these checks and is included in the grading profile
hash. Both host and container worker validate the same rules and explicit strip
scope. Existing lower calls are tightened: method extraction, arguments and deep
chains that might previously have passed the coarse check now fail. The canonical
reviewed reference implementations continue to use direct allowed operations.

## Runtime receiver enforcement

Unknown names/subscripts may contain a non-string despite passing AST checks.
Inside Docker, after policy validation, a trusted AST transformation replaces
accepted string calls with a reserved helper call. The helper requires
`builtins.type(value) is builtins.str` and dispatches explicitly to the original
`builtins.str.strip` or `builtins.str.lower`. It never performs arbitrary getattr
or calls a receiver-supplied method. Wrong receiver types produce a controlled
TypeError before method dispatch. Candidate rebinding of `str` cannot replace the
trusted built-in used by this helper.

The injected helper's dunder name is forbidden in original candidate ASTs.
Attribute extraction, reflection and dynamic namespace access remain prohibited;
candidate globals do not include the worker's modules, request, expected results
or grader. The transformed tree is compiled and executed only inside the existing
restricted Docker worker. Source is never compiled/executed on Windows. Worker
source and the string rules are covered by fresh in-process profile verification.

The method rules, guard, namespace separation and Docker restrictions work
together. This is not a proof that AST validation alone is safe, an arbitrary
Python execution service, or an authorization token in a saved report. Existing
CPU, memory, PID, output and wall limits still apply to expensive operations.

## Deterministic tests

Thirteen new unit tests cover direct/chain/literal/subscript syntax, explicit
strip scope, arguments/keywords/star arguments, unsupported attributes, method
aliases, dynamic lookup/reflection, literal non-string receivers, runtime-only
type uncertainty, excessive nesting, existing security rejections, trusted
bootstrap contents and grading-profile invalidation.

The targeted 71-test suite passed with required disposable-file permissions.
The initial sandboxed run had seven edit-dependent assertion failures; the
controller could not apply temporary edits in that environment. Both logs are
preserved as `runs/step40_targeted_tests.log` and
`runs/step40_targeted_verified_tests.log`. No assertion or security requirement
was relaxed for the passing run.
The separate mocked diagnosis in `runs/step40_sandbox_edit_diagnosis.json`
records the actual `WinError 5` atomic replacement failure; it executed no code.

## Controlled Docker verification

`runs/step40_run_references.py` contains the exact handwritten trusted reference
sources and expected statuses. It does not read preserved candidate source into
its execution list. Fresh readiness/inventory and all eleven mandatory real
isolation probes precede any reference execution. Probe or unexpected runtime/
verification failures stop the run; no failed reference is retried.

Checks cover direct strip/lower, both chain orders, subscript/literal receivers,
candidate rebinding of str, actual guarded runtime errors for integer/list/dict
receivers, and pre-dispatch policy rejections for arguments, keywords, dynamic
lookup, method aliases, upper, excessive chains, unsafe nested calls, the reserved
guard name and non-string literals. All five existing trusted references are also
run under the modified worker, preserving their original expected results.

Complete sources, per-vector results, policy diagnostics, stdout/stderr, runtime
identity/profile checks and cleanup observations are retained in ignored
`runs/step40_reference_integration.json` with its log. These are trusted reference
results, not functional grades for the preserved model candidates.

Actual controlled integration: **24/24 expected outcomes passed**, following
**11/11 fresh real isolation probes**. Fifteen reference jobs ran in separate
restricted containers. There were **50 passing value/type/input-preservation
observations**, including all **29/29 canonical reference vectors**, plus **nine
expected TypeError observations** across the integer/list/dict guard cases.
The nine rejection checks dispatched no container job. Those expected runtime
errors are test coverage, not failed or retried preserved candidates. Each
executed reference retained matched post-execution verification and independently
verified removal. No unexpected execution/isolation failure occurred.

## Limitations and next review

Only zero-argument strip/lower and the reviewed chain forms are covered. General
method calls, static type inference, arbitrary string transformations and
receiver subclasses are not introduced. Unknown receiver types are rejected at
runtime, not claimed as statically proven. The new guard applies to these two
methods; other legacy method families have not received a new comprehensive
type-policy review in this milestone.

A future normalize_tags profile still needs explicit registration/scope review
and a host-side fresh-list identity assertion before any execution proposal.
Preserved candidates must retain exact original source hashes and require
separate explicit user approval. No such candidate permission is granted here.
The historical runtime-verification anomaly remains unresolved.

## Final validation

The full trusted regression suite passed **370/370 tests** in **486.980 seconds**,
including the thirteen new string-policy tests. Final provenance checks confirmed
that the Step 38B report and all preserved snapshot hashes are unchanged. All
three normalize_tags candidates remain policy-rejected and unregistered. No
temporary Git editing staging remained, and the final bounded read-only readiness
check plus separate mandatory inventory definitively confirmed zero containers.

Evidence: `runs/step40_completion.json`, `runs/step40_full_regression_evidence.json`
and their companion logs. Reference execution results remain separate from
preserved-candidate grades. No live generated-code flag was enabled, and original
task fixtures, default model, interactive tools, six-operation budget, pinned
image, Docker restrictions and source-application permissions are unchanged.
Historical intermittent staging failures are not explained by this passing run.
