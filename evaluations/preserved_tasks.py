"""Fixed trusted Step 39 profile; no candidate code or execution permission."""
import copy

ADD_ONE = {
    'id': 'step39_add_one', 'function': 'add_one', 'parameters': ['value'],
    'tests': [{'args': [n], 'expected': value} for n, value in
              [(0, 1), (1, 2), (-1, 0), (41, 42), (-8, -7), (1000000, 1000001)]],
    'assertions': ['exact integer type and value', 'arguments unchanged'],
}

STRING_REVIEWS = {
    'step40_strip': {'id': 'step40_strip', 'function': 'review_strip', 'parameters': ['value'],
        'tests': [{'args': ['  AbC\t'], 'expected': 'AbC'}, {'args': ['\n\t'], 'expected': ''},
                  {'args': ['\u2003Red\u00a0'], 'expected': 'Red'}]},
    'step40_lower': {'id': 'step40_lower', 'function': 'review_lower', 'parameters': ['value'],
        'tests': [{'args': [' AbC '], 'expected': ' abc '}, {'args': [''], 'expected': ''},
                  {'args': ['ÄBC'], 'expected': 'äbc'}]},
    'step40_chain': {'id': 'step40_chain', 'function': 'review_chain', 'parameters': ['value'],
        'tests': [{'args': ['  AbC\t'], 'expected': 'abc'}, {'args': ['\n\t'], 'expected': ''},
                  {'args': ['\u2003RED\u00a0'], 'expected': 'red'}]},
}


def preserved_task(task_id):
    if task_id in STRING_REVIEWS:
        return copy.deepcopy(STRING_REVIEWS[task_id])
    if task_id != ADD_ONE['id']:
        raise ValueError('Unknown preserved-candidate task ID')
    return copy.deepcopy(ADD_ONE)
