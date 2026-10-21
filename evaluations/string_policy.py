"""Narrow string syntax rules; runtime receiver checks are still mandatory."""
import ast

STRING_METHODS = {'strip', 'lower'}
STRIP_FUNCTIONS = {'review_strip', 'review_chain'}


def string_diagnostics(node, parents, function):
    errors = []
    if not isinstance(node, ast.Attribute) or node.attr not in STRING_METHODS:
        return errors
    parent = parents.get(node)
    if not isinstance(parent, ast.Call) or parent.func is not node:
        return ['String methods must be called directly; attribute extraction is forbidden']
    if node.attr == 'strip' and function not in STRIP_FUNCTIONS:
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
