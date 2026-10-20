"""Trusted test doubles only; recovery never invokes candidate execution."""
import copy
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from evaluations import checkpoints as cp
from evaluations import benchmark_functional as benchmark
from evaluations import evaluate_functional as controller
from evaluations.functional_harness import FunctionalHarness
from test_functional_benchmark import generated
from test_functional_worker import FakeBackend
from test_functional_evaluation import response


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'report.json'
        self.report = {'status': 'running', 'process': {'pid': 123, 'creation_id': 'old'},
                       'authorization': {'state': 'active'}, 'tasks_planned': 2,
                       'results': [{'task': 'sum_even', 'status': 'completed', 'worker': {
                           'passed': True, 'executed': 5, 'passed_count': 5, 'planned': 5}},
                                   {'task': 'clamp', 'status': 'generating'}],
                       'task_states': [{'task': 'clamp', 'state': 'running'}],
                       'summary': {'overall_task_success_rate': 1}}

    def inspect(self, report=None, probe=lambda pid: {'state': 'dead'}):
        cp.atomic_write(self.path, self.report if report is None else report)
        return cp.inspect_checkpoint(self.path, probe=probe)

    def test_atomic_roundtrip_and_no_temporary_artifacts(self):
        cp.atomic_write(self.path, self.report)
        self.assertEqual(json.loads(self.path.read_text()), self.report)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_replace_preserves_previous_checkpoint(self):
        cp.atomic_write(self.path, self.report)
        before = self.path.read_bytes()
        with patch.object(cp.os, 'replace', side_effect=OSError('interrupted replace')):
            with self.assertRaises(OSError):
                cp.atomic_write(self.path, {'new': True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_flush_preserves_previous_checkpoint(self):
        cp.atomic_write(self.path, self.report)
        with patch.object(cp.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                cp.atomic_write(self.path, {'new': True})
        self.assertEqual(json.loads(self.path.read_text()), self.report)

    def test_serialization_failure_preserves_previous_checkpoint(self):
        cp.atomic_write(self.path, self.report)
        with self.assertRaises(ValueError):
            cp.atomic_write(self.path, {'nonfinite': float('nan')})
        self.assertEqual(json.loads(self.path.read_text()), self.report)

    def test_malformed_and_partial_checkpoints_fail_closed(self):
        for payload in ('{', 'null', '[]', '{}', '{"results": [1]}', '{"results": [], "authorization": []}'):
            with self.subTest(payload=payload):
                self.path.write_text(payload)
                result = cp.inspect_checkpoint(self.path)
                self.assertEqual(result['status'], 'invalid_checkpoint')
                self.assertFalse(result['execution_authorized'])

    def test_missing_file_does_not_use_leftover_temporary(self):
        self.path.with_suffix('.tmp').write_text(json.dumps(self.report))
        self.assertEqual(cp.inspect_checkpoint(self.path)['status'], 'invalid_checkpoint')

    def test_stale_running_preserves_completed_and_unknown_outcomes(self):
        result = self.inspect()
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['inspection']['effective_authorization'], 'expired_by_process_termination')
        self.assertEqual(result['summary']['vectors_passed'], 5)
        self.assertEqual(result['outcomes_unknown'], ['clamp'])
        self.assertEqual(result['task_states'][1]['state'], 'interrupted')
        self.assertIsNone(result['summary']['overall_task_success_rate'])

    def test_pid_reuse_is_not_a_live_owner(self):
        result = self.inspect(probe=lambda pid: {'state': 'observed', 'creation_id': 'new'})
        self.assertEqual(result['status'], 'interrupted')

    def test_matching_live_owner_still_cannot_authorize_inspection(self):
        result = self.inspect(probe=lambda pid: {'state': 'observed', 'creation_id': 'old'})
        self.assertEqual(result['status'], 'running')
        self.assertFalse(result['inspection']['execution_authorized'])
        self.assertFalse(result['inspection']['resumable'])

    def test_unknown_owner_never_claims_confirmed_process_termination(self):
        result = self.inspect(probe=lambda pid: {'state': 'unknown'})
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['inspection']['owner_liveness'], 'unknown')
        self.assertNotEqual(result['inspection']['effective_authorization'], 'expired_by_process_termination')

    def test_repeated_inspection_never_changes_evidence_or_executes(self):
        cp.atomic_write(self.path, self.report)
        before = self.path.read_bytes()
        with patch.object(benchmark, 'OneRunAuthorization', side_effect=AssertionError('no permit')), \
                patch.object(controller, 'one_functional_case', side_effect=AssertionError('no model')), \
                patch.object(FunctionalHarness, 'run', side_effect=AssertionError('no code')):
            for _ in range(3):
                result = cp.inspect_checkpoint(self.path, probe=lambda pid: {'state': 'dead'})
                self.assertFalse(result['inspection']['execution_authorized'])
        self.assertEqual(before, self.path.read_bytes())

    def test_expired_authorization_cannot_be_recreated(self):
        self.report['authorization']['state'] = 'expired'
        result = self.inspect()
        self.assertEqual(result['authorization']['state'], 'expired')
        self.assertFalse(result['inspection']['resumable'])

    def test_completed_status_without_outcome_is_unknown(self):
        self.report['status'] = 'completed'
        self.report['authorization']['state'] = 'expired'
        self.report['results'][1]['status'] = 'completed'
        result = self.inspect()
        self.assertEqual(result['outcomes_unknown'], ['clamp'])
        self.assertEqual(result['task_states'][1]['state'], 'interrupted')
        self.assertIsNone(result['summary']['overall_task_success_rate'])

    def test_malformed_grading_or_duplicate_tasks_rejected(self):
        for mutate in (lambda r: r['results'][0].update(worker={}),
                       lambda r: r['results'].append(r['results'][0])):
            report = copy.deepcopy(self.report)
            mutate(report)
            self.assertEqual(self.inspect(report)['status'], 'invalid_checkpoint')

    def test_unavailable_process_probe_preserves_unknown_liveness(self):
        def unavailable(pid):
            raise OSError('access denied')
        result = self.inspect(probe=unavailable)
        self.assertEqual(result['inspection']['owner_liveness'], 'unknown')
        self.assertFalse(result['inspection']['execution_authorized'])

    def test_current_process_identity_is_stable(self):
        self.assertEqual(cp.process_identity(), cp.process_identity(os.getpid()))
        self.assertTrue(cp.process_identity().get('creation_id'))

    def test_hard_kill_during_replace_preserves_previous_complete_file(self):
        cp.atomic_write(self.path, self.report)
        marker = self.path.parent / 'ready'
        # Trusted persistence test driver; no candidate source or model call.
        script = '''
import sys, time
from pathlib import Path
from evaluations import checkpoints as cp
def interrupted_replace(source, target):
    Path(sys.argv[2]).write_text('ready')
    time.sleep(30)
cp.os.replace = interrupted_replace
cp.atomic_write(sys.argv[1], {'results': [], 'status': 'running'})
'''
        process = subprocess.Popen([sys.executable, '-c', script, str(self.path), str(marker)])
        try:
            deadline = time.monotonic() + 8
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), 'test driver did not reach replacement boundary')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        self.assertEqual(json.loads(self.path.read_text()), self.report)
        self.assertTrue(list(self.path.parent.glob('*.tmp')))
        result = cp.inspect_checkpoint(self.path, probe=lambda pid: {'state': 'dead'})
        self.assertEqual(result['summary']['vectors_passed'], 5)


