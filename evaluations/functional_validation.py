"""Non-executing functional task validation. AST policy is NOT a sandbox."""
import ast
import json
import re
import shutil
from pathlib import Path
try:
    from .string_policy import STRING_METHODS, STRIP_FUNCTIONS, string_diagnostics, scoped_normalize_allowed, worker_task_contract
except ImportError:
    from string_policy import STRING_METHODS, STRIP_FUNCTIONS, string_diagnostics, scoped_normalize_allowed, worker_task_contract


CASE_ROOT = Path(__file__).resolve().parent / 'functional_cases'
MAX_SOURCE_BYTES = 100_000
MAX_AST_NODES = 5_000


def isolation_status():
    """Report the backend gate, never infer security from Docker discovery."""
    try:
        from .execution_backend import DockerExecutionBackend
    except ImportError:
        from execution_backend import DockerExecutionBackend
    return DockerExecutionBackend().verify()


def load_tasks(root=CASE_ROOT):
    """Validate trusted task data without importing fixture programs."""
    root = Path(root).resolve()
    manifest = json.loads((root / 'tasks.json').read_text(encoding='utf-8'))
    if set(manifest) != {'schema_version', 'tasks'} or manifest['schema_version'] != 1:
        raise ValueError('Unsupported functional manifest')
    tasks = manifest['tasks']
    if not isinstance(tasks, list) or len(tasks) != 5:
        raise ValueError('Expected five functional tasks')
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {
                'id', 'filename', 'function', 'parameters', 'instruction', 'tests'}:
            raise ValueError('Invalid task fields')
        for key in ('id', 'function'):
            if not isinstance(task[key], str) or not re.fullmatch(r'[a-z][a-z0-9_]*', task[key]):
                raise ValueError('Invalid task identifier')
        if task['id'] in seen or task['filename'] != task['id'] + '.py':
            raise ValueError('Duplicate task or unauthorized filename')
        seen.add(task['id'])
        fixture = root / task['filename']
        if fixture.is_symlink() or fixture.resolve().parent != root or not fixture.is_file():
            raise ValueError('Fixture must be a regular file inside functional cases')
        if fixture.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('Fixture is too large')
        params = task['parameters']
        if (not isinstance(params, list) or not params or
                not all(isinstance(p, str) and re.fullmatch(r'[a-z][a-z0-9_]*', p) for p in params)
                or len(params) != len(set(params))):
            raise ValueError('Invalid function parameters')
        if not isinstance(task['instruction'], str) or not task['instruction'].strip():
            raise ValueError('Task instruction required')
        if not isinstance(task['tests'], list) or len(task['tests']) < 3:
            raise ValueError('At least three expected-result vectors required')
        for vector in task['tests']:
            if (not isinstance(vector, dict) or set(vector) != {'args', 'expected'} or
                    not isinstance(vector['args'], list) or len(vector['args']) != len(params)):
                raise ValueError('Invalid expected-result vector')
    return tasks


PURE_CALLS = {
    'sum', 'len', 'min', 'max', 'abs', 'sorted', 'range', 'enumerate', 'zip',
    'int', 'str', 'bool', 'list', 'dict', 'set', 'tuple', 'reversed', 'all', 'any',
}
PURE_METHODS = {'lower', 'split', 'isalnum', 'append', 'get', 'add', 'join', 'items', 'values', 'keys'}
ALLOWED_NODES = {
    'Module', 'FunctionDef', 'arguments', 'arg', 'Return', 'Assign', 'AugAssign',
    'Expr', 'If', 'For', 'Break', 'Continue', 'Pass', 'Name', 'Load', 'Store',
    'Constant', 'List', 'Tuple', 'Dict', 'Set', 'Subscript', 'Slice', 'BinOp',
    'UnaryOp', 'BoolOp', 'Compare', 'IfExp', 'Call', 'Attribute', 'keyword',
    'ListComp', 'SetComp', 'DictComp', 'GeneratorExp', 'comprehension',
    'Add', 'Sub', 'Mult', 'Div', 'FloorDiv', 'Mod', 'USub', 'UAdd', 'Not',
    'And', 'Or', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'In', 'NotIn', 'Is', 'IsNot',
}


