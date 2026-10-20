"""Trusted, explicit file staging in disposable Git repositories.

Not an interactive-agent tool. No source writes, application, resume, push,
source commits, reset or clean operations are implemented.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import uuid


class SafetyError(RuntimeError):
    pass


MAX_FILE_BYTES = 1_000_000


def _git(repo, *args, data=None, ok=(0,)):
    # Do not inherit a caller's alternate repository/index, injected config,
    # external diff, or global/system helpers. These overrides are per-process;
    # no user's Git configuration is modified.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0',
               GIT_AUTHOR_NAME='ALFHA temporary checkpoint',
               GIT_AUTHOR_EMAIL='temporary@localhost',
               GIT_COMMITTER_NAME='ALFHA temporary checkpoint',
               GIT_COMMITTER_EMAIL='temporary@localhost')
    command = ['git', '--no-optional-locks',
               '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull,
               '-c', 'core.autocrlf=false', '-c', 'commit.gpgsign=false',
               '-c', 'core.quotePath=false']
    # check-ignore's stdin protocol takes filenames, not pathspecs, and rejects
    # Git's literal-pathspecs switch. No user input is used as a CLI option.
    if args[0] != 'check-ignore':
        command.append('--literal-pathspecs')
    command += ['-C', str(repo), *args]
    try:
        result = subprocess.run(command, input=data, capture_output=True,
                                timeout=30, env=env, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError('Git transport unavailable') from exc
    if result.returncode not in ok:
        raise SafetyError('Git command failed: ' + args[0] + ': ' + result.stderr.decode('utf-8', errors='replace')[:500])
    return result.stdout


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _path(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise SafetyError('Use an exact relative POSIX file path')
    parts = value.split('/')
    if (PurePosixPath(value).is_absolute() or any(p in ('', '.', '..') for p in parts) or
            any(p.rstrip(' .') != p or p.startswith('.') and p.lower().startswith('.git') for p in parts) or
            any(re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?', p, re.I) for p in parts) or
            any(ord(c) < 32 or c in '<>"|?*' for c in value)):
        raise SafetyError('Unsafe or Git-control path')
    return value


def _reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _safe_file(root, name):
    path = root / _path(name)
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.exists() or parent.is_symlink():
            if _reparse(parent):
                raise SafetyError('Links and reparse points are not authorized')
            if parent.is_file() and parent.stat().st_nlink != 1:
                raise SafetyError('Hard-linked files are not authorized')
    if not path.resolve().is_relative_to(root):
        raise SafetyError('Path escapes workspace')
    # Resolve Windows aliases before checking Git metadata boundaries too.
    _path(path.resolve().relative_to(root).as_posix())
    return path


def _fingerprint(path):
    if _reparse(path):
        return {'kind': 'link', 'target': os.readlink(path)}
    if path.is_dir():
        info = path.stat()
        return {'kind': 'directory', 'mtime_ns': info.st_mtime_ns}
    if not path.is_file():
        raise SafetyError('Unsupported filesystem object')
    # Read for conflict detection only; unrelated content is never copied.
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    info = path.stat()
    return {'kind': 'file', 'sha256': digest.hexdigest(), 'mode': stat.S_IMODE(info.st_mode)}


def _source_snapshot(root):
    """No optional Git index refresh/locks and no filesystem writes."""
    head = _git(root, 'rev-parse', '--verify', 'HEAD').decode().strip()
    refs = _git(root, 'show-ref', '--head')
    # Plumbing inventories do not invoke repository clean/smudge filters.
    # Avoid status/diff against source worktree: those may execute filters.
    ignored = _git(root, 'ls-files', '-z', '--others', '--ignored', '--exclude-standard')
    paths = _git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    files = {}
    for raw in paths:
        if not raw:
            continue
        name = raw.decode('utf-8', errors='strict')
        path = root / name
        # Inventory links without following them or reading external targets.
        for parent in path.parents:
            if parent == root:
                break
            if parent.exists() and _reparse(parent):
                raise SafetyError('Source inventory crosses a link')
        files[name] = _fingerprint(path) if path.exists() or path.is_symlink() else {'kind': 'missing'}
    git_paths = {}
    for name in ('index', 'config', 'HEAD'):
        location = Path(_git(root, 'rev-parse', '--path-format=absolute', '--git-path', name).decode().strip())
        git_paths[name] = _digest(location.read_bytes()) if location.is_file() else None
    return {'head': head, 'refs_sha256': _digest(refs), 'ignored_inventory_sha256': _digest(ignored),
            'git_metadata': git_paths, 'files': files}


class GitCheckpoint:
    """In-memory ownership handle. Saved manifests cannot recreate this handle.

    `prepare` authorizes staging only. It does not authorize project application.
    An authorized existing file must match HEAD and not be ignored. Dirty files
    elsewhere and all untracked/ignored data stay in the source and are not copied.
    """
    def __enter__(self):
        self._owned()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.discard()

    @classmethod
    def prepare(cls, repository, authorized_files):
        requested = Path(repository).absolute()
        for parent in [requested, *requested.parents]:
            if _reparse(parent):
                raise SafetyError('Source path traverses a link')
        source = requested.resolve(strict=True)
        if Path(_git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != source:
            raise SafetyError('Require the exact source repository root')
        if not isinstance(authorized_files, (list, tuple)):
            raise SafetyError('Require an explicit list or tuple of files')
        names = tuple(_path(n) for n in authorized_files)
        if not names or len({n.casefold() for n in names}) != len(names):
            raise SafetyError('Require a nonempty, unique explicit file allowlist')
        if any(a.casefold().startswith(b.casefold() + '/') for a in names for b in names if a != b):
            raise SafetyError('Authorized files cannot be each other\'s parent')
        before = _source_snapshot(source)
        initial = {}
        tracked = {}
        for entry in _git(source, 'ls-tree', '-r', '-z', before['head']).split(b'\0'):
            if entry:
                meta, name = entry.split(b'\t', 1)
                tracked[name.decode()] = meta.decode().split()
        indexed = {}
        for entry in _git(source, 'ls-files', '--stage', '-z').split(b'\0'):
            if entry:
                meta, name = entry.split(b'\t', 1)
                indexed.setdefault(name.decode(), []).append(meta.decode().split())
        for name in names:
            path = _safe_file(source, name)
            if _git(source, 'check-ignore', '--no-index', '-z', '--stdin',
                    data=name.encode() + b'\0', ok=(0, 1)):
                raise SafetyError('Ignored paths are not authorized')
            if name not in tracked:
                if path.exists() or name in indexed:
                    raise SafetyError('Existing untracked files cannot be adopted')
                # A missing child of a tracked file/directory link is also unsafe.
                if any(p.exists() and not p.is_dir() for p in path.parents if p != source):
                    raise SafetyError('Parent is not a directory')
                initial[name] = None
                continue
            mode, kind, oid = tracked[name]
            if indexed.get(name) != [[mode, oid, '0']]:
                raise SafetyError('Authorized file has staged changes or conflicts')
            if mode not in ('100644', '100755') or kind != 'blob':
                raise SafetyError('Only regular tracked files are supported')
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise SafetyError('Authorized file missing or too large')
            blob = _git(source, 'cat-file', 'blob', oid)
            contents = path.read_bytes()
            # Git line-ending normalization may differ from working bytes; do not
            # silently normalize or adopt dirty contents. Either representation
            # must be byte-identical except for CRLF checkout conversion.
            if contents != blob and contents.replace(b'\r\n', b'\n') != blob:
                raise SafetyError('Authorized file has uncommitted changes')
            initial[name] = contents
        if _source_snapshot(source) != before:
            raise SafetyError('Source changed during preparation')
        self = cls()
        self.source, self.authorized, self.initial = source, names, initial
        self.starting_snapshot, self.starting_commit = before, before['head']
        self._root = Path(tempfile.mkdtemp(prefix='alfha-git-')).resolve()
        self._root_identity = self._root.stat().st_ino
        if self._root.is_relative_to(source):
            self._root.rmdir()
            raise SafetyError('Temporary workspace must be outside source')
        self._nonce = uuid.uuid4().hex
        self._marker = self._root / 'ownership.json'
        self._marker.write_text(self._nonce, encoding='ascii')
        self.workspace = self._root / 'workspace'
        self.workspace.mkdir()
        self.state = 'preparing'
        try:
            _git(self.workspace, 'init', '--quiet', '--initial-branch=codex/isolated-task', '--template=')
            for name, contents in initial.items():
                if contents is not None:
                    target = _safe_file(self.workspace, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(contents)
            _git(self.workspace, 'add', '--all')
            _git(self.workspace, 'commit', '--quiet', '--allow-empty', '-m', 'Authorized staging baseline')
            self._baseline = _git(self.workspace, 'rev-parse', 'HEAD').decode().strip()
            self._head = self._baseline
            self._config_hash = _digest((self.workspace / '.git/config').read_bytes())
            self._git_identity = (self.workspace / '.git').stat().st_ino
            self._history = [self._baseline]
            self.state = 'staging'
            self._save_manifest()
            return self
        except BaseException:
            self.discard()
            raise

    def _owned(self):
        # Never traverse a swapped root, ancestor, junction, or symlink for
        # inspection or cleanup. The exact absolute root was created by prepare.
        if self.state == 'discarded':
            raise SafetyError('Workspace already discarded')
        for path in [self._root, *self._root.parents]:
            if _reparse(path):
                raise SafetyError('Ownership path traverses a link')
        if self._root.stat().st_ino != self._root_identity:
            raise SafetyError('Owned root identity changed')
        if _reparse(self._marker) or self._marker.stat().st_nlink != 1 or self._marker.read_text(encoding='ascii') != self._nonce:
            raise SafetyError('Ownership marker mismatch')
        if self._root == self.source or self._root.is_relative_to(self.source):
            raise SafetyError('Cleanup target is not isolated')

    def _guard(self):
        self._owned()
        for base, directories, files in os.walk(self.workspace, followlinks=False):
            for name in directories + files:
                if _reparse(Path(base) / name):
                    raise SafetyError('Links in staging workspace are prohibited')
                if (Path(base) / name).is_file() and (Path(base) / name).stat().st_nlink != 1:
                    raise SafetyError('Hard links in staging workspace are prohibited')
        git_dir = self.workspace / '.git'
        if git_dir.stat().st_ino != self._git_identity or _digest((git_dir / 'config').read_bytes()) != self._config_hash:
            raise SafetyError('Temporary Git configuration changed')
        if _git(self.workspace, 'rev-parse', 'HEAD').decode().strip() != self._head:
            raise SafetyError('Temporary Git history changed externally')

    def write(self, filename, content):
        self._guard()
        if self.state not in ('staging', 'validated') or filename not in self.authorized:
            raise SafetyError('File or task state is not authorized')
        if not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES:
            raise SafetyError('Require bounded bytes')
        target = _safe_file(self.workspace, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        self.state = 'staging'
        self._save_manifest()

    def inspect(self):
        self._guard()
        current_files = set()
        for base, directories, files in os.walk(self.workspace):
            if Path(base) == self.workspace:
                directories[:] = [d for d in directories if d != '.git']
            for name in files:
                current_files.add((Path(base) / name).relative_to(self.workspace).as_posix())
        if not current_files.issubset(self.authorized):
            raise SafetyError('Unauthorized staged filesystem paths')
        modified = [n for n in self.authorized
                    if ((self.workspace / n).read_bytes() if (self.workspace / n).is_file() else None) != self.initial[n]]
        source_unchanged = _source_snapshot(self.source) == self.starting_snapshot
        # Diff is data only. Disable external diff/textconv helpers and include
        # new files using an owned temporary index via git add in this repo only.
        _git(self.workspace, 'add', '--all')
        diff = _git(self.workspace, 'diff', '--cached', '--binary', '--no-ext-diff', '--no-textconv', self._baseline, '--')
        return {'starting_commit': self.starting_commit, 'checkpoint_commit': self._head,
                'authorized_files': list(self.authorized), 'modified_paths': modified,
                'source_unchanged': source_unchanged, 'stale': not source_unchanged,
                'state': self.state, 'diff': diff.decode('utf-8', errors='replace'),
                'application_supported': False, 'approval_required_for_application': True}

    def checkpoint(self, *, validation_passed):
        """Trusted caller attests validation; never executes a validator/candidate."""
        if type(validation_passed) is not bool:
            raise SafetyError('Require explicit validation result')
        if self.state not in ('staging', 'validated'):
            raise SafetyError('Task state does not permit checkpointing')
        review = self.inspect()
        if not validation_passed:
            self.state = 'rejected'
            self._save_manifest()
            raise SafetyError('Validation failed; discard the owned workspace')
        if review['stale']:
            raise SafetyError('Source changed; checkpoint is stale')
        _git(self.workspace, 'commit', '--quiet', '--allow-empty', '-m', 'Validated authorized change checkpoint')
        self._head = _git(self.workspace, 'rev-parse', 'HEAD').decode().strip()
        self._history.append(self._head)
        self.state = 'validated'
        self._save_manifest()
        if _source_snapshot(self.source) != self.starting_snapshot:
            self.state = 'stale'
            self._save_manifest()
            raise SafetyError('Source changed during checkpoint')
        return self.inspect()

    def _save_manifest(self):
        # Metadata is descriptive, not an authorization/resumption capability.
        payload = {'starting_commit': self.starting_commit, 'authorized_files': self.authorized,
                   'state': self.state, 'temporary_commits': getattr(self, '_history', []),
                   'modified_paths': [n for n in self.authorized if
                       ((self.workspace / n).read_bytes() if (self.workspace / n).is_file() else None) != self.initial[n]],
                   'application_supported': False}
        target = _safe_file(self._root, 'manifest.json')
        target.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    def discard(self):
        """Safe rollback is deletion of this exact owned temporary root only."""
        if self.state == 'discarded':
            return
        self._owned()
        # Reject reparse points even inside .git before recursive deletion.
        for base, directories, files in os.walk(self._root, followlinks=False):
            for name in directories + files:
                if _reparse(Path(base) / name):
                    raise SafetyError('Cleanup refused: linked path in temporary root')
                if (Path(base) / name).is_file() and (Path(base) / name).stat().st_nlink != 1:
                    raise SafetyError('Cleanup refused: hard link in temporary root')
        def remove_readonly(function, path, error):
            target = Path(path).resolve()
            if not target.is_relative_to(self._root) or _reparse(Path(path)):
                raise SafetyError('Cleanup target changed')
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            function(path)
        shutil.rmtree(self._root, onexc=remove_readonly)
        self.state = 'discarded'
