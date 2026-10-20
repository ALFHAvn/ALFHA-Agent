"""Non-executing controller/diagnostic tests. Docker responses are test doubles."""
import ast
import copy
import json
import sys
import unittest

from evaluations import evaluate_functional as functional
from evaluations import functional_harness as harness
from evaluations import functional_validation as policy
from evaluations.worker_test_cases import REFERENCE_SOURCES
import test_functional_evaluation as functional_tests
from test_functional_evaluation import response
from test_functional_worker import FakeBackend, raw_output, stream


class CompilationBackend(FakeBackend):
    def __init__(self):
        super().__init__()
        self.failure = None
        self.mutate = lambda raw: None
        self.request = None

    def run_verified_worker(self, program):
        self.calls += 1
        self.request = json.loads(ast.parse(program).body[-1].value.args[0].value)
        frame = {'kind': 'compilation_result', 'version': 1, 'request_id': self.request['request_id'],
                 'task_id': self.request['task_id'], 'status': 'failed' if self.failure else 'passed', 'error': self.failure}
        raw = raw_output([frame])
        self.mutate(raw)
        return raw


class ActionableFeedbackTests(unittest.TestCase):
    def run_case(self, replies, task_id='sum_even'):
        return functional_tests.FunctionalEvaluationTests().run_case(replies, task_id)

    def edit(self):
        return functional_tests.FunctionalEvaluationTests().edit()

    def test_each_missing_edit_argument_is_named_and_rejected(self):
        tool, args = self.edit()
        for missing in args:
            with self.subTest(missing=missing):
                bad = {k: v for k, v in args.items() if k != missing}
                result = self.run_case([response(calls=[(tool, bad)])])
                self.assertFalse(result['changed'])
                self.assertIn('Missing: ' + missing, result['trace'][0]['result'])

    def test_content_argument_names_missing_and_unexpected_fields(self):
        result = self.run_case([response(calls=[('edit_workspace_file', {'filename': 'sum_even.py', 'content': 'BAD'})])])
        error = result['trace'][0]['result']
        self.assertIn('Missing: old_text, new_text', error)
        self.assertIn('Unexpected: "content"', error)
        self.assertNotIn('BAD', error)
        self.assertFalse(result['changed'])

    def test_wrong_types_are_not_coerced(self):
        tool, args = self.edit()
        result = self.run_case([response(calls=[(tool, {**args, 'old_text': 123})])])
        self.assertIn('Must be strings: old_text', result['trace'][0]['result'])
        self.assertFalse(result['changed'])

    def test_corrected_arguments_can_succeed_after_rejection(self):
        tool, args = self.edit()
        result = self.run_case([response(calls=[(tool, {'filename': 'sum_even.py', 'content': 'x'})]),
                                response(calls=[(tool, args)])])
        self.assertEqual(result['successful_edits'], 1)
        self.assertEqual(result['tool_calls'], 2)
        self.assertIn('"policy": "accepted"', result['trace'][1]['result'])

    def test_literal_newlines_are_diagnosed_without_conversion_or_repeated_edits(self):
        tool, args = self.edit()
        bad = {**args, 'old_text': args['old_text'] + r'\n'}
        result = self.run_case([response(calls=[(tool, bad), (tool, bad)])])
        self.assertFalse(result['changed'])
        self.assertEqual(result['successful_edits'], 0)
        self.assertIn('Literal backslash+n', result['trace'][0]['result'])
        self.assertIn('Consecutive unsuccessful edits: 2', result['trace'][1]['result'])
        self.assertEqual(result['tool_calls'], 2)

    def test_multiple_matches_require_unique_context(self):
        tool, args = self.edit()
        first = {**args, 'new_text': '    if numbers:\n        return 0\n    return 0'}
        ambiguous = {'filename': 'sum_even.py', 'old_text': 'return 0', 'new_text': 'return 1'}
        result = self.run_case([response(calls=[(tool, first), (tool, ambiguous)])])
        self.assertEqual(result['successful_edits'], 1)
        self.assertIn('more surrounding text', result['trace'][1]['result'])
        self.assertEqual(result['candidate_source'].count('return 0'), 2)
        self.assertNotIn('return 1', result['candidate_source'])

    def test_policy_feedback_reaches_model_without_expected_outcomes(self):
        tool, args = self.edit()
        replies = iter([response(calls=[(tool, {**args, 'new_text': '    return filter(None, numbers)'})]), response('Done')])
        feedback = []

        def chat(**kwargs):
            feedback.extend(m['content'] for m in kwargs['messages'] if isinstance(m, dict) and m.get('role') == 'tool')
            return next(replies, response())

        result = functional.one_functional_case('sum_even', chat_fn=chat)
        text = '\n'.join(feedback)
        self.assertIn('"policy": "rejected"', text)
        self.assertIn('Unsupported call: filter', text)
        self.assertIn('compilation', text)
        self.assertNotIn('expected', text)
        self.assertNotIn('vectors', text)
        self.assertFalse(result['verification_stages']['policy']['passed'])

    def test_parse_error_and_compilation_unknown_are_separate(self):
        tool, args = self.edit()
        result = self.run_case([response(calls=[(tool, {**args, 'new_text': '    return ('})])])
        stages = result['verification_stages']
        self.assertEqual(stages['ast_parsing']['status'], 'failed')
        self.assertEqual(stages['compilation']['status'], 'not_run')
        self.assertIsNone(stages['compilation']['passed'])

    def test_top_level_return_diagnostic_does_not_invent_extra_function(self):
        task = functional.task_by_id('palindrome')
        source = "def is_palindrome(text):\n    cleaned = ''.join(filter(str.isalnum, text.lower()))\nreturn cleaned == cleaned[::-1]\n"
        checks = policy.validate_source(source, task)
        self.assertTrue(checks['syntax_valid'])
        self.assertFalse(checks['static_policy_passed'])
        self.assertIn('Top-level return is forbidden; indent it inside the required function', checks['diagnostics'])
        self.assertIn('Unsupported call: filter', checks['diagnostics'])
        self.assertNotIn('Nested/extra functions are unsupported', checks['diagnostics'])

    def test_actual_extra_or_nested_functions_still_rejected(self):
        for source in ('def sum_even(numbers):\n    def extra():\n        return 0\n    return 0\n',
                       'def sum_even(numbers):\n    return 0\ndef extra():\n    return 1\n'):
            checks = policy.validate_source(source, functional.task_by_id('sum_even'))
            self.assertFalse(checks['static_policy_passed'])
            self.assertIn('Nested/extra functions are unsupported', checks['diagnostics'])

    def compiler(self):
        backend = CompilationBackend()
        worker = harness.FunctionalHarness(backend)
        worker.prepare()
        return worker, backend

    def test_compile_only_reports_success_without_candidate_invocation(self):
        worker, backend = self.compiler()
        result = worker.compile_only('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['verification_stages']['compilation']['status'], 'passed')
        self.assertFalse(result['candidate_executed'])
        self.assertEqual(result['verification_stages']['functional_tests']['status'], 'not_run')
        self.assertEqual(set(backend.request), {'version', 'request_id', 'task_id', 'source'})
        self.assertNotIn('evaluations.compilation_worker', sys.modules)

    def test_parse_success_compilation_failure_is_reported_independently(self):
        worker, backend = self.compiler()
        backend.failure = "SyntaxError: 'break' outside loop"
        result = worker.compile_only('sum_even', 'def sum_even(numbers):\n    break\n')
        stages = result['verification_stages']
        self.assertTrue(stages['ast_parsing']['passed'])
        self.assertTrue(stages['policy']['passed'])
        self.assertFalse(stages['compilation']['passed'])
        self.assertEqual(stages['functional_tests']['status'], 'not_run')

    def test_unprepared_compilation_is_blocked(self):
        backend = CompilationBackend()
        result = harness.FunctionalHarness(backend).compile_only('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(backend.calls, 0)

    def test_bad_compilation_transport_or_schema_never_reports_success(self):
        mutations = [lambda r: r.update(stderr='noise'), lambda r: r.update(exit_status=False),
                     lambda r: r['cleanup'].update(verified_absent=False),
                     lambda r: r.update(stdout=r['stdout'] + 'noise'),
                     lambda r: r.update(stdout=r['stdout'].replace('"version": 1', '"version": true')),
                     lambda r: r.update(stdout=r['stdout'].replace('"error": null', '"error": null, "passed": true'))]
        for mutate in mutations:
            worker, backend = self.compiler()
            backend.mutate = mutate
            result = worker.compile_only('sum_even', REFERENCE_SOURCES['sum_even'])
            self.assertEqual(result['status'], 'execution_error')
            self.assertIsNone(result['verification_stages']['compilation']['passed'])

    def test_compilation_identity_loss_preserves_raw_evidence(self):
        worker, backend = self.compiler()
        backend.mutate = lambda raw: setattr(backend, 'verified', False)
        result = worker.compile_only('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['status'], 'execution_error')
        self.assertIn('execution', result)
        self.assertFalse(result['isolation_after']['verified'])

    def test_functional_grade_stages_distinguish_wrong_result_from_compilation(self):
        backend = FakeBackend()

        def wrong_values(program):
            request = json.loads(ast.parse(program).body[-1].value.args[0].value)
            task = harness.task_by_id(request['task_id'])
            return raw_output(stream(request, task, values=[999] * len(task['tests'])))

        backend.run_verified_worker = wrong_values
        worker = harness.FunctionalHarness(backend)
        worker.prepare()
        result = worker.run('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertTrue(result['verification_stages']['compilation']['passed'])
        self.assertTrue(result['verification_stages']['docker_execution']['candidate_invocation_attempted'])
        self.assertTrue(result['verification_stages']['docker_execution']['passed'])
        self.assertFalse(result['verification_stages']['functional_tests']['passed'])
        self.assertEqual(result['status'], 'failed')

    def test_functional_worker_compile_error_keeps_legacy_status_and_adds_stage(self):
        backend = FakeBackend()

        def compilation_error(program):
            request = json.loads(ast.parse(program).body[-1].value.args[0].value)
            return raw_output([
                {'kind': 'start', 'version': 1, 'request_id': request['request_id'], 'task_id': request['task_id']},
                {'kind': 'job_error', 'error': "SyntaxError: 'break' outside loop"}])

        backend.run_verified_worker = compilation_error
        worker = harness.FunctionalHarness(backend)
        worker.prepare()
        result = worker.run('sum_even', 'def sum_even(numbers):\n    break\n')
        self.assertEqual(result['status'], 'execution_error')
        self.assertEqual(result['failure_kind'], 'compilation_error')
        self.assertTrue(result['verification_stages']['ast_parsing']['passed'])
        self.assertFalse(result['verification_stages']['compilation']['passed'])
        self.assertEqual(result['verification_stages']['functional_tests']['status'], 'not_run')

    def test_missing_stream_is_not_reported_as_no_candidate_execution(self):
        backend = FakeBackend()
        backend.run_verified_worker = lambda program: raw_output([])
        worker = harness.FunctionalHarness(backend)
        worker.prepare()
        result = worker.run('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['status'], 'malformed_result')
        self.assertIsNone(result['verification_stages']['docker_execution']['candidate_invocation_attempted'])
        self.assertEqual(result['verification_stages']['functional_tests']['status'], 'not_observed')

    def test_postflight_failure_marks_unknown_stages_and_keeps_raw_result(self):
        backend = FakeBackend()
        original = backend.run_verified_worker

        def invalidate(program):
            raw = original(program)
            backend.verified = False
            return raw

        backend.run_verified_worker = invalidate
        worker = harness.FunctionalHarness(backend)
        worker.prepare()
        result = worker.run('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertIn('execution', result)
        self.assertEqual(result['verification_stages']['docker_execution']['status'], 'verification_failed')
        self.assertIsNone(result['verification_stages']['compilation']['passed'])


if __name__ == '__main__':
    unittest.main()
