"""Execution interface and policy; Step 28C permits controlled Docker probes only.

Model execution stays blocked even after successful controlled verification.
Saved reports are evidence, never execution permits.
"""
from dataclasses import asdict, dataclass
import re
import shutil
from typing import Protocol


PROBES = (
    'normal_calculation', 'wall_timeout', 'network_denied', 'host_files_denied',
    'memory_limit', 'cpu_limit', 'process_limit', 'readonly_nonroot',
    'output_limit', 'unsafe_configuration_rejected', 'cleanup',
)
IMAGE_PATTERN = r'python@sha256:[0-9a-f]{64}'


def identity_differences(expected, observed, path='identity'):
    """Compare in-memory identities without normalizing away type/missing evidence."""
    if type(expected) is dict and type(observed) is dict:
        differences = []
        for key in sorted(expected.keys() | observed.keys()):
            field = path + '.' + key
            if key not in expected or key not in observed:
                differences.append({'field': field, 'expected_present': key in expected,
                                    'observed_present': key in observed,
                                    'expected': expected.get(key), 'observed': observed.get(key)})
            else:
                differences.extend(identity_differences(expected[key], observed[key], field))
        return differences
    if type(expected) is not type(observed) or expected != observed:
        return [{'field': path, 'expected': expected, 'observed': observed,
                 'expected_type': type(expected).__name__, 'observed_type': type(observed).__name__}]
    return []


class VerificationRejected(RuntimeError):
    """Carry the original verification rejection across worker/harness boundaries."""
    def __init__(self, report):
        super().__init__('Current complete isolation verification is required')
        self.verification = report


@dataclass(frozen=True)
class ContainerPolicy:
    """Fixed proposed limits. These are not claimed as currently enforced."""
    memory_bytes: int = 256 * 1024 * 1024
    cpu_nanocpus: int = 1_000_000_000
    cpu_seconds: int = 1
    pids: int = 16
    wall_seconds: int = 2
    tmpfs_bytes: int = 1024 * 1024
    output_bytes: int = 64 * 1024
    user: str = '65534:65534'
    network: str = 'none'
    read_only: bool = True
    privileged: bool = False
    host_mounts: tuple = ()

    def __post_init__(self):
        required = {
            'memory_bytes': 268435456, 'cpu_nanocpus': 1000000000,
            'cpu_seconds': 1, 'pids': 16, 'wall_seconds': 2,
            'tmpfs_bytes': 1048576, 'output_bytes': 65536,
            'user': '65534:65534', 'network': 'none', 'read_only': True,
            'privileged': False, 'host_mounts': (),
        }
        for key, value in required.items():
            actual = getattr(self, key)
            if type(actual) is not type(value) or actual != value:
                raise ValueError(f'Unsupported isolation policy: {key}')

    def plan(self, image):
        if not isinstance(image, str) or not re.fullmatch(IMAGE_PATTERN, image):
            raise ValueError('Use an explicitly selected python@sha256:<64 lowercase hex> image')
        return {
            'image': image, 'pull': 'never', **asdict(self),
            'cap_drop': ['ALL'], 'cap_add': [], 'security_opt': ['no-new-privileges:true'],
            'seccomp': 'runtime_default_required', 'pid_namespace': 'private',
            'ipc_namespace': 'private', 'cgroup_namespace': 'private',
            'devices': [], 'host_environment': [], 'volumes': [],
            'tmpfs': {'/tmp': 'rw,noexec,nosuid,nodev,size=1048576,mode=1777'},
            'input_transport': 'bounded UTF-8 program over stdin; never bind mounts',
            'result_transport': 'bounded stdout/stderr; structured probe observations',
            'timeout_cleanup': 'force-remove only owned random-name container; verify absent',
            'enforced': False,
        }


