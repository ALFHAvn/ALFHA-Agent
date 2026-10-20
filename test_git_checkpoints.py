"""Actual Git in disposable test repos; candidate text is never executed."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from git_checkpoints import GitCheckpoint, SafetyError, _git, _source_snapshot


class GitCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='alfha-git-tests-')
        self.source = Path(self.temp.name).resolve() / 'source'
        self.source.mkdir()
        _git(self.source, 'init', '--quiet', '--initial-branch=main', '--template=')
        for name, data in {'code.py': b'original\n', 'other.txt': b'user\n', '.gitignore': b'ignored/\n'}.items():
            (self.source / name).write_bytes(data)
        _git(self.source, 'add', '--all')
        _git(self.source, 'commit', '--quiet', '-m', 'User starting commit')
        self.handles = []

    def tearDown(self):
        for task in self.handles:
            if task.state != 'discarded':
                task.discard()
        # Git object files can be read-only on Windows.
        import shutil, stat
        def writable(function, path, error):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            function(path)
        shutil.rmtree(self.temp.name, onexc=writable)
        self.temp.cleanup()

    def prepare(self, names=('code.py',)):
        task = GitCheckpoint.prepare(self.source, names)
        self.handles.append(task)
        return task

    def test_clean_repository_checkpoint_inspection_and_discard(self):
        before = _source_snapshot(self.source)
        task = self.prepare()
        self.assertFalse(task.workspace.is_relative_to(self.source))
        task.write('code.py', b'revised\n')
        review = task.checkpoint(validation_passed=True)
        self.assertEqual(review['modified_paths'], ['code.py'])
        self.assertEqual(review['starting_commit'], before['head'])
        self.assertIn('+revised', review['diff'])
        self.assertFalse(review['application_supported'])
        self.assertTrue(review['approval_required_for_application'])
        self.assertNotEqual(review['checkpoint_commit'], task._baseline)
        self.assertEqual(_git(task.workspace, 'branch', '--show-current').strip(), b'codex/isolated-task')
        self.assertEqual(_git(task.workspace, 'remote'), b'')
        root = task._root
        task.discard()
        task.discard()
        self.assertFalse(root.exists())
        self.assertEqual(before, _source_snapshot(self.source))

    def test_unrelated_dirty_staged_untracked_and_ignored_data_preserved(self):
        (self.source / 'other.txt').write_bytes(b'staged user work\n')
        _git(self.source, 'add', 'other.txt')
        (self.source / 'other.txt').write_bytes(b'unstaged user work\n')
        (self.source / 'untracked.txt').write_bytes(b'untracked user data')
        (self.source / 'ignored').mkdir()
        secret = self.source / 'ignored/secret.txt'
        secret.write_bytes(b'ignored user data')
        before = _source_snapshot(self.source)
        task = self.prepare()
        self.assertFalse((task.workspace / 'other.txt').exists())
        self.assertFalse((task.workspace / 'untracked.txt').exists())
        self.assertFalse((task.workspace / 'ignored').exists())
        task.write('code.py', b'changed\n')
        task.checkpoint(validation_passed=True)
        task.discard()
        self.assertEqual(before, _source_snapshot(self.source))
        self.assertEqual(secret.read_bytes(), b'ignored user data')

    def test_dirty_authorized_file_rejected(self):
        (self.source / 'code.py').write_bytes(b'user edits\n')
        before = _source_snapshot(self.source)
        with self.assertRaises(SafetyError):
            self.prepare()
        self.assertEqual(before, _source_snapshot(self.source))

    def test_staged_authorized_file_rejected_even_if_worktree_matches_head(self):
        (self.source / 'code.py').write_bytes(b'staged user edits\n')
        _git(self.source, 'add', 'code.py')
        (self.source / 'code.py').write_bytes(b'original\n')
        with self.assertRaisesRegex(SafetyError, 'staged'):
            self.prepare()

    def test_existing_untracked_authorized_path_rejected(self):
        (self.source / 'new.py').write_bytes(b'user data')
        with self.assertRaisesRegex(SafetyError, 'untracked'):
            self.prepare(('new.py',))
        self.assertEqual((self.source / 'new.py').read_bytes(), b'user data')

    def test_ignored_existing_and_missing_paths_rejected(self):
        (self.source / 'ignored').mkdir()
        (self.source / 'ignored/existing.py').write_bytes(b'user data')
        for name in ('ignored/existing.py', 'ignored/new.py'):
            with self.subTest(name=name), self.assertRaisesRegex(SafetyError, 'Ignored'):
                self.prepare((name,))

    def test_new_authorized_file_is_inspectable_without_source_creation(self):
        task = self.prepare(('new.py',))
        task.write('new.py', b'candidate text\n')
        review = task.checkpoint(validation_passed=True)
        self.assertIn('new file mode', review['diff'])
        self.assertEqual(review['modified_paths'], ['new.py'])
        self.assertFalse((self.source / 'new.py').exists())

    def test_unauthorized_paths_and_git_control_paths_rejected(self):
        for name in ('../outside', '/outside', 'C:/outside', 'a\\b', '.git/config',
                     '.gitattributes', 'a/../code.py', 'a//b', 'a:stream', 'NUL.txt', 'a. /b', 'a\nfile'):
            with self.subTest(name=name), self.assertRaises(SafetyError):
                self.prepare((name,))
        task = self.prepare()
        with self.assertRaises(SafetyError):
            task.write('other.txt', b'not authorized')
        self.assertEqual((self.source / 'other.txt').read_bytes(), b'user\n')

    def test_case_aliases_and_empty_allowlists_rejected(self):
        for names in ((), ('code.py', 'CODE.py'), ('new', 'new/code.py'), 'code.py'):
            with self.assertRaises(SafetyError):
                self.prepare(names)

    def test_conflicting_source_edit_makes_checkpoint_stale(self):
        task = self.prepare()
        task.write('code.py', b'candidate\n')
        (self.source / 'code.py').write_bytes(b'new user work\n')
        self.assertTrue(task.inspect()['stale'])
        with self.assertRaisesRegex(SafetyError, 'stale'):
            task.checkpoint(validation_passed=True)
        task.discard()
        self.assertEqual((self.source / 'code.py').read_bytes(), b'new user work\n')

    def test_external_untracked_and_ref_changes_detected(self):
        for change in ('untracked', 'branch'):
            task = self.prepare()
            if change == 'untracked':
                (self.source / 'new-user.txt').write_text('new')
            else:
                _git(self.source, 'branch', 'user-branch')
            self.assertTrue(task.inspect()['stale'])
            task.discard()

    def test_source_change_during_prepare_rejected(self):
        actual = _source_snapshot
        count = 0
        def race(root):
            nonlocal count
            count += 1
            if count == 2:
                (self.source / 'other.txt').write_bytes(b'external change')
            return actual(root)
        with patch('git_checkpoints._source_snapshot', side_effect=race), self.assertRaises(SafetyError):
            self.prepare()
        self.assertEqual((self.source / 'other.txt').read_bytes(), b'external change')

    def test_failed_validation_prevents_commit_and_further_checkpoint(self):
        task = self.prepare()
        task.write('code.py', b'bad candidate')
        head = task._head
        with self.assertRaisesRegex(SafetyError, 'Validation failed'):
            task.checkpoint(validation_passed=False)
        self.assertEqual(task._head, head)
        with self.assertRaises(SafetyError):
            task.checkpoint(validation_passed=True)
        self.assertEqual(task.state, 'rejected')

    def test_abort_discard_preserves_user_commit_history(self):
        before = _source_snapshot(self.source)
        task = self.prepare()
        task.write('code.py', b'unfinished')
        task.discard()
        self.assertEqual(before, _source_snapshot(self.source))
        with self.assertRaises(SafetyError):
            task.inspect()

    def test_unauthorized_direct_file_write_detected(self):
        task = self.prepare()
        (task.workspace / 'other.txt').write_bytes(b'not allowed')
        with self.assertRaisesRegex(SafetyError, 'Unauthorized'):
            task.inspect()

    def test_changed_temporary_history_rejected(self):
        task = self.prepare()
        _git(task.workspace, 'commit', '--allow-empty', '--quiet', '-m', 'external')
        with self.assertRaisesRegex(SafetyError, 'history'):
            task.inspect()

    def test_changed_temporary_config_rejected_without_running_git(self):
        task = self.prepare()
        (task.workspace / '.git/config').write_text('[core]\nrepositoryformatversion = 0\n')
        with patch('git_checkpoints._git', side_effect=AssertionError('no git after tamper')):
            with self.assertRaisesRegex(SafetyError, 'configuration'):
                task.inspect()

    def test_ownership_marker_mismatch_refuses_deletion(self):
        task = self.prepare()
        task._marker.write_text('wrong')
        with self.assertRaisesRegex(SafetyError, 'Ownership'):
            task.discard()
        self.assertTrue(task.workspace.exists())
        task._marker.write_text(task._nonce)

    def test_hardlink_write_and_cleanup_refused_without_touching_user_file(self):
        task = self.prepare()
        external = Path(self.temp.name) / 'outside.txt'
        external.write_bytes(b'outside user data')
        target = task.workspace / 'code.py'
        target.unlink()
        os.link(external, target)
        try:
            with self.assertRaises(SafetyError):
                task.write('code.py', b'overwrite')
            with self.assertRaises(SafetyError):
                task.discard()
            self.assertEqual(external.read_bytes(), b'outside user data')
        finally:
            target.unlink()

    def test_git_config_and_environment_are_not_mutated_or_inherited(self):
        before = (self.source / '.git/config').read_bytes()
        with patch.dict(os.environ, {'GIT_DIR': str(self.source / '.git'),
                                     'GIT_INDEX_FILE': str(self.source / 'DO-NOT-CREATE'),
                                     'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.hooksPath',
                                     'GIT_CONFIG_VALUE_0': '/not/authorized'}):
            task = self.prepare()
            task.write('code.py', b'safe data')
            task.checkpoint(validation_passed=True)
        self.assertEqual(before, (self.source / '.git/config').read_bytes())
        self.assertFalse((self.source / 'DO-NOT-CREATE').exists())

    def test_source_plumbing_never_calls_status_diff_or_content_filters(self):
        calls = []
        actual = _git
        def record(root, *args, **kwargs):
            if Path(root) == self.source:
                calls.append(args[0])
            return actual(root, *args, **kwargs)
        with patch('git_checkpoints._git', side_effect=record):
            task = self.prepare()
            task.inspect()
        self.assertNotIn('status', calls)
        self.assertNotIn('diff', calls)
        self.assertNotIn('add', calls)
        self.assertNotIn('commit', calls)

    def test_validation_requires_exact_boolean(self):
        task = self.prepare()
        with self.assertRaises(SafetyError):
            task.checkpoint(validation_passed='passed')

    def test_context_manager_aborted_operation_discards_only_owned_root(self):
        before = _source_snapshot(self.source)
        task = self.prepare()
        with self.assertRaisesRegex(ValueError, 'aborted'):
            with task:
                task.write('code.py', b'partial work')
                raise ValueError('aborted')
        self.assertFalse(task._root.exists())
        self.assertEqual(before, _source_snapshot(self.source))

    def test_cleanup_refuses_junction_and_preserves_external_directory(self):
        task = self.prepare()
        outside = Path(self.temp.name) / 'user-files'
        outside.mkdir()
        (outside / 'keep.txt').write_bytes(b'user file')
        link = task.workspace / 'linked'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(link))
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(SafetyError):
                task.inspect()
            with self.assertRaises(SafetyError):
                task.discard()
            self.assertEqual((outside / 'keep.txt').read_bytes(), b'user file')
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_new_source_commit_invalidates_checkpoint_without_rewriting_history(self):
        task = self.prepare()
        (self.source / 'other.txt').write_bytes(b'new commit')
        _git(self.source, 'add', 'other.txt')
        _git(self.source, 'commit', '--quiet', '-m', 'New user commit')
        new_head = _git(self.source, 'rev-parse', 'HEAD')
        with self.assertRaises(SafetyError):
            task.checkpoint(validation_passed=True)
        task.discard()
        self.assertEqual(_git(self.source, 'rev-parse', 'HEAD'), new_head)

    def test_source_change_during_temporary_commit_still_fails_closed(self):
        task = self.prepare()
        real = _source_snapshot
        count = 0
        def race(root):
            nonlocal count
            count += 1
            if count == 2:
                (self.source / 'other.txt').write_bytes(b'race user data')
            return real(root)
        with patch('git_checkpoints._source_snapshot', side_effect=race):
            with self.assertRaisesRegex(SafetyError, 'during checkpoint'):
                task.checkpoint(validation_passed=True)
        self.assertEqual(task.state, 'stale')
        self.assertEqual((self.source / 'other.txt').read_bytes(), b'race user data')

    def test_ignored_files_remain_untouched_when_discarding_stale_task(self):
        (self.source / 'ignored').mkdir()
        task = self.prepare()
        secret = self.source / 'ignored/new-secret'
        secret.write_bytes(b'new user data')
        self.assertTrue(task.inspect()['stale'])
        task.discard()
        self.assertEqual(secret.read_bytes(), b'new user data')

    def test_require_exact_root_and_existing_commit(self):
        folder = self.source / 'subfolder'
        folder.mkdir()
        with self.assertRaises(SafetyError):
            GitCheckpoint.prepare(folder, ['code.py'])
        unborn = Path(self.temp.name) / 'unborn'
        unborn.mkdir()
        _git(unborn, 'init', '--quiet', '--template=')
        with self.assertRaises(SafetyError):
            GitCheckpoint.prepare(unborn, ['new.py'])

    def test_source_git_operations_are_read_only_allowlist(self):
        calls = []
        actual = _git
        def record(root, *args, **kwargs):
            if Path(root) == self.source:
                calls.append(args[0])
            return actual(root, *args, **kwargs)
        with patch('git_checkpoints._git', side_effect=record):
            task = self.prepare()
            task.write('code.py', b'new text')
            task.checkpoint(validation_passed=True)
            task.discard()
        self.assertTrue(set(calls).issubset({'rev-parse', 'show-ref', 'ls-files',
                                           'ls-tree', 'cat-file', 'check-ignore'}))

    def test_source_content_filter_is_not_executed(self):
        (self.source / '.gitattributes').write_text('code.py filter=trap\n')
        _git(self.source, 'config', 'filter.trap.clean', 'alfha-command-that-does-not-exist')
        _git(self.source, 'config', 'filter.trap.required', 'true')
        before = (self.source / '.git/config').read_bytes()
        task = self.prepare()
        task.write('code.py', b'candidate data\n')
        self.assertTrue(task.inspect()['source_unchanged'])
        self.assertEqual(before, (self.source / '.git/config').read_bytes())

    def test_failed_temporary_initialization_cleans_owned_root(self):
        actual = _git
        temporary_roots = []
        def fail(root, *args, **kwargs):
            if args[0] == 'init' and Path(root) != self.source:
                temporary_roots.append(Path(root).parent)
                raise SafetyError('controlled initialization failure')
            return actual(root, *args, **kwargs)
        with patch('git_checkpoints._git', side_effect=fail):
            with self.assertRaisesRegex(SafetyError, 'initialization failure'):
                self.prepare()
        self.assertEqual(len(temporary_roots), 1)
        self.assertFalse(temporary_roots[0].exists())


if __name__ == '__main__':
    unittest.main()
