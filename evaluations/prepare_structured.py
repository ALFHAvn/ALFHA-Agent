"""Build reviewable Step 38 requests offline; this module cannot invoke a model."""
import copy
import hashlib
import json
from pathlib import Path

from proposal_protocol import proposal_schema

BASELINE = Path(__file__).with_name('step36_plan.json')
SYSTEM = (
    'Return exactly one raw JSON document matching the supplied JSON schema. '
    'No prose, Markdown, native tool calls or extra fields. Use version 1 and changes. '
    'Each change must use operation replace_text, an exact authorized filename, old_text '
    'copied exactly from the supplied file (one match), and new_text. JSON newline escapes '
    'must decode to real newlines. At most six operations total; at most one replacement '
    'per file. To coordinate several changes in a file, replace one larger exact region. '
    'Only read and modify the supplied authorized files. No creation, deletion or execution. '
    'All changes are validated together before any edit; invalid batches are rejected. '
    'There is one response only, with no correction or retry. Changes remain review-only.'
)


def build_plan():
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    plan = {
        'status': 'pending_explicit_live_approval', 'preparation_commit': '416f47b',
        'baseline_plan_sha256': hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
        'models': baseline['models'], 'attempts': 6, 'attempts_per_model_per_scenario': 1,
        'controller': {
            'operation_budget': 6, 'responses_per_attempt': 1, 'automatic_retries': 0,
            'corrective_prompts': 0, 'native_tools': False, 'text_recovery': False,
            'atomic_batch_validation': True, 'max_response_bytes': 65536,
            'request_timeout_seconds': 180, 'candidate_execution': 'disabled',
            'source_application': 'unsupported', 'approval_is_not_execution_capability': True,
        }, 'scenarios': {}, 'model_requests': [],
    }
    for key, scenario in baseline['scenarios'].items():
        request = copy.deepcopy(scenario['request_template'])
        request.pop('tool_policy')
        # Preserve requirements verbatim; replace only legacy native-tool instructions.
        requirement = request['description'].split('Use actual tools to inspect and edit')[0].rstrip()
        request['description'] = requirement
        request['source_repository'] = str(Path('APPROVED_DISPOSABLE_SOURCE').absolute())
        schema = proposal_schema(request)
        context = {'task': requirement, 'authorized_files': request['authorized_files'],
                   'initial_files': scenario['initial_files']}
        messages = [{'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, indent=2)}]
        plan['scenarios'][key] = {
            'request_template': {k: v for k, v in request.items() if k != 'source_repository'},
            'initial_files': scenario['initial_files'],
            'file_sha256': {name: hashlib.sha256(text.encode()).hexdigest()
                            for name, text in scenario['initial_files'].items()},
            'acceptance': scenario.get('static_acceptance', [
                'syntax_target.py changed to exactly the baseline expected_source',
                'AST parsing passes; original signature and body preserved',
                'Source unchanged, staging discarded, diff and trace retained']),
            **({'expected_source': scenario['expected_source']} if key == 'A' else {}),
        }
        for model in baseline['models']:
            plan['model_requests'].append({'scenario': key, 'payload': {
                'model': model, 'messages': copy.deepcopy(messages), 'format': copy.deepcopy(schema),
                'options': copy.deepcopy(baseline['chat_options']), 'stream': False}})
    # Same ordering as Step 36: each model A then B.
    plan['model_requests'].sort(key=lambda item: (baseline['models'].index(item['payload']['model']),
                                               item['scenario']))
    return plan


if __name__ == '__main__':
    print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
