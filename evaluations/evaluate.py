
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "cases"
RUNS_DIR = BASE_DIR / "runs"


def evaluate_python_file(filename):
    """Check Python syntax without executing the file."""
    path = (CASES_DIR / filename).resolve()

    if not path.is_relative_to(CASES_DIR.resolve()):
        raise ValueError("File is outside evaluation cases.")

    if path.suffix != ".py":
        raise ValueError("Only Python files are supported.")

    if not path.is_file():
        raise FileNotFoundError(filename)

    source = path.read_text(encoding="utf-8-sig")

    try:
        ast.parse(source, filename=filename)
        return {
            "file": filename,
            "syntax_valid": True,
            "error": None,
        }
    except SyntaxError as error:
        return {
            "file": filename,
            "syntax_valid": False,
            "error": (
                f"Line {error.lineno}: {error.msg}"
            ),
        }


def main():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for path in sorted(CASES_DIR.glob("*.py")):
        result = evaluate_python_file(path.name)
        results.append(result)

        status = (
            "PASS" if result["syntax_valid"] else "FAIL"
        )
        print(f"[{status}] {path.name}")

        if result["error"]:
            print(f"       {result['error']}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "syntax_valid": sum(
            result["syntax_valid"] for result in results
        ),
        "results": results,
    }

    output = RUNS_DIR / "latest.json"
    output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"\nReport saved: {output}")


if __name__ == "__main__":
    main()
