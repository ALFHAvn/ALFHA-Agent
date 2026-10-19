import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import main
from evaluations import evaluate_agent as ev


def response(content='', calls=()):
    return NS(message=NS(content=content, tool_calls=[
        NS(function=NS(name=name, arguments=args)) for name, args in calls]))


class EvaluationControllerTests(unittest.TestCase):
    def run_case(self, source, responses):
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / 'case.py'
            case.write_text(source, encoding='utf-8')
            original = main.WORKSPACE
            stream = iter(responses)
            with patch.object(main, 'chat', side_effect=lambda **kw: next(stream, response())):
                result = ev.one_case(case)
            self.assertEqual(case.read_text(encoding='utf-8'), source)
            self.assertEqual(main.WORKSPACE, original)
            return result

    def proposal(self, **changes):
        args = dict(filename='case.py', old_text='print(1', new_text='print(1)')
        args.update(changes)
        return json.dumps(dict(name='edit_workspace_file', arguments=args))

    def test_valid_json_recovery_and_independent_verification(self):
        result = self.run_case('print(1', [response(self.proposal())])
        self.assertTrue(result['passed'])
        self.assertEqual(result['successful_edits'], 1)
        self.assertFalse(result['verified_by_agent'])
        self.assertTrue(result['recoveries'][0]['accepted'])
        self.assertEqual(result['trace'][0]['origin'], 'json_recovery')
        self.assertEqual(len(result['verification_results']), 2)

    def test_fenced_json(self):
        self.assertTrue(self.run_case('print(1', [response('```json\n' + self.proposal() + '\n```')])['passed'])

    def test_reject_invalid_proposals(self):
        proposals = [
            self.proposal(filename='../case.py'), self.proposal(filename='other.py'),
            self.proposal(filename='workspace/case.py'), self.proposal(filename='C:\\case.py'),
            self.proposal(content='print(1)'), self.proposal(old_text=''),
            self.proposal(old_text=5), self.proposal(new_text=None),
            self.proposal(old_text='missing'), self.proposal(new_text='print(1'),
            '{"name":"edit_workspace_file","name":"edit_workspace_file","arguments":{}}',
            'Explanation: ' + self.proposal(), self.proposal() + self.proposal(),
            json.dumps({'name': 'run_workspace_tests', 'arguments': {'filename': 'test_agent.py'}}),
            json.dumps({'name': 'edit_workspace_file', 'arguments': []}),
            json.dumps({'name': 'edit_workspace_file', 'arguments': {'filename': 'case.py'}}),
            'not json',
        ]
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                result = self.run_case('print(1', [response(proposal)])
                self.assertFalse(result['passed'])
                self.assertFalse(result['changed'])

    def test_ambiguous_edit(self):
        result = self.run_case('print(1\nprint(1', [response(self.proposal())])
        self.assertFalse(result['changed'])
        self.assertIn('Multiple matches', result['trace'][0]['result'])

    def test_recovered_edit_still_invalid(self):
        result = self.run_case('print(1', [response(self.proposal(new_text='print(2'))])
        self.assertTrue(result['changed'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['verification_results'][0]['syntax_valid'])

    def test_real_calls_use_same_validation(self):
        result = self.run_case('print(1', [response(calls=[
            ('run_workspace_tests', {'filename': 'test_agent.py'}),
            ('edit_workspace_file', {'filename': '../case.py', 'old_text': 'print(1', 'new_text': 'print(1)'}),
            ('edit_workspace_file', {'filename': 'case.py', 'content': 'print(1)'}),
        ])])
        self.assertFalse(result['changed'])
        self.assertTrue(all(c['result'].startswith('Error:') for c in result['trace']))

    def test_budget_and_final_verification(self):
        read = ('read_workspace_file', {'filename': 'case.py'})
        edit = ('edit_workspace_file', {'filename': 'case.py', 'old_text': 'print(1', 'new_text': 'print(1)'})
        result = self.run_case('print(1', [response(calls=[read]*5 + [edit])])
        self.assertEqual(result['tool_calls'], 6)
        self.assertTrue(result['passed'])
        result = self.run_case('print(1', [response(calls=[read]*6 + [edit])])
        self.assertEqual(result['tool_calls'], 0)
        self.assertFalse(result['passed'])

    def test_valid_file_unchanged(self):
        result = self.run_case('print(1)', [response(self.proposal()), response(calls=[
            ('edit_workspace_file', {'filename': 'case.py', 'old_text': '1', 'new_text': '2'})])])
        self.assertTrue(result['passed'])
        self.assertFalse(result['changed'])

    def test_error_restores_isolation(self):
        with patch.object(main, 'chat', side_effect=RuntimeError('offline')):
            result = ev.one_case(ev.CASES / 'missing_indentation.py')
        self.assertIn('offline', result['error'])
        self.assertFalse(result['passed'])

    def test_verification_invalidated_after_edit(self):
        result = self.run_case('print(1', [response(calls=[
            ('edit_workspace_file', {'filename': 'case.py', 'old_text': 'print(1', 'new_text': 'print(1)'}),
            ('check_python_syntax', {'filename': 'case.py'}),
            ('edit_workspace_file', {'filename': 'case.py', 'old_text': 'print(1)', 'new_text': 'print(2'}),
        ])])
        self.assertFalse(result['verified_by_agent'])
        self.assertFalse(result['passed'])


if __name__ == '__main__':
    unittest.main()