def validate_inspection(document, image_id):
    """Validate prospective docker-inspect evidence; this does not verify runtime.

    Deliberately reject absent/malformed evidence and any host mounts or expanded
    privileges. A future executor must call this before starting every container.
    Unit tests using synthetic documents are not actual security verification.
    """
    errors = []
    if not isinstance(document, dict):
        return ['Missing container inspection object']
    host, config = document.get('HostConfig'), document.get('Config')
    if not isinstance(host, dict) or not isinstance(config, dict):
        return ['Missing HostConfig or Config']
    expected = {
        'NetworkMode': 'none', 'Privileged': False, 'ReadonlyRootfs': True,
        'Memory': 268435456, 'MemorySwap': 268435456, 'NanoCpus': 1000000000,
        'PidsLimit': 16, 'PidMode': '', 'IpcMode': 'private', 'CgroupnsMode': 'private',
        'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
        'Tmpfs': {'/tmp': 'rw,noexec,nosuid,nodev,size=1048576,mode=1777'},
    }
    for key, value in expected.items():
        actual = host.get(key)
        if type(actual) is not type(value) or actual != value:
            errors.append(f'Isolation setting mismatch: {key}')
    # Moby declares HostConfig.Mounts and Sysctls with JSON omitempty. Their
    # absence means no requested mounts/sysctls, not unavailable evidence.
    # Effective top-level Mounts MUST still be present and empty below.
    for key in ('Mounts', 'Sysctls'):
        if host.get(key) not in (None, [], {}):
            errors.append(f'Unexpected isolation setting: {key}')
    for key in ('Binds', 'CapAdd', 'Devices', 'DeviceRequests', 'VolumesFrom',
                'PortBindings', 'ExtraHosts', 'Links', 'GroupAdd'):
        if key not in host or host[key] not in (None, [], {}):
            errors.append(f'Unexpected or missing isolation evidence: {key}')
    if document.get('Mounts') != [] or config.get('Volumes') not in (None, {}):
        errors.append('Host/image mounts are forbidden')
    if config.get('User') != '65534:65534':
        errors.append('Non-root numeric UID/GID required')
    if not isinstance(image_id, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) or document.get('Image') != image_id:
        errors.append('Image identity mismatch')
    limits = host.get('Ulimits')
    if not isinstance(limits, list) or not any(
            isinstance(limit, dict) and limit.get('Name') == 'cpu' and
            type(limit.get('Soft')) is int and limit['Soft'] == 1 and
            type(limit.get('Hard')) is int and limit['Hard'] == 1 for limit in limits):
        errors.append('CPU-time ulimit required')
    return errors


def blocked_result(reason):
    return {
        'status': 'blocked', 'reason': reason, 'stdout': '', 'stderr': '',
        'exit_status': None, 'timed_out': False, 'output_truncated': False,
        'results': [], 'container_id': None,
        'cleanup': {'status': 'not_created', 'verified_absent': True},
    }


class ExecutionBackend(Protocol):
    def verify(self) -> dict: ...
    def execute(self, source: str, task: dict) -> dict: ...


class DockerExecutionBackend:
    """Controlled-probe adapter; live candidate execution is disabled for Step 28C."""
    def __init__(self, image=None):
        self.policy = ContainerPolicy()
        self.image = image
        self._probe_report = None
        self._transport = None
        if image is not None:
            self.policy.plan(image)  # Reject mutable tags and command injection.

    def verify(self):
        if self._probe_report is not None:
            import copy
            report = copy.deepcopy(self._probe_report)
            audit_start = len(getattr(self._transport, 'audit', []))
            current = {'status': 'failed', 'classification': None, 'identity_differences': []}
            try:
                identity = self._transport.preflight()
                current['observed_identity'] = identity
                from pathlib import Path
                import hashlib
                from . import verify_docker_isolation
                current_probes = hashlib.sha256(Path(verify_docker_isolation.__file__).read_bytes()).hexdigest()
                differences = identity_differences(report.get('identity'), identity)
                current['identity_differences'] = differences
                current['probe_source_sha256'] = current_probes
                if identity != report.get('identity') or current_probes != report.get('probe_runner_sha256'):
                    report['verified'] = False
                    report['reason'] = 'Runtime/image/policy/transport/probe identity changed; reverify.'
                    current['classification'] = 'identity_mismatch' if differences else 'probe_source_mismatch'
                elif differences:
                    # Equality alone considers True == 1; evidence types matter.
                    report['verified'] = False
                    report['reason'] = 'Runtime identity evidence type changed; reverify.'
                    current['classification'] = 'identity_mismatch'
                else:
                    current['status'] = 'passed' if report.get('verified') is True else 'failed'
                    current['classification'] = 'matched' if report.get('verified') is True else 'initial_probes_failed'
            except Exception as exc:
                report['verified'] = False
                report['reason'] = f'Current identity verification failed: {exc}'
                current['failure'] = getattr(exc, 'failure', {'category': 'verification_exception',
                                                            'message': f'{type(exc).__name__}: {exc}'})
                current['classification'] = current['failure']['category']
            current['commands'] = copy.deepcopy(getattr(self._transport, 'audit', [])[audit_start:])
            report['current_verification'] = current
            report['execution_enabled'] = False
            return report
        tools = {name: shutil.which(name) for name in ('docker', 'podman', 'wsl')}
        reason = ('Docker CLI unavailable.' if not tools['docker'] else
                  'Docker discovered, but discovery is not isolation verification.')
        reason += ' Explicit controlled security verification is required; live execution is disabled in Step 28C.'
        return {
            'backend': 'docker-linux', 'verified': False, 'execution_enabled': False,
            'reason': reason, 'detected_executables': tools,
            'image': self.image, 'proposed_policy': self.policy.plan(self.image) if self.image else None,
            'required_controls': {
                'filesystem_isolation': True, 'no_host_secrets': True,
                'network_denied': True, 'wall_timeout': True, 'memory_limit': True,
                'cpu_limit': True, 'process_limit': True, 'bounded_output': True,
                'process_tree_cleanup': True,
            },
            'enforced_execution_controls': None,
            'security_checks': {name: {'status': 'not_run', 'evidence': None} for name in PROBES},
        }

    def execute(self, source, task):
        return blocked_result('Step 28C authorizes controlled probes only; live candidate execution remains disabled.')

    def run_security_checks(self, *, stop_on_failure=False, progress=None):
        """Explicit authorized action, never performed by verify() or execute()."""
        from pathlib import Path
        from .docker_transport import DockerTransport
        from .verify_docker_isolation import run_security_probes
        if not self.image:
            raise ValueError('An explicitly selected immutable image is required')
        self._probe_report = None
        self._transport = DockerTransport(self.image)
        options = {'stop_on_failure': stop_on_failure, 'progress': progress} if stop_on_failure or progress is not None else {}
        self._probe_report = run_security_probes(self._transport, Path(__file__).resolve().parent / 'runs', **options)
        return self.verify()

    def run_verified_worker(self, program):
        """Offline harness only; never an exposed model tool or live enablement."""
        report = self.verify()
        checks = report.get('security_checks', {})
        if (report.get('verified') is not True or set(checks) != set(PROBES) or
                not all(c.get('status') == 'passed' and c.get('evidence') for c in checks.values())):
            raise VerificationRejected(report)
        return self._transport.run_controlled(program)


