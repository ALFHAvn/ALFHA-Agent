"""Real Docker transport for trusted isolation probes. Never runs Python on host."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

from .execution_backend import ContainerPolicy, validate_inspection


PINNED_IMAGE = 'python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d'
LOCAL_ENDPOINTS = {'npipe:////./pipe/dockerDesktopLinuxEngine', 'unix:///var/run/docker.sock'}


class IsolationError(RuntimeError):
    pass


def bounded_command(argv, *, timeout, input_bytes=b'', limit=65536):
    """Bound both pipes while reading; kill the CLI on timeout/output overflow.

    Killing the CLI does not stop its container. The caller must ALWAYS remove
    its owned container and independently verify absence, including on exceptions.
    """
    if not isinstance(input_bytes, bytes) or len(input_bytes) > 100_000:
        raise IsolationError('Input exceeds transport limit')
    env = {key: value for key, value in os.environ.items() if not key.startswith('DOCKER_')}
    started = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, shell=False, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    buffers = [bytearray(), bytearray()]
    lock, overflow = threading.Lock(), threading.Event()
    io_errors = []

    def read_pipe(stream, index):
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with lock:
                    remaining = limit - sum(map(len, buffers))
                    buffers[index].extend(chunk[:max(remaining, 0)])
                    if len(chunk) > remaining:
                        overflow.set()
        except (OSError, ValueError) as exc:
            io_errors.append(str(exc))

    def write_input():
        try:
            proc.stdin.write(input_bytes)
            proc.stdin.flush()
        except (OSError, ValueError):
            pass  # Early container exit/CLI kill can close stdin normally.
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    readers = [threading.Thread(target=read_pipe, args=(stream, index), daemon=True)
               for index, stream in enumerate((proc.stdout, proc.stderr))]
    writer = threading.Thread(target=write_input, daemon=True)
    for thread in readers + [writer]:
        thread.start()
    timed_out = False
    try:
        while proc.poll() is None:
            if overflow.is_set():
                proc.kill()
                break
            if time.monotonic() - started >= timeout:
                timed_out = True
                proc.kill()
                break
            time.sleep(0.01)
        proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
        for thread in readers + [writer]:
            thread.join(timeout=1)
        incomplete = any(t.is_alive() for t in readers + [writer])
        for stream in (proc.stdout, proc.stderr):
            if not incomplete:
                stream.close()
    # Invalid UTF-8 replacement characters can expand captured bytes. Bound the
    # returned text too, not only the raw pipe buffers.
    text_streams, remaining = [], limit
    for buffer in buffers:
        encoded = bytes(buffer).decode('utf-8', errors='replace').encode('utf-8')
        if len(encoded) > remaining:
            overflow.set()
        text = encoded[:remaining].decode('utf-8', errors='ignore')
        remaining -= len(text.encode('utf-8'))
        text_streams.append(text)
    return {
        'stdout': text_streams[0],
        'stderr': text_streams[1],
        'returncode': proc.returncode, 'timed_out': timed_out,
        'output_truncated': overflow.is_set(), 'io_incomplete': incomplete or bool(io_errors),
        'duration_seconds': time.monotonic() - started,
    }


class DockerTransport:
    """Only controlled probe scripts are authorized in Step 28C.

    No caller-supplied Docker flags, mounts, environment, context or entrypoint.
    Scripts travel over stdin, not argv or a host mount. There is no image pull.
    """
    def __init__(self, image=PINNED_IMAGE, *, command_runner=bounded_command):
        self.policy = ContainerPolicy()
        self.policy.plan(image)
        self.image = image
        self.runner = command_runner
        self.cli = shutil.which('docker')
        if not self.cli:
            installed = Path.home() / 'AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe'
            if installed.is_file():
                self.cli = str(installed)
        if not self.cli:
            raise IsolationError('Docker CLI not found')
        self.audit = []
        self.poisoned = False

    def command(self, args, *, timeout=10, input_bytes=b''):
        result = self.runner([self.cli, '--context', 'desktop-linux', *args],
                             timeout=timeout, input_bytes=input_bytes, limit=self.policy.output_bytes)
        self.audit.append({'operation': args[0], 'returncode': result['returncode'],
                           'timed_out': result['timed_out'], 'output_truncated': result['output_truncated']})
        return result

    def checked_json(self, args):
        result = self.command(args)
        if result['returncode'] != 0 or result['timed_out'] or result['output_truncated'] or result['io_incomplete']:
            raise IsolationError(f'Docker metadata command failed: {args[0]}: {result["stderr"][:500]}')
        try:
            return json.loads(result['stdout'])
        except (ValueError, TypeError) as exc:
            raise IsolationError('Malformed Docker metadata') from exc

    def preflight(self):
        if self.poisoned:
            raise IsolationError('Transport locked after unverified cleanup')
        contexts = self.checked_json(['context', 'inspect', 'desktop-linux'])
        endpoint = contexts[0]['Endpoints']['docker']['Host']
        if endpoint not in LOCAL_ENDPOINTS:
            raise IsolationError('Only the local Linux Docker endpoint is permitted')
        info = self.checked_json(['info', '--format', '{{json .}}'])
        if (info.get('OSType') != 'linux' or info.get('Architecture') not in ('x86_64', 'amd64') or
                str(info.get('CgroupVersion')) != '2' or
                not all(info.get(k) is True for k in ('MemoryLimit', 'SwapLimit', 'CpuCfsQuota', 'PidsLimit')) or
                'name=seccomp,profile=builtin' not in info.get('SecurityOptions', [])):
            raise IsolationError('Linux/amd64, cgroup v2, resource limits and default seccomp are required')
        image = self.checked_json(['image', 'inspect', self.image])[0]
        if (image.get('Os') != 'linux' or image.get('Architecture') != 'amd64' or
                self.image not in image.get('RepoDigests', []) or
                image.get('Config', {}).get('Volumes') or
                not re.fullmatch(r'sha256:[a-f0-9]{64}', image.get('Id', ''))):
            raise IsolationError('Pinned Linux/amd64 image identity/configuration mismatch')
        return {'endpoint': endpoint, 'daemon_id': info['ID'], 'server_version': info['ServerVersion'],
                'kernel': info['KernelVersion'], 'cgroup_version': info['CgroupVersion'],
                'image': self.image, 'image_id': image['Id'], 'image_size_bytes': image.get('Size'),
                'docker_cli': self.cli,
                'policy': self.policy.plan(self.image),
                'policy_validator_sha256': hashlib.sha256(Path(__file__).with_name('execution_backend.py').read_bytes()).hexdigest(),
                'transport_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def create_arguments(self, name, image_id):
        if not re.fullmatch(r'alfha-eval-[0-9a-f]{32}', name):
            raise IsolationError('Invalid owned container name')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
            raise IsolationError('Invalid local immutable image ID')
        return [
            'create', '--name', name, '--label', 'alfha.execution=security-probe',
            '--pull', 'never', '--platform', 'linux/amd64', '--interactive',
            '--network', 'none', '--user', self.policy.user, '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--cpus', '1', '--memory', '268435456', '--memory-swap', '268435456',
            '--pids-limit', '16', '--ulimit', 'cpu=1:1', '--ulimit', 'nofile=64:64',
            '--ulimit', 'fsize=1048576:1048576', '--ipc', 'private', '--shm-size', '1048576', '--cgroupns', 'private',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1048576,mode=1777',
            '--workdir', '/tmp', '--log-driver', 'none', '--entrypoint', 'python3',
            image_id, '-I', '-B', '-u', '-',
        ]

    def cleanup(self, name):
        if not re.fullmatch(r'alfha-eval-[0-9a-f]{32}', name):
            raise IsolationError('Refusing cleanup of an unowned name')
        evidence = []
        for _ in range(2):
            removal = self.command(['rm', '--force', '--volumes', name])
            absence = self.command(['container', 'inspect', name])
            evidence.append({'remove': removal, 'inspect': absence})
            if (not absence['timed_out'] and not absence['output_truncated'] and not absence['io_incomplete'] and
                    absence['returncode'] != 0 and
                    any(message in absence['stderr'].lower() for message in ('no such container', 'no such object'))):
                return {'status': 'removed', 'verified_absent': True, 'evidence': evidence}
        self.poisoned = True
        return {'status': 'unverified', 'verified_absent': False, 'evidence': evidence}

    def run_controlled(self, program):
        if not isinstance(program, str) or len(program.encode('utf-8')) > 100_000:
            raise IsolationError('Controlled program exceeds input limit')
        identity = self.preflight()
        name = 'alfha-eval-' + uuid.uuid4().hex
        result = {'status': 'transport_error', 'container_name': name, 'container_id': None,
                  'stdout': '', 'stderr': '', 'exit_status': None, 'timed_out': False,
                  'output_truncated': False, 'policy_verification': [], 'identity': identity}
        try:
            created = self.command(self.create_arguments(name, identity['image_id']))
            if created['returncode'] != 0 or created['timed_out'] or created['output_truncated'] or created['io_incomplete']:
                raise IsolationError('Container creation failed: ' + created['stderr'][:500])
            result['container_id'] = created['stdout'].strip()
            inspection = self.checked_json(['container', 'inspect', name])[0]
            errors = validate_inspection(inspection, identity['image_id'])
            # Command and image environment are also checked before START.
            config = inspection.get('Config', {})
            if (config.get('Entrypoint') != ['python3'] or config.get('Cmd') != ['-I', '-B', '-u', '-'] or
                    config.get('WorkingDir') != '/tmp' or config.get('OpenStdin') is not True or
                    config.get('Tty') is not False):
                errors.append('Unexpected container entrypoint/command/stdio configuration')
            image_config = self.checked_json(['image', 'inspect', identity['image_id']])[0]['Config']
            if config.get('Env') != image_config.get('Env'):
                errors.append('Unexpected injected container environment')
            result['policy_verification'] = errors
            if inspection.get('HostConfig', {}).get('ShmSize') != 1048576:
                errors.append('Shared-memory scratch limit mismatch')
            result['inspection'] = inspection
            if errors:
                raise IsolationError('Effective container policy mismatch: ' + '; '.join(errors))
            attached = self.command(['start', '--attach', '--interactive', name],
                                    timeout=self.policy.wall_seconds, input_bytes=program.encode('utf-8'))
            result.update(stdout=attached['stdout'], stderr=attached['stderr'],
                          timed_out=attached['timed_out'], output_truncated=attached['output_truncated'],
                          duration_seconds=attached['duration_seconds'], io_incomplete=attached['io_incomplete'])
            if attached['timed_out'] or attached['output_truncated'] or attached['io_incomplete']:
                result['kill_result'] = self.command(['kill', name])
            state = self.checked_json(['container', 'inspect', name])[0]['State']
            result['container_state'] = state
            result['exit_status'] = state['ExitCode'] if not state['Running'] else None
            exited = state.get('Status') == 'exited' and not state['Running']
            consistent_exit = (attached['timed_out'] or attached['output_truncated'] or
                               attached['returncode'] == result['exit_status'])
            result['status'] = 'completed' if not attached['io_incomplete'] and exited and consistent_exit else 'transport_error'
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            try:
                result['cleanup'] = self.cleanup(name)
            except Exception as exc:
                self.poisoned = True
                result['cleanup'] = {'status': 'unverified', 'verified_absent': False, 'error': str(exc)}
            if not result['cleanup']['verified_absent']:
                result['status'] = 'transport_error'
        return result
