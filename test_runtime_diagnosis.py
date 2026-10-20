"""Deterministic incident diagnostics using synthetic Docker evidence only."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from evaluations import verify_docker_isolation
from evaluations.docker_transport import DockerTransport, IsolationError, PINNED_IMAGE
from evaluations.execution_backend import DockerExecutionBackend, PROBES, VerificationRejected, identity_differences
from evaluations.diagnose_runtime import run_diagnosis
from test_docker_transport import FakeDocker, completed


class RuntimeDiagnosisTests(unittest.TestCase):
    def make(self):
        fake = FakeDocker()
        with patch('evaluations.docker_transport.shutil.which', return_value='docker.exe'):
            transport = DockerTransport(command_runner=fake)
        backend = DockerExecutionBackend(PINNED_IMAGE)
        backend._transport = transport
        backend._probe_report = {'verified': True, 'execution_enabled': False,
            'identity': transport.preflight(),
            'probe_runner_sha256': hashlib.sha256(Path(verify_docker_isolation.__file__).read_bytes()).hexdigest()}
        return backend, transport, fake

    def lifecycle_backend(self):
        backend, transport, fake = self.make()
        backend._probe_report['security_checks'] = {p: {'status': 'passed', 'evidence': 'TEST DOUBLE'} for p in PROBES}
        backend.run_security_checks = backend.verify

        def runner(argv, **kwargs):
            if argv[3] == 'ps':
                return completed('' if not fake.containers else 'TEST CONTAINER REMAINS')
            if argv[3] == 'start':
                program = kwargs['input_bytes'].decode()
                code = 7 if 'SystemExit' in program else 0
                timeout = 'sleep' in program
                fake.doc['State'].update(ExitCode=code, Status='exited', Running=False)
                raw = completed('42\n' if 'print' in program else '', code=code)
                raw['timed_out'] = timeout
                return raw
            return fake(argv, **kwargs)

        transport.runner = runner
        return backend, transport, fake

    def test_diagnosis_runs_each_trusted_lifecycle_and_checks_cleanup(self):
        backend, transport, fake = self.lifecycle_backend()
        result = run_diagnosis(backend, cycles=3)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['summary']['cycles_passed'], 3)
        self.assertEqual(result['summary']['boundary_checks_recorded'], 6)
        self.assertEqual([c['program'] for c in result['cycles']], ['normal', 'nonzero_exit', 'wall_timeout'])
        self.assertTrue(result['no_evaluation_containers'])
        self.assertEqual(result['historical_root_cause'], 'unresolved')
        self.assertFalse(result['model_invoked'])

    def test_diagnosis_preflight_failure_never_executes(self):
        backend, transport, fake = self.lifecycle_backend()
        fake.info['MemoryLimit'] = False
        result = run_diagnosis(backend, cycles=3)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['cycles'], [])
        self.assertFalse(any(c[0][3] == 'create' for c in fake.calls))

    def test_diagnosis_stops_without_retry_on_failed_execution(self):
        backend, transport, fake = self.lifecycle_backend()
        fake.fail_create = True
        result = run_diagnosis(backend, cycles=3)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['cycles']), 1)
        self.assertEqual(sum(c[0][3] == 'create' for c in fake.calls), 1)
        self.assertTrue(result['no_evaluation_containers'])
        self.assertTrue(result['cycles'][0]['commands'])

    def test_diagnosis_rejects_uncertain_final_container_query(self):
        backend, transport, fake = self.lifecycle_backend()
        runner = transport.runner
        transport.runner = lambda argv, **kw: completed('unrelated-evaluation-container') if argv[3] == 'ps' else runner(argv, **kw)
        result = run_diagnosis(backend, cycles=1)
        self.assertFalse(result['no_evaluation_containers'])
        self.assertEqual(result['status'], 'failed')

    def test_diagnosis_rejects_invalid_cycle_counts(self):
        for count in (0, 101, True, '3'):
            with self.assertRaises(ValueError):
                run_diagnosis(None, cycles=count)

    def test_incomplete_io_retains_raw_evidence_and_never_retries(self):
        backend, transport, fake = self.make()
        calls = []

        def runner(argv, **kwargs):
            if argv[3] == 'info':
                calls.append(argv)
                raw = completed(json.dumps(fake.info), stderr='read evidence')
                raw.update(io_incomplete=True, io_errors=['controlled pipe error'])
                return raw
            return fake(argv, **kwargs)

        transport.runner = runner
        report = backend.verify()
        self.assertFalse(report['verified'])
        current = report['current_verification']
        self.assertEqual(current['classification'], 'metadata_incomplete_io')
        self.assertEqual(current['failure']['operation'][0], 'info')
        self.assertEqual(current['failure']['evidence']['stdout'], json.dumps(fake.info))
        self.assertEqual(current['commands'][-1]['result']['io_errors'], ['controlled pipe error'])
        self.assertEqual(len(calls), 1)
        self.assertFalse(any(call[0][3] == 'create' for call in fake.calls))

    def test_identity_mismatch_reports_exact_field(self):
        backend, transport, fake = self.make()
        fake.info['KernelVersion'] = 'changed-kernel'
        report = backend.verify()
        self.assertFalse(report['verified'])
        current = report['current_verification']
        self.assertEqual(current['classification'], 'identity_mismatch')
        self.assertEqual(current['identity_differences'], [{
            'field': 'identity.kernel', 'expected': 'test', 'observed': 'changed-kernel',
            'expected_type': 'str', 'observed_type': 'str'}])
        self.assertEqual(backend._probe_report['identity']['kernel'], 'test')

    def test_missing_evidence_and_policy_violation_are_distinct_failures(self):
        for missing in (True, False):
            backend, transport, fake = self.make()
            if missing:
                del fake.info['MemoryLimit']
            else:
                fake.info['MemoryLimit'] = False
            report = backend.verify()
            self.assertFalse(report['verified'])
            self.assertEqual(report['current_verification']['classification'],
                             'metadata_invalid_schema' if missing else 'policy_mismatch')

    def test_transport_failures_are_not_policy_mismatches(self):
        for field, value, category in (
                ('returncode', 1, 'metadata_transport_error'),
                ('timed_out', True, 'metadata_timeout'),
                ('output_truncated', True, 'metadata_output_limit')):
            backend, transport, fake = self.make()

            def runner(argv, **kwargs):
                if argv[3] == 'info':
                    raw = completed(stderr='controlled Docker failure')
                    raw[field] = value
                    return raw
                return fake(argv, **kwargs)

            transport.runner = runner
            report = backend.verify()
            self.assertFalse(report['verified'])
            self.assertEqual(report['current_verification']['classification'], category)

    def test_malformed_duplicate_and_nonfinite_json_fail_closed(self):
        for stdout in ('{', '{"MemoryLimit":false,"MemoryLimit":true}', '{"x":NaN}'):
            backend, transport, fake = self.make()
            transport.runner = lambda argv, **kw: completed(stdout) if argv[3] == 'info' else fake(argv, **kw)
            report = backend.verify()
            self.assertFalse(report['verified'])
            failure = report['current_verification']['failure']
            self.assertEqual(failure['category'], 'metadata_malformed_json')
            self.assertEqual(failure['evidence']['stdout'], stdout)

    def test_spawn_exception_is_captured_with_operation(self):
        backend, transport, fake = self.make()

        def runner(argv, **kwargs):
            raise OSError('controlled spawn failure')

        transport.runner = runner
        report = backend.verify()
        self.assertFalse(report['verified'])
        current = report['current_verification']
        self.assertEqual(current['classification'], 'transport_exception')
        self.assertEqual(current['failure']['operation'][:2], ['context', 'inspect'])
        self.assertIn('controlled spawn failure', current['commands'][0]['exception'])

    def test_inconsistent_container_inspection_never_starts_and_cleans(self):
        backend, transport, fake = self.make()

        def runner(argv, **kwargs):
            if argv[3:5] == ['container', 'inspect'] and argv[-1] in fake.containers:
                return completed('[]')
            return fake(argv, **kwargs)

        transport.runner = runner
        result = transport.run_controlled('TRUSTED TEST DATA')
        self.assertEqual(result['failure']['category'], 'metadata_invalid_schema')
        self.assertFalse(any(call[0][3] == 'start' for call in fake.calls))
        self.assertTrue(result['cleanup']['verified_absent'])

    def test_real_policy_fields_still_fail_before_start(self):
        for section, field, value in (
                ('HostConfig', 'NetworkMode', 'host'), ('Config', 'User', '0'),
                ('HostConfig', 'Memory', 0), ('HostConfig', 'PidsLimit', 0),
                ('HostConfig', 'SecurityOpt', []), ('HostConfig', 'CapAdd', ['SYS_ADMIN'])):
            backend, transport, fake = self.make()
            fake.doc[section][field] = value
            result = transport.run_controlled('TRUSTED TEST DATA')
            self.assertEqual(result['failure']['category'], 'policy_mismatch')
            self.assertTrue(result['failure']['evidence']['errors'])
            self.assertTrue(result['cleanup']['verified_absent'])
            self.assertFalse(any(call[0][3] == 'start' for call in fake.calls))

    def test_missing_exit_state_is_not_success_and_cleanup_is_preserved(self):
        backend, transport, fake = self.make()
        del fake.doc['State']['Running']
        result = transport.run_controlled('TRUSTED TEST DATA')
        self.assertEqual(result['status'], 'transport_error')
        self.assertEqual(result['failure']['category'], 'metadata_invalid_schema')
        self.assertTrue(result['cleanup']['verified_absent'])

    def test_identity_diff_does_not_coerce_types_or_missing_fields(self):
        differences = identity_differences({'memory': 1, 'field': None}, {'memory': True})
        self.assertEqual({d['field'] for d in differences}, {'identity.memory', 'identity.field'})

    def test_internal_worker_verification_rejection_preserves_original_reason(self):
        backend, transport, fake = self.make()
        fake.info['MemoryLimit'] = False
        with self.assertRaises(VerificationRejected) as rejected:
            backend.run_verified_worker('TRUSTED TEST DATA')
        self.assertEqual(rejected.exception.verification['current_verification']['classification'], 'policy_mismatch')
        self.assertFalse(any(c[0][3] == 'create' for c in fake.calls))

    def test_harness_preserves_rejected_internal_verification_and_postflight(self):
        from evaluations.functional_harness import FunctionalHarness
        from evaluations.worker_test_cases import REFERENCE_SOURCES
        from test_functional_worker import FakeBackend
        backend = FakeBackend()
        harness = FunctionalHarness(backend)
        harness.prepare()
        failure = {'verified': False, 'reason': 'controlled metadata failure',
                   'current_verification': {'classification': 'metadata_incomplete_io'}}

        def rejected(program):
            raise VerificationRejected(failure)

        backend.run_verified_worker = rejected
        result = harness.run('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['status'], 'execution_error')
        self.assertEqual(result['isolation'], failure)

        backend = FakeBackend()
        harness = FunctionalHarness(backend)
        harness.prepare()
        original = backend.run_verified_worker

        def invalidate(program):
            raw = original(program)
            backend.verified = False
            return raw

        backend.run_verified_worker = invalidate
        result = harness.run('sum_even', REFERENCE_SOURCES['sum_even'])
        self.assertEqual(result['status'], 'execution_error')
        self.assertFalse(result['isolation_after']['verified'])
        self.assertTrue(result['execution']['cleanup']['verified_absent'])

    def test_unverified_cleanup_has_separate_failure_and_locks_transport(self):
        backend, transport, fake = self.make()
        fake.fail_cleanup = True
        result = transport.run_controlled('TRUSTED TEST DATA')
        self.assertFalse(result['cleanup']['verified_absent'])
        self.assertTrue(transport.poisoned)
        report = backend.verify()
        self.assertFalse(report['verified'])
        self.assertEqual(report['current_verification']['classification'], 'cleanup_unverified')


if __name__ == '__main__':
    unittest.main()
