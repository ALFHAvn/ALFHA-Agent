"""Narrow string syntax rules; runtime receiver checks are still mandatory."""
import ast
import hashlib
try:
    from .normalize_profile import SCOPE as NORMALIZE_SCOPE, SOURCE_HASHES as NORMALIZE_HASHES
except ImportError:
    from normalize_profile import SCOPE as NORMALIZE_SCOPE, SOURCE_HASHES as NORMALIZE_HASHES

STRING_METHODS = {'strip', 'lower'}
STRIP_FUNCTIONS = {'review_strip', 'review_chain'}


def scoped_normalize_allowed(source, task):
    return (type(task.get('string_scope')) is str and task['string_scope'] == NORMALIZE_SCOPE
            and task.get('function') == 'normalize_tags' and task.get('parameters') == ['tags']
            and hashlib.sha256(source.encode('utf-8')).hexdigest() in NORMALIZE_HASHES)


def worker_task_contract(request):
    task = {'function': request['function'], 'parameters': request['parameters']}
    if request['task_id'] == 'step41_normalize_tags':
        task['string_scope'] = request.get('string_scope')
        if not scoped_normalize_allowed(request['source'], task):
            raise ValueError('Missing/invalid Step 41 scope, contract or preserved source hash')
    elif 'string_scope' in request:
        raise ValueError('String scope is restricted to the fixed Step 41 task')
    return task


def string_diagnostics(node, parents, function, scoped=False):
    errors = []
    if not isinstance(node, ast.Attribute) or node.attr not in STRING_METHODS:
        return errors
    parent = parents.get(node)
    if not isinstance(parent, ast.Call) or parent.func is not node:
        return ['String methods must be called directly; attribute extraction is forbidden']
    if node.attr == 'strip' and function not in STRIP_FUNCTIONS and not scoped:
        errors.append('Unsupported attribute: strip')
        errors.append('strip requires an explicitly reviewed string-operation profile')
    if parent.args or parent.keywords:
        errors.append('String methods accept zero positional arguments and no keywords')
    methods = [node.attr]
    receiver = node.value
    while isinstance(receiver, ast.Call):
        if not isinstance(receiver.func, ast.Attribute) or receiver.func.attr not in STRING_METHODS:
            errors.append('Unsupported nested string receiver call')
            break
        methods.append(receiver.func.attr)
        receiver = receiver.func.value
    if len(methods) > 2 or len(set(methods)) != len(methods):
        errors.append('String chains allow at most one strip and one lower')
    if not isinstance(receiver, (ast.Name, ast.Subscript, ast.Constant)):
        errors.append('String receiver must be a name, subscript or string literal')
    if isinstance(receiver, ast.Constant) and type(receiver.value) is not str:
        errors.append('String receiver literal must have exact str type')
    return errors
