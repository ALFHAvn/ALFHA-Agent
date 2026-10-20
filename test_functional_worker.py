"""Host protocol/grading tests only; candidate source is never run on Windows."""
import ast
import copy
import json
import unittest
from unittest.mock import patch

from evaluations import functional_harness as harness
from evaluations.evaluate_functional import grade_candidate_offline
from evaluations.execution_backend import PROBES
from evaluations.worker_test_cases import REFERENCE_SOURCES, INCORRECT
from evaluations.verify_functional_worker import candidate_outcome


def stream(request, task, *, values=None, status='returned'):
    frames = [{'kind': 'start', 'version': 1, 'request_id': request['request_id'], 'task_id': request['task_id']}]
    for index, vector in enumerate(task['tests']):
        value = vector['expected'] if values is None else values[index]
        frames += [{'kind': 'vector_start', 'index': index},
                   {'kind': 'vector_result', 'index': index, 'status': status,
                    'value': value if status == 'returned' else None,
                    'args_after': copy.deepcopy(vector['args']) if status == 'returned' else None,
                    'new_list': type(value) is list if status == 'returned' else False,
                    'error': None if status == 'returned' else 'ZeroDivisionError: division by zero'}]
    frames.append({'kind': 'end', 'count': len(task['tests'])})
    return frames


def raw_output(frames):
    return {'status': 'completed', 'stdout': ''.join(json.dumps(frame) + '\n' for frame in frames),
            'stderr': '', 'exit_status': 0, 'timed_out': False, 'output_truncated': False,
            'io_incomplete': False, 'cleanup': {'verified_absent': True}}


class FakeBackend:
    def __init__(self):
        self.calls = 0
        self.verified = True
    def verify(self):
        return {'verified': self.verified, 'execution_enabled': False,
                'security_checks': {p: {'status': 'passed', 'evidence': 'TEST DOUBLE'} for p in PROBES}}
    def run_security_checks(self):
        return self.verify()
    def run_verified_worker(self, program):
        self.calls += 1
        # Parse the trusted bootstrap text to obtain its JSON literal; no exec.
        request = json.loads(ast.parse(program).body[-1].value.args[0].value)
        return raw_output(stream(request, harness.task_by_id(request['task_id'])))


