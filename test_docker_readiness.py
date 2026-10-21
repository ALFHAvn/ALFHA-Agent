"""Deterministic read-only readiness clocks/transports; no Docker or model calls."""
import json
import unittest
from unittest.mock import Mock, patch

from evaluations.docker_readiness import check_docker_readiness, parse_inventory
from evaluations import dependency_preflight


def result(**extra):
    return dict(stdout='', stderr='', returncode=0, timed_out=False,
                output_truncated=False, io_incomplete=False, **extra)


class Clock:
    now = 0.0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class ReadinessTests(unittest.TestCase):
    def run_checks(self, values, timeout=20):
        self.clock = Clock(); self.calls = []
        values = iter(values)
        def runner(argv, *, timeout):
            self.calls.append((argv, timeout))
            value = next(values)
            if isinstance(value, Exception): raise value
            duration, value = value
            self.clock.now += duration
            return value
        return check_docker_readiness(readiness_timeout=timeout, runner=runner, cli='docker.exe',
                                      clock=self.clock, sleep=self.clock.sleep)

    def test_delayed_wake_then_separate_inventory(self):
        r = self.run_checks([(3, {**result(), 'timed_out': True}), (1.2, result()), (0.1, result())])
        self.assertTrue(r['ready'])
        self.assertEqual(r['poll_count'], 2)
        self.assertAlmostEqual(r['readiness_duration_seconds'], 4.7)
        self.assertEqual(r['inventory_status'], 'verified')
        self.assertIn('--size', self.calls[0][0])
        self.assertNotIn('-q', self.calls[0][0])
        self.assertIn('--format', self.calls[-1][0])
        self.assertFalse(r['isolation_verified'])
        self.assertFalse(r['execution_authorized'])

    def test_bounded_readiness_timeout_no_inventory(self):
        r = self.run_checks([(3, {**result(), 'timed_out': True}),
                             (1.5, {**result(), 'timed_out': True})], timeout=5)
        self.assertFalse(r['ready']); self.assertEqual(r['status'], 'readiness_timeout')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1][1], 1.5)
        self.assertIsNone(r['inventory'])

    def test_inventory_timeout_never_retried_or_empty(self):
        r = self.run_checks([(0.1, result()), (3, {**result(), 'timed_out': True})])
        self.assertFalse(r['ready']); self.assertEqual(r['inventory_status'], 'unknown')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1][1], 3)
        self.assertNotIn('containers', r['inventory'])

    def test_final_inventory_transport_failures(self):
        for field, value in [('returncode', 1), ('stderr', 'warning'),
                             ('output_truncated', True), ('io_incomplete', True)]:
            with self.subTest(field=field):
                r = self.run_checks([(0, result()), (0, {**result(), field: value})])
                self.assertFalse(r['ready']); self.assertEqual(r['inventory_status'], 'unknown')
                self.assertEqual(len(self.calls), 2)

    def test_incomplete_readiness_evidence_is_not_polled_again(self):
        r = self.run_checks([(0, {**result(), 'io_incomplete': True})])
        self.assertEqual(r['status'], 'readiness_evidence_failed')
        self.assertEqual(len(self.calls), 1)

    def test_empty_or_inconsistent_transport_schema_fails_closed(self):
        r = self.run_checks([(0, result()), (0, {})])
        self.assertFalse(r['ready']); self.assertEqual(r['inventory_status'], 'unknown')

    def test_inventory_valid_other_container_and_owned_rejected(self):
        for name in ('unrelated', 'alfha-functional-123'):
            row = dict(ID='a'*64, Names=name, Image='example', State='running', Labels='')
            r = self.run_checks([(0, result()), (0, {**result(), 'stdout': json.dumps(row)})])
            self.assertEqual(r['ready'], name == 'unrelated')
            self.assertEqual(r['inventory_status'], 'verified')

    def test_malformed_inventory_rejected(self):
        row = dict(ID='a'*64, Names='x', Image='example', State='running', Labels='')
        for text in ('{}', 'not json', '\n', json.dumps(row)+'\n'+json.dumps(row),
                     '{"ID":"a","ID":"b"}', '{"ID":NaN}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_inventory(text)

    def test_readiness_malformed_ids_rejected(self):
        r = self.run_checks([(0, {**result(), 'stdout': 'partial-id\n'})])
        self.assertFalse(r['ready']); self.assertEqual(r['poll_count'], 1)

    def test_readiness_uses_engine_size_path_then_independent_inventory(self):
        r = self.run_checks([(0.1, result()), (0.1, result())])
        self.assertTrue(r['ready'])
        self.assertIn('--size', self.calls[0][0])
        self.assertNotIn('--size', self.calls[1][0])
        self.assertEqual(len(self.calls), 2)

    def test_no_success_returned_after_readiness_deadline(self):
        r = self.run_checks([(5, result())], timeout=5)
        self.assertFalse(r['ready']); self.assertIsNone(r['inventory'])

    def test_configuration_rejected_before_commands(self):
        for timeout in (True, 0, 61, float('inf'), float('nan'), '20'):
            runner = Mock()
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                check_docker_readiness(readiness_timeout=timeout, runner=runner)
            runner.assert_not_called()

    def test_inventory_exception_preserved_without_retry(self):
        r = self.run_checks([(0, result()), OSError('transport disappeared')])
        self.assertEqual(r['inventory_status'], 'unknown')
        self.assertIn('transport disappeared', r['error'])
        self.assertEqual(len(self.calls), 2)

    def test_cli_stops_before_other_dependencies_on_readiness_failure(self):
        with patch('evaluations.docker_readiness.check_docker_readiness', return_value={'ready': False}), \
                patch.object(dependency_preflight, 'check_dependencies') as deps, patch('builtins.print'):
            self.assertEqual(dependency_preflight.main(['--verify-docker-inventory']), 2)
        deps.assert_not_called()

    def test_cli_includes_inventory_evidence_on_success(self):
        with patch('evaluations.docker_readiness.check_docker_readiness', return_value={'ready': True}) as ready, \
                patch.object(dependency_preflight, 'check_dependencies', return_value={'ready': True}), \
                patch('builtins.print') as output:
            self.assertEqual(dependency_preflight.main(['--verify-docker-inventory', '--readiness-timeout', '25']), 0)
        ready.assert_called_once_with(readiness_timeout=25)
        self.assertEqual(json.loads(output.call_args.args[0])['docker_readiness'], {'ready': True})
