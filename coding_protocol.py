"""Deterministic tool visibility and data-only single-proposal parsing."""
import copy
import json


DEFAULT_POLICY = {'inspection_first': False, 'single_json_recovery': False}


def parse_text(content):
    if not isinstance(content, str) or not content.strip():
        return 'empty', None, 'Empty response is not task completion'
    text = content.strip()
    if not text.startswith(('{', '[')):
        kind = 'malformed' if '"arguments"' in text or '"name"' in text else 'text'
        return kind, None, 'Use native tools; prose/fences are never converted to actions'
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('Nonstandard JSON constant: ' + value)
    try:
        value = json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        return 'malformed', None, str(exc)
    if isinstance(value, list):
        return 'multiple', None, 'Arrays of proposals are never dispatched, including one-element arrays'
    if not isinstance(value, dict) or set(value) != {'name', 'arguments'} or not isinstance(value['name'], str) or not isinstance(value['arguments'], dict):
        return 'malformed', None, 'Require exactly one raw object with name and arguments'
    return 'single', value, 'Single proposal still requires explicit recovery permission and full validation'


def available_tools(schemas, signatures, authorization, policy, inspected):
    pending = {n for n, ops in authorization.items() if 'read' in ops and
               ('modify' in ops or 'delete' in ops)} - inspected
    inspecting = policy['inspection_first'] and bool(pending)
    result = []
    for schema in schemas:
        name = schema['function']['name']
        operation = signatures[name][0]
        if inspecting and name != 'read_file':
            continue
        paths = [n for n, ops in authorization.items() if operation in ops] if operation else []
        if operation and not paths:
            continue
        tool = copy.deepcopy(schema)
        if operation:
            tool['function']['parameters']['properties']['filename']['enum'] = paths
        result.append(tool)
    return result, 'inspection' if inspecting else 'editing'
