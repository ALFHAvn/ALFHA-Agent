"""Read-only dependency diagnostics, mocked services and real disposable staging."""
import copy
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import httpx

from evaluations import dependency_preflight as preflight
from evaluations.docker_transport import DockerTransport, IsolationError, PINNED_IMAGE
from test_docker_transport import FakeDocker, completed
import test_coding_workflow as workflow
from coding_workflow import run_task


class DependencyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDocker()
        with patch('evaluations.docker_transport.shutil.which', return_value='docker.exe'):
            self.transport = DockerTransport(command_runner=self.fake)
        self.tags = {'models': [{'model': 'qwen3:4b', 'digest': 'a' * 64}]}
        self.details = {'capabilities': ['completion', 'tools'], 'template': '{{ .Tools }}'}
        self.metadata = Mock(side_effect=lambda method, path, payload=None:
                             copy.deepcopy(self.tags if path == '/api/tags' else self.details))

    def check(self):
        return preflight.check_dependencies(metadata=self.metadata, docker_factory=lambda: self.transport)

    def test_healthy_metadata_is_not_execution_or_isolation_authorization(self):
        report = self.check()
        self.assertTrue(report['ready'])
        self.assertFalse(report['model_invoked'])
        self.assertFalse(report['execution_authorized'])
        self.assertFalse(report['isolation_verified'])
        self.assertEqual([c[0][3] for c in self.fake.calls], ['context', 'info', 'image'])
        self.assertEqual([c.args[:2] for c in self.metadata.call_args_list],
                         [('GET', '/api/tags'), ('POST', '/api/show')])

    def test_unavailable_ollama_is_infrastructure_not_model_failure(self):
        self.metadata.side_effect = httpx.ConnectError('connection refused')
        report = self.check()
        self.assertFalse(report['ready'])
        self.assertEqual(report['failure_domain'], 'infrastructure')
        self.assertEqual(report['checks']['ollama_api']['category'], 'unavailable')
        self.assertEqual(report['checks']['ollama_models']['qwen3:4b']['status'], 'not_checked')
        self.metadata.assert_called_once()

    def test_ollama_timeout_has_no_retry(self):
        self.metadata.side_effect = httpx.ReadTimeout('read deadline')
        self.assertEqual(self.check()['checks']['ollama_api']['category'], 'timeout')
        self.metadata.assert_called_once()

    def test_missing_model_does_not_pull_or_show(self):
        self.tags['models'] = []
        report = self.check()
        self.assertEqual(report['checks']['ollama_api']['status'], 'passed')
        self.assertEqual(report['checks']['ollama_models']['qwen3:4b']['category'], 'model_missing')
        self.assertFalse(report['ready'])
        self.metadata.assert_called_once()

    def test_missing_or_duplicate_inventory_evidence_fails_closed(self):
        for tags in ({}, {'models': [None]}, {'models': [{'model': 'qwen3:4b'}]},
                     {'models': self.tags['models'] * 2}):
            with self.subTest(tags=tags):
                self.tags = tags
                self.assertFalse(self.check()['ready'])

    def test_model_without_tools_or_template_rejected(self):
        for details in ({}, {'capabilities': ['completion'], 'template': 'x'},
                        {'capabilities': ['completion', 'tools'], 'template': ''}):
            self.details = details
            report = self.check()
            self.assertFalse(report['ready'])
            self.assertEqual(report['checks']['ollama_models']['qwen3:4b']['category'], 'model_incompatible')

    def test_missing_docker_cli_fails_closed(self):
        def missing():
            raise IsolationError('Docker CLI not found')
        report = preflight.check_dependencies(metadata=self.metadata, docker_factory=missing)
        self.assertFalse(report['ready'])
        self.assertEqual(report['checks']['docker_image']['status'], 'not_checked')

    def test_docker_engine_unavailable_preserves_evidence(self):
        self.transport.runner = lambda *a, **k: completed(stderr='daemon unavailable', code=1)
        report = self.check()
        self.assertEqual(report['checks']['docker_engine']['category'], 'metadata_transport_error')
        self.assertIn('daemon unavailable', json.dumps(report['docker_metadata_audit']))
        self.assertFalse(report['ready'])

    def test_docker_timeout_fails_without_retry(self):
        self.transport.runner = Mock(return_value={**completed(), 'timed_out': True})
        report = self.check()
        self.assertEqual(report['checks']['docker_engine']['category'], 'metadata_timeout')
        self.transport.runner.assert_called_once()

    def test_windows_engine_and_missing_security_controls_rejected(self):
        for key, value in (('OSType', 'windows'), ('MemoryLimit', False), ('PidsLimit', False),
                           ('SecurityOptions', []), ('CgroupVersion', '1')):
            with self.subTest(key=key):
                original = self.fake.info[key]
                self.fake.info[key] = value
                self.assertEqual(self.check()['checks']['docker_engine']['category'], 'policy_mismatch')
                self.fake.info[key] = original

    def test_remote_docker_context_rejected(self):
        self.fake.endpoint = 'tcp://remote.example:2375'
        self.assertEqual(self.check()['checks']['docker_engine']['category'], 'policy_mismatch')
        self.assertEqual(len(self.fake.calls), 1)

    def test_missing_or_wrong_image_keeps_engine_distinct(self):
        for image in ([], [{**self.fake.image, 'RepoDigests': ['other']}], [{}]):
            def runner(argv, **kwargs):
                return completed(json.dumps(image)) if argv[3] == 'image' else self.fake(argv, **kwargs)
            self.transport.runner = runner
            report = self.check()
            self.assertEqual(report['checks']['docker_engine']['status'], 'passed')
            self.assertEqual(report['checks']['docker_image']['status'], 'failed')
            self.assertFalse(report['ready'])

    def test_invalid_model_scopes_rejected_before_io(self):
        for models in ([], ['x'], ['a:b', 'a:b'], ['x:y'] * 4, ['http://example:a']):
            with self.assertRaises(ValueError):
                preflight.check_dependencies(models, metadata=self.metadata)
        self.metadata.assert_not_called()

    def test_cli_runner_only_allows_exact_readonly_commands_and_bounded_timeout(self):
        prefix = ['docker.exe', '--context', 'desktop-linux']
        with patch.object(preflight, 'bounded_command', return_value=completed()) as command:
            preflight.readonly_docker_command(prefix + ['image', 'inspect', PINNED_IMAGE], timeout=100)
            self.assertEqual(command.call_args.kwargs['timeout'], 3)
            for args in (['pull', PINNED_IMAGE], ['start', 'x'], ['run', PINNED_IMAGE],
                         ['info', '--format', '{{json .}}', '--extra']):
                with self.assertRaises(preflight.DependencyError):
                    preflight.readonly_docker_command(prefix + args, timeout=3)
            self.assertEqual(command.call_count, 1)

    def test_http_transport_enforces_endpoint_status_schema_and_size(self):
        for status, content, category in ((503, b'down', 'http_error'),
                (302, b'', 'http_error'), (200, b'{', 'malformed_metadata'),
                (200, b'{"models":[],"models":[]}', 'malformed_metadata'),
                (200, b'x' * (preflight.OUTPUT_LIMIT + 1), 'output_limit')):
            with self.subTest(category=category):
                response = Mock(status=status, length=None, read1=io.BytesIO(content).read1)
                with patch.object(preflight, 'MetadataConnection') as connection:
                    connection.return_value.getresponse.return_value = response
                    with self.assertRaises(preflight.DependencyError) as caught:
                        preflight.ollama_metadata('GET', '/api/tags')
                    self.assertEqual(caught.exception.category, category)
                    connection.return_value.close.assert_called_once()
        with self.assertRaises(preflight.DependencyError):
            preflight.ollama_metadata('POST', '/api/chat', {})

    def test_stream_deadline_rejects_slow_metadata(self):
        response = Mock(status=200, length=None, read1=io.BytesIO(b'{}').read1)
        with patch.object(preflight, 'MetadataConnection') as connection, patch.object(
                preflight.time, 'monotonic', side_effect=[0, 4]):
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(preflight.DependencyError) as caught:
                preflight.ollama_metadata('GET', '/api/tags')
            self.assertEqual(caught.exception.category, 'timeout')

    def test_socket_deadline_applies_to_each_header_and_body_read(self):
        with preflight.DeadlineSocket() as sock:
            sock.deadline = 3
            with patch.object(preflight.time, 'monotonic', return_value=4):
                with self.assertRaises(TimeoutError):
                    sock.recv_into(bytearray(1))
                with self.assertRaises(TimeoutError):
                    sock.sendall(b'x')

    def test_truncated_http_body_rejected_even_when_json_is_complete(self):
        response = Mock(status=200, length=100, read1=io.BytesIO(b'{}').read1)
        with patch.object(preflight, 'MetadataConnection') as connection:
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(preflight.DependencyError) as caught:
                preflight.ollama_metadata('GET', '/api/tags')
            self.assertEqual(caught.exception.category, 'incomplete_metadata')

    def test_functional_cli_blocked_dependencies_never_claim_authorization(self):
        from evaluations import benchmark_functional as benchmark
        evidence = {'ready': False, 'checks': {'docker_engine': {'status': 'failed'}}}
        with tempfile.TemporaryDirectory() as temp, patch.object(benchmark.controller.syntax, 'RUNS', Path(temp)), \
                patch.object(preflight, 'check_dependencies', return_value=evidence), \
                patch.object(benchmark, 'OneRunAuthorization') as authorization, \
                patch('ollama.Client') as client, patch.object(benchmark, 'run_benchmark') as run:
            self.assertEqual(benchmark.main(['--authorize-once']), 2)
            report = json.loads(next(Path(temp).glob('*.json')).read_text())
            self.assertEqual(report['failure_domain'], 'infrastructure')
            self.assertFalse(report['model_invoked'])
            self.assertEqual(report['authorization']['state'], 'not_granted')
            authorization.assert_not_called()
            client.assert_not_called()
            run.assert_not_called()


