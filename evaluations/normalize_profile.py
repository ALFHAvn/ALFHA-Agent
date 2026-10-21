"""Fixed Step 41 host oracle; no execution permission or candidate code."""
import copy

TASK_ID = 'step41_normalize_tags'
SCOPE = 'step41-preserved-normalize-v1'
SOURCE_HASHES = {
    '9619107e7cb8bdfcfdcd02f13e19190dfcc02706c15b73487ed8b73d2674a0c5',
    '902a186ced6c570fdb2ddf74f5f4a34ec060394afc54723e644374596f82fbca',
    '2ab54f18c286675de6822d9364d3bf455f78a917a9db253782d1574311277207',
}

TESTS = [
    ('empty', [], []),
    ('trims_and_lowercases', ['  RED ', 'Blue  '], ['red', 'blue']),
    ('discards_empty', ['', '   ', '\t'], []),
    ('deduplicates_in_order', ['Blue', ' red ', 'BLUE', 'Red', 'green'], ['blue', 'red', 'green']),
    ('input_unchanged', [' Blue ', 'BLUE'], ['blue']),
    ('returns_new_list', ['red'], ['red']),
    ('all_whitespace', ['', ' ', '\t', '\n', '\r\n'], []),
    ('empty_between_values', [' red ', '', '\t', 'BLUE', ' '], ['red', 'blue']),
    ('order_not_sorting', ['b', 'a', 'B', 'c', 'a'], ['b', 'a', 'c']),
    ('repeated_normalized', ['MiXeD', 'mixed', ' MIXED '], ['mixed']),
    ('unicode_whitespace', ['\u2003Red\u00a0', '\tBLUE\n'], ['red', 'blue']),
    ('internal_whitespace_retained', ['red blue', 'Red Blue'], ['red blue']),
]


def task(string_scope):
    if type(string_scope) is not str or string_scope != SCOPE:
        raise ValueError('Explicit Step 41 job-scoped string policy is required')
    return {'id': TASK_ID, 'function': 'normalize_tags', 'parameters': ['tags'],
            'string_scope': SCOPE, 'require_new_list': True,
            'tests': [{'name': name, 'args': [copy.deepcopy(args)], 'expected': copy.deepcopy(expected)}
                      for name, args, expected in TESTS]}
