"""Repeat trusted Docker lifecycles with raw evidence; never calls a model.

Historical reports are diagnostic input only, never execution permits. There are
no caller-supplied programs, Docker options, image overrides or execution retries.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .docker_transport import PINNED_IMAGE
from .execution_backend import DockerExecutionBackend, PROBES

RUNS = Path(__file__).resolve().parent / 'runs'
PROGRAMS = (
    ('normal', 'print(6 * 7)\n', 0, False),
    ('nonzero_exit', 'raise SystemExit(7)\n', 7, False),
    ('wall_timeout', 'import time\ntime.sleep(30)\n', None, True),
)


def ready(report):
    checks = report.get('security_checks', {})
    return (report.get('verified') is True and set(checks) == set(PROBES) and
            all(c.get('status') == 'passed' and c.get('evidence') for c in checks.values()))


def verification_snapshot(report):
    return {key: report.get(key) for key in ('verified', 'reason', 'current_verification')}


def run_diagnosis(backend, *, cycles=20, save=lambda report: None):
    if type(cycles) is not int or not 1 <= cycles <= 100:
        raise ValueError('Use between 1 and 100 controlled cycles')
    report = {'schema_version': 1, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'mode': 'trusted_runtime_diagnosis', 'model_invoked': False,
              'live_evaluation_enabled': False, 'historical_root_cause': 'unresolved',
              'execution_retries': 0, 'inspection_retries': 0,
              'cycles_requested': cycles, 'cycles': [], 'status': 'preflight', 'error': None}
    save(report)
    try:
        print('Fresh mandatory isolation checks (no model requests)...', flush=True)
        report['initial_verification'] = backend.run_security_checks()
        save(report)
        if not ready(report['initial_verification']):
            raise RuntimeError('Mandatory initial isolation verification failed')
        for index in range(cycles):
            name, program, exit_status, timed_out = PROGRAMS[index % len(PROGRAMS)]
            print(f'Controlled cycle {index + 1}/{cycles}: {name}', flush=True)
            row = {'index': index, 'program': name, 'source_sha256': hashlib.sha256(program.encode()).hexdigest(),
                   'status': 'in_progress'}
            report['cycles'].append(row)
            audit_start = len(backend._transport.audit)
            try:
                before = backend.verify()
                row['before'] = verification_snapshot(before)
                save(report)
                if not ready(before):
                    raise RuntimeError('Verification failed before controlled execution')
                raw = backend.run_verified_worker(program)
                row['execution'] = raw
                after = backend.verify()
                row['after'] = verification_snapshot(after)
                execution_ok = (raw.get('status') == 'completed' and
                                raw.get('cleanup', {}).get('verified_absent') is True and
                                raw.get('timed_out') is timed_out and raw.get('output_truncated') is False and
                                raw.get('io_incomplete') is False and raw.get('stderr') == '' and
                                (raw.get('exit_status') == exit_status if not timed_out else
                                 raw.get('container_state', {}).get('Status') == 'exited') and
                                (raw.get('stdout') == '42\n' if name == 'normal' else raw.get('stdout') == ''))
                row['status'] = 'passed' if ready(after) and execution_ok else 'failed'
                if row['status'] != 'passed':
                    raise RuntimeError('Controlled lifecycle or post-execution verification failed')
            finally:
                row['commands'] = copy.deepcopy(backend._transport.audit[audit_start:])
                save(report)
        report['status'] = 'completed'
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        if hasattr(exc, 'verification'):
            report['rejected_verification'] = exc.verification
        if hasattr(exc, 'failure'):
            report['failure'] = exc.failure
        if report['cycles'] and report['cycles'][-1]['status'] == 'in_progress':
            report['cycles'][-1]['status'] = 'failed'
    finally:
        transport = getattr(backend, '_transport', None)
        if transport is not None:
            try:
                raw = transport.command(['ps', '-a', '--filter', 'label=alfha.execution=security-probe',
                                         '--format', '{{.ID}} {{.Names}}'])
                report['cleanup_query'] = raw
                report['no_evaluation_containers'] = (raw['returncode'] == 0 and not raw['timed_out'] and
                    not raw['output_truncated'] and not raw['io_incomplete'] and raw['stdout'].strip() == '' and
                    raw['stderr'] == '')
            except Exception as exc:
                report['cleanup_error'] = f'{type(exc).__name__}: {exc}'
                report['no_evaluation_containers'] = False
        else:
            report['no_evaluation_containers'] = False
        if report['no_evaluation_containers'] is not True:
            report['status'] = 'failed'
        report['summary'] = {'cycles_attempted': len(report['cycles']),
                             'cycles_passed': sum(c['status'] == 'passed' for c in report['cycles']),
                             'boundary_checks_recorded': sum(int('before' in c) + int('after' in c) for c in report['cycles'])}
        report['completed_utc'] = datetime.now(timezone.utc).isoformat()
        save(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=20, choices=range(1, 101))
    args = parser.parse_args(argv)
    RUNS.mkdir(parents=True, exist_ok=True)
    output = RUNS / ('runtime_diagnosis_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')

    def save(report):
        pending = output.with_suffix('.json.tmp')
        pending.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        pending.replace(output)

    result = run_diagnosis(DockerExecutionBackend(PINNED_IMAGE), cycles=args.cycles, save=save)
    print(result['summary'], flush=True)
    print(f'Report: {output}', flush=True)
    if result['error']:
        print(result['error'], flush=True)
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
