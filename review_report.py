"""Reopen a bounded local review report. No generation, staging, or apply API."""
import argparse
import json
from pathlib import Path

MAX_REPORT_BYTES = 2_000_000


def load_report(path):
    # Bound reads even if the file grows. Do not follow paths stored in a report.
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError('Review report exceeds the 2 MB inspection limit')
    report = json.loads(data)
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise ValueError('Expected an interactive review report with schema_version=1')
    for key in ('status', 'run_id', 'combined_diff'):
        if not isinstance(report.get(key), str):
            raise ValueError('Missing or invalid report field: ' + key)
    return report


def render_report(report):
    # JSON escaping prevents candidate text from issuing terminal control codes.
    # Retained claims are displayed as claims, never as fresh verification.
    fields = ('run_id', 'status', 'model_requests', 'budget_used', 'budget',
              'ready_for_human_review', 'source_unchanged', 'workspace_discarded',
              'validation', 'errors', 'missing_required_changes', 'candidate_hashes',
              'combined_diff', 'final_files')
    selected = {key: report[key] for key in fields if key in report}
    return ('Saved evidence only; claims have not been reverified. No generation, '
            'execution, source application, or authorization is restored.\n' +
            json.dumps(selected, ensure_ascii=True, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', help='Exact path to the saved interactive report.json')
    args = parser.parse_args(argv)
    try:
        print(render_report(load_report(args.report)))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print('Cannot inspect report: ' + ascii(str(exc)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
