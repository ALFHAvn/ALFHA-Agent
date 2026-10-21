"""Offline classification tests: no staging or dispatch of historical proposals."""
import unittest
from unittest.mock import patch
from evaluations.analyze_proposals import classify_call, classify_message


class ProposalAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.auth = {'a.py': ['read', 'modify'], 'b.py': ['read', 'modify']}
        self.files = {'a.py': 'A = 1\n', 'b.py': 'B = 2\n'}

    def call(self, name='edit_file', **args):
        if not args: args = {'filename': 'a.py', 'old_text': 'A = 1', 'new_text': 'A = 2'}
        return {'name': name, 'arguments': args}

    def test_authorized_single_and_multiple_edits_are_only_data(self):
        import json
        calls = [self.call(), self.call(filename='b.py', old_text='B = 2', new_text='B = 3')]
        with patch('multi_file_tasks.MultiFileTask.write_text', side_effect=AssertionError('No proposal execution')):
            single = classify_message({'content': json.dumps(calls[0])}, self.auth, self.files)
            batch = classify_message({'content': json.dumps(calls)}, self.auth, self.files)
        self.assertEqual(single['safe_edit_units'], 1)
        self.assertTrue(batch['safe_multiple_edit_document'])
        self.assertEqual(self.files['a.py'], 'A = 1\n')

    def test_nonmatching_missing_unauthorized_and_explanation(self):
        self.assertEqual(classify_call(self.call(old_text='missing', new_text='new', filename='a.py'), self.auth, self.files)['category'], 'missing_or_nonmatching_replacement_text')
        self.assertEqual(classify_call(self.call(filename='outside.py', old_text='A = 1', new_text='A = 2'), self.auth, self.files)['category'], 'unauthorized_operation')
        self.assertEqual(classify_call(self.call('modify_file', filename='a.py', content='X'), self.auth, self.files)['category'], 'unauthorized_operation')
        self.assertEqual(classify_call(self.call(filename='a.py', new_text='A = 2'), self.auth, self.files)['category'], 'malformed_or_ambiguous_json')
        self.assertIn('non_actionable_explanation', classify_message({'content': 'All files changed'}, self.auth, self.files)['categories'])

    def test_fences_trailing_text_duplicates_and_empty_array_never_salvaged(self):
        for text in ('```json\n{}\n```', '{}\n{}', '{"name":"x","name":"y"}', '[]'):
            result = classify_message({'content': text}, self.auth, self.files)
            self.assertIn('malformed_or_ambiguous_json', result['categories'])
            self.assertEqual(result['safe_edit_units'], 0)
