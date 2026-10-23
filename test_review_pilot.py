"""Mock model + real disposable Git. Candidate code is parsed, never executed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_review_pilot as pilot
import review_report
import test_coding_workflow as fixtures
import test_interactive_review as review_fixtures
from git_checkpoints import _git, _source_snapshot


class PilotTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    run_mock = review_fixtures.ReviewTests.run_mock

    def request(self):
        return {'description': pilot.DESCRIPTION, 'source_repository': str(self.root),
                'authorized_files': {'a.py': ['read', 'modify'], 'b.py': ['read', 'modify']},
                'required_changed_files': ['a.py', 'b.py'],
                'validation_requirements': {'static': True, 'docker_execution': False}}

    def test_preparation_is_offline_and_preserves_source(self):
        # Redirect only temporary directory creation into this test-owned root.
        real_mkdtemp = tempfile.mkdtemp
        with patch.object(pilot.tempfile, 'mkdtemp',
                          side_effect=lambda **kw: real_mkdtemp(dir=self.root, **kw)), \
             patch('interactive_review.Client', side_effect=AssertionError('No model')):
            output, plan = pilot.prepare()
        source = Path(plan['request']['source_repository'])
        self.assertEqual(plan, json.loads(output.read_bytes()))
        self.assertFalse(plan['generation_authorized'])
        self.assertFalse(plan['candidate_execution_authorized'])
        self.assertEqual(plan['payload']['format']['properties']['version']['const'], 2)
        self.assertEqual(plan['operation_budget'], 6)
        self.assertTrue(plan['inspection_discarded'])
        self.assertEqual(plan['starting_snapshot'], _source_snapshot(source))
        self.assertEqual(plan['request']['authorized_files']['README.md'], ['read'])
        self.assertEqual(set(plan['fixture_hashes']), set(pilot.FILES))
        for name in pilot.FILES:
            self.assertEqual((source/name).read_bytes(), (pilot.FIXTURES/name).read_bytes())

    def install_pilot(self):
        for name in ('a.py', 'b.py'):
            (self.root/name).unlink()
        for name in pilot.FILES:
            (self.root/name).write_bytes((pilot.FIXTURES/name).read_bytes())
        _git(self.root, 'add', '--all')
        _git(self.root, 'commit', '--quiet', '-m', 'Pilot baseline')
        req = self.request()
        req['authorized_files'] = {'duration.py': ['read', 'modify'],
                                   'test_duration.py': ['read', 'modify'], 'README.md': ['read']}
        req['required_changed_files'] = ['duration.py', 'test_duration.py']
        return req

    def changes(self):
        module = (pilot.FIXTURES/'duration.py').read_text()
        tests = (pilot.FIXTURES/'test_duration.py').read_text()
        replacement = ('    if seconds < 0:\n        raise ValueError("negative duration")\n'
                       '    minutes, remainder = divmod(seconds, 60)\n'
                       '    return f"{minutes}:{remainder:02d}"')
        test_text = tests + '\n\ndef test_boundaries():\n' + ''.join(
            f'    assert format_duration({value}) == {expected!r}\n'
            for value, expected in ((1,'0:01'),(59,'0:59'),(60,'1:00'),(61,'1:01'),
                                    (3600,'60:00'),(3661,'61:01')))
        test_text += ('\n\ndef test_negative():\n    try:\n        format_duration(-1)\n'
                      '    except ValueError:\n        pass\n    else:\n        assert False\n')
        return [review_fixtures.line('duration.py', module.split('\n'),
                 module.replace('    return str(seconds)', replacement).split('\n')),
                review_fixtures.line('test_duration.py', tests.split('\n'), test_text.split('\n'))]

    def test_pilot_two_file_mock_retains_evidence_and_read_only_context(self):
        req = self.install_pilot()
        result, calls = self.run_mock(review_fixtures.reply(*self.changes()), req)
        self.assertTrue(result['ready_for_human_review'])
        self.assertEqual(result['budget_used'], 2)
        self.assertEqual(set(result['final_files']), {'duration.py', 'test_duration.py', 'README.md'})
        self.assertEqual(result['final_files']['README.md'], (pilot.FIXTURES/'README.md').read_text())
        self.assertEqual(len(calls), 1)
        loaded = review_report.load_report(result['report_path'])
        self.assertIn('Saved evidence only', review_report.render_report(loaded))

    def test_read_only_edit_rejects_whole_batch(self):
        req = self.install_pilot()
        changes = self.changes() + [review_fixtures.line('README.md', ['# Time report'], ['# Changed'])]
        result, _ = self.run_mock(review_fixtures.reply(*changes), req)
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['combined_diff'], '')
        self.assertFalse(result['ready_for_human_review'])

    def test_missing_second_file_is_incomplete(self):
        req = self.install_pilot()
        result, _ = self.run_mock(review_fixtures.reply(self.changes()[0]), req)
        self.assertFalse(result['ready_for_human_review'])
        self.assertEqual(result['missing_required_changes'], ['test_duration.py'])


class SavedReportTests(unittest.TestCase):
    def test_untrusted_claims_do_not_restore_authority_or_terminal_controls(self):
        report = {'run_id': 'saved', 'status': 'prepared', 'combined_diff': '\x1b[31m',
                  'ready_for_human_review': True, 'authorization': True,
                  'source_repository': 'untrusted-path'}
        text = review_report.render_report(report)
        self.assertNotIn('\x1b', text)
        self.assertIn('\\u001b', text)
        self.assertNotIn('untrusted-path', text)
        self.assertNotIn('"authorization"', text)
        self.assertIn('claims have not been reverified', text)

    def test_malformed_missing_and_oversized_reports(self):
        with tempfile.TemporaryDirectory(prefix='alfha-report-tests-') as folder:
            path = Path(folder)/'report.json'
            for value in ('{', '[]', '{}', '{"schema_version":1}'):
                path.write_text(value)
                with self.assertRaises(ValueError): review_report.load_report(path)
            path.write_bytes(b' ' * (review_report.MAX_REPORT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, '2 MB'): review_report.load_report(path)

    def test_saved_report_inspection_does_not_create_live_client(self):
        with tempfile.TemporaryDirectory(prefix='alfha-report-tests-') as folder:
            path = Path(folder)/'report.json'
            path.write_text(json.dumps({'schema_version':1,'run_id':'saved',
                                       'status':'interrupted','combined_diff':''}))
            with patch('interactive_review.Client', side_effect=AssertionError('No live call')), \
                 patch('builtins.print'):
                self.assertEqual(review_report.main([str(path)]), 0)
