"""Step 25: isolated syntax-repair evaluation with strict JSON edit recovery.

Run: .venv/Scripts/python.exe evaluations/evaluate_agent.py
Requires Ollama and qwen3:4b. No generated Python is executed.
"""
import ast
import hashlib
import importlib.util
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
    except (SyntaxError, UnicodeError, OSError, ValueError):
        return False


def parse_proposal(text):
    """Accept one complete JSON object, optionally in a JSON code fence.

    No substring extraction, Python literals, duplicate keys, or argument coercion.
    Authorization and edit validation happen separately before dispatch.
    """
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    if not isinstance(text, str) or len(text.encode("utf-8")) > 100_000:
        raise ValueError("Proposal must be text under 100 KB")
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4]
    proposal = json.loads(text, object_pairs_hook=unique)
    if not isinstance(proposal, dict) or set(proposal) != {"name", "arguments"}:
        raise ValueError("Expected exactly name and arguments")
    if proposal["name"] != "edit_workspace_file":
        raise ValueError("Only edit proposals can be recovered")
    return proposal


def validate_call(name, args, filename, initially_valid):
    schemas = {
        "read_workspace_file": {"filename"},
        "check_python_syntax": {"filename"},
        "edit_workspace_file": {"filename", "old_text", "new_text"},
    }
    if not isinstance(name, str) or name not in schemas:
        return "Error: Tool not permitted in evaluation"
    if (not isinstance(args, dict) or set(args) != schemas[name]
            or not all(isinstance(value, str) for value in args.values())):
        return "Error: Invalid tool arguments (exact string fields required)"
    if args["filename"] != filename:
        return "Error: Only the current evaluation file is authorized"
    if name == "edit_workspace_file" and initially_valid:
        return "Error: Initially valid files must not be edited"
    return None


def one_case(case, chat_fn=None):
    """Run only read/edit/parse tools in an owned disposable directory.

    A private module instance keeps evaluation workspace state out of main.
    Generated source is parsed, never imported or executed.
    """
    case = Path(case)
    chat_fn = chat_fn or alfha.chat
    with tempfile.TemporaryDirectory(prefix="alfha-eval-") as temporary:
        workspace = Path(temporary).resolve()
        target = workspace / case.name
        target.write_bytes(case.read_bytes())
        before = sha256(target)
        initially_valid = syntax_ok(target)
        spec = importlib.util.spec_from_file_location("_alfha_evaluation", ROOT / "main.py")
        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        agent.WORKSPACE = workspace
        calls, recoveries, verifications = [], [], []
        answer, error = "", None
        verified = False
        recovery_used = False

        def dispatch(name, args, origin):
            nonlocal verified
            result = validate_call(name, args, case.name, initially_valid)
            if result is None:
                result = agent.execute_tool(name, args)
            calls.append({"tool": name, "arguments": args, "result": result,
                          "origin": origin})
            if name == "check_python_syntax":
                verified = result == f"Syntax OK: {case.name}"
            if name == "edit_workspace_file" and result.startswith("Successfully"):
                verified = False
                verifications.append({"stage": "after_edit", "syntax_valid": syntax_ok(target)})
            return result

        definitions = agent.select_tools(ALLOWED)
        messages = [
            {"role": "system", "content": (
                "You are ALFHA in an isolated syntax-repair evaluation. "
                f"Only file '{case.name}' is authorized. "
                "Read it, repair syntax with real tools, and check syntax. "
                "If already valid, do not edit. Do not execute code. "
                "Use exactly filename, old_text, new_text for edits. "
                "Never output fake tool-call JSON. Syntax is not functional correctness."
            )},
            {"role": "user", "content": f"Inspect {case.name}, fix syntax errors, and verify."},
        ]
        try:
            for _ in range(MAX_CALLS + 2):
                if len(calls) >= MAX_CALLS:
                    break
                message = chat_fn(model=agent.MODEL, messages=messages, tools=definitions).message
                messages.append(message)
                requested = message.tool_calls or []
                if not requested:
                    answer = message.content or ""
                    if not recovery_used and not initially_valid:
                        recovery_used = True
                        try:
                            proposal = parse_proposal(answer)
                            result = dispatch(proposal["name"], proposal["arguments"], "json_recovery")
                            recoveries.append({"accepted": result.startswith("Successfully"), "result": result})
                            messages.append({"role": "system", "content": (
                                "Evaluation controller processed your JSON proposal: " + result +
                                " Use real tools for further actions."
                            )})
                            continue
                        except (ValueError, TypeError) as exc:
                            recoveries.append({"accepted": False, "result": str(exc)})
                    if not verified and len(calls) < MAX_CALLS and not any(
                            isinstance(m, dict) and m.get("content") == "Use real tools to finish and verify."
                            for m in messages):
                        messages.append({"role": "system", "content": "Use real tools to finish and verify."})
                        continue
                    break
                if len(calls) + len(requested) > MAX_CALLS:
                    error = "Tool-call budget exceeded; batch not executed"
                    break
                for call in requested:
                    name, args = call.function.name, call.function.arguments
                    result = dispatch(name, args, "tool_interface")
                    messages.append({"role": "tool", "name": name, "content": result})
            else:
                error = "Response iteration limit reached"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        final_valid = syntax_ok(target)
        verifications.append({"stage": "final", "syntax_valid": final_valid})
        changed = sha256(target) != before
        edits = sum(c["tool"] == "edit_workspace_file" and c["result"].startswith("Successfully") for c in calls)
        passed = (error is None and final_valid and
                  (not changed if initially_valid else changed and edits > 0))
        return {
            "case": case.name, "initial_syntax_valid": initially_valid,
            "final_syntax_valid": final_valid, "changed": changed,
            "successful_edits": edits, "verified_by_agent": verified,
            "verified_by_controller": final_valid, "verification_results": verifications,
            "tool_calls": len(calls), "recovery_used": recovery_used,
            "recoveries": recoveries, "passed": passed, "error": error,
            "answer": answer, "trace": calls,
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