class PreflightWorkflowTests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp
    tearDown = workflow.WorkflowTests.tearDown
    request = workflow.WorkflowTests.request

    def test_unavailable_dependency_records_zero_attempts_before_staging(self):
        evidence = {'ready': False, 'failure_domain': 'infrastructure',
                    'checks': {'ollama_api': {'status': 'failed', 'category': 'timeout'}}}
        with patch('coding_workflow.check_dependencies', return_value=evidence), patch(
                'coding_workflow.MultiFileTask.prepare') as prepare:
            chat = Mock()
            report = run_task(self.request(), chat_fn=chat)
        self.reports.append(Path(report['report_path']))
        prepare.assert_not_called()
        chat.assert_not_called()
        self.assertEqual(report['status'], 'preflight_failed')
        self.assertEqual(report['failure_domain'], 'infrastructure')
        self.assertEqual(report['model_requests'], 0)
        self.assertEqual(report['budget_used'], 0)
        self.assertEqual(report['trace'], [])
        self.assertEqual(report['dependency_preflight'], evidence)
        self.assertEqual(json.loads(self.reports[-1].read_text()), report)

    def test_later_model_transport_failure_is_not_tool_call_failure(self):
        report = run_task(self.request(), chat_fn=Mock(side_effect=httpx.ConnectError('Ollama stopped')))
        self.reports.append(Path(report['report_path']))
        self.assertEqual(report['failure_domain'], 'infrastructure')
        self.assertEqual(report['model_request_failure']['exception_type'], 'ConnectError')
        self.assertEqual(report['trace'], [])
        self.assertEqual(report['budget_used'], 0)
        self.assertTrue(report['workspace_discarded'])

    def test_blocked_report_cannot_write_inside_source(self):
        evidence = self.root / 'owned-report-placeholder'
        evidence.mkdir()
        with patch('coding_workflow.check_dependencies', return_value={'ready': False}), patch(
                'coding_workflow.tempfile.mkdtemp', return_value=str(evidence)):
            with self.assertRaisesRegex(workflow.SafetyError, 'outside source'):
                run_task(self.request(), chat_fn=Mock())
        self.assertFalse(evidence.exists())

    def test_authorization_rejection_is_model_tool_use_not_infrastructure(self):
        replies = iter([workflow.response(('read_file', {'filename': 'unauthorized.py'})),
                        workflow.response(text='Done'), workflow.response(text='Done')])
        report = run_task(self.request(), chat_fn=lambda **kw: next(replies))
        self.reports.append(Path(report['report_path']))
        self.assertEqual(report['failure_domain'], 'model_tool_use_or_completion')
        self.assertEqual(report['budget_used'], 1)
        self.assertEqual(len(report['rejected_actions']), 1)
        self.assertTrue(report['workspace_discarded'])
