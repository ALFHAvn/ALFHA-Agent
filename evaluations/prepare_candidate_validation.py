"""Step 39 data-only preparation. Never imports, compiles or executes candidates."""
import copy
import hashlib
import json
from pathlib import Path

from .functional_harness import task_by_id, profile_hash
from .functional_validation import validate_source
from .preserved_tasks import preserved_task

MODELS = ('qwen3:4b', 'qwen2.5-coder:3b-instruct-q4_K_M', 'qwen2.5-coder:7b-instruct-q4_K_M')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tasks():
    """Proposed trusted checks, not a replacement for the canonical five tasks."""
    return {
        'A': preserved_task('step39_add_one'),
        'B': {'id': 'step39_normalize_tags', 'function': 'normalize_tags', 'parameters': ['tags'],
              'tests': [{'name': name, 'args': [tags], 'expected': expected} for name, tags, expected in [
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
              ]],
              'assertions': ['exact list type, element types, order and values',
                             'arguments unchanged against independent deep copy',
                             'returned list is not the supplied input list, including empty input']},
    }


def prepare(root=Path(__file__).with_name('runs')):
    """Require actual final snapshots and matching write evidence; no diff replay."""
    root = Path(root)
    path = root / 'step38b_live_comparison.json'
    original = path.read_bytes()
    live = json.loads(original)
    if live.get('status') != 'completed' or len(live.get('attempts', [])) != 6:
        raise ValueError('Require the preserved complete six-attempt run')
    plan_path = Path(__file__).with_name('step38_plan.json')
    if digest(plan_path.read_bytes()) != live['plan_sha256']:
        raise ValueError('Original Step 38 plan identity changed')
    proposed_tasks = tasks()
    result = {'schema_version': 1, 'status': 'blocked_pending_review',
              'approval_status': 'not_authorized', 'candidate_execution': False,
              'model_generation': False, 'original_run_sha256': digest(original),
              'original_plan_sha256': live['plan_sha256'], 'original_run_id': live['run_id'],
              'execution_profile_sha256': profile_hash(), 'tasks': proposed_tasks,
              'worker_input': 'source and copied args only; no expected values or grades',
              'candidates': [], 'associated_test_snapshots': [],
              'blockers': ['normalize_tags is not registered; only the fixed add_one scope is supported.',
                           'All preserved normalize_tags sources use unsupported strip; no policy exceptions allowed.']}
    for number, row in enumerate(live['attempts'], 1):
        scenario = row['scenario']
        if (row['index'] != number or row['model'] != MODELS[(number - 1) // 2] or
                scenario != ('A' if number % 2 else 'B') or row['status'] != 'completed'):
            raise ValueError('Unexpected attempt identity/state')
        stage_path = root / f'step38b_{number:02d}_{scenario}_staging.json'
        stage_bytes = stage_path.read_bytes()
        stage = json.loads(stage_bytes)
        if stage != row['staging_report']:
            raise ValueError('Independent staging record mismatch')
        files = row.get('candidate_files')
        names = {'syntax_target.py'} if scenario == 'A' else {'tag_utils.py', 'test_tag_utils.py'}
        if (not isinstance(files, dict) or set(files) != names or files != stage.get('final_files') or
                not stage['workspace_discarded'] or stage['status'] != 'prepared' or
                set(stage['review']['modified_paths']) != names):
            raise ValueError('Missing or inconsistent actual final snapshots; no reconstruction permitted')
        for name, source in files.items():
            sha = digest(source.encode('utf-8'))
            writes = [e for e in stage['accepted_changes'] if e['filename'] == name]
            saved = next((e for e in stage['review']['per_file'] if e['filename'] == name), None)
            if not writes or writes[-1]['sha256'] != sha or saved is None or saved['sha256'] != sha:
                raise ValueError('Candidate bytes disagree with successful write or final file hash')
        name = 'syntax_target.py' if scenario == 'A' else 'tag_utils.py'
        task = proposed_tasks[scenario]
        try:
            task_by_id(task['id'])
        except ValueError:
            registered = False
        else:
            registered = True
        source = files[name]
        checks = validate_source(source, task)
        result['candidates'].append({
            'attempt': number, 'model': row['model'], 'scenario': scenario, 'filename': name,
            'source': source, 'source_sha256': digest(source.encode('utf-8')),
            'staging_evidence_sha256': digest(stage_bytes), 'policy': checks,
            'worker_task_registered': registered, 'execution_permitted': False,
            'eligible_after_explicit_approval_and_fresh_verification': bool(registered and checks['static_policy_passed']),
            'functional_status': 'not_run', 'planned_vectors': len(task['tests']),
            'static_completion_in_step38b': None,
        })
        if scenario == 'B':
            source = files['test_tag_utils.py']
            result['associated_test_snapshots'].append({'attempt': number, 'source': source,
                'source_sha256': digest(source.encode('utf-8')), 'execution_scope': 'excluded'})
    # Return detached plain data. No persisted value can grant execution authority.
    return copy.deepcopy(result)


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=True, indent=2))
