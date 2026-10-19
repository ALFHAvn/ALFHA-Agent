"""Step 24E: isolated, one-file-at-a-time ALFHA syntax-repair benchmark.

Place this file at evaluations/evaluate_agent.py in the ALFHA-Agent project.
Run from project root: python evaluations/evaluate_agent.py
Requires Ollama running and the existing Python ollama package.
"""
import ast
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main as alfha  # noqa: E402

CASES = Path(__file__).resolve().parent / "cases"
RUNS = Path(__file__).resolve().parent / "runs"
MAX_CALLS = 6
ALLOWED = {"read_workspace_file", "edit_workspace_file", "check_python_syntax"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def syntax_ok(path):
    try:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.name)
        return True
    except (SyntaxError, UnicodeError):
        return False


def one_case(case):
    """Copy a case into a disposable workspace and run real model tool calls."""
    with tempfile.TemporaryDirectory(prefix="alfha-eval-") as temporary:
        workspace = Path(temporary).resolve()
        target = workspace / case.name
        target.write_bytes(case.read_bytes())
        before = sha256(target)
        initially_valid = syntax_ok(target)
        original_workspace = alfha.WORKSPACE
        calls = []
        answer = ""
        error = None
        verified = False
        recovery_used = False
        try:
            # Only one benchmark is run at a time; restore in finally.
            alfha.WORKSPACE = workspace
            definitions = alfha.select_tools(ALLOWED)
            messages = [
                {"role": "system", "content": (
                    "You are ALFHA in an isolated evaluation. "
                    f"Only file '{case.name}' is authorized. "
                    "Inspect the file, repair Python syntax errors with real tools, "
                    "and verify with check_python_syntax. "
                    "If already valid, do not edit. "
                    "Do not execute code. Never output fake tool-call JSON. "
                    "Do not claim success without verification."
                )},
                {"role": "user", "content": (
                    f"Inspect {case.name}, fix any Python syntax errors, "
                    "and verify syntax using your tools."
                )},
            ]
            # Six tool calls maximum; additional model responses cannot execute tools.
            for _ in range(MAX_CALLS + 2):
                response = alfha.chat(model=alfha.MODEL, messages=messages, tools=definitions)
                message = response.message
                messages.append(message)
                requested = message.tool_calls or []
                if not requested:
                    answer = message.content or ""
                    if not verified and not recovery_used and len(calls) < MAX_CALLS:
                        recovery_used = True
                        messages.append({"role": "system", "content": (
                            "The task is not yet verified. Use actual registered tools "
                            "to inspect, repair if needed, and verify the authorized file. "
                            "Do not merely describe the solution."
                        )})
                        continue
                    break
                if len(calls) + len(requested) > MAX_CALLS:
                    error = "Tool-call budget exceeded; batch not executed"
                    break
                for tool_call in requested:
                    name = tool_call.function.name
                    args = tool_call.function.arguments
                    if not isinstance(args, dict):
                        result = "Error: Invalid tool arguments"
                    elif name not in ALLOWED:
                        result = "Error: Tool not permitted in evaluation"
                    elif args.get("filename") != case.name:
                        result = "Error: Only the current evaluation file is authorized"
                    else:
                        result = alfha.execute_tool(name, args)
                    calls.append({"tool": name, "arguments": args, "result": result})
                    if name == "check_python_syntax" and result == f"Syntax OK: {case.name}":
                        verified = True
                    elif name == "edit_workspace_file" and result.startswith("Successfully"):
                        verified = False  # A new edit invalidates prior verification.
                    messages.append({"role": "tool", "name": name, "content": result})
            else:
                error = "Response iteration limit reached"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            alfha.WORKSPACE = original_workspace

        final_valid = syntax_ok(target)
        changed = sha256(target) != before
        edits = sum(c["tool"] == "edit_workspace_file" and c["result"].startswith("Successfully") for c in calls)
        # Existing valid code should not be changed; invalid code must be repaired and verified.
        passed = (final_valid and verified and (not changed if initially_valid else changed and edits > 0))
        return {
            "case": case.name,
            "initial_syntax_valid": initially_valid,
            "final_syntax_valid": final_valid,
            "changed": changed,
            "successful_edits": edits,
            "verified_by_agent": verified,
            "tool_calls": len(calls),
            "recovery_used": recovery_used,
            "passed": passed,
            "error": error,
            "answer": answer,
            "trace": calls,
        }


def main():
    RUNS.mkdir(parents=True, exist_ok=True)
    cases = sorted(CASES.glob("*.py"))
    if not cases:
        raise SystemExit("No .py cases found in evaluations/cases")
    results = []
    for case in cases:
        print(f"Evaluating {case.name}...", flush=True)
        result = one_case(case)
        results.append(result)
        print(f"  {'PASS' if result['passed'] else 'FAIL'} | "
              f"calls={result['tool_calls']} edits={result['successful_edits']} "
              f"verified={result['verified_by_agent']}", flush=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": alfha.MODEL,
        "total": len(results),
        "passed": sum(r["passed"] for r in results),
        "results": results,
    }
    output = RUNS / "agent_latest.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nScore: {report['passed']}/{report['total']}")
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
