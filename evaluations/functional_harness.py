"""Host-side grading. Candidate code is data and is executed only in Docker."""
import hashlib
import inspect
import json
import math
from pathlib import Path
import uuid

from . import functional_validation as policy
from .docker_transport import PINNED_IMAGE
from .execution_backend import DockerExecutionBackend, PROBES, exact_json_equal

WORKER = Path(__file__).with_name('functional_worker.py')


class ProtocolError(ValueError):
    pass


class UnexpectedOutput(ProtocolError):
    pass


def task_by_id(task_id):
    for task in policy.load_tasks():
        if task['id'] == task_id:
            return task
    raise ValueError('Unknown functional task ID')


def profile_hash():
    digest = hashlib.sha256()
    for path in [Path(__file__), WORKER, Path(policy.__file__),
                 *sorted(policy.CASE_ROOT.glob('*'))]:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def make_request(task_id, source):
    task = task_by_id(task_id)
    checks = policy.validate_source(source, task)
    if not checks['static_policy_passed']:
        raise ValueError('Candidate policy rejected: ' + '; '.join(checks['diagnostics']))
    request = {
        'version': 1, 'request_id': uuid.uuid4().hex, 'task_id': task_id,
        'function': task['function'], 'parameters': task['parameters'], 'source': source,
        'vectors': [{'args': vector['args']} for vector in task['tests']],
    }
    # No expected values, assertions, grading functions or host paths are sent.
    return request


def worker_program(request):
    prefix = ('import ast\nMAX_SOURCE_BYTES=100000\nMAX_AST_NODES=5000\n' +
              'PURE_CALLS=' + repr(policy.PURE_CALLS) + '\n' +
              'PURE_METHODS=' + repr(policy.PURE_METHODS) + '\n' +
              'ALLOWED_NODES=' + repr(policy.ALLOWED_NODES) + '\n' +
              inspect.getsource(policy.validate_source) + '\n')
    program = (prefix + WORKER.read_text(encoding='utf-8') + '\nworker_main(' +
               repr(json.dumps(request, allow_nan=False, ensure_ascii=True)) + ')\n')
    if len(program.encode('utf-8')) > 100_000:
        raise ValueError('Worker and request exceed transport input limit')
    return program


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError('Duplicate result field')
        result[key] = value
    return result


def _plain(value, depth=0, budget=None):
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise ProtocolError('Result structure exceeds limits')
    if value is None or type(value) is bool:
        return
    if type(value) is int and value.bit_length() <= 4096:
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is str and len(value.encode('utf-8')) <= 4096:
        return
    if type(value) is list:
        for item in value:
            _plain(item, depth + 1, budget)
        return
    if type(value) is dict and all(type(key) is str and len(key) <= 4096 for key in value):
        for item in value.values():
            _plain(item, depth + 1, budget)
        return
    raise ProtocolError('Unsupported result value')


