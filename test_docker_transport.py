"""Transport unit tests use synthetic Docker responses, never host candidate code."""
import copy
import hashlib
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from evaluations.docker_transport import DockerTransport, IsolationError, PINNED_IMAGE, bounded_command
from evaluations.execution_backend import DockerExecutionBackend
from evaluations import verify_docker_isolation
from test_execution_backend import inspected_container, IMAGE_ID


def completed(stdout='', stderr='', code=0, **changes):
    return dict(stdout=stdout, stderr=stderr, returncode=code, timed_out=False,
                output_truncated=False, io_incomplete=False, duration_seconds=0.01, **changes)


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.containers = set()
        self.doc = inspected_container()
        self.doc['HostConfig']['ShmSize'] = 1048576
        self.doc['Config'].update(Entrypoint=['python3'], Cmd=['-I', '-B', '-u', '-'],
                                  WorkingDir='/tmp', OpenStdin=True, Tty=False, Env=[])
        self.doc['State'] = {'Status': 'exited', 'Running': False, 'ExitCode': 0, 'OOMKilled': False}
        self.endpoint = 'npipe:////./pipe/dockerDesktopLinuxEngine'
        self.info = dict(OSType='linux', Architecture='x86_64', CgroupVersion='2', MemoryLimit=True,
                         SwapLimit=True, CpuCfsQuota=True, PidsLimit=True,
                         SecurityOptions=['name=seccomp,profile=builtin'], ID='test-daemon',
                         ServerVersion='test', KernelVersion='test')
        self.image = dict(Os='linux', Architecture='amd64', RepoDigests=[PINNED_IMAGE],
                          Id=IMAGE_ID, Size=100, Config={'Env': [], 'Volumes': None})
        self.fail_create = self.fail_attach = self.fail_cleanup = self.timeout = False

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        args = argv[3:]
        if args[:2] == ['context', 'inspect']:
            return completed(json.dumps([{'Endpoints': {'docker': {'Host': self.endpoint}}}]))
        if args[0] == 'info':
            return completed(json.dumps(self.info))
        if args[:2] == ['image', 'inspect']:
            return completed(json.dumps([self.image]))
        if args[0] == 'create':
            self.containers.add(args[args.index('--name') + 1])
            return completed('c' * 64, code=1 if self.fail_create else 0)
        if args[:2] == ['container', 'inspect']:
            if self.fail_cleanup:
                return completed(stderr='Cannot connect to daemon', code=1)
            if args[-1] not in self.containers:
                return completed(stderr='Error: No such container: ' + args[-1], code=1)
            return completed(json.dumps([self.doc]))
        if args[0] == 'start':
            if self.fail_attach:
                raise OSError('attachment lost')
            result = completed('{"calculation":42}')
            result['timed_out'] = self.timeout
            return result
        if args[0] == 'kill':
            self.doc['State']['ExitCode'] = 137
            return completed()
        if args[0] == 'rm':
            if not self.fail_cleanup:
                self.containers.discard(args[-1])
            return completed(code=1 if self.fail_cleanup else 0)
        raise AssertionError(args)


