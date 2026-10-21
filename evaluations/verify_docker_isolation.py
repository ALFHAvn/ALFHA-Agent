"""Run ONLY trusted, controlled programs through the real Docker transport.

    python -m evaluations.verify_docker_isolation

No model requests or generated candidates; this never enables live evaluations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from .docker_transport import DockerTransport, PINNED_IMAGE
from .execution_backend import PROBES, DockerExecutionBackend


def json_output(result):
    try:
        return json.loads(result['stdout'])
    except (ValueError, KeyError):
        return None


def clean(result):
    return result.get('cleanup', {}).get('verified_absent') is True


def success(result):
    return (result.get('status') == 'completed' and result.get('exit_status') == 0 and
            result.get('timed_out') is False and result.get('output_truncated') is False and
            not result.get('policy_verification') and clean(result))


NORMAL = '''import json, os, resource
from pathlib import Path
print(json.dumps({'calculation': 6 * 7, 'uid': os.getuid(), 'gid': os.getgid(),
 'memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip(),
 'swap_max': Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
 'cpu_max': Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
 'pids_max': Path('/sys/fs/cgroup/pids.max').read_text().strip(),
 'cpu_rlimit': resource.getrlimit(resource.RLIMIT_CPU)}))
'''

NETWORK = '''import socket, json
from pathlib import Path
tcp_denied = dns_denied = False
tcp_error = None
try:
    socket.create_connection(('198.51.100.1', 80), timeout=0.2).close()
except OSError as error:
    tcp_denied, tcp_error = True, error.errno
try:
    socket.getaddrinfo('alfha-isolation.invalid', 80)
except OSError:
    dns_denied = True
print(json.dumps({'tcp_denied': tcp_denied, 'tcp_errno': tcp_error, 'dns_denied': dns_denied,
 'interfaces': sorted(p.name for p in Path('/sys/class/net').iterdir()),
 'routes': Path('/proc/net/route').read_text()}))
'''

MEMORY = '''import json
from pathlib import Path
print(json.dumps({'memory_max': Path('/sys/fs/cgroup/memory.max').read_text().strip()}), flush=True)
chunks = []
for i in range(24):
    chunks.append(bytearray(32 * 1024 * 1024))
raise RuntimeError('Memory limit was not enforced')
'''

PIDS = '''import os, signal, time, errno, json
from pathlib import Path
children = []
blocked = False
error_number = None
try:
    for i in range(20):
        try:
            pid = os.fork()
        except OSError as error:
            error_number = error.errno
            blocked = error.errno == errno.EAGAIN
            break
        if pid == 0:
            time.sleep(30)
            os._exit(0)
        children.append(pid)
    print(json.dumps({'children': len(children), 'blocked': blocked, 'errno': error_number,
     'pids_max': Path('/sys/fs/cgroup/pids.max').read_text().strip()}), flush=True)
finally:
    for pid in children:
        os.kill(pid, signal.SIGKILL)
    for pid in children:
        os.waitpid(pid, 0)
'''

READONLY = '''import os, errno, json, ctypes
from pathlib import Path
denied = False
try:
    Path('/alfha-readonly-probe').write_text('controlled')
except OSError as error:
    denied = error.errno == errno.EROFS
scratch = Path('/tmp/alfha-scratch')
scratch.write_text('controlled')
scratch_ok = scratch.read_text() == 'controlled'
scratch.unlink()
scratch_bounded = False
try:
    with scratch.open('wb') as stream:
        for i in range(20):
            stream.write(b'x' * 65536)
except OSError as error:
    scratch_bounded = error.errno in (errno.ENOSPC, errno.EFBIG)
finally:
    scratch.unlink(missing_ok=True)
status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
root_uid_denied = False
try:
    os.setuid(0)
except OSError as error:
    root_uid_denied = error.errno == errno.EPERM
libc = ctypes.CDLL(None, use_errno=True)
unshare_result = libc.unshare(0x10000000)
unshare_errno = ctypes.get_errno()
print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(), 'root_write_denied': denied,
 'scratch_ok': scratch_ok, 'scratch_bounded': scratch_bounded,
 'cap_effective': status['CapEff'].strip(), 'no_new_privs': status['NoNewPrivs'].strip(),
 'seccomp': status['Seccomp'].strip(), 'root_uid_denied': root_uid_denied,
 'unshare_denied': unshare_result == -1 and unshare_errno in (errno.EPERM, errno.EACCES),
 'docker_socket_exists': Path('/var/run/docker.sock').exists()}))
'''


def run_security_probes(transport, runs_dir, *, stop_on_failure=False, progress=None):
    """Collect actual observations, not just accepted Docker options."""
    checks = {name: {'status': 'not_run', 'evidence': None} for name in PROBES}
    report = {
        'schema_version': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'backend': 'docker-linux', 'verified': False, 'execution_enabled': False,
        'live_benchmark_enabled': False, 'model_invoked': False,
        'reason': 'Controlled verification in progress; live execution remains disabled.',
        'security_checks': checks,
        'probe_runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'stop_on_failure': stop_on_failure,
    }
    def publish():
        report['audit'] = transport.audit
        if progress is not None:
            import copy
            progress(copy.deepcopy(report))
    publish()
    try:
        report['identity'] = transport.preflight()
    except Exception as exc:
        report['reason'] = f'Preflight failed: {type(exc).__name__}: {exc}'
        report['failure'] = getattr(exc, 'failure', None)
        publish()
        return report

    def probe(name, operation):
        print(f'Checking {name}...', flush=True)
        try:
            passed, evidence = operation()
            checks[name] = {'status': 'passed' if passed else 'failed', 'evidence': evidence}
        except Exception as exc:
            checks[name] = {'status': 'failed', 'evidence': {
                'error': f'{type(exc).__name__}: {exc}', 'failure': getattr(exc, 'failure', None)}}
        if checks[name]['status'] != 'passed':
            report['reason'] = f'Mandatory probe failed: {name}; execution remains disabled.'
        publish()
        return not (stop_on_failure and checks[name]['status'] != 'passed')

    def normal():
        r = transport.run_controlled(NORMAL)
        data = json_output(r) or {}
        return success(r) and data.get('calculation') == 42 and data.get('uid') == 65534, r
    if not probe('normal_calculation', normal): return report

    def wall():
        r = transport.run_controlled('import time\ntime.sleep(30)\n')
        return r.get('timed_out') is True and r.get('duration_seconds', 99) < 5 and clean(r), r
    if not probe('wall_timeout', wall): return report

    def network():
        r = transport.run_controlled(NETWORK)
        d = json_output(r) or {}
        return (success(r) and d.get('tcp_denied') and d.get('dns_denied') and
                d.get('tcp_errno') in (1, 13, 101, 113) and d.get('interfaces') == ['lo'] and
                len(d.get('routes', '').splitlines()) == 1), r
    if not probe('network_denied', network): return report

    def host_files():
        Path(runs_dir).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='alfha-host-sentinel-', dir=runs_dir) as directory:
            marker = Path(directory) / 'harmless-sentinel.txt'
            marker.write_text('ALFHA harmless host sentinel', encoding='utf-8')
            host_path = marker.resolve().as_posix()
            drive, relative = host_path.split(':', 1)
            paths = [host_path, '/host/' + marker.name,
                     '/run/desktop/mnt/host/' + drive.lower() + relative,
                     '/mnt/host/' + drive.lower() + relative]
            code = ('import json\nfrom pathlib import Path\npaths = ' + repr(paths) +
                    '\nprint(json.dumps({"visible": [p for p in paths if Path(p).exists()], '
                    '"docker_socket": Path("/var/run/docker.sock").exists()}))\n')
            r = transport.run_controlled(code)
            d = json_output(r) or {}
            intact = marker.read_text() == 'ALFHA harmless host sentinel'
        r['host_sentinel_intact'] = intact
        r['host_sentinel_removed'] = not Path(directory).exists()
        return (success(r) and d.get('visible') == [] and d.get('docker_socket') is False and intact and
                r['host_sentinel_removed'] and r.get('inspection', {}).get('Mounts') == []), r
    if not probe('host_files_denied', host_files): return report

    def memory():
        r = transport.run_controlled(MEMORY)
        d = json_output(r) or {}
        return (r.get('container_state', {}).get('OOMKilled') is True and r.get('exit_status') == 137 and
                d.get('memory_max') == '268435456' and not r.get('timed_out') and clean(r)), r
    if not probe('memory_limit', memory): return report

    def cpu():
        limits = transport.run_controlled(NORMAL)
        r = transport.run_controlled('while True:\n    pass\n')
        d = json_output(limits) or {}
        quota = d.get('cpu_max', '').split()
        enforced = (len(quota) == 2 and quota[0].isdigit() and quota[1].isdigit() and
                    int(quota[0]) == int(quota[1]) and d.get('cpu_rlimit') == [1, 1])
        return (success(limits) and enforced and r.get('exit_status') == 137 and not r.get('timed_out') and
                not r.get('container_state', {}).get('OOMKilled') and clean(r)), {'limits': limits, 'busy_loop': r}
    if not probe('cpu_limit', cpu): return report

    def pids():
        r = transport.run_controlled(PIDS)
        d = json_output(r) or {}
        return (success(r) and d.get('blocked') is True and d.get('errno') == 11 and
                1 <= d.get('children', 0) <= 15 and d.get('pids_max') == '16'), r
    if not probe('process_limit', pids): return report

    def readonly():
        r = transport.run_controlled(READONLY)
        d = json_output(r) or {}
        return (success(r) and d.get('uid') == 65534 and d.get('gid') == 65534 and
                d.get('root_write_denied') and d.get('scratch_ok') and d.get('scratch_bounded') and
                d.get('cap_effective') == '0000000000000000' and d.get('no_new_privs') == '1' and
                d.get('seccomp') == '2' and d.get('root_uid_denied') is True and
                d.get('unshare_denied') is True and d.get('docker_socket_exists') is False), r
    if not probe('readonly_nonroot', readonly): return report

    def output():
        r = transport.run_controlled('import sys\nsys.stdout.write("x" * 262144)\nsys.stdout.flush()\n')
        size = len(r['stdout'].encode('utf-8')) + len(r['stderr'].encode('utf-8'))
        return r.get('output_truncated') is True and size <= 65536 and clean(r), r
    if not probe('output_limit', output): return report

    def unsafe():
        rejected = []
        before = len(transport.audit)
        for option in ('--privileged', '--network=host', '--user=0', '--mount=/var/run/docker.sock'):
            try:
                transport.run_controlled('print(42)', docker_options=[option])
            except TypeError:
                rejected.append(option)
        no_commands = before == len(transport.audit)
        # Also validate the effective settings of an actual normally executed container.
        r = transport.run_controlled('print(42)\n')
        return len(rejected) == 4 and no_commands and success(r), {
            'rejected_options': rejected, 'no_commands_for_rejections': no_commands, 'actual_container': r}
    if not probe('unsafe_configuration_rejected', unsafe): return report

    def cleanup():
        results = [transport.run_controlled(code) for code in (
            'print(42)\n', 'raise SystemExit(7)\n', 'import time\ntime.sleep(30)\n')]
        return (all(clean(r) for r in results) and results[0].get('exit_status') == 0 and
                results[1].get('exit_status') == 7 and results[2].get('timed_out') is True), results
    if not probe('cleanup', cleanup): return report
    try:
        report['identity_after'] = transport.preflight()
        report['identity_unchanged'] = report['identity_after'] == report['identity']
    except Exception as exc:
        report['identity_unchanged'] = False
        report['postflight_error'] = str(exc)
    report['verified'] = report['identity_unchanged'] and all(c['status'] == 'passed' for c in checks.values())
    report['enforced_execution_controls'] = ({
        'network': 'none', 'uid_gid': '65534:65534', 'read_only_root': True,
        'capabilities': 'none', 'no_new_privileges': True, 'seccomp_mode': 2,
        'memory_bytes': 268435456, 'swap_bytes': 0, 'cpu_quota': 'one CPU',
        'cpu_seconds': 1, 'processes': 16, 'tmpfs_bytes': 1048576,
        'output_bytes': 65536, 'wall_seconds': 2, 'cleanup_verified': True,
    } if report['verified'] else None)
    report['reason'] = ('All mandatory controlled probes passed. Model execution remains disabled for Step 28C.'
                        if report['verified'] else 'Mandatory verification incomplete/failed; execution remains disabled.')
    report['audit'] = transport.audit
    publish()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default=PINNED_IMAGE)
    args = parser.parse_args()
    runs = Path(__file__).resolve().parent / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    try:
        backend = DockerExecutionBackend(args.image)
        report = backend.run_security_checks()
    except Exception as exc:
        report = {'verified': False, 'execution_enabled': False, 'reason': str(exc),
                  'security_checks': {p: {'status': 'not_run', 'evidence': None} for p in PROBES}}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = runs / f'isolation_{stamp}.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print({name: check['status'] for name, check in report['security_checks'].items()})
    print(f'Report: {output}')
    return 0 if report['verified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