def validate_source(source, task):
    """Parse source and inspect its contract; never compile, import, or evaluate it.

    This deliberately narrow policy diagnoses unsupported/unsafe source. Passing
    does not prove resource bounds, security, or functional correctness.
    """
    result = {'syntax_valid': False, 'contract_valid': False,
              'static_policy_passed': False, 'diagnostics': []}
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
        result['diagnostics'].append('Source must be UTF-8 text under 100 KB')
        return result
    try:
        tree = ast.parse(source.lstrip('\ufeff'))
    except (SyntaxError, ValueError, RecursionError) as exc:
        result['diagnostics'].append(f'Parse error: {exc}')
        return result
    result['syntax_valid'] = True
    scoped = scoped_normalize_allowed(source, task)
    if task.get('string_scope') is not None and not scoped:
        result['diagnostics'].append('Invalid string scope, function contract or preserved source hash')
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        result['diagnostics'].append('AST node limit exceeded')
        return result
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    function = body[0] if len(body) == 1 and isinstance(body[0], ast.FunctionDef) else None
    primary = body[0] if body and isinstance(body[0], ast.FunctionDef) else None
    if function is None:
        result['diagnostics'].append('Only the required function and optional module docstring are allowed')
    else:
        args = function.args
        if (function.name != task['function'] or
                [a.arg for a in args.args] != task['parameters'] or
                args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or
                args.defaults or args.kw_defaults or function.decorator_list or
                function.returns or any(a.annotation for a in args.args) or
                getattr(function, 'type_params', [])):
            result['diagnostics'].append('Function name/signature must match the task without decorators or annotations')
        else:
            result['contract_valid'] = True
    for node in nodes:
        result['diagnostics'].extend(string_diagnostics(node, parents, task['function'], scoped))
        kind = type(node).__name__
        if kind not in ALLOWED_NODES:
            result['diagnostics'].append(f'Unsupported AST node: {kind}')
        if isinstance(node, ast.FunctionDef) and node is not primary:
            result['diagnostics'].append('Nested/extra functions are unsupported')
        if isinstance(node, ast.Return) and node in body:
            result['diagnostics'].append('Top-level return is forbidden; indent it inside the required function')
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            result['diagnostics'].append('Dunder names are forbidden')
        if isinstance(node, ast.Attribute) and node.attr not in PURE_METHODS | STRING_METHODS:
            result['diagnostics'].append(f'Unsupported attribute: {node.attr}')
        if isinstance(node, ast.Call):
            if not ((isinstance(node.func, ast.Name) and node.func.id in PURE_CALLS) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr in PURE_METHODS | STRING_METHODS)):
                result['diagnostics'].append('Unsupported call target')
                if isinstance(node.func, ast.Name):
                    result['diagnostics'].append('Unsupported call: ' + node.func.id[:80])
    result['diagnostics'] = sorted(set(result['diagnostics']))
    result['static_policy_passed'] = result['contract_valid'] and not result['diagnostics']
    return result


def verification_stages(checks):
    return {
        'ast_parsing': {'status': 'passed' if checks['syntax_valid'] else 'failed', 'passed': checks['syntax_valid']},
        'compilation': {'status': 'not_run', 'passed': None, 'reason': 'Requires verified Docker compilation; never compiled on host'},
        'policy': {'status': 'accepted' if checks['static_policy_passed'] else 'rejected',
                   'passed': checks['static_policy_passed']},
        'docker_execution': {'status': 'not_run', 'passed': None, 'candidate_invocation_attempted': False},
        'functional_tests': {'status': 'not_run', 'passed': None},
    }


def function_fingerprint(source, name):
    try:
        tree = ast.parse(source.lstrip('\ufeff'))
        return [ast.dump(n, include_attributes=False) for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == name]
    except (SyntaxError, ValueError, RecursionError):
        return None


def assess_candidate(original, candidate, task):
    checks = validate_source(candidate, task)
    changed = original != candidate
    function_changed = function_fingerprint(original, task['function']) != function_fingerprint(candidate, task['function'])
    return {
        'changed': changed, 'target_function_changed': function_changed,
        'requested_change_confirmed': None,
        'requested_change_status': 'candidate_only' if changed and function_changed else 'not_demonstrated',
        'controller_verification': checks,
        'verified_by_controller': checks['syntax_valid'],
        'syntax_valid': checks['syntax_valid'],
        'verification_stages': verification_stages(checks),
        'functional_tests': {
            'status': 'not_run', 'passed': None, 'executed': 0,
            'planned': len(task['tests']),
            'reason': 'Execution isolation has not been verified.',
            'vectors': task['tests'],
            'assertions': ['exact value and type', 'arguments unchanged',
                           'new result list for unique_order'],
        },
        'passed': None,
    }