def parse_stream(request, text, *, incomplete=False):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 65536:
        raise ProtocolError('Worker output exceeds limit')
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        if incomplete:
            lines.pop()  # A killed process can leave one partial final frame.
        else:
            raise ProtocolError('Unterminated worker frame')
    frames = []
    for line in lines:
        try:
            frame = json.loads(line, object_pairs_hook=_unique,
                               parse_constant=lambda value: (_ for _ in ()).throw(ProtocolError('Non-finite JSON')))
        except ProtocolError:
            raise
        except (ValueError, RecursionError) as exc:
            raise UnexpectedOutput('Non-protocol stdout') from exc
        if type(frame) is not dict:
            raise ProtocolError('Worker frame must be an object')
        frames.append(frame)
    if not frames:
        if incomplete:
            return {'rows': [], 'started': 0, 'ended': False, 'job_error': None}
        raise ProtocolError('Worker produced no header')
    header = frames.pop(0)
    if (set(header) != {'kind', 'version', 'request_id', 'task_id'} or header['kind'] != 'start' or
            type(header['version']) is not int or header['version'] != 1 or
            header['request_id'] != request['request_id'] or header['task_id'] != request['task_id']):
        raise ProtocolError('Worker header mismatch')
    rows, started, waiting, ended = [], 0, False, False
    for frame in frames:
        if ended:
            raise UnexpectedOutput('Output after end frame')
        kind = frame.get('kind')
        if kind == 'job_error':
            if set(frame) != {'kind', 'error'} or started or len(frames) != 1 or type(frame['error']) is not str or len(frame['error']) > 1024:
                raise ProtocolError('Invalid job error')
            return {'rows': [], 'started': 0, 'ended': False, 'job_error': frame['error']}
        if kind == 'vector_start':
            if (set(frame) != {'kind', 'index'} or waiting or type(frame['index']) is not int or
                    frame['index'] != started or started >= len(request['vectors'])):
                raise ProtocolError('Out-of-order vector start')
            started += 1
            waiting = True
        elif kind == 'vector_result':
            if (set(frame) != {'kind', 'index', 'status', 'value', 'args_after', 'new_list', 'error'} or
                    not waiting or type(frame['index']) is not int or frame['index'] != started - 1 or
                    frame['status'] not in ('returned', 'runtime_error', 'result_error') or
                    type(frame['new_list']) is not bool):
                raise ProtocolError('Invalid vector result')
            if frame['status'] == 'returned':
                if (frame['error'] is not None or type(frame['args_after']) is not list or
                        len(frame['args_after']) != len(request['vectors'][frame['index']]['args']) or
                        (frame['new_list'] and type(frame['value']) is not list)):
                    raise ProtocolError('Invalid return observation')
                _plain(frame['value'])
                _plain(frame['args_after'])
            elif (type(frame['error']) is not str or len(frame['error']) > 1024 or
                  frame['value'] is not None or frame['args_after'] is not None or frame['new_list'] is not False):
                raise ProtocolError('Invalid error observation')
            rows.append(frame)
            waiting = False
        elif kind == 'end':
            if (set(frame) != {'kind', 'count'} or waiting or type(frame['count']) is not int or
                    frame['count'] != len(request['vectors']) or len(rows) != len(request['vectors'])):
                raise ProtocolError('Incomplete end frame')
            ended = True
        else:
            raise ProtocolError('Unknown worker frame')
    if not ended and not incomplete:
        raise ProtocolError('Missing final frame')
    return {'rows': rows, 'started': started, 'ended': ended, 'job_error': None}


