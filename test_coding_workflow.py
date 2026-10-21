"""Mocked model, real Git staging; no candidate execution."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ollama import ChatResponse
from git_checkpoints import _git, _source_snapshot, SafetyError
from coding_workflow import run_task, validate_request


def response(*calls, text=''):
    return ChatResponse(message={'role': 'assistant', 'content': text,
                                 'tool_calls': [{'function': {'name': n, 'arguments': a}} for n, a in calls]})


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='alfha-workflow-tests-')
        self.root = Path(self.temp.name).resolve()
        _git(self.root, 'init', '--quiet', '--initial-branch=main', '--template=')
        (self.root / 'a.py').write_bytes(b'A = 1\n')
        (self.root / 'b.py').write_bytes(b'B = 2\n')
        _git(self.root, 'add', '--all')
        _git(self.root, 'commit', '--quiet', '-m', 'Baseline')
        self.reports = []

    def tearDown(self):
        import shutil, stat
        def writable(function, path, error):
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            function(path)
        for path in self.reports:
            shutil.rmtree(path.parent, onexc=writable)
        shutil.rmtree(self.root, onexc=writable)
        self.temp.cleanup()

    def request(self):
        return {'description': 'Coordinate A and B values; review only.', 'source_repository': str(self.root),
                'authorized_files': {'a.py': ['read', 'modify'], 'b.py': ['read', 'modify']},
                'validation_requirements': {'static': True, 'docker_execution': False}}

    def run_replies(self, replies, request=None):
        replies = iter(replies)
        self.messages = []
        def chat(**kwargs):
            self.assertEqual(kwargs['model'], 'qwen3:4b')
            self.messages.append(list(kwargs['messages']))
            value = next(replies)
            if isinstance(value, BaseException):
                raise value
            if callable(value):
                return value()
            return value
        report = run_task(request or self.request(), chat_fn=chat)
        self.reports.append(Path(report['report_path']))
        self.assertTrue(report['workspace_discarded'])
        self.assertEqual(json.loads(self.reports[-1].read_text()), report)
        return report

    def edits(self):
        return response(('edit_file', {'filename': 'a.py', 'old_text': 'A = 1', 'new_text': 'A = 3'}),
                        ('edit_file', {'filename': 'b.py', 'old_text': 'B = 2', 'new_text': 'B = 3'}))

    def test_two_file_workflow_preserves_source_and_durable_diff(self):
        before = _source_snapshot(self.root)
        report = self.run_replies([self.edits(), response(text='Done')])
        self.assertTrue(report['ready_for_human_review'])
        self.assertEqual(report['budget_used'], 2)
        self.assertEqual(report['review']['modified_paths'], ['a.py', 'b.py'])
        self.assertIn('+A = 3', report['review']['diff'])
        self.assertEqual(before, _source_snapshot(self.root))
        self.assertEqual(report['candidate_execution'], 'disabled')

    def test_three_file_task_with_explicit_creation(self):
        request = self.request()
        request['authorized_files']['c.json'] = ['create', 'read']
        report = self.run_replies([self.edits(), response(('create_file', {'filename': 'c.json', 'content': '{}\n'})), response(text='Done')], request)
        self.assertTrue(report['ready_for_human_review'])
        self.assertEqual(len(report['review']['modified_paths']), 3)
        self.assertFalse((self.root / 'c.json').exists())

    def test_missing_ambiguous_or_execution_authorization_rejected_before_model(self):
        for mutate in (lambda r: r.pop('description'), lambda r: r.update(authorized_files={}),
                       lambda r: r['authorized_files'].update({'a.py': []}),
                       lambda r: r['validation_requirements'].update(docker_execution=True),
                       lambda r: r['validation_requirements'].update(static=1)):
            request = self.request()
            mutate(request)
            with patch('ollama.Client', side_effect=AssertionError('No model')), self.assertRaises(SafetyError):
                run_task(request)

    def test_invalid_arguments_then_corrected_action_within_budget(self):
        invalid = response(('edit_file', {'filename': 'a.py', 'content': 'bad'}))
        report = self.run_replies([invalid, self.edits(), response(text='Done')])
        self.assertEqual(report['trace'][0]['status'], 'rejected')
        self.assertIn('Expected exactly', report['trace'][0]['error'])
        self.assertEqual(report['budget_used'], 3)
        self.assertTrue(report['ready_for_human_review'])

    def test_unauthorized_paths_operations_and_tools_rejected(self):
        request = self.request()
        request['authorized_files']['a.py'] = ['read']
        report = self.run_replies([
            response(('edit_file', {'filename': 'a.py', 'old_text': '1', 'new_text': '9'}),
                     ('read_file', {'filename': '../secret'}),
                     ('delete_file', {'filename': 'b.py'}), ('run_python', {'filename': 'a.py'})),
            response(text='Stopped'), response(text='Stopped')], request)
        self.assertTrue(all(t['status'] == 'rejected' for t in report['trace']))
        self.assertEqual(report['review']['modified_paths'], [])

    def test_fake_json_is_never_executed(self):
        report = self.run_replies([response(text=json.dumps({'name': 'delete_file', 'arguments': {'filename': 'a.py'}})), response(text='Stopped')])
        self.assertEqual(report['budget_used'], 0)
        self.assertEqual(report['recovered_calls'], 0)
        self.assertEqual(report['review']['modified_paths'], [])

    def test_interrupt_retains_partial_edit_and_pending_model_evidence(self):
        report = self.run_replies([self.edits(), KeyboardInterrupt()])
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(len(report['review']['modified_paths']), 2)
        self.assertTrue(report['model_request_pending'])
        self.assertFalse(report['ready_for_human_review'])

    def test_model_transport_failure_keeps_partial_diff(self):
        report = self.run_replies([self.edits(), ConnectionError('offline')])
        self.assertEqual(report['status'], 'failed')
        self.assertIn('+B = 3', report['review']['diff'])
        self.assertTrue(report['errors'])

    def test_failed_static_validation_does_not_claim_success(self):
        report = self.run_replies([response(('edit_file', {'filename': 'a.py', 'old_text': 'A = 1', 'new_text': 'def broken('})), response(text='Done'), response(text='Done')])
        self.assertFalse(report['review']['validation']['passed'])
        self.assertFalse(report['ready_for_human_review'])
        self.assertEqual(report['review']['compilation'], 'not_run')

    def test_stale_source_stops_before_proposed_action(self):
        def changed():
            (self.root / 'a.py').write_bytes(b'user changed\n')
            return self.edits()
        report = self.run_replies([changed])
        self.assertEqual(report['status'], 'stale')
        self.assertFalse(report['ready_for_human_review'])
        self.assertEqual(report['review']['modified_paths'], [])
        self.assertEqual((self.root / 'a.py').read_bytes(), b'user changed\n')

    def test_six_call_budget_counts_rejections(self):
        report = self.run_replies([response(*[('read_file', {'filename': 'outside'})] * 6)])
        self.assertEqual(report['budget_used'], 6)
        self.assertEqual(report['status'], 'budget_exhausted')
        self.assertFalse(report['ready_for_human_review'])

    def test_oversized_batch_not_partially_executed(self):
        report = self.run_replies([response(*[('read_file', {'filename': 'a.py'})] * 7)])
        self.assertEqual(report['budget_used'], 0)
        self.assertEqual(report['native_calls_requested'], 7)
        self.assertEqual(report['status'], 'budget_exhausted')

    def test_ambiguous_edit_rejected_and_original_preserved(self):
        report = self.run_replies([response(('edit_file', {'filename': 'a.py', 'old_text': '', 'new_text': 'bad'})), response(text='Done'), response(text='Done')])
        self.assertEqual(report['trace'][0]['status'], 'rejected')
        self.assertEqual(report['review']['modified_paths'], [])

    def test_explicit_delete_only_affects_temporary_copy(self):
        request = self.request()
        request['authorized_files']['b.py'] = ['delete']
        request['required_changed_files'] = ['b.py']
        report = self.run_replies([response(('delete_file', {'filename': 'b.py'})), response(text='Done')], request)
        self.assertTrue(report['ready_for_human_review'])
        self.assertTrue((self.root / 'b.py').exists())
        self.assertEqual(report['review']['per_file'][1]['status'], 'deleted')

    def test_read_permissions_and_model_feedback_are_enforced_separately(self):
        request = self.request()
        request['authorized_files']['b.py'] = ['modify']
        report = self.run_replies([response(('read_file', {'filename': 'a.py'}),
                                            ('read_file', {'filename': 'b.py'})),
                                   self.edits(), response(text='Done')], request)
        self.assertEqual(report['trace'][0]['result'], 'A = 1\n')
        self.assertEqual(report['trace'][1]['status'], 'rejected')
        self.assertEqual(len(report['accepted_changes']), 2)
        self.assertEqual(len(report['rejected_actions']), 1)
        self.assertTrue(report['ready_for_human_review'])

    def test_literal_newline_failure_can_be_corrected_within_budget(self):
        report = self.run_replies([response(('edit_file', {'filename': 'a.py', 'old_text': 'A = 1\\n', 'new_text': 'A = 7\n'})),
                                   self.edits(), response(text='Done')])
        self.assertIn('found 0', report['trace'][0]['error'])
        self.assertTrue(report['ready_for_human_review'])
        self.assertEqual(report['budget_used'], 3)

    def test_malformed_native_call_is_recorded_and_never_dispatched(self):
        class Malformed:
            def model_dump(self, **kwargs):
                return {'message': {'role': 'assistant', 'content': '', 'tool_calls': [{'function': 'bad'}]}}
        report = self.run_replies([Malformed(), response(text='Stopped'), response(text='Stopped')])
        self.assertEqual(report['budget_used'], 1)
        self.assertEqual(report['trace'][0]['status'], 'rejected')
        self.assertIn('Malformed native', report['trace'][0]['error'])
        self.assertEqual(report['review']['modified_paths'], [])


if __name__ == '__main__':
    unittest.main()
