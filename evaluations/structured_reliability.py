"""Step 42 offline preparation and supplied-response assessment. No live adapters."""
import ast
import hashlib
import json
from pathlib import Path
import time

from proposal_protocol import proposal_schema, run_proposals
from git_checkpoints import SafetyError, _safe_file, _source_snapshot
from .prepare_structured import SYSTEM
from .functional_harness import task_by_id, profile_hash
from .functional_validation import validate_source
from .docker_transport import PINNED_IMAGE
from .execution_backend import ContainerPolicy
from .checkpoints import atomic_write

FIXTURES = Path(__file__).with_name('reliability_tasks.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False).encode()).hexdigest()


def request_for(task, source):
    return {'description': task['description'], 'source_repository': str(Path(source).absolute()),
            'authorized_files': {name: ['read', 'modify'] for name in task['initial_files']},
            'required_changed_files': list(task['initial_files']),
            'validation_requirements': {'static': True, 'docker_execution': False}}


def build_plan():
    tasks = json.loads(FIXTURES.read_text(encoding='utf-8'))
    if len(tasks) != 4 or len({t['id'] for t in tasks}) != 4:
        raise ValueError('Require the four fixed reliability tasks')
    for task in tasks:
        functional = task_by_id(task['functional_task'])
        if not validate_source(task['reference_source'], functional)['static_policy_passed']:
            raise ValueError('Trusted reference must fit unchanged execution policy')
        task['functional_profile'] = functional
        task['fixture_sha256'] = digest(task['initial_files'])
    attempts = []
    for round_id, seed in enumerate((42, 43, 44), 1):
        for task in tasks:
            request = request_for(task, 'APPROVED_DISPOSABLE_SOURCE')
            context = {'task': task['description'], 'authorized_files': request['authorized_files'],
                       'initial_files': task['initial_files']}
            attempts.append({'id': f'r{round_id}-{task["id"]}', 'round': round_id, 'task': task['id'],
                'payload': {'model': 'qwen3:4b', 'stream': False,
                    'options': {'temperature': 0, 'seed': seed, 'num_ctx': 8192},
                    'messages': [{'role': 'system', 'content': SYSTEM},
                                 {'role': 'user', 'content': json.dumps(context, ensure_ascii=True, indent=2)}],
                    'format': proposal_schema(request)}})
    return {'version': 1, 'status': 'pending_separate_approval', 'tasks': tasks, 'attempts': attempts,
        'controller': {'operation_budget': 6, 'responses_per_attempt': 1, 'retries': 0,
                       'native_tools': False, 'text_recovery': False, 'timeout_seconds': 180},
        'model_generation_authorized': False, 'candidate_execution_authorized': False,
        'source_application': False, 'docker_scope': {'maximum_jobs': 12,
            'maximum_vectors': sum(len(t['functional_profile']['tests']) for t in tasks) * 3,
            'image': PINNED_IMAGE, 'policy': json.loads(json.dumps(ContainerPolicy().plan(PINNED_IMAGE))),
            'profile_sha256': profile_hash(), 'string_scope': None,
            'generated_test_files_executed': False}}


def static_assessment(task, files):
    """Structural requirements only; never infer semantics from AST shape."""
    checks, trees = {}, {}
    for name in task['initial_files']:
        try:
            trees[name] = ast.parse(files[name])
            checks['ast:' + name] = True
        except (SyntaxError, ValueError, TypeError, KeyError):
            checks['ast:' + name] = False
        checks['changed:' + name] = files.get(name) != task['initial_files'][name] and name in files
    module = trees.get(task['module'])
    functions = [n for n in module.body if isinstance(n, ast.FunctionDef)] if module else []
    contract = task['functional_profile']
    checks['signature'] = bool(len(functions) == 1 and functions[0].name == contract['function'] and
        ast.dump(functions[0].args) == ast.dump(ast.parse(task['reference_source']).body[0].args))
    if 'exact_source' in task:
        checks['exact_repair'] = files.get(task['module']) == task['exact_source']
    if task.get('test_file'):
        tree = trees.get(task['test_file'])
        # Require the entire trusted test AST: preserves existing assertions and
        # excludes skips, decorators, shadowing, and misleading extra top-level code.
        checks['test_contract'] = bool(tree and ast.dump(tree) == ast.dump(ast.parse(task['expected_test_source'])))
    checks['only_authorized_files'] = set(files) == set(task['initial_files'])
    return {'checks': checks, 'completed': all(checks.values()),
            'semantic_correctness': 'not_established_by_static_checks'}


def assess_response(task_id, source, response):
    """One supplied response, real disposable staging. No generation/execution API."""
    plan = build_plan()
    task = next((t for t in plan['tasks'] if t['id'] == task_id), None)
    if task is None:
        raise ValueError('Unknown fixed task')
    source = Path(source).resolve()
    before = _source_snapshot(source)
    for name, text in task['initial_files'].items():
        try:
            actual = _safe_file(source, name).read_bytes()
        except OSError as exc:
            raise SafetyError('Required source fixture unavailable: ' + name) from exc
        if actual != text.encode('utf-8'):
            raise SafetyError('Source fixture mismatch before staging')
    started = time.monotonic()
    staged = run_proposals(request_for(task, source), [response])
    after = _source_snapshot(source)
    integrity = before == after and staged['workspace_discarded'] is True
    static = static_assessment(task, staged.get('final_files', {}))
    report = {'task': task_id, 'plan_sha256': digest(plan), 'fixture_sha256': task['fixture_sha256'],
        'elapsed_assessment_seconds': time.monotonic() - started,
        'model_response_seconds': None, 'model_invoked': False,
        'proposal_valid': bool(len(staged['events']) == 1 and staged['events'][0]['status'] == 'accepted'),
        'successful_edits': len(staged['accepted_changes']), 'budget_used': staged['budget_used'],
        'rejected_proposals': sum(e['status'] == 'rejected' for e in staged['events']),
        'changed_files': staged.get('review', {}).get('modified_paths', []),
        'errors': staged['errors'], 'staging_status': staged['status'],
        'source_unchanged': before == after, 'cleanup_verified': staged['workspace_discarded'],
        'static': static, 'static_task_completed': bool(static['completed'] and integrity and staged['ready_for_human_review']),
        'functional': {'status': 'not_run', 'passed': None, 'executed': 0,
                       'planned': len(task['functional_profile']['tests'])}, 'staging': staged}
    output = Path(staged['report_path']).with_name('assessment.json')
    report['assessment_path'] = str(output)
    atomic_write(output, report)
    return report


def summarize(records):
    """Fixed denominator, unique attempt identities; unknown results stay unknown."""
    plan = build_plan(); allowed = {a['id']: a for a in plan['attempts']}
    seen = set(); per_task = {t['id']: {'attempted': 0, 'static_passed': 0, 'static_known': 0,
                                     'static_unknown': 0} for t in plan['tasks']}
    for row in records:
        key = row['attempt_id']
        if key not in allowed or key in seen or row['task'] != allowed[key]['task']:
            raise ValueError('Unknown, duplicate or mismatched attempt')
        outcome = row['static_task_completed']
        if outcome is not None and type(outcome) is not bool:
            raise ValueError('Require a Boolean static result or explicit unknown')
        seen.add(key); bucket = per_task[row['task']]
        bucket['attempted'] += 1; bucket['static_passed'] += int(outcome is True)
        bucket['static_known'] += int(outcome is not None)
        bucket['static_unknown'] += int(outcome is None)
    for bucket in per_task.values():
        n = bucket['static_known']; bucket['static_rate'] = bucket['static_passed'] / n if n else None
    passed = sum(b['static_passed'] for b in per_task.values())
    known = sum(b['static_known'] for b in per_task.values())
    return {'planned': 12, 'attempted': len(seen), 'unattempted': 12-len(seen), 'static_passed': passed,
            'static_known': known, 'static_unknown': len(seen)-known,
            'static_rate': passed/known if known else None, 'per_task': per_task,
            'functional_rate': None, 'functional_status': 'separate_authorization_and_results_required',
            'small_sample_warning': 'Three attempts per task; seeds do not establish independent samples.'}


if __name__ == '__main__':
    print(json.dumps(build_plan(), ensure_ascii=True, indent=2))