def grade_execution(task, request, raw):
    """Grade observations, never trust candidate grades or execute its text."""
    result = {
        'status': 'execution_error', 'passed': False, 'executed': 0, 'attempted': 0,
        'planned': len(task['tests']), 'passed_count': 0, 'score': None,
        'results': [{'index': i, 'status': 'not_run', 'passed': False} for i in range(len(task['tests']))],
        'reason': None,
    }
    if (not isinstance(raw, dict) or type(raw.get('cleanup')) is not dict or
            raw['cleanup'].get('verified_absent') is not True):
        result['reason'] = 'Unverified cleanup or missing transport result'
        return result
    if (type(raw.get('timed_out')) is not bool or type(raw.get('output_truncated')) is not bool or
            type(raw.get('stdout')) is not str or type(raw.get('stderr')) is not str):
        result['reason'] = 'Malformed transport metadata'
        return result
    if raw.get('output_truncated') is True:
        result.update(status='output_limit', reason='Worker output exceeded the shared limit')
        return result
    if raw.get('status') != 'completed' or raw.get('io_incomplete') is True:
        result['reason'] = 'Docker transport did not establish completed execution'
        return result
    if raw.get('stderr') != '':
        result.update(status='unexpected_output', reason='Unexpected worker stderr')
        return result
    aborted = raw.get('timed_out') is True or type(raw.get('exit_status')) is not int or raw['exit_status'] != 0
    try:
        observations = parse_stream(request, raw.get('stdout'), incomplete=aborted)
    except ProtocolError as exc:
        result.update(status='unexpected_output' if isinstance(exc, UnexpectedOutput) else 'malformed_result', reason=str(exc))
        return result
    if observations['job_error']:
        result['reason'] = observations['job_error']
        return result
    result['attempted'] = observations['started']
    for row in observations['rows']:
        index = row['index']
        vector = task['tests'][index]
        outcome = {'index': index, 'status': row['status'], 'passed': False, 'error': row['error']}
        if row['status'] == 'returned':
            value_ok = exact_json_equal(row['value'], vector['expected'])
            args_ok = exact_json_equal(row['args_after'], vector['args'])
            identity_ok = task['id'] != 'unique_order' or row['new_list']
            outcome.update(status='passed' if value_ok and args_ok and identity_ok else 'failed_assertion',
                           passed=bool(value_ok and args_ok and identity_ok), actual=row['value'],
                           expected=vector['expected'], value_matches=value_ok,
                           arguments_unchanged=args_ok, result_identity_valid=bool(identity_ok))
        result['results'][index] = outcome
        result['executed'] += 1
        result['passed_count'] += int(outcome['passed'])
    result['score'] = result['passed_count'] / result['planned']
    if aborted:
        result['status'] = 'timeout' if raw.get('timed_out') is True else 'execution_error'
        result['reason'] = 'Wall deadline reached' if raw.get('timed_out') is True else 'Nonzero container exit/resource termination'
        if observations['started'] > len(observations['rows']):
            result['results'][observations['started'] - 1]['status'] = result['status']
        return result
    if any(r['status'] == 'runtime_error' for r in result['results']):
        result['status'] = 'runtime_error'
    elif any(r['status'] == 'result_error' for r in result['results']):
        result['status'] = 'result_error'
    else:
        result['passed'] = result['passed_count'] == result['planned']
        result['status'] = 'passed' if result['passed'] else 'failed'
    return result


class FunctionalHarness:
    """Explicit offline worker API. No model requests or live execution flag."""
    def __init__(self, backend=None):
        self.backend = backend or DockerExecutionBackend(PINNED_IMAGE)
        self._profile = None

    def prepare(self):
        report = self.backend.run_security_checks()
        checks = report.get('security_checks', {})
        ready = report.get('verified') is True and set(checks) == set(PROBES) and all(
            check.get('status') == 'passed' and check.get('evidence') for check in checks.values())
        self._profile = profile_hash() if ready else None
        return report

    def run(self, task_id, source):
        task = task_by_id(task_id)
        checks = policy.validate_source(source, task)
        base = {'task': task_id, 'model_invoked': False, 'live_evaluation_enabled': False,
                'static_validation': checks, 'planned': len(task['tests']), 'executed': 0,
                'passed_count': 0, 'passed': False, 'score': None,
                'results': [{'index': i, 'status': 'not_run', 'passed': False} for i in range(len(task['tests']))]}
        if not checks['static_policy_passed']:
            return {**base, 'status': 'policy_rejected', 'reason': checks['diagnostics']}
        verification = self.backend.verify()
        if self._profile is None or self._profile != profile_hash() or verification.get('verified') is not True:
            return {**base, 'status': 'blocked', 'reason': 'Current isolation/profile verification required',
                    'isolation': verification}
        try:
            request = make_request(task_id, source)
            program = worker_program(request)
            raw = self.backend.run_verified_worker(program)
            after = self.backend.verify()
            if after.get('verified') is not True or self._profile != profile_hash():
                return {**base, 'status': 'execution_error', 'reason': 'Verification identity changed during execution',
                        'execution': raw, 'isolation': verification, 'isolation_after': after}
            grade = grade_execution(task, request, raw)
        except Exception as exc:
            return {**base, 'status': 'execution_error', 'reason': f'{type(exc).__name__}: {exc}',
                    'isolation': getattr(exc, 'verification', verification),
                    'failure': getattr(exc, 'failure', None)}
        return {**base, **grade, 'request_id': request['request_id'],
                'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                'grading_profile_sha256': self._profile, 'execution': raw,
                'isolation': verification, 'isolation_after': after}
