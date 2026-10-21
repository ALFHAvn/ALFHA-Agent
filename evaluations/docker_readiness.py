"""Bounded read-only engine wake-up polling, followed by one strict inventory.

Never creates containers, starts services, or retries isolation verification.
Readiness is neither isolation verification nor execution authorization.
"""
import argparse
import json
import math
import re
import time

from .checkpoints import timestamp
from .docker_transport import DockerTransport, bounded_command, metadata_object, invalid_constant

DEFAULT_READINESS_TIMEOUT = 20.0
OPERATION_TIMEOUT = 3.0
POLL_INTERVAL = 0.5
MAX_POLLS = 40


def _transport_ok(result):
    required = {'stdout': str, 'stderr': str, 'returncode': int, 'timed_out': bool,
                'output_truncated': bool, 'io_incomplete': bool}
    return (isinstance(result, dict) and all(type(result.get(k)) is t for k, t in required.items())
            and result['returncode'] == 0 and not result['stderr'].strip()
            and not any(result[k] for k in ('timed_out', 'output_truncated', 'io_incomplete')))


def parse_inventory(text):
    """Validate every row; partial, duplicate and inconsistent evidence fails closed."""
    containers = []
    for line in text.splitlines():
        if not line.strip():
            raise ValueError('Blank inventory row')
        row = json.loads(line, object_pairs_hook=metadata_object, parse_constant=invalid_constant)
        if (not isinstance(row, dict) or not isinstance(row.get('ID'), str) or
                not re.fullmatch(r'[a-f0-9]{64}', row['ID']) or
                any(not isinstance(row.get(k), str) or not row[k].strip()
                    for k in ('Names', 'Image', 'State')) or not isinstance(row.get('Labels'), str)):
            raise ValueError('Missing or invalid container inventory fields')
        containers.append(row)
    if (len({r['ID'] for r in containers}) != len(containers) or
            len({r['Names'] for r in containers}) != len(containers)):
        raise ValueError('Duplicate container identities')
    return containers


def check_docker_readiness(*, readiness_timeout=DEFAULT_READINESS_TIMEOUT,
                           runner=bounded_command, cli=None, clock=time.monotonic,
                           sleep=time.sleep):
    if (type(readiness_timeout) not in (int, float) or not math.isfinite(readiness_timeout)
            or not 1 <= readiness_timeout <= 60):
        raise ValueError('Readiness timeout must be finite and between 1 and 60 seconds')
    start = clock()
    report = {'started_utc': timestamp(), 'ready': False, 'status': 'waiting',
              'readiness_timeout_seconds': readiness_timeout, 'operation_timeout_seconds': OPERATION_TIMEOUT,
              'poll_interval_seconds': POLL_INTERVAL, 'max_polls': MAX_POLLS, 'polls': [],
              'inventory': None, 'inventory_status': 'not_checked', 'isolation_verified': False,
              'execution_authorized': False, 'read_only': True, 'model_invoked': False}
    phase = 'readiness'
    try:
        executable = cli or DockerTransport().cli
        deadline = start + readiness_timeout
        for _ in range(MAX_POLLS):
            remaining = deadline - clock()
            if remaining <= 0:
                break
            # Quiet ps can be served by Desktop's idle cache without waking WSL.
            # Explicit sizes require the engine path used by the final JSON view.
            argv = [executable, '--context', 'desktop-linux', 'ps', '-a', '--no-trunc',
                    '--size', '--format', '{{json .}}']
            event = {'utc': timestamp(), 'argv': argv, 'timeout_seconds': min(OPERATION_TIMEOUT, remaining)}
            report['polls'].append(event)
            try:
                result = runner(argv, timeout=event['timeout_seconds'])
                event['result'] = result
            except (OSError, TimeoutError) as exc:
                event['error'] = f'{type(exc).__name__}: {exc}'
                result = None
            if isinstance(result, dict) and (result.get('output_truncated') or result.get('io_incomplete')):
                raise ValueError('Incomplete readiness evidence')
            if _transport_ok(result):
                parse_inventory(result['stdout'])
                if clock() >= deadline:
                    break
                report['service_ready'] = True
                break
            remaining = deadline - clock()
            if remaining > 0:
                sleep(min(POLL_INTERVAL, remaining))
        report['readiness_duration_seconds'] = clock() - start
        if not report.get('service_ready'):
            report['status'] = 'readiness_timeout'
            return report
        # A separate, definitive inventory. It is NEVER retried on failure.
        phase = 'inventory'
        argv = [executable, '--context', 'desktop-linux', 'ps', '-a', '--no-trunc', '--format', '{{json .}}']
        report['inventory'] = {'utc': timestamp(), 'argv': argv}
        result = runner(argv, timeout=OPERATION_TIMEOUT)
        report['inventory']['result'] = result
        if not _transport_ok(result):
            report['status'] = 'inventory_failed'
            report['inventory_status'] = 'unknown'
            return report
        containers = parse_inventory(result['stdout'])
        report['inventory']['containers'] = containers
        owned = [r for r in containers if 'alfha' in r['Names'].lower() or 'alfha' in r['Labels'].lower()]
        report['inventory']['alfha_containers'] = owned
        report['inventory_status'] = 'verified'
        report['ready'] = not owned
        report['status'] = 'ready' if not owned else 'cleanup_required'
        return report
    except Exception as exc:
        report['status'] = phase + '_evidence_failed'
        report['inventory_status'] = 'unknown' if phase == 'inventory' else 'not_checked'
        report['error'] = f'{type(exc).__name__}: {exc}'
        return report
    finally:
        report['poll_count'] = len(report['polls'])
        report.setdefault('readiness_duration_seconds', clock() - start)
        report['total_duration_seconds'] = clock() - start
        report['completed_utc'] = timestamp()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness-timeout', type=float, default=DEFAULT_READINESS_TIMEOUT)
    args = parser.parse_args(argv)
    result = check_docker_readiness(readiness_timeout=args.readiness_timeout)
    print(json.dumps(result, indent=2))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
