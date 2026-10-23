"""Step 45 data-only protocol tests; candidates are never executed."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_coding_workflow as fixtures
from git_checkpoints import SafetyError, _source_snapshot
from proposal_protocol import (envelope, validate_changes, run_proposals,
                               proposal_schema, proposal_messages)


def change(name='a.py', old=None, new=None):
    return {'operation': 'replace_lines', 'filename': name,
            'old_lines': ['A = 1', ''] if old is None else old,
            'new_lines': ['A = 3', ''] if new is None else new}


def document(*changes, version=2):
    return json.dumps({'version': version, 'changes': list(changes)})


class LineParserTests(unittest.TestCase):
    authorization = {'a.py': ['read', 'modify'], 'b.py': ['read', 'modify']}
    contents = {'a.py': 'A = 1\n', 'b.py': 'B = 2\n'}

    def validate(self, *changes):
        return validate_changes(list(changes), self.authorization, self.contents,
                                allow_line_arrays=True)

    def test_opt_in_required_in_parser_and_validator(self):
        with self.assertRaises(SafetyError):
            envelope(document(change()))
        with self.assertRaises(SafetyError):
            validate_changes([change()], self.authorization, self.contents)
        self.assertEqual(envelope(document(change()), allow_line_arrays=True), [change()])

    def test_opt_in_requires_boolean(self):
        for value in (1, 'true', None, [], {}):
            with self.subTest(value=value), self.assertRaises(SafetyError):
                envelope(document(change()), allow_line_arrays=value)

    def test_multiline_and_interior_empty_lines(self):
        self.assertEqual(self.validate(change(new=['A = 3', '', 'B = 4', ''])),
                         {'a.py': 'A = 3\n\nB = 4\n'})

    def test_no_implicit_trailing_newline(self):
        self.assertEqual(self.validate(change(new=['A = 3'])), {'a.py': 'A = 3'})

    def test_multiple_trailing_newlines(self):
        self.assertEqual(self.validate(change(new=['A = 3', '', ''])), {'a.py': 'A = 3\n\n'})

    def test_empty_replacement_is_explicit(self):
        for new in ([], ['']):
            self.assertEqual(self.validate(change(new=new)), {'a.py': ''})

    def test_empty_old_target_rejected(self):
        for old in ([], ['']):
            with self.subTest(old=old), self.assertRaises(SafetyError):
                self.validate(change(old=old))

    def test_noop_rejected(self):
        with self.assertRaises(SafetyError):
            self.validate(change(new=['A = 1', '']))

    def test_malformed_arrays_and_elements_rejected(self):
        for value in ('A = 1', None, {}, [1], [True], [None], [[]], ['x\ny'], ['x\ry']):
            for field in ('old_lines', 'new_lines'):
                item = change(); item[field] = value
                with self.subTest(value=value, field=field), self.assertRaises(SafetyError):
                    self.validate(item)

    def test_literal_backslashes_are_not_unescaped(self):
        item = change(new=[r'# literal\n', 'A = 3', ''])
        self.assertEqual(self.validate(item)['a.py'], '# literal\\n\nA = 3\n')
        with self.assertRaisesRegex(SafetyError, 'found 0'):
            self.validate(change(old=[r'A = 1\n']))

    def test_legacy_literal_preservation_even_when_opted_in(self):
        item = {'operation': 'replace_text', 'filename': 'a.py',
                'old_text': r'A = 1\n', 'new_text': 'A = 3\n'}
        for enabled in (False, True):
            with self.assertRaisesRegex(SafetyError, 'literal backslash'):
                validate_changes([item], self.authorization, self.contents, allow_line_arrays=enabled)
        literal_source = {'a.py': r'A = 1\n'}
        self.assertEqual(validate_changes([item], self.authorization, literal_source), {'a.py': 'A = 3\n'})

    def test_mixed_fields_missing_fields_and_wrong_operation_rejected(self):
        for field in ('old_text', 'new_text', 'content', 'extra'):
            item = change(); item[field] = 'x'
            with self.assertRaises(SafetyError):
                envelope(document(item), allow_line_arrays=True)
        for field in change():
            item = change(); del item[field]
            with self.assertRaises(SafetyError):
                self.validate(item)
        item = change(); item['operation'] = 'replace_text'
        with self.assertRaises(SafetyError):
            envelope(document(item), allow_line_arrays=True)

    def test_versions_cannot_mix_or_self_authorize(self):
        legacy = {'operation': 'replace_text', 'filename': 'b.py', 'old_text': 'B = 2', 'new_text': 'B = 3'}
        for raw in (document(change(), version=1), document(change(), legacy),
                    document(legacy), document(change(), version=True),
                    document(change(), version=3)):
            with self.assertRaises(SafetyError):
                envelope(raw, allow_line_arrays=True)
        with self.assertRaises(SafetyError):
            self.validate(change(), legacy)

    def test_missing_and_ambiguous_targets(self):
        with self.assertRaisesRegex(SafetyError, 'found 0'):
            self.validate(change(old=['missing']))
        with self.assertRaisesRegex(SafetyError, 'found 2'):
            validate_changes([change(old=['A'], new=['B'])], self.authorization,
                             {'a.py': 'A\nA\n'}, allow_line_arrays=True)

    def test_duplicate_filename_rejected(self):
        with self.assertRaisesRegex(SafetyError, 'Duplicate filename'):
            self.validate(change(), change())

    def test_unauthorized_paths_and_read_only_rejected(self):
        for name in ('../a.py', 'A.py', 'new.py', 'E:/a.py', 'a.py/../b.py'):
            with self.assertRaises(SafetyError):
                self.validate(change(name))
        with self.assertRaises(SafetyError):
            validate_changes([change()], {'a.py': ['read']}, self.contents, allow_line_arrays=True)

    def test_legacy_default_schema_and_messages_unchanged(self):
        req = {'description': 'Review only', 'source_repository': 'E:/example',
               'authorized_files': self.authorization,
               'validation_requirements': {'static': True, 'docker_execution': False}}
        legacy = proposal_schema(req)
        extended = proposal_schema(req, allow_line_arrays=True)
        self.assertEqual(extended['oneOf'][0], legacy)
        self.assertEqual(legacy['properties']['version']['const'], 1)
        line = extended['oneOf'][1]
        self.assertEqual(line['properties']['version']['const'], 2)
        self.assertEqual(line['properties']['changes']['maxItems'], 6)
        self.assertEqual(line['properties']['changes']['items']['properties']['filename']['enum'], ['a.py', 'b.py'])
        self.assertEqual(proposal_messages(req, self.contents),
                         proposal_messages(req, self.contents, allow_line_arrays=False))
        self.assertIn('version=2', proposal_messages(req, self.contents, allow_line_arrays=True)[0]['content'])


class LineStagingTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    request = fixtures.WorkflowTests.request

    def run_data(self, changes, *, enabled=True):
        before = _source_snapshot(self.root)
        with patch('ollama.Client', side_effect=AssertionError('No live model')):
            result = run_proposals(self.request(), [document(*changes)], allow_line_arrays=enabled)
        self.reports.append(Path(result['report_path']))
        self.assertEqual(json.loads(self.reports[-1].read_bytes()), result)
        self.assertEqual(before, _source_snapshot(self.root))
        self.assertTrue(result['workspace_discarded'])
        self.assertFalse(result['model_invoked'])
        return result

    def test_two_file_multiline_edit_and_diff(self):
        result = self.run_data([change(new=['A = 3', '', '# reviewed', '']),
                               change('b.py', ['B = 2', ''], ['B = 3', ''])])
        self.assertTrue(result['ready_for_human_review'])
        self.assertEqual(result['budget_used'], 2)
        self.assertEqual(len(result['accepted_changes']), 2)
        self.assertEqual(result['final_files']['a.py'], 'A = 3\n\n# reviewed\n')
        self.assertIn('+# reviewed', result['review']['diff'])
        self.assertEqual(result['protocol'], 'explicit-replacements-v1+lines-v2')

    def test_invalid_second_array_rejects_entire_batch(self):
        result = self.run_data([change(), change('b.py', ['B = 2', ''], [None])])
        self.assertEqual(result['budget_used'], 2)
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['initial_files'], result['final_files'])
        self.assertEqual(result['review']['diff'], '')

    def test_unauthorized_second_path_is_atomic(self):
        result = self.run_data([change(), change('../b.py')])
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['initial_files'], result['final_files'])

    def test_nonmatching_second_target_is_atomic(self):
        result = self.run_data([change(), change('b.py', ['missing'], ['B = 3'])])
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['events'][0]['diagnostic']['code'], 'replacement_not_found')

    def test_default_runner_rejects_version_two(self):
        result = self.run_data([change()], enabled=False)
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['protocol'], 'explicit-replacements-v1')

    def test_oversized_batch_exhausts_existing_budget_without_write(self):
        result = self.run_data([change()] * 7)
        self.assertEqual(result['budget_used'], 6)
        self.assertEqual(result['accepted_changes'], [])

    def test_opted_in_runner_still_accepts_legacy(self):
        before = _source_snapshot(self.root)
        raw = document({'operation': 'replace_text', 'filename': 'a.py',
                        'old_text': 'A = 1', 'new_text': 'A = 3'}, version=1)
        result = run_proposals(self.request(), [raw], allow_line_arrays=True)
        self.reports.append(Path(result['report_path']))
        self.assertEqual(result['final_files']['a.py'], 'A = 3\n')
        self.assertTrue(result['workspace_discarded'])
        self.assertEqual(before, _source_snapshot(self.root))


if __name__ == '__main__':
    unittest.main()
