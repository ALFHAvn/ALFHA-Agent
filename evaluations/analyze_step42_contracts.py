"""Read-only provenance analysis. Does not stage historical proposals or execute code."""
import hashlib
import json
from pathlib import Path

from proposal_protocol import envelope
from .contract_diagnostics import test_contract


def analyze(root=Path(__file__).with_name('runs')):
    root = Path(root)
    report_path = root / 'step42_live_results.json'
    raw = report_path.read_bytes()
    report = json.loads(raw)
    tasks = {task['id']: task for task in report['plan']['tasks']}
    rows = []
    for row in report['attempts']:
        if row['task'] not in ('bounds', 'stable_unique'):
            continue
        saved_path = root / f'step42_{row["attempt_id"]}_response.json'
        saved = json.loads(saved_path.read_bytes())
        content = saved['message']['content']
        if content != row['raw_content'] or saved != row['raw_response']:
            raise ValueError('Saved response copies disagree')
        round_trip = json.loads(json.dumps(content))
        if round_trip != content:
            raise ValueError('Response archive round-trip changed content')
        changes = envelope(content)
        if changes != json.loads(content)['changes']:
            raise ValueError('Strict parser disagrees with independent JSON decoding')
        task = tasks[row['task']]
        prompt = json.loads(row['payload']['messages'][1]['content'])
        if prompt['initial_files'] != task['initial_files'] or prompt['task'] != task['description']:
            raise ValueError('Recorded request differs from reviewed task')
        item = {'attempt_id': row['attempt_id'], 'task': row['task'],
                'saved_response_sha256': hashlib.sha256(saved_path.read_bytes()).hexdigest(),
                'archive_round_trip_identical': True, 'independent_decoder_agrees': True,
                'corrective_responses_sent': 0, 'changes': []}
        for change in changes:
            text = change['old_text']
            item['changes'].append({'filename': change['filename'],
                'literal_backslash_n': '\\n' in text, 'actual_newlines': text.count('\n'),
                'exact_matches': task['initial_files'][change['filename']].count(text)})
        snapshot = json.loads(Path(row['candidate_snapshot_path']).read_bytes())
        if snapshot['files'] != row['candidate_files']:
            raise ValueError('Retained final candidate differs')
        if any(hashlib.sha256(text.encode()).hexdigest() != snapshot['sha256'][name]
               for name, text in snapshot['files'].items()):
            raise ValueError('Retained candidate hash mismatch')
        if row['task'] == 'stable_unique':
            item['identity_requirement_present_in_request'] = 'result is not values' in prompt['task']
            item['contract'] = test_contract(task['expected_test_source'],
                                            snapshot['files'][task['test_file']], task['test_file'])
        rows.append(item)
    return {'analysis_only': True, 'model_requests': 0, 'candidate_jobs': 0,
        'historical_report_sha256': hashlib.sha256(raw).hexdigest(), 'rows': rows,
        'confirmed': ['Literal escapes already occur in earliest retained response content',
                      'Archive round-trip and independent/controller JSON decoding agree',
                      'Identity requirement was explicit; generated tests substituted !=',
                      'One-response benchmark sent no corrective feedback'],
        'limitations': ['No raw HTTP bytes retained: cannot independently audit SDK/wire boundary',
                        'Generation escape confusion is supported, but exact causal mechanism is unproven',
                        'Auxiliary model text is self-report, not proof of internal reasoning',
                        'No live reliability improvement measured']}


if __name__ == '__main__':
    print(json.dumps(analyze(), indent=2))
