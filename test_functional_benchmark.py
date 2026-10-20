"""Live-run orchestration tests with explicit model/transport test doubles."""
import copy
import unittest
from unittest.mock import patch

from evaluations import benchmark_functional as benchmark
from evaluations import evaluate_functional as controller
from evaluations.functional_harness import FunctionalHarness
from evaluations.functional_validation import assess_candidate, CASE_ROOT, load_tasks
from evaluations.worker_test_cases import REFERENCE_SOURCES
from test_functional_worker import FakeBackend


def generated(task_id, **kwargs):
    task = controller.task_by_id(task_id)
    source = REFERENCE_SOURCES[task_id]
    original = (CASE_ROOT / task['filename']).read_text(encoding='utf-8-sig')
    return {**controller.empty_telemetry(), **assess_candidate(original, source, task),
            'task': task_id, 'candidate_source': source, 'model_requests': 2,
            'tool_calls': 3, 'native_calls_dispatched': 2, 'recovered_json_calls': 1,
            'successful_edits': 1, 'retry_prompts': 1, 'verified_by_agent': True,
            'budget_remaining': 3}


class FunctionalBenchmarkTests(unittest.TestCase):
    def setUp(self):
        # Test doubles only; production live entry points remain disabled.
        for mock in (patch.object(benchmark, 'DockerExecutionBackend', FakeBackend),
                     patch.object(FakeBackend, 'image', benchmark.PINNED_IMAGE, create=True)):
            mock.start()
            self.addCleanup(mock.stop)

    def test_unresolved_incident_disables_live_api_and_cli(self):
        with patch.object(benchmark, 'LIVE_EVALUATION_ENABLED', False), \
                patch('ollama.Client', side_effect=AssertionError('No model access')), \
                patch.object(FunctionalHarness, 'prepare', side_effect=AssertionError('No live preparation')):
            result, calls, _ = self.run_fake(authorization=None)
            calls.assert_not_called()
            self.assertEqual(result['status'], 'incomplete')
            self.assertIn('Live evaluation disabled', result['error'])
            self.assertEqual(benchmark.main([]), 2)

    def run_fake(self, implementation=generated, backend=None, authorization='fresh'):
        saved = []
        worker = FunctionalHarness(backend or FakeBackend())
        with patch.object(controller, 'one_functional_case', side_effect=implementation) as calls:
            result = benchmark.run_benchmark(chat_fn=object(), harness=worker,
                                             model_metadata={'test_double': True},
                                             authorization=benchmark.OneRunAuthorization() if authorization == 'fresh' else authorization,
                                             save=lambda r: saved.append(copy.deepcopy(r)))
        return result, calls, saved

    def test_five_tasks_once_and_29_independent_vectors(self):
        result, calls, saved = self.run_fake()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([c.args[0] for c in calls.call_args_list], [t['id'] for t in load_tasks()])
        self.assertEqual(result['summary']['vectors_passed'], 29)
        self.assertEqual(result['summary']['vectors_executed'], 29)
        self.assertEqual(result['summary']['overall_task_success_rate'], 1)
        self.assertEqual(result['summary']['average_model_tool_calls'], 3)
        self.assertEqual(result['summary']['recovered_json_calls'], 5)
        self.assertTrue(result['protected_files_unchanged'])
        self.assertTrue(any(r['results'] and r['results'][-1]['status'] == 'generating' for r in saved))
        self.assertTrue(all(r['model_invoked'] for r in result['results']))
        self.assertEqual(result['authorization']['state'], 'expired')
        self.assertFalse(benchmark.LIVE_EVALUATION_ENABLED)

    def test_authorization_cannot_be_reused_after_completion_or_abort(self):
        for successful in (True, False):
            backend = FakeBackend()
            permit = benchmark.OneRunAuthorization()
            backend.verified = successful
            first, _, _ = self.run_fake(backend=backend, authorization=permit)
            self.assertEqual(first['authorization']['state'], 'expired')
            second, calls, _ = self.run_fake(authorization=permit)
            calls.assert_not_called()
            self.assertEqual(second['authorization']['state'], 'expired')
            self.assertIn('consumed or expired', second['error'])

    def test_scope_changes_or_unpinned_backend_are_rejected_before_model(self):
        backend = FakeBackend()
        backend.image = 'python:latest'
        result, calls, _ = self.run_fake(backend=backend)
        calls.assert_not_called()
        self.assertEqual(result['authorization']['state'], 'expired')
        tasks = copy.deepcopy(load_tasks())
        tasks[0]['tests'][0]['expected'] = 999
        with patch.object(benchmark, 'load_tasks', return_value=tasks):
            result, calls, _ = self.run_fake()
        calls.assert_not_called()
        self.assertIn('scope/policy binding mismatch', result['error'])

    def test_duplicate_out_of_order_and_cross_harness_use_rejected(self):
        worker = FunctionalHarness(FakeBackend())
        permit = benchmark.OneRunAuthorization()
        permit.claim(worker)
        with self.assertRaises(RuntimeError):
            permit.task(worker, 'clamp', 'model')
        with self.assertRaises(RuntimeError):
            permit.task(FunctionalHarness(FakeBackend()), 'sum_even', 'model')
        permit.task(worker, 'sum_even', 'model')
        with self.assertRaises(RuntimeError):
            permit.task(worker, 'sum_even', 'model')
        permit.expire()
        with self.assertRaises(RuntimeError):
            permit.task(worker, 'sum_even', 'grade')

    def test_controller_runtime_error_expires_and_stops_before_grading(self):
        def error(task_id, **kwargs):
            return {**generated(task_id), 'error': 'ConnectionError: controlled model failure'}
        backend = FakeBackend()
        result, calls, _ = self.run_fake(error, backend)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result['authorization']['state'], 'expired')
        self.assertIsNone(result['summary']['overall_task_success_rate'])

    def test_report_write_failure_still_expires_authorization(self):
        permit = benchmark.OneRunAuthorization()
        with self.assertRaises(OSError):
            benchmark.run_benchmark(chat_fn=object(), harness=FunctionalHarness(FakeBackend()),
                authorization=permit, model_metadata={}, save=lambda r: (_ for _ in ()).throw(OSError('disk failure')))
        self.assertEqual(permit.state, 'expired')

    def test_changed_fixture_fingerprint_blocks_even_fresh_authorization(self):
        with patch.object(benchmark, 'fixture_hash', return_value='changed'):
            result, calls, _ = self.run_fake()
        calls.assert_not_called()
        self.assertEqual(result['authorization']['state'], 'expired')

    def test_worker_runtime_failure_stops_remaining_tasks_and_expires(self):
        for status in ('runtime_error', 'timeout', 'result_error'):
            with self.subTest(status=status):
                grade = {'worker': {'status': status, 'passed': False, 'planned': 5, 'executed': 0,
                                    'passed_count': 0}, 'functional_tests': {},
                         'requested_change_confirmed': False, 'requested_change_status': 'not_demonstrated'}
                with patch.object(controller, 'grade_candidate_offline', return_value=grade):
                    result, calls, _ = self.run_fake()
                self.assertEqual(calls.call_count, 1)
                self.assertEqual(result['authorization']['state'], 'expired')
                self.assertIsNone(result['summary']['overall_task_success_rate'])

    def test_security_failure_prevents_any_model_call(self):
        backend = FakeBackend()
        backend.verified = False
        result, calls, _ = self.run_fake(backend=backend)
        calls.assert_not_called()
        self.assertEqual(result['status'], 'incomplete')
        self.assertIsNone(result['summary']['overall_task_success_rate'])
        self.assertEqual(result['summary']['vectors_executed'], 0)

    def test_partial_error_does_not_retry_or_invent_score(self):
        def fail_second(task_id, **kwargs):
            if task_id == load_tasks()[1]['id']:
                raise ConnectionError('model unavailable')
            return generated(task_id)
        result, calls, _ = self.run_fake(fail_second)
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(result['summary']['vectors_passed'], 5)
        self.assertEqual(result['summary']['tasks_graded'], 1)
        self.assertIsNone(result['summary']['overall_task_success_rate'])
        self.assertIn('model unavailable', result['error'])
        self.assertEqual(len(result['unattempted_tasks']), 3)

    def test_boundary_failure_retains_exact_reason_and_completed_grade(self):
        backend = FakeBackend()
        original = backend.verify
        count = 0

        def verify():
            nonlocal count
            count += 1
            report = original()
            if count == 6:
                report.update(verified=False, reason='TEST DOUBLE metadata command incomplete')
            return report

        backend.verify = verify
        result, calls, _ = self.run_fake(backend=backend)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(result['summary']['vectors_passed'], 5)
        self.assertEqual(result['status'], 'incomplete')
        failure = result['verification_boundaries'][-1]
        self.assertEqual(failure['stage'], 'after_grading')
        self.assertFalse(failure['accepted'])
        self.assertIn('metadata command incomplete', failure['verification']['reason'])

    def test_keyboard_interrupt_checkpoints_without_resuming(self):
        def interrupted(task_id, **kwargs):
            raise KeyboardInterrupt()
        result, calls, saved = self.run_fake(interrupted)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(result['status'], 'interrupted')
        self.assertIsNone(result['summary']['overall_task_success_rate'])
        self.assertEqual(saved[-1]['status'], 'interrupted')

    def test_policy_rejection_is_scored_without_execution_or_retry(self):
        def unsafe(task_id, **kwargs):
            row = generated(task_id)
            row['candidate_source'] = 'import os\n' + row['candidate_source']
            return row
        backend = FakeBackend()
        result, calls, _ = self.run_fake(unsafe, backend)
        self.assertEqual(calls.call_count, 5)
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result['summary']['vectors_executed'], 0)
        self.assertEqual(result['summary']['overall_task_success_rate'], 0)
        self.assertEqual(result['summary']['grading_status_counts'], {'policy_rejected': 5})

    def test_budget_violation_fails_closed_before_execution(self):
        def over_budget(task_id, **kwargs):
            return {**generated(task_id), 'tool_calls': 7}
        backend = FakeBackend()
        result, calls, _ = self.run_fake(over_budget, backend)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result['status'], 'incomplete')

    def test_grading_integrity_failure_stops_remaining_tasks(self):
        backend = FakeBackend()
        backend.run_verified_worker = lambda program: {'status': 'failed'}
        result, calls, _ = self.run_fake(backend=backend)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['results'][0]['worker']['status'], 'execution_error')
        self.assertIsNone(result['summary']['overall_task_success_rate'])

    def test_evidence_required_for_each_mandatory_probe(self):
        evidence = FakeBackend().verify()
        evidence['security_checks']['cleanup']['evidence'] = ''
        self.assertFalse(benchmark.security_ready(evidence))
        del evidence['security_checks']['cleanup']
        self.assertFalse(benchmark.security_ready(evidence))

    def test_real_controller_to_worker_bridge_without_host_execution(self):
        from ollama import ChatResponse

        def chat(**kwargs):
            task = next(t for t in load_tasks() if t['filename'] in kwargs['messages'][0]['content'])
            if kwargs['messages'][-1]['role'] == 'user':
                original = (CASE_ROOT / task['filename']).read_text(encoding='utf-8-sig')
                calls = [
                    {'function': {'name': 'edit_workspace_file', 'arguments': {
                        'filename': task['filename'], 'old_text': original,
                        'new_text': REFERENCE_SOURCES[task['id']]}}},
                    {'function': {'name': 'check_python_syntax', 'arguments': {'filename': task['filename']}}},
                ]
                return ChatResponse(message={'role': 'assistant', 'content': '', 'tool_calls': calls})
            return ChatResponse(message={'role': 'assistant', 'content': 'Done'})

        # Neither chat nor the fake transport executes candidate Python here.
        result = benchmark.run_benchmark(chat_fn=chat, harness=FunctionalHarness(FakeBackend()),
                                         model_metadata={'test_double': True}, authorization=benchmark.OneRunAuthorization())
        self.assertEqual(result['summary']['vectors_passed'], 29)
        self.assertEqual(result['summary']['model_tool_calls'], 10)
        self.assertEqual(result['summary']['agent_syntax_verified'], 5)
        self.assertEqual(result['summary']['controller_syntax_valid'], 5)
        self.assertTrue(all(r['budget_remaining'] == 4 for r in result['results']))

    def test_lost_verification_between_tasks_prevents_next_model_request(self):
        backend = FakeBackend()
        original = backend.run_verified_worker

        def invalidate(program):
            result = original(program)
            backend.verified = False
            return result

        backend.run_verified_worker = invalidate
        result, calls, _ = self.run_fake(backend=backend)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(result['status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