class OrchestrationCrashTests(unittest.TestCase):
    def run_fake(self, generate=generated, grade=None):
        saved = []
        with patch.object(benchmark, 'DockerExecutionBackend', FakeBackend), \
                patch.object(FakeBackend, 'image', benchmark.PINNED_IMAGE, create=True), \
                patch.object(controller, 'one_functional_case', side_effect=generate), \
                patch.object(controller, 'grade_candidate_offline', side_effect=grade or controller.grade_candidate_offline):
            permit = benchmark.OneRunAuthorization()
            result = benchmark.run_benchmark(chat_fn=object(), harness=FunctionalHarness(FakeBackend()),
                                             model_metadata={}, authorization=permit,
                                             save=lambda r: saved.append(copy.deepcopy(r)))
        return result, saved, permit

    def test_generation_interruption_preserves_first_grade_and_partial_progress(self):
        def generate(task_id, **kwargs):
            if task_id == 'clamp':
                kwargs['progress']({'event': 'before_model_request', 'telemetry': {'model_requests': 1}, 'complete': False})
                raise KeyboardInterrupt()
            return generated(task_id)
        result, saved, permit = self.run_fake(generate)
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual([t['state'] for t in result['task_states']],
                         ['completed', 'interrupted', 'pending', 'pending', 'pending'])
        self.assertEqual(len(result['completed_results']), 1)
        self.assertEqual(result['in_progress_telemetry'][0]['progress']['telemetry']['model_requests'], 1)
        self.assertEqual(result['summary']['vectors_passed'], 5)
        self.assertEqual(result['summary']['vectors_not_run'], 24)
        self.assertEqual(permit.state, 'expired')
        self.assertTrue(all(r['run_id'] == permit.run_id and r['checkpoint_utc'] for r in saved))
        self.assertEqual([r['checkpoint_sequence'] for r in saved], list(range(1, len(saved) + 1)))

    def test_grading_interruption_retains_candidate_without_inventing_grade(self):
        def grade(*args):
            raise KeyboardInterrupt()
        result, saved, permit = self.run_fake(grade=grade)
        self.assertEqual(result['task_states'][0]['state'], 'interrupted')
        self.assertEqual(result['task_states'][0]['phase'], 'grading')
        self.assertIn('candidate_source', result['in_progress_telemetry'][0])
        self.assertEqual(result['summary']['vectors_executed'], 0)
        self.assertEqual(permit.state, 'expired')

    def test_controller_progress_retains_response_and_edit_before_next_request(self):
        saved = []
        original = (controller.CASE_ROOT / 'sum_even.py').read_text(encoding='utf-8-sig')
        edit = response(calls=[('edit_workspace_file', {'filename': 'sum_even.py',
                        'old_text': original, 'new_text': 'def sum_even(numbers):\n    return 0\n'})])
        replies = iter([edit, KeyboardInterrupt()])
        def chat(**kwargs):
            value = next(replies)
            if isinstance(value, BaseException):
                raise value
            return value
        with self.assertRaises(KeyboardInterrupt):
            controller.one_functional_case('sum_even', chat_fn=chat, progress=saved.append)
        self.assertEqual(saved[-1]['event'], 'before_model_request')
        self.assertEqual(saved[-1]['telemetry']['model_requests'], 2)
        self.assertEqual(len(saved[-1]['telemetry']['model_responses']), 1)
        self.assertEqual(len(saved[-1]['telemetry']['trace']), 1)
        self.assertEqual(saved[-1]['telemetry']['tool_calls'], 1)
        self.assertEqual(saved[-1]['telemetry']['successful_edits'], 1)
        self.assertIn('return 0', saved[-1]['candidate_source'])

    def test_progress_write_failure_stops_without_grading_or_retry(self):
        def generation(task_id, **kwargs):
            kwargs['progress']({'event': 'before_model_request'})
            self.fail('must stop after failed checkpoint')
        saved = []
        def save(report):
            if report['in_progress_telemetry'] and 'progress' in report['in_progress_telemetry'][0] and report['status'] == 'running':
                raise OSError('checkpoint disk failure')
            saved.append(copy.deepcopy(report))
        with patch.object(benchmark, 'DockerExecutionBackend', FakeBackend), \
                patch.object(FakeBackend, 'image', benchmark.PINNED_IMAGE, create=True), \
                patch.object(controller, 'one_functional_case', side_effect=generation) as model, \
                patch.object(controller, 'grade_candidate_offline', side_effect=AssertionError('no execution')):
            permit = benchmark.OneRunAuthorization()
            result = benchmark.run_benchmark(chat_fn=object(), harness=FunctionalHarness(FakeBackend()),
                                             model_metadata={}, authorization=permit, save=save)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(permit.state, 'expired')
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['summary']['vectors_executed'], 0)
        self.assertIn('checkpoint disk failure', result['error'])


if __name__ == '__main__':
    unittest.main()
