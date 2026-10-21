"""Stop/checkpoint behavior with fake transports; no Docker execution."""
import json
from pathlib import Path
import unittest

from evaluations.verify_docker_isolation import run_security_probes
from evaluations.docker_transport import IsolationError


class Transport:
    def __init__(self, results):
        self.results = iter(results); self.audit = []; self.calls = 0
    def preflight(self): return {'test_double': True}
    def run_controlled(self, program):
        self.calls += 1; self.audit.append({'call': self.calls})
        value = next(self.results)
        if isinstance(value, Exception): raise value
        return value


def normal():
    return {'status': 'completed', 'stdout': json.dumps({'calculation': 42, 'uid': 65534}),
            'stderr': '', 'exit_status': 0, 'timed_out': False, 'output_truncated': False,
            'io_incomplete': False, 'cleanup': {'verified_absent': True}}


class ProbeStopTests(unittest.TestCase):
    def test_first_behavior_failure_stops_and_checkpoints(self):
        t = Transport([{}]); records = []
        r = run_security_probes(t, Path('.'), stop_on_failure=True, progress=records.append)
        self.assertEqual(t.calls, 1)
        self.assertFalse(r['verified'])
        self.assertEqual(r['security_checks']['normal_calculation']['status'], 'failed')
        self.assertEqual(r['security_checks']['wall_timeout']['status'], 'not_run')
        self.assertEqual(records[-1], r)

    def test_full_transport_failure_object_preserved(self):
        error = IsolationError('inspection incomplete', category='inspection_failure',
                               operation=['inspect'], evidence={'raw': 'original'})
        t = Transport([error]); records = []
        r = run_security_probes(t, Path('.'), stop_on_failure=True, progress=records.append)
        self.assertEqual(r['security_checks']['normal_calculation']['evidence']['failure'], error.failure)
        self.assertEqual(t.calls, 1)

    def test_passed_first_probe_followed_by_failure_does_not_continue(self):
        t = Transport([normal(), normal()]); records = []
        r = run_security_probes(t, Path('.'), stop_on_failure=True, progress=records.append)
        self.assertEqual(t.calls, 2)
        self.assertEqual(r['security_checks']['normal_calculation']['status'], 'passed')
        self.assertEqual(r['security_checks']['wall_timeout']['status'], 'failed')
        self.assertEqual(r['security_checks']['network_denied']['status'], 'not_run')

    def test_checkpoint_failure_does_not_dispatch_probe(self):
        t = Transport([])
        def fail(report): raise OSError('checkpoint unavailable')
        with self.assertRaises(OSError):
            run_security_probes(t, Path('.'), stop_on_failure=True, progress=fail)
        self.assertEqual(t.calls, 0)
