# Step 25 evaluation controller

Run the authorized test suite:

    .venv\Scripts\python.exe -m unittest -v test_agent test_evaluation_controller

Run the live local model benchmark (Ollama must be running):

    .venv\Scripts\python.exe evaluations/evaluate_agent.py

The controller copies each case into an owned TemporaryDirectory and loads a private
instance of the trusted main module. It never changes main.WORKSPACE. Only exact
read_workspace_file, edit_workspace_file, and check_python_syntax argument schemas
are allowed, and filename must equal the current case basename. Initially valid
files cannot be edited. Existing atomic editing and unique-match checks are reused.

One JSON edit proposal may be recovered per initially invalid case. Only a complete
JSON object with exactly name and arguments is accepted, optionally fenced with
```json. Duplicate keys, extra prose, extra fields, unsupported tools, and argument
coercion are rejected. Recovery shares the six-call budget with real calls. Invalid
parsed proposals consume a call; rejected JSON parsing consumes the recovery attempt.

Every successful edit receives an independent AST syntax check; a final independent
check runs even after budget exhaustion or a model exception. The report preserves
agent verification separately from controller verification, records call origins,
recovery outcomes, successful edits, and verification stages. Passing requires final
valid syntax, no controller/model error, and a successful modifying edit for an
initially invalid case; initially valid cases must remain byte-identical. Controller
verification can satisfy this syntax benchmark without an agent verification call.
This benchmark does not measure functional correctness. Generated cases are never
executed or imported. The interactive controller in main.py is unchanged.

Validation: 20 tests passed (10 original, 10 controller tests, with 17 invalid proposal
subcases). Initial sandbox test run hit Windows access-denied errors during atomic
replacement in temporary directories; approved execution outside the sandbox passed.
No new live Ollama score is claimed by these deterministic regression tests.
