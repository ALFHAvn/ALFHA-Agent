"""Fixed trusted Step 39 profile; no candidate code or execution permission."""
import copy

ADD_ONE = {
    'id': 'step39_add_one', 'function': 'add_one', 'parameters': ['value'],
    'tests': [{'args': [n], 'expected': value} for n, value in
              [(0, 1), (1, 2), (-1, 0), (41, 42), (-8, -7), (1000000, 1000001)]],
    'assertions': ['exact integer type and value', 'arguments unchanged'],
}


def preserved_task(task_id):
    if task_id != ADD_ONE['id']:
        raise ValueError('Unknown preserved-candidate task ID')
    return copy.deepcopy(ADD_ONE)
