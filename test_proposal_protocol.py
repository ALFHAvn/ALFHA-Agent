"""Mocked data-only proposals with real disposable Git; no candidate execution."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from git_checkpoints import SafetyError, _git, _source_snapshot
from multi_file_tasks import MultiFileTask
from proposal_protocol import envelope, strict_json, run_proposals, proposal_schema
import test_coding_workflow as fixtures


def edit(filename='a.py', old='A = 1', new='A = 3', **extra):
    return dict(operation='replace_text', filename=filename, old_text=old, new_text=new, **extra)


def proposal(*changes):
    return json.dumps({'version': 1, 'changes': list(changes)})


class ParserTests(unittest.TestCase):
    def test_only_exact_raw_envelope_and_unique_fields(self):
        for raw in ('```json\n{}\n```', '{} trailing', '[{}]', '{"version":true,"changes":[{}]}',
                    '{"version":1,"changes":[]}', '{"version":1,"changes":[{}],"extra":1}',
                    '{"version":1,"version":1,"changes":[{}]}', '{"version":NaN,"changes":[{}]}'):
            with self.subTest(raw=raw), self.assertRaises(SafetyError):
                envelope(raw)
        self.assertEqual(envelope(proposal(edit())), [edit()])

    def test_input_size_and_depth_bounded(self):
        for raw in ('x' * 65537, '[' * 2000 + ']' * 2000):
            with self.assertRaises(SafetyError):
                strict_json(raw)


class ProposalTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    request = fixtures.WorkflowTests.request

    def run_data(self, data, request=None):
        before = _source_snapshot(self.root)
        with patch('ollama.Client', side_effect=AssertionError('No live model')), patch(
                'coding_workflow.check_dependencies', side_effect=AssertionError('No dependency contact')):
            result = run_proposals(request or self.request(), data)
        self.reports.append(Path(result['report_path']))
        self.assertEqual(json.loads(self.reports[-1].read_text(encoding='utf-8')), result)
        self.assertTrue(result['workspace_discarded'])
        self.assertFalse(result['model_invoked'])
        self.assertEqual(before, _source_snapshot(self.root))
        return result

    def one_file(self):
        r = self.request()
        r['authorized_files'] = {'a.py': ['read', 'modify']}
        return r

    def test_single_file_success_and_review_diff_retained(self):
        r = self.run_data([proposal(edit())], self.one_file())
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['budget_used'], 1)
        self.assertIn('+A = 3', r['review']['diff'])
        self.assertEqual(r['review']['functional_tests'], 'not_run')

    def test_schema_exposes_only_exact_explicit_modify_paths(self):
        req = self.request(); req['authorized_files']['b.py'] = ['read']
        with patch.object(MultiFileTask, 'prepare', side_effect=AssertionError('No staging for schema')):
            schema = proposal_schema(req)
        changes = schema['properties']['changes']
        self.assertEqual(changes['maxItems'], 6)
        self.assertEqual(changes['items']['properties']['filename']['enum'], ['a.py'])
        self.assertFalse(changes['items']['additionalProperties'])

    def test_two_file_batch(self):
        r = self.run_data([proposal(edit(), edit('b.py', 'B = 2', 'B = 3'))])
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['review']['modified_paths'], ['a.py', 'b.py'])
        self.assertEqual(r['budget_used'], 2)

    def test_three_file_batch(self):
        (self.root / 'c.py').write_bytes(b'C = 2\n')
        _git(self.root, 'add', '--all'); _git(self.root, 'commit', '--quiet', '-m', 'Third fixture')
        req = self.request(); req['authorized_files']['c.py'] = ['read', 'modify']
        r = self.run_data([proposal(edit(), edit('b.py', 'B = 2', 'B = 3'), edit('c.py', 'C = 2', 'C = 3'))], req)
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['budget_used'], 3)

    def test_invalid_second_change_cannot_apply_first(self):
        r = self.run_data([proposal(edit(), edit('unauthorized.py'))])
        self.assertEqual(r['events'][0]['status'], 'rejected')
        self.assertEqual(r['budget_used'], 2)
        self.assertEqual(r['final_files'], r['initial_files'])
        self.assertEqual(r['review']['diff'], '')

    def test_nonmatching_second_change_preserves_both_files(self):
        r = self.run_data([proposal(edit(), edit('b.py', 'MISSING', 'B = 3'))])
        self.assertEqual(r['final_files'], r['initial_files'])
        self.assertIn('found 0', r['events'][0]['error'])

    def test_duplicate_file_batch_rejected_before_write(self):
        r = self.run_data([proposal(edit(), edit('a.py', 'A = 3', 'A = 4'))])
        self.assertEqual(r['accepted_changes'], [])
        self.assertIn('Duplicate filename', r['events'][0]['error'])

    def test_literal_newlines_not_automatically_decoded(self):
        r = self.run_data([proposal(edit(old='A = 1\\n', new='A = 4\n'))])
        self.assertIn('actual newlines', r['events'][0]['error'])
        self.assertEqual(r['accepted_changes'], [])

    def test_ambiguous_old_text_rejected(self):
        (self.root / 'a.py').write_bytes(b'A = 1\nA = 1\n')
        _git(self.root, 'add', '--all'); _git(self.root, 'commit', '--quiet', '-m', 'Ambiguous fixture')
        r = self.run_data([proposal(edit())])
        self.assertIn('found 2', r['events'][0]['error'])
        self.assertEqual(r['review']['diff'], '')

    def test_missing_unexpected_or_typed_arguments_rejected(self):
        missing = edit(); del missing['old_text']
        typed = edit(); typed['new_text'] = None
        r = self.run_data([proposal(missing), proposal(edit(content='bad')), proposal(typed)])
        self.assertEqual(r['budget_used'], 3)
        self.assertEqual(r['accepted_changes'], [])
        self.assertEqual(r['final_files'], r['initial_files'])

    def test_execution_creation_deletion_and_path_escape_rejected(self):
        changes = []
        for op in ('run', 'create', 'delete'):
            x = edit(); x['operation'] = op; changes.append(proposal(x))
        changes += [proposal(edit('../a.py')), proposal(edit('A.py')), proposal(edit('new.py'))]
        r = self.run_data(changes)
        self.assertEqual(r['budget_used'], 6)
        self.assertTrue(all(e['status'] == 'rejected' for e in r['events']))
        self.assertEqual(r['review']['diff'], '')

    def test_only_explicit_read_modify_authorization(self):
        req = self.request(); req['authorized_files']['a.py'] = ['read']
        r = self.run_data([proposal(edit())], req)
        self.assertEqual(r['accepted_changes'], [])
        req['authorized_files']['a.py'] = ['modify']
        with self.assertRaises(SafetyError):
            run_proposals(req, [proposal(edit())])

    def test_malformed_response_consumes_budget_then_valid_batch(self):
        r = self.run_data(['Explanation, not a proposal', proposal(edit(), edit('b.py', 'B = 2', 'B = 3'))])
        self.assertEqual(r['budget_used'], 3)
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['events'][0]['status'], 'rejected')

    def test_six_rejections_exhaust_budget_and_oversized_batch_never_writes(self):
        r = self.run_data([proposal(*[edit() for _ in range(7)])])
        self.assertEqual(r['budget_used'], 6)
        self.assertEqual(r['accepted_changes'], [])
        self.assertIn('budget', r['events'][0]['error'])
        r = self.run_data(['invalid'] * 6)
        self.assertEqual(r['budget_used'], 6)
        self.assertEqual(len(r['events']), 6)

    def test_batch_cannot_use_more_than_remaining_slots(self):
        r = self.run_data(['invalid'] * 5 + [proposal(edit(), edit('b.py', 'B = 2', 'B = 3'))])
        self.assertEqual(r['budget_used'], 6)
        self.assertEqual(r['accepted_changes'], [])
        self.assertEqual(r['events'][-1]['charged_operations'], 1)

    def test_static_failure_and_incomplete_required_files_not_success(self):
        r = self.run_data([proposal(edit(new='def broken('))])
        self.assertFalse(r['validation']['passed'])
        self.assertFalse(r['ready_for_human_review'])
        r = self.run_data([proposal(edit())])
        self.assertEqual(r['missing_required_changes'], ['b.py'])
        self.assertFalse(r['ready_for_human_review'])

    def test_invalid_response_sources_or_native_policy_cannot_enable_live_calls(self):
        for data in (lambda: 'x', [], ['x'] * 7, [None], ['\ud800'], ['x' * 65537]):
            with self.assertRaises(SafetyError):
                run_proposals(self.request(), data)
        req = self.request(); req['tool_policy'] = {'inspection_first': True, 'single_json_recovery': True}
        with self.assertRaises(SafetyError):
            run_proposals(req, [proposal(edit())])

    def test_untracked_user_file_preserved_and_not_in_context(self):
        (self.root / 'private.txt').write_bytes(b'user data')
        r = self.run_data([proposal(edit(), edit('b.py', 'B = 2', 'B = 3'))])
        self.assertTrue(r['ready_for_human_review'])
        self.assertNotIn('private.txt', r['initial_files'])
        self.assertEqual((self.root / 'private.txt').read_bytes(), b'user data')

    def test_hardlinked_source_fails_before_staging(self):
        import os
        alias = self.root / 'alias'
        os.link(self.root / 'a.py', alias)
        try:
            with self.assertRaises(SafetyError):
                run_proposals(self.request(), [proposal(edit())])
            self.assertEqual(alias.read_bytes(), b'A = 1\n')
        finally:
            alias.unlink()

    def test_write_failure_retains_partial_diff_without_readiness(self):
        original = MultiFileTask.write_text
        def fail(task, name, text):
            if name == 'b.py':
                raise OSError('Controlled write failure')
            return original(task, name, text)
        with patch.object(MultiFileTask, 'write_text', fail):
            r = self.run_data([proposal(edit(), edit('b.py', 'B = 2', 'B = 3'))])
        self.assertEqual(r['status'], 'staging_failed')
        self.assertFalse(r['ready_for_human_review'])
        self.assertEqual(r['review']['modified_paths'], ['a.py'])
        self.assertEqual(r['events'][0]['status'], 'staging_failed')

    def test_interruption_discards_only_staging_and_preserves_report(self):
        with patch.object(MultiFileTask, 'write_text', side_effect=KeyboardInterrupt):
            r = self.run_data([proposal(edit())])
        self.assertEqual(r['status'], 'interrupted')
        self.assertEqual(r['events'][0]['status'], 'interrupted')
        self.assertFalse(r['ready_for_human_review'])
        self.assertEqual(r['final_files'], r['initial_files'])

    def test_unexpected_staging_edit_is_not_adopted(self):
        original = MultiFileTask.inspect
        changed = False
        def mutate(task):
            nonlocal changed
            if not changed:
                changed = True
                (task.workspace / 'a.py').write_bytes(b'A = 99\n')
            return original(task)
        with patch.object(MultiFileTask, 'inspect', mutate):
            r = self.run_data([proposal(edit(old='A = 99'))])
        self.assertEqual(r['status'], 'integrity_or_stale_failure')
        self.assertEqual(r['accepted_changes'], [])
        self.assertFalse(r['ready_for_human_review'])

    def test_stale_source_stops_without_any_staged_write(self):
        original = MultiFileTask.inspect
        changed = False
        def mutate(task):
            nonlocal changed
            if not changed:
                changed = True
                (self.root / 'b.py').write_bytes(b'USER_EDIT = 9\n')
            return original(task)
        with patch.object(MultiFileTask, 'inspect', mutate):
            r = run_proposals(self.request(), [proposal(edit())])
        self.reports.append(Path(r['report_path']))
        self.assertEqual(r['status'], 'integrity_or_stale_failure')
        self.assertFalse(r['ready_for_human_review'])
        self.assertEqual(r['accepted_changes'], [])
        self.assertEqual((self.root / 'b.py').read_bytes(), b'USER_EDIT = 9\n')
        self.assertTrue(r['workspace_discarded'])