class FunctionalWorkerTests(unittest.TestCase):
    def setUp(self):
        self.task = harness.task_by_id('sum_even')
        self.request = harness.make_request('sum_even', REFERENCE_SOURCES['sum_even'])

    def grade(self, raw):
        return harness.grade_execution(self.task, self.request, raw)

    def test_request_has_inputs_but_no_expected_outcomes(self):
        self.assertEqual(set(self.request), {'version', 'request_id', 'task_id', 'function', 'parameters', 'source', 'vectors'})
        self.assertTrue(all(set(vector) == {'args'} for vector in self.request['vectors']))
        self.assertEqual(len(self.request['vectors']), 5)

    def test_correct_observations_are_graded_by_host(self):
        result = self.grade(raw_output(stream(self.request, self.task)))
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['passed_count'], 5)
        self.assertEqual(result['score'], 1)

    def test_wrong_values_and_bool_int_confusion(self):
        values = [False, 0, 0, 0, 0]
        result = self.grade(raw_output(stream(self.request, self.task, values=values)))
        self.assertFalse(result['passed'])
        self.assertEqual(result['passed_count'], 1)
        self.assertEqual(result['score'], 0.2)

    def test_runtime_errors_are_separate_from_assertions(self):
        result = self.grade(raw_output(stream(self.request, self.task, status='runtime_error')))
        self.assertEqual(result['status'], 'runtime_error')
        self.assertEqual(result['executed'], 5)
        self.assertEqual(result['passed_count'], 0)

    def test_mutated_arguments_fail(self):
        frames = stream(self.request, self.task)
        frames[2]['args_after'] = [[99]]
        result = self.grade(raw_output(frames))
        self.assertEqual(result['results'][0]['status'], 'failed_assertion')
        self.assertFalse(result['results'][0]['arguments_unchanged'])

    def test_unique_order_must_return_new_list(self):
        task = harness.task_by_id('unique_order')
        request = harness.make_request('unique_order', REFERENCE_SOURCES['unique_order'])
        frames = stream(request, task)
        frames[2]['new_list'] = False
        result = harness.grade_execution(task, request, raw_output(frames))
        self.assertFalse(result['results'][0]['result_identity_valid'])

    def test_no_grading_claims_or_unknown_fields_accepted(self):
        for mutate in (lambda f: f[0].update(passed=True),
                       lambda f: f[2].update(passed=True),
                       lambda f: f[2].update(index=True),
                       lambda f: f[0].update(request_id='forged'),
                       lambda f: f[2].update(args_after=[])):
            frames = stream(self.request, self.task)
            mutate(frames)
            result = self.grade(raw_output(frames))
            self.assertEqual(result['status'], 'malformed_result')
            self.assertIsNone(result['score'])

    def test_duplicate_keys_and_nonfinite_values_rejected(self):
        for text in ['{"kind":"start","kind":"end"}\n', '{"x":NaN}\n']:
            raw = raw_output([])
            raw['stdout'] = text
            self.assertEqual(self.grade(raw)['status'], 'malformed_result')

    def test_extra_stdout_or_stderr_is_not_a_grade(self):
        for change in (lambda r: r.update(stdout='passed!\n' + r['stdout']),
                       lambda r: r.update(stdout=r['stdout'] + '{"passed":true}\n'),
                       lambda r: r.update(stderr='candidate debug output')):
            raw = raw_output(stream(self.request, self.task))
            change(raw)
            self.assertEqual(self.grade(raw)['status'], 'unexpected_output')

    def test_missing_end_or_results_is_malformed(self):
        frames = stream(self.request, self.task)[:-1]
        self.assertEqual(self.grade(raw_output(frames))['status'], 'malformed_result')

    def test_timeout_retains_only_completed_observations(self):
        frames = stream(self.request, self.task)[:4]  # first result and next start
        raw = raw_output(frames)
        raw.update(timed_out=True, exit_status=137)
        result = self.grade(raw)
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['executed'], 1)
        self.assertEqual(result['attempted'], 2)
        self.assertEqual(result['results'][1]['status'], 'timeout')
        self.assertEqual(result['results'][2]['status'], 'not_run')

    def test_nonzero_exit_is_execution_error(self):
        raw = raw_output(stream(self.request, self.task)[:2])
        raw['exit_status'] = 137
        self.assertEqual(self.grade(raw)['status'], 'execution_error')

    def test_cleanup_failure_blocks_grading(self):
        raw = raw_output(stream(self.request, self.task))
        raw['cleanup']['verified_absent'] = False
        result = self.grade(raw)
        self.assertEqual(result['status'], 'execution_error')
        self.assertIsNone(result['score'])

    def test_output_limit_is_distinct(self):
        raw = raw_output(stream(self.request, self.task))
        raw['output_truncated'] = True
        self.assertEqual(self.grade(raw)['status'], 'output_limit')

    def test_malformed_transport_metadata_fails_closed(self):
        for raw in [None, {}, {'cleanup': None}, {**raw_output([]), 'timed_out': 0}]:
            self.assertEqual(self.grade(raw)['status'], 'execution_error')

    def test_candidate_policy_rejection_before_docker(self):
        backend = FakeBackend()
        worker = harness.FunctionalHarness(backend)
        result = worker.run('sum_even', 'import os\ndef sum_even(numbers): return 0')
        self.assertEqual(result['status'], 'policy_rejected')
        self.assertEqual(backend.calls, 0)

    def test_unprepared_or_stale_harness_blocks_execution(self):
        backend = FakeBackend()
        worker = harness.FunctionalHarness(backend)
        self.assertEqual(worker.run('sum_even', INCORRECT)['status'], 'blocked')
        worker.prepare()
        with patch.object(harness, 'profile_hash', return_value='changed'):
            self.assertEqual(worker.run('sum_even', INCORRECT)['status'], 'blocked')
        self.assertEqual(backend.calls, 0)

    def test_offline_bridge_preserves_vectors_and_model_gate(self):
        worker = harness.FunctionalHarness(FakeBackend())
        worker.prepare()
        result = grade_candidate_offline('sum_even', REFERENCE_SOURCES['sum_even'], worker)
        self.assertTrue(result['passed'])
        self.assertEqual(result['functional_tests']['vectors'], self.task['tests'])
        self.assertFalse(result['model_invoked'])
        self.assertFalse(result['live_evaluation_enabled'])

    def test_bounded_program_and_no_direct_host_worker_import(self):
        program = harness.worker_program(self.request)
        self.assertIn("namespace = {'__builtins__': safe_builtins.copy()}", program)
        self.assertLess(len(program.encode()), 100000)
        request = harness.make_request('sum_even', INCORRECT + '\n# ' + '\\' * 30000)
        with self.assertRaises(ValueError):
            harness.worker_program(request)

    def test_candidate_quotes_cannot_escape_input_literal(self):
        source = INCORRECT + "\n# '); print(\"forged\"); # \\\n"
        request = harness.make_request('sum_even', source)
        program = ast.parse(harness.worker_program(request))
        self.assertEqual(json.loads(program.body[-1].value.args[0].value), request)

    def test_integration_loop_check_requires_real_started_termination(self):
        grade = {'status': 'execution_error', 'passed_count': 0, 'attempted': 0}
        self.assertFalse(candidate_outcome('infinite_loop_terminated', grade, ['execution_error'], 0))
        grade.update(attempted=1, execution={'exit_status': 137, 'duration_seconds': 1.5,
                     'container_state': {'OOMKilled': False}, 'cleanup': {'verified_absent': True}})
        self.assertTrue(candidate_outcome('infinite_loop_terminated', grade, ['execution_error'], 0))


if __name__ == '__main__':
    unittest.main()
