"""Step 44 preparation and offline assessment only. No live adapter or execution."""
import copy
import hashlib
import inspect
import json
from pathlib import Path

from proposal_protocol import proposal_messages, proposal_schema, envelope
from git_checkpoints import SafetyError
from .checkpoints import atomic_write
from .structured_reliability import (build_plan as baseline_builder, request_for,
                                     assess_response, digest)

BASELINE = Path(__file__).with_name('step42_plan.json')
FOCUS = ('bounds', 'stable_unique')
PROMPT_VERSION = 'step43-structured-instructions-v1'


def build_plan():
    raw = BASELINE.read_bytes()
    baseline = json.loads(raw)
    if baseline != baseline_builder():
        raise ValueError('Frozen Step 42 baseline differs from its builder')
    tasks = [copy.deepcopy(t) for t in baseline['tasks'] if t['id'] in FOCUS]
    attempts = []
    for old in baseline['attempts']:
        if old['task'] not in FOCUS:
            continue
        task = next(t for t in tasks if t['id'] == old['task'])
        request = request_for(task, 'APPROVED_DISPOSABLE_SOURCE')
        messages = proposal_messages(request, task['initial_files'])
        payload = copy.deepcopy(old['payload'])
        # Deliberately do not use the helper's added user checklist. Preserve
        # the historical user message exactly; only system guidance changes.
        payload['messages'][0] = messages[0]
        assert payload['format'] == proposal_schema(request)
        attempts.append({'attempt_id': 'step44-' + old['id'], 'round': old['round'],
            'task': old['task'], 'baseline_attempt_id': old['id'],
            'prompt_version': PROMPT_VERSION, 'request_version': 'step44-focused-v1',
            'baseline_payload_sha256': digest(old['payload']), 'payload_sha256': digest(payload),
            'system_prompt_sha256': hashlib.sha256(messages[0]['content'].encode()).hexdigest(),
            'user_message_sha256': hashlib.sha256(payload['messages'][1]['content'].encode()).hexdigest(),
            'schema_sha256': digest(payload['format']), 'payload': payload})
    if len(tasks) != 2 or len(attempts) != 6:
        raise ValueError('Require two tasks and six fixed requests')
    return {'schema_version': 1, 'status': 'pending_separate_generation_approval',
        'preparation_base_commit': 'f9c9779', 'model': 'qwen3:4b',
        'prompt_intervention': 'system_message_only', 'baseline_plan_sha256': hashlib.sha256(raw).hexdigest(),
        'instruction_builder_sha256': hashlib.sha256(inspect.getsource(proposal_messages).encode()).hexdigest(),
        'validation_sources_sha256': {str(path.as_posix()): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path('proposal_protocol.py'), Path('evaluations/structured_reliability.py'),
                         Path('evaluations/contract_diagnostics.py'))},
        'protocol_version': 'explicit-replacements-v1', 'prompt_version': PROMPT_VERSION,
        'controller': copy.deepcopy(baseline['controller']), 'maximum_generation_requests': 6,
        'generation_authorized': False, 'candidate_execution_authorized': False,
        'generated_test_execution': False, 'source_application': False,
        'tasks': tasks, 'attempts': attempts,
        'success_definition': 'All unchanged original static criteria, both required file changes, integrity and cleanup; functional correctness remains untested',
        'feedback_delivery': 'report_only; no corrective response or retry',
        'preflight_required_after_approval': ['approved commit/plan/controller hashes and pristine fixtures',
            'bounded read-only Docker readiness then mandatory definitive inventory',
            'Ollama API and exact retained qwen3:4b model identity',
            'Linux engine and approved pinned image metadata', 'no ALFHA editing/execution staging'],
        'lifecycle': 'One fresh request per slot; checkpoint before generation and raw response before parsing; stop on infrastructure/integrity failure; no resume; authorization expires on completion or abort',
        'recommendation_gate': 'After live outcomes, assess readiness for limited human review; no automatic interactive integration or application'}


