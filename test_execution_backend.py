"""Interface/policy tests only. No candidate programs or real containers run."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ollama import ChatResponse
from evaluations import execution_backend as execution
from evaluations import evaluate_functional as functional
from evaluations.functional_validation import assess_candidate, CASE_ROOT


IMAGE = 'python@sha256:' + 'a' * 64
IMAGE_ID = 'sha256:' + 'b' * 64


def inspected_container():
    return {
        'Image': IMAGE_ID, 'Mounts': [], 'Config': {'User': '65534:65534', 'Volumes': None},
        'HostConfig': {
            'NetworkMode': 'none', 'Privileged': False, 'ReadonlyRootfs': True,
            'Memory': 268435456, 'MemorySwap': 268435456, 'NanoCpus': 1000000000,
            'PidsLimit': 16, 'PidMode': '', 'IpcMode': 'private', 'CgroupnsMode': 'private',
            'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
            'Tmpfs': {'/tmp': 'rw,noexec,nosuid,nodev,size=1048576,mode=1777'},
            'Binds': None, 'Mounts': None, 'CapAdd': None, 'Devices': None,
            'DeviceRequests': None, 'VolumesFrom': None, 'PortBindings': {},
            'ExtraHosts': None, 'Links': None, 'GroupAdd': None, 'Sysctls': None,
            'Ulimits': [{'Name': 'cpu', 'Soft': 1, 'Hard': 1}],
        },
    }


def test_verification():
    # Trusted dependency-injection fixture, never persisted or used by the CLI.
    return {'verified': True, 'execution_enabled': True,
            'security_checks': {p: {'status': 'passed', 'evidence': 'UNIT TEST DOUBLE ONLY'} for p in execution.PROBES}}


class ExecutionBackendTests(unittest.TestCase):
    def task(self, task_id='sum_even'):
        return functional.task_by_id(task_id)

    def assessment(self, task_id='sum_even'):
        task = self.task(task_id)
        original = (CASE_ROOT / task['filename']).read_text()
        candidate = original.replace('sum(numbers)', 'sum(n for n in numbers if n % 2 == 0)')
        if candidate == original:
            candidate = original.replace('sorted(set(numbers))', 'list(dict.fromkeys(numbers))')
        return assess_candidate(original, candidate, task)

    def observations(self, task):
        return {
            'status': 'completed', 'stdout': '', 'stderr': '', 'exit_status': 0,
            'timed_out': False, 'output_truncated': False,
            'cleanup': {'verified_absent': True},
            'results': [{'value': copy.deepcopy(v['expected']), 'args_after': copy.deepcopy(v['args']), 'new_list': True} for v in task['tests']],
        }

    def adapter(self, result):
        return Mock(verify=Mock(return_value=test_verification()), execute=Mock(return_value=result))

    def test_missing_runtime_is_blocked_without_process_or_artifacts(self):
        with patch.object(execution.shutil, 'which', return_value=None), \
                patch('subprocess.Popen', side_effect=AssertionError('No host process permitted')):
            backend = execution.DockerExecutionBackend()
            status = backend.verify()
            result = backend.execute('while True: pass', self.task())
        self.assertFalse(status['verified'])
        self.assertIsNone(status['enforced_execution_controls'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['cleanup'], {'status': 'not_created', 'verified_absent': True})
        self.assertIsNone(result['exit_status'])

    def test_installed_docker_does_not_unlock_execution(self):
        with patch.object(execution.shutil, 'which', return_value='docker.exe'):
            backend = execution.DockerExecutionBackend(IMAGE)
            status = backend.verify()
            self.assertFalse(status['execution_enabled'])
            self.assertEqual(backend.execute('print(42)', self.task())['status'], 'blocked')
        self.assertTrue(all(c['status'] == 'not_run' and c['evidence'] is None for c in status['security_checks'].values()))

    def test_mutable_or_injected_images_rejected(self):
        for image in ['python:3.12-slim', '--privileged', IMAGE + ' --network host', 'evil@sha256:' + 'a' * 64, 'python@sha256:abc']:
            with self.subTest(image=image), self.assertRaises(ValueError):
                execution.DockerExecutionBackend(image)

    def test_policy_has_no_mounts_credentials_devices_or_privileges(self):
        policy = execution.ContainerPolicy().plan(IMAGE)
        self.assertEqual(policy['network'], 'none')
        self.assertEqual(policy['user'], '65534:65534')
        self.assertTrue(policy['read_only'])
        self.assertFalse(policy['privileged'])
        for field in ['host_mounts', 'volumes', 'devices', 'host_environment', 'cap_add']:
            self.assertFalse(policy[field])
        self.assertEqual(policy['pull'], 'never')
        self.assertFalse(policy['enforced'])

    def test_policy_weakening_rejected(self):
        for field, value in [('network', 'host'), ('privileged', True), ('read_only', False),
                             ('user', '0'), ('pids', 0), ('memory_bytes', 0), ('wall_seconds', 0),
                             ('host_mounts', ('E:/Project',)), ('cpu_seconds', 100), ('output_bytes', 0)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(execution.ContainerPolicy(), **{field: value})

    def test_inspection_expected_policy_is_only_synthetic_evidence(self):
        self.assertEqual(execution.validate_inspection(inspected_container(), IMAGE_ID), [])
        self.assertFalse(execution.DockerExecutionBackend().verify()['verified'])

    def test_dangerous_inspections_rejected(self):
        changes = [
            ('NetworkMode', 'host'), ('Privileged', True), ('ReadonlyRootfs', False),
            ('Memory', 0), ('MemorySwap', -1), ('NanoCpus', 0), ('PidsLimit', -1),
            ('PidMode', 'host'), ('IpcMode', 'host'), ('CgroupnsMode', 'host'),
            ('CapAdd', ['SYS_ADMIN']), ('SecurityOpt', ['seccomp=unconfined']),
            ('Binds', ['E:/Project:/host']), ('Mounts', [{'Type': 'bind', 'Source': '/'}]),
            ('Devices', [{'PathOnHost': '/dev/sda'}]), ('Ulimits', []), ('Tmpfs', {}),
        ]
        for field, value in changes:
            document = inspected_container()
            document['HostConfig'][field] = value
            with self.subTest(field=field):
                self.assertTrue(execution.validate_inspection(document, IMAGE_ID))

    def test_absent_malformed_and_mismatched_inspection_rejected(self):
        for document in [None, {}, {'HostConfig': [], 'Config': {}},
                         {**inspected_container(), 'Image': 'different'},
                         {**inspected_container(), 'Mounts': [{'Source': '/host'}]},
                         {**inspected_container(), 'Config': {'User': 'root', 'Volumes': {'/host': {}}}}]:
            with self.subTest(document=document):
                self.assertTrue(execution.validate_inspection(document, IMAGE_ID))

    def test_incomplete_or_failed_verification_blocks_adapter(self):
        for report in [{}, None, {'verified': True}, test_verification()]:
            if report and 'security_checks' in report:
                report['security_checks']['network_denied']['status'] = 'failed'
            backend = Mock(verify=Mock(return_value=report))
            result = execution.apply_execution(self.assessment(), 'candidate data', self.task(), backend)
            backend.execute.assert_not_called()
            self.assertIsNone(result['functional_tests']['passed'])

    def test_verification_exception_fails_closed(self):
        backend = Mock(verify=Mock(side_effect=RuntimeError('daemon unavailable')))
        result = execution.apply_execution(self.assessment(), 'data', self.task(), backend)
        self.assertEqual(result['execution']['status'], 'blocked')
        backend.execute.assert_not_called()

    def test_structured_values_are_graded_on_host_without_source_execution(self):
        task = self.task()
        result = execution.apply_execution(self.assessment(), 'NOT EXECUTABLE PYTHON', task, self.adapter(self.observations(task)))
        self.assertTrue(result['functional_tests']['passed'])
        self.assertEqual(result['functional_tests']['executed'], 5)
        self.assertTrue(result['requested_change_confirmed'])

    def test_wrong_value_and_boolean_integer_confusion_fail(self):
        for value in [999, False]:
            observed = self.observations(self.task())
            observed['results'][0]['value'] = value
            result = execution.apply_execution(self.assessment(), 'data', self.task(), self.adapter(observed))
            self.assertFalse(result['functional_tests']['passed'])
            self.assertFalse(result['passed'])

    def test_mutated_arguments_fail(self):
        observed = self.observations(self.task())
        observed['results'][0]['args_after'] = [[99]]
        result = execution.apply_execution(self.assessment(), 'data', self.task(), self.adapter(observed))
        self.assertFalse(result['functional_tests']['passed'])

    def test_identity_assertion_for_unique_order(self):
        task = self.task('unique_order')
        observed = self.observations(task)
        observed['results'][0]['new_list'] = False
        assessment = self.assessment('unique_order')
        # Static policy rejects dict.fromkeys; a synthetic permitted assessment is
        # used only to test result grading, never candidate execution.
        assessment['controller_verification']['static_policy_passed'] = True
        result = execution.apply_execution(assessment, 'data', task, self.adapter(observed))
        self.assertFalse(result['functional_tests']['passed'])

    def test_timeout_output_and_cleanup_failures_cannot_pass(self):
        for change in [lambda r: r.update(timed_out=True),
                       lambda r: r.update(exit_status=137),
                       lambda r: r.update(output_truncated=True),
                       lambda r: r.update(stdout='x' * 65537),
                       lambda r: r.update(cleanup={'verified_absent': False}),
                       lambda r: r.update(results=[])]:
            observed = self.observations(self.task())
            change(observed)
            result = execution.apply_execution(self.assessment(), 'data', self.task(), self.adapter(observed))
            self.assertIsNone(result['functional_tests']['passed'])
            self.assertEqual(result['functional_tests']['status'], 'execution_error')

    def test_unsafe_source_blocked_even_with_test_verification(self):
        task = self.task()
        assessment = assess_candidate('def sum_even(numbers): return 0', 'import os', task)
        backend = self.adapter(self.observations(task))
        result = execution.apply_execution(assessment, 'import os', task, backend)
        backend.execute.assert_not_called()
        self.assertEqual(result['execution']['status'], 'blocked')

    def test_backend_exception_and_malformed_results_are_not_passes(self):
        for observed in [None, {}, 'passed']:
            result = execution.apply_execution(self.assessment(), 'data', self.task(), self.adapter(observed))
            self.assertIsNone(result['functional_tests']['passed'])
        backend = self.adapter(None)
        backend.execute.side_effect = RuntimeError('lost connection')
        result = execution.apply_execution(self.assessment(), 'data', self.task(), backend)
        self.assertEqual(result['execution']['status'], 'blocked')

    def test_functional_controller_uses_backend_without_changing_budget(self):
        response = ChatResponse(message={'role': 'assistant', 'content': '', 'tool_calls': [
            {'function': {'name': 'edit_workspace_file', 'arguments': {
                'filename': 'sum_even.py', 'old_text': 'sum(numbers)',
                'new_text': 'sum(n for n in numbers if n % 2 == 0)'}}}]})
        replies = iter([response])
        backend = execution.DockerExecutionBackend()
        result = functional.one_functional_case('sum_even', chat_fn=lambda **kw: next(replies, ChatResponse(message={'role': 'assistant', 'content': 'Done'})), backend=backend)
        self.assertEqual(result['max_tool_calls'], 6)
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(result['execution']['status'], 'blocked')
        self.assertIsNone(result['functional_tests']['passed'])

    def test_verification_cli_records_not_run_and_cannot_reach_model(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(functional.syntax, 'RUNS', Path(directory)), \
                patch.object(functional.syntax.alfha, 'chat', side_effect=AssertionError('No model request allowed')):
            self.assertEqual(functional.main(['--verify-execution', '--image', IMAGE]), 2)
            report = json.loads(next(Path(directory).glob('functional_static_*.json')).read_text())
        self.assertFalse(report['model_invoked'])
        self.assertFalse(report['isolation']['verified'])
        self.assertEqual(len(report['isolation']['security_checks']), len(execution.PROBES))
        self.assertTrue(all(r['execution']['status'] == 'blocked' for r in report['results']))
        self.assertEqual(report['summary']['functional_tests_executed'], 0)


if __name__ == '__main__':
    unittest.main()
