"""Review-only coordinated text editing; no candidate execution or source apply."""
import ast
import copy
import hashlib
import json
from datetime import datetime, timezone

from git_checkpoints import GitCheckpoint, SafetyError, _safe_file


def _text(data):
    try:
        value = data.decode('utf-8')
    except (UnicodeError, AttributeError) as exc:
        raise SafetyError('Only UTF-8 text is authorized') from exc
    if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
        raise SafetyError('Binary/control-byte content is not authorized')
    return value


class MultiFileTask(GitCheckpoint):
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.operations.append({'operation': 'abort', 'status': 'failed',
                                    'error': exc_type.__name__ + ': ' + str(exc_value)[:500]})
        super().__exit__(exc_type, exc_value, traceback)

    @classmethod
    def prepare(cls, repository, authorized_files, *, create_files=(), delete_files=()):
        for scope in (create_files, delete_files):
            if not isinstance(scope, (tuple, list)) or any(n not in authorized_files for n in scope):
                raise SafetyError('Creation/deletion permissions must be explicit allowlist subsets')
        task = super().prepare(repository, authorized_files)
        try:
            for name, data in task.initial.items():
                if data is None and name not in create_files:
                    raise SafetyError('Absent files require explicit creation permission')
                if data is not None:
                    _text(data)
            if any(task.initial[n] is not None for n in create_files):
                raise SafetyError('Creation permission requires an absent file')
            if any(task.initial[n] is None for n in delete_files):
                raise SafetyError('Deletion permission requires an existing file')
            task.create_files, task.delete_files = tuple(create_files), tuple(delete_files)
            task.operations, task.validation = [], None
            task._last_review = None
            task._last_safe_review = None
            return task
        except BaseException:
            # No subclass evidence fields yet; base ownership cleanup only.
            GitCheckpoint.discard(task)
            raise

    def _operation(self, kind, filename, action):
        event = {'sequence': len(self.operations) + 1, 'operation': kind,
                 'filename': filename if isinstance(filename, str) else '<invalid>',
                 'timestamp_utc': datetime.now(timezone.utc).isoformat()}
        try:
            self._guard()
            if filename not in self.authorized or self.state not in ('staging', 'validated'):
                raise SafetyError('File or task state is not authorized')
            result = action()
            event['status'] = 'succeeded'
            return result
        except (SafetyError, OSError, ValueError, TypeError) as exc:
            event.update(status='rejected', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            self.operations.append(event)

    def read_text(self, filename):
        def read():
            return _text(_safe_file(self.workspace, filename).read_bytes())
        return self._operation('read', filename, read)

    def write(self, filename, content):
        def write():
            _text(content)
            if self.initial[filename] is None and filename not in self.create_files:
                raise SafetyError('Creation is not authorized')
            super(MultiFileTask, self).write(filename, content)
            self.validation = None
        return self._operation('write', filename, write)

    def write_text(self, filename, text):
        if not isinstance(text, str):
            # Route type errors through the same audit path.
            return self.write(filename, None)
        return self.write(filename, text.encode('utf-8'))

    def delete(self, filename):
        def remove():
            if filename not in self.delete_files:
                raise SafetyError('Deletion is not authorized')
            _safe_file(self.workspace, filename).unlink()
            self.validation = None
            self.state = 'staging'
            self._save_manifest()
        return self._operation('delete', filename, remove)

    def inspect(self):
        self._guard()
        files = []
        for name in self.authorized:
            path = _safe_file(self.workspace, name)
            if path.exists() and not path.is_file():
                raise SafetyError('Authorized file replaced by a directory')
            current = path.read_bytes() if path.is_file() else None
            original = self.initial[name]
            if original is not None and current is None and name not in self.delete_files:
                raise SafetyError('Unauthorized deletion: ' + name)
            if original is None and current is not None and name not in self.create_files:
                raise SafetyError('Unauthorized creation: ' + name)
            if current is not None:
                _text(current)
            status = ('unchanged' if current == original else 'created' if original is None
                      else 'deleted' if current is None else 'modified')
            files.append({'filename': name, 'status': status,
                          'sha256': hashlib.sha256(current).hexdigest() if current is not None else None})
        review = super().inspect()
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        current_validation = self.validation if self.validation and self.validation['content_digest'] == digest else None
        review.update(per_file=files, content_digest=digest,
                      validation=current_validation or {'status': 'not_run'},
                      creation_authorized=list(self.create_files), deletion_authorized=list(self.delete_files),
                      ready_for_user_review=bool(current_validation and current_validation['passed'] and
                                                 review['source_unchanged'] and review['modified_paths'] and
                                                 self.state in ('staging', 'validated')),
                      execution='not_run', functional_tests='not_run', compilation='not_run')
        return review

    def validate(self):
        """Actual non-executing text/AST/JSON checks; never claims compilability."""
        try:
            review = self.inspect()
            results = []
            for row in review['per_file']:
                name = row['filename']
                outcome = {'filename': name, 'check': 'UTF-8 text', 'passed': True}
                if row['sha256'] is not None:
                    source = _text(_safe_file(self.workspace, name).read_bytes())
                    try:
                        if name.endswith('.py'):
                            outcome['check'] = 'AST parsing only'
                            ast.parse(source.removeprefix('\ufeff'))
                        elif name.endswith('.json'):
                            outcome['check'] = 'JSON parsing'
                            json.loads(source)
                    except (SyntaxError, ValueError, RecursionError) as exc:
                        outcome.update(passed=False, error=f'{type(exc).__name__}: {exc}')
                else:
                    outcome['check'] = 'authorized absence; no source to parse'
                results.append(outcome)
            self.validation = {'status': 'completed', 'passed': all(r['passed'] for r in results),
                               'content_digest': review['content_digest'], 'results': results,
                               'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                               'scope': 'static checks only; no compilation/execution/functional tests'}
            self.operations.append({'operation': 'validate', 'status': 'succeeded' if self.validation['passed'] else 'failed',
                                    'results': copy.deepcopy(results)})
            return copy.deepcopy(self.validation)
        except (SafetyError, OSError) as exc:
            self.operations.append({'operation': 'validate', 'status': 'rejected', 'error': str(exc)})
            raise

    def checkpoint(self, *, validation_passed=True):
        try:
            review = self.inspect()
            if not review['validation'].get('passed') or validation_passed is not True:
                raise SafetyError('Current static validation evidence is required')
            return super().checkpoint(validation_passed=True)
        except (SafetyError, OSError) as exc:
            self.operations.append({'operation': 'checkpoint', 'status': 'rejected', 'error': str(exc)})
            raise

    def report(self):
        if self.state == 'discarded':
            return copy.deepcopy(self._last_review)
        try:
            result = self.inspect()
            result['integrity'] = 'passed'
            self._last_safe_review = copy.deepcopy(result)
        except (SafetyError, OSError) as exc:
            result = {'starting_commit': self.starting_commit, 'checkpoint_commit': self._head,
                      'authorized_files': list(self.authorized), 'integrity': 'rejected',
                      'error': str(exc), 'ready_for_user_review': False,
                      'application_supported': False, 'last_safe_review': copy.deepcopy(self._last_safe_review)}
        result['operations'] = copy.deepcopy(self.operations)
        result['failed_operations'] = [e for e in result['operations'] if e['status'] != 'succeeded']
        self._last_review = copy.deepcopy(result)
        return result

    def discard(self):
        if self.state == 'discarded':
            return
        if hasattr(self, 'operations'):
            self.report()
        super().discard()
        if getattr(self, '_last_review', None) is not None:
            self._last_review.update(workspace_discarded=True, ready_for_user_review=False, state='discarded')
