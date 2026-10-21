"""Container-only worker source. The host reads this file; NEVER imports/runs it.

The trusted bootstrap supplies validate_source, PURE_CALLS and policy constants.
Expected outcomes and grading logic are deliberately absent from the request.
"""
import builtins
import json
import math
import os
import sys
import ast


def _guard_string_method(value, method):
    if builtins.type(value) is not builtins.str:
        raise TypeError('String receiver must have exact str type')
    if method == 'strip':
        return builtins.str.strip(value)
    if method == 'lower':
        return builtins.str.lower(value)
    raise ValueError('Unsupported guarded string method')


class _GuardStrings(ast.NodeTransformer):
    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr in STRING_METHODS:
            return ast.copy_location(ast.Call(func=ast.Name(id='__alfha_string_method__', ctx=ast.Load()),
                args=[node.func.value, ast.Constant(value=node.func.attr)], keywords=[]), node)
        return node


def _plain(value, depth=0, budget=None):
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise ValueError('Result exceeds structural limits')
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind is int:
        if value.bit_length() > 4096:
            raise ValueError('Integer result too large')
        return value
    if kind is float and math.isfinite(value):
        return value
    if kind is str and len(value.encode('utf-8')) <= 4096:
        return value
    if kind is list:
        return [_plain(v, depth + 1, budget) for v in value]
    if kind is dict and all(type(k) is str and len(k) <= 4096 for k in value):
        return {k: _plain(v, depth + 1, budget) for k, v in value.items()}
    raise ValueError('Only bounded plain JSON return values are supported')


def worker_main(request_json):
    # Defense against accidentally invoking the candidate on a Windows host.
    if sys.platform != 'linux' or os.getuid() != 65534 or not os.path.exists('/.dockerenv'):
        raise RuntimeError('Worker requires the restricted non-root Linux container')
    request = json.loads(request_json)
    fields = {'version', 'request_id', 'task_id', 'function', 'parameters', 'source', 'vectors'}
    if (set(request) not in (fields, fields | {'string_scope'})
            or request['version'] != 1):
        raise ValueError('Invalid input protocol')
    task = worker_task_contract(request)
    checks = validate_source(request['source'], task)
    if not checks['static_policy_passed']:
        raise ValueError('Worker rejected candidate policy')

    def emit(frame):
        sys.stdout.write(json.dumps(frame, allow_nan=False, separators=(',', ':')) + '\n')
        sys.stdout.flush()

    emit({'kind': 'start', 'version': 1, 'request_id': request['request_id'], 'task_id': request['task_id']})
    try:
        tree = ast.parse(request['source'])
        code = compile(ast.fix_missing_locations(_GuardStrings().visit(tree)), '<candidate>', 'exec')
    except BaseException as exc:
        emit({'kind': 'job_error', 'error': type(exc).__name__ + ': ' + str(exc)[:512]})
        return
    # Full builtins, caller frames, modules, job data and emit are NOT placed in
    # candidate globals. In particular aliasing sum=eval/open/print cannot work.
    safe_builtins = {name: getattr(builtins, name) for name in PURE_CALLS}
    for index, vector in enumerate(request['vectors']):
        emit({'kind': 'vector_start', 'index': index})
        args = json.loads(json.dumps(vector['args'], allow_nan=False))
        namespace = {'__builtins__': safe_builtins.copy()}
        namespace['__alfha_string_method__'] = _guard_string_method
        row = {'kind': 'vector_result', 'index': index, 'status': 'runtime_error',
               'value': None, 'args_after': None, 'new_list': False, 'error': None}
        try:
            exec(code, namespace, namespace)
            value = namespace[request['function']](*args)
        except BaseException as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)[:512]
        else:
            try:
                row.update(status='returned', value=_plain(value), args_after=_plain(args),
                           new_list=type(value) is list and all(value is not arg for arg in args))
            except BaseException as exc:
                row['status'] = 'result_error'
                row['error'] = type(exc).__name__ + ': ' + str(exc)[:512]
        emit(row)
    emit({'kind': 'end', 'count': len(request['vectors'])})