def verification_passed(report):
    """Require complete, current probe evidence from a trusted in-process adapter.

    This is a report-shape check, not a cryptographic attestation. The production
    adapter never returns verified=True; saved reports are never read as permits.
    """
    if not isinstance(report, dict) or report.get('verified') is not True or report.get('execution_enabled') is not True:
        return False
    checks = report.get('security_checks')
    return (isinstance(checks, dict) and set(checks) == set(PROBES) and
            all(isinstance(check, dict) and check.get('status') == 'passed' and
                bool(check.get('evidence')) for check in checks.values()))


def exact_json_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(exact_json_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(exact_json_equal(actual[k], expected[k]) for k in expected)
    return actual == expected


def apply_execution(assessment, source, task, backend):
    """Integrate structured observations without executing source on this host."""
    try:
        verification = backend.verify()
    except Exception as exc:
        verification = {'verified': False, 'execution_enabled': False,
                        'reason': f'Backend verification error: {type(exc).__name__}: {exc}'}
    if not isinstance(verification, dict):
        verification = {'verified': False, 'execution_enabled': False, 'reason': 'Invalid backend verification report'}
    assessment['isolation'] = verification
    if not verification_passed(verification):
        execution = blocked_result(verification.get('reason', 'Missing security verification'))
    elif not assessment['controller_verification']['static_policy_passed']:
        execution = blocked_result('Candidate failed non-executing policy validation')
    else:
        try:
            execution = backend.execute(source, task)
        except Exception as exc:
            execution = blocked_result(f'Backend error: {type(exc).__name__}: {exc}')
    assessment['execution'] = execution
    if not isinstance(execution, dict) or execution.get('status') == 'blocked':
        assessment['functional_tests']['reason'] = execution.get('reason', 'Invalid backend result') if isinstance(execution, dict) else 'Invalid backend result'
        return assessment
    results = execution.get('results')
    cleanup = execution.get('cleanup')
    streams = [execution.get('stdout'), execution.get('stderr')]
    bounded_streams = (all(isinstance(stream, str) for stream in streams) and
                       sum(len(stream.encode('utf-8')) for stream in streams) <= ContainerPolicy().output_bytes)
    if (execution.get('status') != 'completed' or type(execution.get('exit_status')) is not int or
            execution['exit_status'] != 0 or execution.get('timed_out') is not False or
            execution.get('output_truncated') is not False or not isinstance(cleanup, dict) or
            cleanup.get('verified_absent') is not True or not bounded_streams or not isinstance(results, list) or
            len(results) != len(task['tests'])):
        assessment['functional_tests']['status'] = 'execution_error'
        assessment['functional_tests']['reason'] = 'Incomplete execution, timeout, output limit, or cleanup failure'
        return assessment
    outcomes = []
    for index, (observed, vector) in enumerate(zip(results, task['tests'])):
        valid = isinstance(observed, dict)
        passed = (valid and 'value' in observed and exact_json_equal(observed['value'], vector['expected']) and
                  'args_after' in observed and exact_json_equal(observed['args_after'], vector['args']) and
                  (task['id'] != 'unique_order' or observed.get('new_list') is True))
        outcomes.append({'index': index, 'passed': bool(passed)})
    passed = all(row['passed'] for row in outcomes)
    assessment['functional_tests'].update(status='passed' if passed else 'failed',
                                         passed=passed, executed=len(outcomes), results=outcomes, reason=None)
    assessment['requested_change_confirmed'] = bool(assessment['target_function_changed'] and passed)
    assessment['requested_change_status'] = 'confirmed' if assessment['requested_change_confirmed'] else 'not_demonstrated'
    assessment['passed'] = bool(assessment['changed'] and assessment['requested_change_confirmed'] and assessment['syntax_valid'])
    return assessment
