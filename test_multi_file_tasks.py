"""Coordinated editing tests with actual disposable Git, no candidate execution."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from git_checkpoints import _git, _source_snapshot, SafetyError
from multi_file_tasks import MultiFileTask


class MultiFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='alfha-multi-tests-')
        self.root = Path(self.temp.name).resolve()
        _git(self.root, 'init', '--quiet', '--initial-branch=main', '--template=')
        for name, text in {'a.py': 'VALUE = 1\n', 'b.py': 'OTHER = 2\n', 'c.json': '{"value": 3}\n'}.items():
            (self.root / name).write_text(text, encoding='utf-8')
        _git(self.root, 'add', '--all')
        _git(self.root, 'commit', '--quiet', '-m', 'Test baseline')
        self.tasks = []

    def tearDown(self):
        for task in self.tasks:
            task.discard()
        import shutil, stat
        def writable(function, path, error):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            function(path)
        shutil.rmtree(self.root, onexc=writable)
        self.temp.cleanup()

    def task(self, files=('a.py', 'b.py'), **kwargs):
        task = MultiFileTask.prepare(self.root, files, **kwargs)
        self.tasks.append(task)
        return task

    def test_two_files_combined_review_and_checkpoint(self):
        before = _source_snapshot(self.root)
        task = self.task()
        self.assertIn('VALUE', task.read_text('a.py'))
        task.write_text('a.py', 'VALUE = 4\n')
        task.write_text('b.py', 'OTHER = 5\n')
        self.assertFalse(task.report()['ready_for_user_review'])
        self.assertTrue(task.validate()['passed'])
        report = task.checkpoint()
        self.assertEqual(report['modified_paths'], ['a.py', 'b.py'])
        self.assertTrue(report['ready_for_user_review'])
        self.assertIn('+VALUE = 4', report['diff'])
        self.assertIn('+OTHER = 5', report['diff'])
        self.assertEqual(report['functional_tests'], 'not_run')
        self.assertEqual(_source_snapshot(self.root), before)

    def test_three_files_existing_and_explicit_creation(self):
        task = self.task(('a.py', 'b.py', 'new.json'), create_files=('new.json',))
        task.write_text('a.py', 'VALUE = 3\n')
        task.write_text('b.py', 'OTHER = 3\n')
        task.write_text('new.json', '{"coordinated": true}\n')
        task.validate()
        report = task.report()
        self.assertEqual([r['status'] for r in report['per_file']], ['modified', 'modified', 'created'])
        self.assertTrue(report['ready_for_user_review'])
        self.assertFalse((self.root / 'new.json').exists())

    def test_missing_creation_permission_rejected(self):
        with self.assertRaises(SafetyError):
            self.task(('a.py', 'new.py'))

    def test_unauthorized_read_write_and_traversal_are_audited(self):
        task = self.task()
        for name in ('c.json', '../escape.py', 'C:/outside.py'):
            with self.assertRaises(SafetyError):
                task.read_text(name)
            with self.assertRaises(SafetyError):
                task.write_text(name, 'bad')
        report = task.report()
        self.assertEqual(len(report['failed_operations']), 6)
        self.assertEqual(report['modified_paths'], [])

    def test_partial_failure_preserves_successful_edits(self):
        task = self.task()
        task.write_text('a.py', 'VALUE = 9\n')
        with self.assertRaises(SafetyError):
            task.write_text('c.json', 'wrong scope')
        report = task.report()
        self.assertEqual(report['modified_paths'], ['a.py'])
        self.assertIn('+VALUE = 9', report['diff'])
        self.assertEqual(len(report['failed_operations']), 1)

    def test_binary_write_rejected_and_original_bytes_retained(self):
        task = self.task()
        original = task.read_text('a.py')
        for data in (b'\x00binary', b'\xff\xfe', b'text\x01'):
            with self.assertRaises(SafetyError):
                task.write('a.py', data)
        self.assertEqual(task.read_text('a.py'), original)
        self.assertEqual(len(task.report()['failed_operations']), 3)

    def test_binary_initial_file_rejected(self):
        (self.root / 'binary.bin').write_bytes(b'\x00\xff')
        _git(self.root, 'add', 'binary.bin')
        _git(self.root, 'commit', '--quiet', '-m', 'Binary fixture')
        with self.assertRaises(SafetyError):
            self.task(('binary.bin',))

    def test_direct_binary_modification_fails_integrity(self):
        task = self.task()
        (task.workspace / 'a.py').write_bytes(b'\0')
        report = task.report()
        self.assertEqual(report['integrity'], 'rejected')
        self.assertFalse(report['ready_for_user_review'])

    def test_deletion_requires_distinct_permission(self):
        task = self.task()
        with self.assertRaises(SafetyError):
            task.delete('a.py')
        (task.workspace / 'b.py').unlink()
        self.assertEqual(task.report()['integrity'], 'rejected')

    def test_explicit_deletion_is_reported_without_source_deletion(self):
        task = self.task(delete_files=('b.py',))
        task.delete('b.py')
        task.validate()
        self.assertEqual(task.report()['per_file'][1]['status'], 'deleted')
        self.assertTrue((self.root / 'b.py').exists())

    def test_validation_failures_then_correction(self):
        task = self.task(('a.py', 'c.json'))
        task.write_text('a.py', 'def broken(\n')
        task.write_text('c.json', '{')
        result = task.validate()
        self.assertFalse(result['passed'])
        with self.assertRaises(SafetyError):
            task.checkpoint()
        task.write_text('a.py', 'VALUE = 4\n')
        task.write_text('c.json', '{}\n')
        self.assertTrue(task.validate()['passed'])
        self.assertTrue(task.report()['ready_for_user_review'])
        self.assertTrue(task.report()['failed_operations'])

    def test_validation_invalidated_after_write_or_external_edit(self):
        task = self.task()
        task.write_text('a.py', 'VALUE = 5\n')
        task.validate()
        task.write_text('b.py', 'OTHER = 7\n')
        report = task.report()
        self.assertIn('validation', report, json.dumps(report, ensure_ascii=True))
        self.assertEqual(report['validation']['status'], 'not_run', json.dumps(report, ensure_ascii=True))
        task.validate()
        (task.workspace / 'a.py').write_bytes(b'VALUE = 6\n')
        self.assertFalse(task.report()['ready_for_user_review'])

    def test_boolean_alone_cannot_claim_validation(self):
        task = self.task()
        task.write_text('a.py', 'VALUE = 5\n')
        with self.assertRaises(SafetyError):
            task.checkpoint(validation_passed=True)
        self.assertEqual(task.report()['validation']['status'], 'not_run')

    def test_stale_source_and_conflicts_disable_review(self):
        task = self.task()
        task.write_text('a.py', 'VALUE = 9\n')
        task.validate()
        (self.root / 'a.py').write_bytes(b'user changes\n')
        report = task.report()
        self.assertTrue(report['stale'])
        self.assertFalse(report['ready_for_user_review'])
        with self.assertRaises(SafetyError):
            task.checkpoint()

    def test_untracked_user_files_not_copied_or_changed(self):
        user = self.root / 'user.txt'
        user.write_bytes(b'private user work')
        task = self.task()
        self.assertFalse((task.workspace / 'user.txt').exists())
        task.discard()
        self.assertEqual(user.read_bytes(), b'private user work')

    def test_repeated_checks_reject_unauthorized_file_added_later(self):
        task = self.task()
        task.report()
        task.validate()
        (task.workspace / 'unauthorized.py').write_bytes(b'other data')
        for _ in range(3):
            self.assertFalse(task.report()['ready_for_user_review'])
        with self.assertRaises(SafetyError):
            task.validate()

    def test_junction_escape_rejected_and_outside_preserved(self):
        task = self.task()
        outside = self.root / 'user-folder'
        outside.mkdir()
        link = task.workspace / 'escape'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(link))
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(SafetyError):
                task.write_text('a.py', 'bad')
            self.assertFalse(task.report()['ready_for_user_review'])
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()
        self.assertEqual(list(outside.iterdir()), [])

    def test_discard_keeps_report_and_failed_operations_inspectable(self):
        task = self.task()
        task.write_text('a.py', 'VALUE = 9\n')
        with self.assertRaises(SafetyError):
            task.delete('a.py')
        task.discard()
        report = task.report()
        self.assertTrue(report['workspace_discarded'])
        self.assertIn('+VALUE = 9', report['diff'])
        self.assertEqual(len(report['failed_operations']), 1)
        self.assertFalse(task.workspace.exists())
        json.dumps(report)

    def test_ast_success_does_not_claim_compilation_or_execution(self):
        task = self.task()
        task.write_text('a.py', 'return 1\n')
        self.assertTrue(task.validate()['passed'])
        report = task.report()
        self.assertEqual(report['compilation'], 'not_run')
        self.assertEqual(report['execution'], 'not_run')
        self.assertEqual(report['functional_tests'], 'not_run')

    def test_aborted_context_preserves_audit_and_discards_only_owned_workspace(self):
        before = _source_snapshot(self.root)
        task = self.task()
        with self.assertRaisesRegex(RuntimeError, 'controlled abort'):
            with task:
                task.write_text('a.py', 'VALUE = 8\n')
                raise RuntimeError('controlled abort')
        report = task.report()
        self.assertTrue(report['workspace_discarded'])
        self.assertEqual(report['failed_operations'][-1]['operation'], 'abort')
        self.assertEqual(before, _source_snapshot(self.root))


if __name__ == '__main__':
    unittest.main()
