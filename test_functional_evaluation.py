import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ollama import ChatResponse
import main
from evaluations import evaluate_functional as functional
from evaluations import functional_validation as validation


def response(content='', calls=()):
    return ChatResponse(message={'role': 'assistant', 'content': content,
        'tool_calls': [{'function': {'name': name, 'arguments': args}} for name, args in calls]})


class FunctionalEvaluationTests(unittest.TestCase):
    def task(self, task_id='sum_even'):
        return functional.task_by_id(task_id)

    def edit(self, new='    return sum(n for n in numbers if n % 2 == 0)'):
        return ('edit_workspace_file', {'filename': 'sum_even.py',
                'old_text': '    return sum(numbers)', 'new_text': new})

    def run_case(self, replies, task_id='sum_even'):
        original_workspace = main.WORKSPACE
        snapshots = {p: p.read_bytes() for p in validation.CASE_ROOT.iterdir() if p.is_file()}
        stream = iter(replies)
        seen_workspaces = []
        real_temp = tempfile.TemporaryDirectory

        def temporary(*args, **kwargs):
            temporary = real_temp(*args, **kwargs)
            seen_workspaces.append(Path(temporary.name))
            return temporary

        with patch.object(functional.tempfile, 'TemporaryDirectory', side_effect=temporary), \
                patch('subprocess.run', side_effect=AssertionError('Candidate execution is forbidden')):
            result = functional.one_functional_case(task_id, chat_fn=lambda **kw: next(stream, response()))
        self.assertEqual(main.WORKSPACE, original_workspace)
        for path, source in snapshots.items():
            self.assertEqual(path.read_bytes(), source)
        self.assertTrue(seen_workspaces)
        self.assertTrue(all(not p.exists() for p in seen_workspaces))
        self.assertEqual(result['functional_tests']['status'], 'not_run')
        self.assertIsNone(result['functional_tests']['passed'])
        self.assertIsNone(result['passed'])
        return result

    def test_five_tasks_with_expected_vectors_and_valid_starters(self):
        tasks = validation.load_tasks()
        self.assertEqual(len(tasks), 5)
        self.assertEqual(sum(len(t['tests']) for t in tasks), 29)
        for task in tasks:
            with self.subTest(task=task['id']):
                source = (validation.CASE_ROOT / task['filename']).read_text(encoding='utf-8')
                self.assertTrue(validation.validate_source(source, task)['static_policy_passed'])
                self.assertTrue(all('expected' in vector for vector in task['tests']))

    def test_valid_native_edit_and_separate_verification(self):
        result = self.run_case([response(calls=[self.edit(),
            ('check_python_syntax', {'filename': 'sum_even.py'})])])
        self.assertTrue(result['changed'])
        self.assertTrue(result['target_function_changed'])
        self.assertTrue(result['syntax_valid'])
        self.assertTrue(result['verified_by_agent'])
        self.assertTrue(result['controller_verification']['static_policy_passed'])
        self.assertIsNone(result['requested_change_confirmed'])
        self.assertEqual(result['native_calls_dispatched'], 2)
        self.assertEqual(result['successful_edits'], 1)
        self.assertEqual(result['budget_remaining'], 4)
        self.assertEqual([v['stage'] for v in result['verification_results']], ['after_edit', 'final'])

    def test_valid_json_recovery_for_syntax_valid_starter(self):
        tool, args = self.edit()
        result = self.run_case([response(json.dumps({'name': tool, 'arguments': args}))])
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertTrue(result['recoveries'][0]['accepted'])
        self.assertTrue(result['syntax_valid'])
        self.assertFalse(result['verified_by_agent'])
        self.assertEqual(result['tool_calls'], 1)

    def test_empty_response_does_not_consume_later_strict_recovery(self):
        # Replay the recorded clamp response pattern with a fixed test double.
        # Candidate text is only edited/parsed; no Docker/model execution occurs.
        read = ('read_workspace_file', {'filename': 'clamp.py'})
        proposal = json.dumps({'name': 'edit_workspace_file', 'arguments': {
            'filename': 'clamp.py', 'old_text': '    return min(value, lower)\n',
            'new_text': '    return max(min(value, upper), lower)\n'}})
        result = self.run_case([response(calls=[read]), response(),
            response(calls=[read]), response(proposal),
            response(calls=[('check_python_syntax', {'filename': 'clamp.py'})]),
            response('Done')], task_id='clamp')
        self.assertEqual(result['successful_edits'], 1)
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertEqual(result['tool_calls'], 4)
        self.assertEqual(result['budget_remaining'], 2)
        self.assertTrue(result['verified_by_agent'])
        self.assertIn('return max(min(value, upper), lower)', result['candidate_source'])
        self.assertIsNone(result['passed'])  # No claim about executed vectors.

    def test_malformed_proposal_does_not_consume_later_strict_recovery(self):
        tool, args = self.edit()
        bad = json.dumps({'filename': 'sum_even.py', 'content': 'not authorized'})
        result = self.run_case([response(bad), response(json.dumps({'name': tool, 'arguments': args}))])
        self.assertEqual(result['invalid_json_proposals'], 1)
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertEqual(result['successful_edits'], 1)

    def test_parsed_unauthorized_proposal_consumes_only_dispatch_and_stays_rejected(self):
        tool, args = self.edit()
        unauthorized = {**args, 'filename': '../main.py'}
        result = self.run_case([response(), response(json.dumps({'name': tool, 'arguments': unauthorized})),
                               response(json.dumps({'name': tool, 'arguments': args}))])
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(result['invalid_dispatched_calls'], 1)
        self.assertFalse(result['changed'])
        self.assertIn('Only the current evaluation file', result['trace'][0]['result'])

    def test_preserved_recovery_obeys_remaining_six_call_budget(self):
        tool, args = self.edit()
        result = self.run_case([response(),
            response(calls=[('read_workspace_file', {'filename': 'sum_even.py'})] * 5),
            response(json.dumps({'name': tool, 'arguments': args}))])
        self.assertEqual(result['tool_calls'], 6)
        self.assertEqual(result['budget_remaining'], 0)
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertEqual(result['model_requests'], 3)

    def test_literal_backslash_newline_is_not_normalized_into_an_edit(self):
        tool, args = self.edit()
        malformed = {**args, 'old_text': args['old_text'] + r'\n'}
        result = self.run_case([response(calls=[(tool, malformed)])])
        self.assertFalse(result['changed'])
        self.assertEqual(result['successful_edits'], 0)
        self.assertEqual(result['trace'][0]['raw_result'], 'Error: Text not found. File unchanged.')
        self.assertIn('Literal backslash+n', result['trace'][0]['result'])

    def test_palindrome_recorded_candidate_still_rejected_despite_ast_parse(self):
        source = ("def is_palindrome(text):\n"
                  "    cleaned = ''.join(filter(str.isalnum, text.lower()))\n"
                  "return cleaned == cleaned[::-1]\n")
        checks = validation.validate_source(source, self.task('palindrome'))
        self.assertTrue(checks['syntax_valid'])  # Parser-only field, not compile evidence.
        self.assertFalse(checks['contract_valid'])
        self.assertFalse(checks['static_policy_passed'])
        self.assertIn('Unsupported call target', checks['diagnostics'])

    def test_no_change_or_model_claim_does_not_pass(self):
        result = self.run_case([response('All functional tests passed!')])
        self.assertFalse(result['changed'])
        self.assertTrue(result['syntax_valid'])
        self.assertEqual(result['requested_change_status'], 'not_demonstrated')
        self.assertEqual(result['functional_tests']['executed'], 0)

    def test_wrong_but_valid_code_does_not_count_as_functional_success(self):
        result = self.run_case([response(calls=[self.edit('    return 123')])])
        self.assertTrue(result['syntax_valid'])
        self.assertTrue(result['changed'])
        self.assertIsNone(result['functional_tests']['passed'])

    def test_unauthorized_tools_paths_and_arguments(self):
        bad_calls = [
            ('run_workspace_tests', {'filename': 'test_agent.py'}),
            ('write_workspace_file', {'filename': 'new.py', 'content': 'pass'}),
            ('edit_workspace_file', {'filename': '../main.py', 'old_text': 'x', 'new_text': 'y'}),
            ('read_workspace_file', {'filename': 'tasks.json'}),
            ('edit_workspace_file', {'filename': 'sum_even.py', 'content': 'pass'}),
            ('edit_workspace_file', {'filename': 'sum_even.py', 'old_text': '', 'new_text': 'pass'}),
        ]
        result = self.run_case([response(calls=bad_calls)])
        self.assertFalse(result['changed'])
        self.assertEqual(result['tool_calls'], 6)
        self.assertEqual(result['invalid_dispatched_calls'], 6)

    def test_oversized_batch_never_executes(self):
        result = self.run_case([response(calls=[self.edit()] * 7)])
        self.assertFalse(result['changed'])
        self.assertEqual(result['native_calls_requested'], 7)
        self.assertEqual(result['tool_calls'], 0)
        self.assertIn('budget exceeded', result['error'])

    def test_final_verification_after_last_budgeted_edit(self):
        reads = [('read_workspace_file', {'filename': 'sum_even.py'})] * 5
        result = self.run_case([response(calls=reads + [self.edit()])])
        self.assertEqual(result['tool_calls'], 6)
        self.assertTrue(result['syntax_valid'])
        self.assertFalse(result['verified_by_agent'])
        self.assertEqual(result['budget_remaining'], 0)

    def test_new_edit_invalidates_agent_verification(self):
        result = self.run_case([response(calls=[
            ('check_python_syntax', {'filename': 'sum_even.py'}),
            self.edit('    return (')])])
        self.assertFalse(result['verified_by_agent'])
        self.assertFalse(result['syntax_valid'])

    def test_unsent_retry_after_final_recovery_is_not_counted(self):
        tool, args = self.edit()
        result = self.run_case([
            response(calls=[('read_workspace_file', {'filename': 'sum_even.py'})] * 5),
            response(json.dumps({'name': tool, 'arguments': args})),
        ])
        self.assertEqual(result['tool_calls'], 6)
        self.assertEqual(result['recovered_json_calls'], 1)
        self.assertEqual(result['retry_prompts'], 0)
        self.assertTrue(result['verified_by_controller'])

    def test_invalid_proposals_and_retry_recorded(self):
        bad = json.dumps({'filename': 'sum_even.py', 'old_text': 'x', 'new_text': 'y'})
        result = self.run_case([response(bad), response(bad)])
        self.assertEqual(result['invalid_json_proposals'], 2)
        self.assertEqual(result['retry_prompts'], 1)
        self.assertFalse(result['recoveries'][0]['accepted'])
        self.assertFalse(result['changed'])

    def test_model_exception_is_recorded_and_workspace_removed(self):
        def offline(**kwargs):
            raise ConnectionError('offline')
        original_workspace = main.WORKSPACE
        result = functional.one_functional_case('sum_even', chat_fn=offline)
        self.assertIn('offline', result['error'])
        self.assertEqual(result['model_requests'], 1)
        self.assertEqual(main.WORKSPACE, original_workspace)
        self.assertIsNone(result['passed'])

    def test_unsafe_generated_source_is_only_parsed(self):
        unsafe = '    import socket\n    open("SHOULD_NOT_EXIST", "w").write("bad")\n    return 0'
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'marker'
            unsafe = unsafe.replace('SHOULD_NOT_EXIST', marker.as_posix())
            result = self.run_case([response(calls=[self.edit(unsafe)])])
            self.assertFalse(marker.exists())
        self.assertTrue(result['syntax_valid'])
        self.assertFalse(result['controller_verification']['static_policy_passed'])

    def test_static_rejects_unsafe_or_unsupported_operations(self):
        bodies = [
            'import os\ndef sum_even(numbers):\n    return 0',
            'def sum_even(numbers):\n    import socket\n    return 0',
            'def sum_even(numbers):\n    return eval("1")',
            'def sum_even(numbers):\n    return __import__("os")',
            'def sum_even(numbers):\n    return numbers.__class__',
            'def sum_even(numbers):\n    while True:\n        pass',
            'def sum_even(numbers):\n    return sum_even(numbers)',
            '@open("bad")\ndef sum_even(numbers):\n    return 0',
            'def sum_even(numbers=open("bad")):\n    return 0',
            'def sum_even(numbers):\n    return 0\nopen("bad", "w")',
            'def sum_even(numbers):\n    global state\n    return 0',
            'def sum_even(numbers):\n    return numbers.clear()',
        ]
        for source in bodies:
            with self.subTest(source=source):
                self.assertFalse(validation.validate_source(source, self.task())['static_policy_passed'])

    def test_static_size_and_contract_limits(self):
        for source in ['x' * 100_001, 'def sum_even(other):\n    return 0', 'def sum_even(numbers):\n    return (']:
            with self.subTest(length=len(source)):
                self.assertFalse(validation.validate_source(source, self.task())['static_policy_passed'])

    def test_comments_do_not_demonstrate_function_change(self):
        source = 'def sum_even(numbers):\n    return sum(numbers)\n'
        result = validation.assess_candidate(source, '# fixed\n' + source, self.task())
        self.assertTrue(result['changed'])
        self.assertFalse(result['target_function_changed'])
        self.assertEqual(result['requested_change_status'], 'not_demonstrated')

    def test_unknown_task_never_reaches_model(self):
        with patch.object(main, 'chat', side_effect=AssertionError('Model must not be invoked')):
            with self.assertRaises(ValueError):
                functional.one_functional_case('../main', chat_fn=main.chat)

    def test_manifest_rejects_unauthorized_filenames_and_bad_vectors(self):
        manifest = json.loads((validation.CASE_ROOT / 'tasks.json').read_text())
        for change in [lambda t: t.update(filename='../main.py'),
                       lambda t: t.update(filename='C:\\main.py'),
                       lambda t: t.update(tests=[{'args': [], 'expected': 0}] * 3)]:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for task in manifest['tasks']:
                    (root / task['filename']).write_bytes((validation.CASE_ROOT / task['filename']).read_bytes())
                bad = copy.deepcopy(manifest)
                change(bad['tasks'][0])
                (root / 'tasks.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    validation.load_tasks(root)

    def test_isolation_is_not_inferred_from_installed_container_tools(self):
        with patch.object(validation.shutil, 'which', return_value='fake-installed-tool'):
            status = validation.isolation_status()
        self.assertFalse(status['verified'])
        self.assertFalse(status['execution_enabled'])
        self.assertIsNone(status['enforced_execution_controls'])

    def test_static_cli_and_live_gate_never_invoke_model(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(functional.syntax, 'RUNS', Path(directory)), \
                patch.object(main, 'chat', side_effect=AssertionError('No live benchmark allowed')):
            self.assertEqual(functional.main([]), 0)
            self.assertEqual(functional.main(['--live']), 2)
            reports = [json.loads(p.read_text()) for p in Path(directory).glob('functional_static_*.json')]
        self.assertEqual(len(reports), 2)
        for report in reports:
            self.assertFalse(report['model_invoked'])
            self.assertEqual(report['summary']['functional_tests_executed'], 0)
            self.assertIsNone(report['summary']['functional_success_rate'])


if __name__ == '__main__':
    unittest.main()
