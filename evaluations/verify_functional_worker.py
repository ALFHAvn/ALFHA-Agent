"""Explicit offline integration checks; no Ollama calls or live benchmark."""
from datetime import datetime, timezone
import json
from pathlib import Path

from .functional_harness import FunctionalHarness, make_request, worker_program, grade_execution, task_by_id
from .evaluate_functional import grade_candidate_offline
from . import worker_test_cases as cases


def candidate_outcome(name, grade, expected_status, expected_passed):
    good = grade['status'] in expected_status
    if expected_passed is not None:
        good = good and grade['passed_count'] == expected_passed
    raw = grade.get('execution')
    if raw is not None:
        good = good and raw.get('cleanup', {}).get('verified_absent') is True
    if name.startswith('reference_'):
        good = good and grade['passed'] is True and grade['executed'] == grade['planned']
    if name == 'infinite_loop_terminated':
        good = (good and grade.get('attempted') == 1 and raw is not None and
                raw.get('exit_status') == 137 and raw.get('duration_seconds', 99) < 5 and
                raw.get('container_state', {}).get('OOMKilled') is False)
    if name == 'compile_error_inside_docker':
        good = good and grade['executed'] == 0 and 'SyntaxError' in (grade.get('reason') or '')
    if name == 'aliased_eval_unavailable':
        good = (good and grade['executed'] == grade['planned'] and
                all("NameError: name 'eval'" in (r.get('error') or '') for r in grade['results']))
    if name == 'grading_print_rejected':
        good = good and 'execution' not in grade
    return bool(good)


def main():
    runs = Path(__file__).resolve().parent / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = runs / f'worker_integration_{stamp}.json'
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'model_invoked': False,
              'live_evaluation_enabled': False, 'checks': []}

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')

    worker = FunctionalHarness()
    try:
        report['isolation'] = worker.prepare()
    except Exception as exc:
        report['isolation'] = {'verified': False, 'reason': f'{type(exc).__name__}: {exc}'}
    save()
    if not report['isolation'].get('verified'):
        print('BLOCKED: current isolation verification did not pass.', flush=True)
        print(f'Report: {output}')
        return 2

    compilation_cases = [
        ('compile_only_valid', cases.REFERENCE_SOURCES['sum_even'], 'passed', True, True),
        ('compile_only_top_return', 'def sum_even(numbers):\n    total = 0\nreturn total\n', 'failed', True, False),
        ('compile_only_break', 'def sum_even(numbers):\n    break\n', 'failed', True, True),
        ('compile_only_parse_error', 'def sum_even(numbers):\n    return (\n', 'failed', False, False),
        ('compile_only_filter', 'def sum_even(numbers):\n    return filter(None, numbers)\n', 'passed', True, False),
        ('compile_only_top_raise_not_invoked', 'raise RuntimeError("MUST_NOT_EXECUTE")\ndef sum_even(numbers):\n    return 0\n', 'passed', True, False),
    ]
    for name, source, compilation, parsed, accepted in compilation_cases:
        print(f'Worker integration: {name}', flush=True)
        result = worker.compile_only('sum_even', source)
        stages = result['verification_stages']
        good = (result['status'] == 'completed' and stages['compilation']['status'] == compilation and
                stages['ast_parsing']['passed'] is parsed and stages['policy']['passed'] is accepted and
                result['candidate_executed'] is False and stages['functional_tests']['status'] == 'not_run' and
                result.get('execution', {}).get('cleanup', {}).get('verified_absent') is True)
        report['checks'].append({'name': name, 'passed': bool(good), 'diagnostic': result})
        save()

    def candidate_check(name, task_id, source, expected_status, expected_passed=None):
        print(f'Worker integration: {name}', flush=True)
        assessment = grade_candidate_offline(task_id, source, worker)
        grade = assessment['worker']
        good = candidate_outcome(name, grade, expected_status, expected_passed)
        report['checks'].append({'name': name, 'passed': bool(good), 'expected_status': expected_status,
                                 'expected_passed_vectors': expected_passed, 'assessment': assessment})
        save()

    for task_id, source in cases.REFERENCE_SOURCES.items():
        candidate_check('reference_' + task_id, task_id, source, ['passed'], len(task_by_id(task_id)['tests']))
    candidate_check('incorrect_values', 'sum_even', cases.INCORRECT, ['failed'], 2)
    candidate_check('runtime_exceptions', 'sum_even', cases.EXCEPTION, ['runtime_error'], 0)
    candidate_check('infinite_loop_terminated', 'sum_even', cases.INFINITE, ['timeout', 'execution_error'], 0)
    candidate_check('input_mutation', 'sum_even', cases.MUTATING, ['failed'], 0)
    candidate_check('grading_print_rejected', 'sum_even', cases.FALSIFYING, ['policy_rejected'], 0)
    candidate_check('aliased_eval_unavailable', 'sum_even', cases.ALIASED_EVAL, ['runtime_error'], 0)
    candidate_check('unsupported_return_value', 'sum_even', cases.BAD_RESULT, ['result_error'], 0)
    candidate_check('compile_error_inside_docker', 'sum_even', 'def sum_even(numbers):\n    break\n', ['execution_error'], 0)

    task = task_by_id('sum_even')
    request = make_request('sum_even', cases.REFERENCE_SOURCES['sum_even'])
    program = worker_program(request)
    # Trusted diagnostics deliberately corrupt the wire stream. They run only in
    # the same restricted Docker environment; host schema grading must reject it.
    diagnostics = [
        ('forged_grade_frame', 'print(\'{"passed":true}\')\n', 'malformed_result'),
        ('unexpected_stdout', 'print("noise")\n' + program, 'unexpected_output'),
        ('unexpected_stderr', 'import sys\nsys.stderr.write("noise")\n' + program, 'unexpected_output'),
        ('extra_grade_after_end', program + '\nprint(\'{"passed":true}\')\n', 'unexpected_output'),
        ('wall_timeout_classification', 'import time\ntime.sleep(30)\n' + program, 'timeout'),
        ('output_flood', 'import sys\nsys.stdout.write("x" * 262144)\nsys.stdout.flush()\n' + program, 'output_limit'),
    ]
    for name, wire_program, expected in diagnostics:
        print(f'Worker integration: {name}', flush=True)
        try:
            raw = worker.backend.run_verified_worker(wire_program)
            grade = grade_execution(task, request, raw)
            good = grade['status'] == expected and grade['passed'] is False and raw['cleanup']['verified_absent'] is True
            entry = {'name': name, 'passed': bool(good), 'expected_status': expected, 'grade': grade, 'execution': raw}
        except Exception as exc:
            entry = {'name': name, 'passed': False, 'error': f'{type(exc).__name__}: {exc}'}
        report['checks'].append(entry)
        save()
    report['summary'] = {
        'checks': len(report['checks']), 'passed': sum(c['passed'] for c in report['checks']),
        'reference_vectors_passed': sum(c['assessment']['worker']['passed_count'] for c in report['checks'] if c['name'].startswith('reference_')),
        'live_evaluation_enabled': False,
    }
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    print(report['summary'])
    print(f'Report: {output}')
    return 0 if report['summary']['passed'] == report['summary']['checks'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