class DockerTransportTests(unittest.TestCase):
    def make(self):
        fake = FakeDocker()
        with patch('evaluations.docker_transport.shutil.which', return_value='docker.exe'):
            transport = DockerTransport(command_runner=fake)
        return transport, fake

    def test_fixed_policy_and_stdin_transport(self):
        transport, fake = self.make()
        program = 'print(6 * 7)'
        result = transport.run_controlled(program)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['cleanup']['verified_absent'])
        self.assertFalse(fake.containers)
        start = next(call for call in fake.calls if call[0][3] == 'start')
        self.assertEqual(start[1]['input_bytes'], program.encode())
        self.assertNotIn(program, start[0])
        create = next(call[0] for call in fake.calls if call[0][3] == 'create')
        self.assertIn('--read-only', create)
        self.assertIn('--cap-drop', create)
        self.assertIn('none', create)
        self.assertNotIn('--mount', create)
        self.assertNotIn('--privileged', create)
        self.assertIn(IMAGE_ID, create)

    def test_policy_mismatch_never_starts_and_cleans(self):
        transport, fake = self.make()
        fake.doc['HostConfig']['NetworkMode'] = 'host'
        result = transport.run_controlled('print(42)')
        self.assertTrue(result['policy_verification'])
        self.assertFalse(any(c[0][3] == 'start' for c in fake.calls))
        self.assertTrue(result['cleanup']['verified_absent'])

    def test_no_host_environment_injection(self):
        transport, fake = self.make()
        fake.doc['Config']['Env'] = ['SECRET=not-allowed']
        result = transport.run_controlled('print(42)')
        self.assertIn('Unexpected injected container environment', result['policy_verification'])
        self.assertFalse(any(c[0][3] == 'start' for c in fake.calls))

    def test_moby_omitted_empty_fields_with_required_effective_mounts(self):
        transport, fake = self.make()
        del fake.doc['HostConfig']['Mounts']
        del fake.doc['HostConfig']['Sysctls']
        result = transport.run_controlled('print(42)')
        self.assertEqual(result['status'], 'completed')
        transport, fake = self.make()
        del fake.doc['Mounts']
        result = transport.run_controlled('print(42)')
        self.assertTrue(result['policy_verification'])
        self.assertFalse(any(c[0][3] == 'start' for c in fake.calls))

    def test_timeout_kills_container_then_removes_and_confirms_absence(self):
        transport, fake = self.make()
        fake.timeout = True
        result = transport.run_controlled('controlled data')
        operations = [call[0][3] for call in fake.calls]
        self.assertIn('kill', operations)
        self.assertLess(operations.index('kill'), operations.index('rm'))
        self.assertTrue(result['timed_out'])
        self.assertTrue(result['cleanup']['verified_absent'])

    def test_create_and_attach_failures_still_clean(self):
        for field in ('fail_create', 'fail_attach'):
            transport, fake = self.make()
            setattr(fake, field, True)
            result = transport.run_controlled('controlled data')
            self.assertEqual(result['status'], 'transport_error')
            self.assertTrue(result['cleanup']['verified_absent'])
            self.assertFalse(fake.containers)

    def test_cleanup_uncertainty_locks_transport(self):
        transport, fake = self.make()
        fake.fail_cleanup = True
        result = transport.run_controlled('controlled data')
        self.assertFalse(result['cleanup']['verified_absent'])
        self.assertTrue(transport.poisoned)
        with self.assertRaises(IsolationError):
            transport.run_controlled('controlled data')

    def test_remote_context_and_missing_resource_controls_fail_before_create(self):
        for configure in (lambda f: setattr(f, 'endpoint', 'tcp://remote:2375'),
                          lambda f: f.info.update(PidsLimit=False),
                          lambda f: f.info.update(SecurityOptions=[]),
                          lambda f: f.info.update(OSType='windows'),
                          lambda f: f.image.update(RepoDigests=[])):
            transport, fake = self.make()
            configure(fake)
            with self.assertRaises(IsolationError):
                transport.run_controlled('controlled data')
            self.assertFalse(any(c[0][3] == 'create' for c in fake.calls))

    def test_unsafe_options_and_names_rejected(self):
        transport, fake = self.make()
        with self.assertRaises(TypeError):
            transport.run_controlled('controlled data', docker_options=['--privileged'])
        with self.assertRaises(IsolationError):
            transport.cleanup('unrelated-user-container')
        with self.assertRaises(IsolationError):
            transport.create_arguments('--network=host', IMAGE_ID)
        self.assertFalse(fake.calls)

    def test_input_bound(self):
        transport, fake = self.make()
        with self.assertRaises(IsolationError):
            transport.run_controlled('x' * 100001)
        self.assertFalse(fake.calls)

    def test_unstarted_container_does_not_report_completion(self):
        transport, fake = self.make()
        fake.doc['State']['Status'] = 'created'
        result = transport.run_controlled('print(42)')
        self.assertEqual(result['status'], 'transport_error')
        self.assertTrue(result['cleanup']['verified_absent'])

    def test_output_capped_during_read_without_running_host_program(self):
        class Process:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO(b'x' * 200000)
                self.stderr = io.BytesIO(b'y' * 200000)
                self.returncode = 0
            def poll(self): return self.returncode
            def wait(self, timeout=None): return self.returncode
            def kill(self): self.returncode = -9
        with patch('evaluations.docker_transport.subprocess.Popen', return_value=Process()):
            result = bounded_command(['docker.exe', 'synthetic'], timeout=1)
        self.assertTrue(result['output_truncated'])
        self.assertLessEqual(len(result['stdout']) + len(result['stderr']), 65536)

    def test_cli_deadline_kills_mock_process(self):
        class Process:
            def __init__(self):
                self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
                self.returncode = None
            def poll(self): return self.returncode
            def wait(self, timeout=None): return self.returncode
            def kill(self): self.returncode = -9
        process = Process()
        with patch('evaluations.docker_transport.subprocess.Popen', return_value=process):
            result = bounded_command(['docker.exe', 'synthetic'], timeout=0)
        self.assertTrue(result['timed_out'])
        self.assertEqual(process.returncode, -9)

    def test_invalid_utf8_cannot_expand_returned_output_past_limit(self):
        class Process:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO(b'\xff' * 65536)
                self.stderr = io.BytesIO()
                self.returncode = 0
            def poll(self): return self.returncode
            def wait(self, timeout=None): return self.returncode
            def kill(self): self.returncode = -9
        with patch('evaluations.docker_transport.subprocess.Popen', return_value=Process()):
            result = bounded_command(['docker.exe', 'synthetic'], timeout=1)
        self.assertTrue(result['output_truncated'])
        self.assertLessEqual(len(result['stdout'].encode()) + len(result['stderr'].encode()), 65536)

    def test_verified_probes_cannot_enable_live_execution(self):
        identity = {'daemon_id': 'unit-test'}
        backend = DockerExecutionBackend(PINNED_IMAGE)
        backend._transport = SimpleNamespace(preflight=lambda: identity)
        backend._probe_report = {'verified': True, 'execution_enabled': False, 'identity': identity,
            'probe_runner_sha256': hashlib.sha256(Path(verify_docker_isolation.__file__).read_bytes()).hexdigest()}
        report = backend.verify()
        self.assertTrue(report['verified'])
        self.assertFalse(report['execution_enabled'])
        self.assertEqual(backend.execute('NEVER RUN THIS', {})['status'], 'blocked')
        report['verified'] = False
        self.assertTrue(backend.verify()['verified'])

    def test_changed_runtime_identity_invalidates_cached_verification(self):
        backend = DockerExecutionBackend(PINNED_IMAGE)
        backend._transport = SimpleNamespace(preflight=lambda: {'daemon_id': 'changed'})
        backend._probe_report = {'verified': True, 'execution_enabled': False, 'identity': {'daemon_id': 'old'},
            'probe_runner_sha256': hashlib.sha256(Path(verify_docker_isolation.__file__).read_bytes()).hexdigest()}
        self.assertFalse(backend.verify()['verified'])


if __name__ == '__main__':
    unittest.main()