def assess_attempt(attempt_id, source, raw_response):
    """One supplied response in disposable Git; never contacts a model."""
    plan = build_plan()
    spec = next((a for a in plan['attempts'] if a['attempt_id'] == attempt_id), None)
    if spec is None:
        raise SafetyError('Unknown Step 44 attempt identity')
    task = next(t for t in plan['tasks'] if t['id'] == spec['task'])
    result = assess_response(spec['task'], source, raw_response)
    multiline = []
    try:
        changes = envelope(raw_response)
        for change in changes:
            if not isinstance(change, dict):
                continue
            old, new, name = (change.get(k) for k in ('old_text', 'new_text', 'filename'))
            if type(old) is str and type(new) is str and type(name) is str:
                multiline.append({'filename': name, 'old_actual_newlines': old.count('\n'),
                    'old_literal_backslash_n': '\\n' in old, 'new_actual_newlines': new.count('\n'),
                    'new_literal_backslash_n': '\\n' in new,
                    'old_exact_matches': task['initial_files'][name].count(old) if name in task['initial_files'] else None})
    except SafetyError:
        pass  # Original staging report retains the exact rejection; no salvage.
    report = {'attempt_id': attempt_id, 'baseline_attempt_id': spec['baseline_attempt_id'],
        'task': spec['task'], 'round': spec['round'], 'prompt_version': PROMPT_VERSION,
        'plan_sha256': digest(plan), 'payload_sha256': spec['payload_sha256'],
        'response_origin': 'supplied_offline_data', 'model_invoked': False,
        'raw_response': raw_response, 'response_sha256': hashlib.sha256(raw_response.encode()).hexdigest(),
        'proposal_valid': result['proposal_valid'], 'successful_edits': result['successful_edits'],
        'budget_used': result['budget_used'], 'multiline_observations': multiline,
        'complete_static_task': result['static_task_completed'],
        'implementation_static': result['static']['implementation_static'],
        'generated_test_contract': result['static']['generated_test_contract'],
        'functional_status': 'not_run', 'functional_passed': None,
        'feedback': result['feedback'], 'assessment': result,
        'candidate_sha256': {n: hashlib.sha256(t.encode()).hexdigest()
                             for n, t in result['staging'].get('final_files', {}).items()}}
    output = Path(result['assessment_path']).with_name('step44_assessment.json')
    report['report_path'] = str(output)
    atomic_write(output, report)
    return report


def duplication_report(records, historical):
    """Exact content comparison, not semantic similarity or evidence of generation.

    Historical records are never counted as new outcomes. A future authorized
    live caller must retain real request events; supplied strings alone prove
    neither that generation occurred nor that an attempt succeeded.
    """
    allowed = {a['attempt_id'] for a in build_plan()['attempts']}
    seen, groups, matches, patterns = set(), {}, [], {}
    for row in records:
        key = row['attempt_id']
        if key not in allowed or key in seen:
            raise ValueError('Unknown or repeated Step 44 attempt ID')
        seen.add(key)
        content = row.get('raw_response')
        if content is not None:
            if type(content) is not str:
                raise ValueError('Response content must be text or explicit unknown')
            groups.setdefault(content, []).append(key)
            matches.append({'attempt_id': key, 'historical_exact_matches':
                            [old for old, text in historical.items() if text == content]})
        for code in {d['code'] for d in row.get('feedback', [])}:
            patterns.setdefault(code, []).append(key)
    return {'analyzed_new_records': len(seen), 'unprovided_slots': 6-len(seen),
        'unknown_response_slots': sum(r.get('raw_response') is None for r in records),
        'distinct_response_texts': len(groups), 'historical_records': len(historical),
        'exact_new_duplicate_groups': [{'attempt_ids': keys, 'response_sha256': hashlib.sha256(text.encode()).hexdigest()}
                                      for text, keys in groups.items() if len(keys) > 1],
        'historical_matches': matches,
        'recurring_failure_patterns': [{'code': code, 'attempt_ids': keys} for code, keys in sorted(patterns.items()) if len(keys) > 1],
        'does_not_prove_live_generation': True, 'functional_results': 'not_measured',
        'limitation': 'Small correlated sample; exact repeats and different seeds are not independent evidence.'}


def summarize_attempts(records):
    """Separate full static outcomes from JSON/edit success; preserve unknowns."""
    allowed = {a['attempt_id']: a for a in build_plan()['attempts']}
    seen = set()
    per_task = {t: {'attempted': 0, 'known': 0, 'passed': 0, 'unknown': 0} for t in FOCUS}
    per_round = {str(n): {'attempted': 0, 'known': 0, 'passed': 0, 'unknown': 0} for n in (1, 2, 3)}
    valid = edits = 0
    for row in records:
        key = row['attempt_id']
        if key not in allowed or key in seen:
            raise ValueError('Unknown or duplicate new attempt ID')
        spec = allowed[key]
        if row['task'] != spec['task'] or row['round'] != spec['round']:
            raise ValueError('Attempt task/round differs from fixed plan')
        outcome = row['complete_static_task']
        if outcome is not None and type(outcome) is not bool:
            raise ValueError('Require Boolean complete-static outcome or explicit unknown')
        seen.add(key)
        valid += int(row.get('proposal_valid') is True)
        count = row.get('successful_edits', 0)
        if type(count) is not int or not 0 <= count <= 2:
            raise ValueError('Require actual edit count for the two authorized files')
        edits += count
        for bucket in (per_task[spec['task']], per_round[str(spec['round'])]):
            bucket['attempted'] += 1; bucket['known'] += int(outcome is not None)
            bucket['passed'] += int(outcome is True); bucket['unknown'] += int(outcome is None)
    known = sum(x['known'] for x in per_task.values())
    passed = sum(x['passed'] for x in per_task.values())
    return {'planned': 6, 'attempted': len(seen), 'unattempted': 6-len(seen),
        'complete_static_known': known, 'complete_static_unknown': len(seen)-known,
        'complete_static_passed': passed, 'complete_static_rate': passed/known if known else None,
        'valid_proposals': valid, 'successful_edits': edits, 'per_task': per_task, 'per_round': per_round,
        'functional_results': 'not_measured', 'interactive_integration_authorized': False}


if __name__ == '__main__':
    print(json.dumps(build_plan(), ensure_ascii=True, indent=2))
