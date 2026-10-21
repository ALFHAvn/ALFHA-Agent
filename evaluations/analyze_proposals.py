"""Read-only classification of retained model proposals. Never stages an edit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from git_checkpoints import SafetyError
from proposal_protocol import strict_json
from .checkpoints import atomic_write, timestamp


def classify_call(call, authorization, contents):
    result = {'proposal': call, 'safely_interpretable_edit': False}
    def finish(category, reason):
        result.update(category=category, reason=reason)
        return result
    if not isinstance(call, dict) or set(call) != {'name', 'arguments'} or not isinstance(call['arguments'], dict):
        return finish('malformed_or_ambiguous_json', 'Require exact name/arguments object')
    name, args = call['name'], call['arguments']
    fields = {'read_file': {'filename'}, 'edit_file': {'filename', 'old_text', 'new_text'}, 'validate_files': set()}
    if not isinstance(name, str) or name not in fields:
        return finish('unauthorized_operation', 'Unsupported operation; do not translate modify_file/content implicitly')
    if set(args) != fields[name] or any(not isinstance(value, str) for value in args.values()):
        return finish('malformed_or_ambiguous_json', 'Missing, unexpected or non-string arguments')
    if name == 'validate_files':
        return finish('authorized_validation', 'Not an edit')
    filename = args['filename']
    operation = 'read' if name == 'read_file' else 'modify'
    if filename not in authorization or operation not in authorization[filename]:
        return finish('unauthorized_operation', 'Filename/operation not authorized')
    if name == 'read_file':
        return finish('authorized_inspection', 'Not an edit')
    if filename not in contents:
        return finish('missing_or_nonmatching_replacement_text', 'No retained file content to verify the replacement')
    count = contents[filename].count(args['old_text']) if args['old_text'] else 0
    if not args['old_text'] or count != 1:
        return finish('missing_or_nonmatching_replacement_text', f'Exact old_text matches: {count}; empty/ambiguous matches rejected')
    if args['old_text'] == args['new_text']:
        return finish('non_actionable_explanation', 'No-op replacement')
    result['safely_interpretable_edit'] = True
    return finish('valid_single_edit', 'Authorized exact replacement as data; not permission to dispatch/recover')


def classify_message(message, authorization, contents):
    units = []
    raw = message.get('content') or ''
    doc = {'units': units, 'raw_content': raw, 'categories': [],
           'safe_multiple_edit_document': False, 'historical_execution': 'none by this analysis'}
    for call in message.get('tool_calls') or []:
        units.append(classify_call(call.get('function') if isinstance(call, dict) else call, authorization, contents))
    if raw.strip():
        try:
            parsed = strict_json(raw)
        except (SafetyError, UnicodeError) as exc:
            category = ('malformed_or_ambiguous_json' if any(x in raw for x in ('{', '[', '```'))
                        else 'non_actionable_explanation')
            doc['text_classification'] = {'category': category, 'reason': str(exc)}
        else:
            proposals = parsed if isinstance(parsed, list) else [parsed]
            if not proposals:
                doc['text_classification'] = {'category': 'malformed_or_ambiguous_json', 'reason': 'Empty proposal array'}
            for call in proposals:
                units.append(classify_call(call, authorization, contents))
            edits = [u for u in units if u['safely_interpretable_edit']]
            names = [u['proposal']['arguments']['filename'] for u in edits]
            doc['safe_multiple_edit_document'] = (len(edits) > 1 and len(edits) == len(proposals) and
                len(names) == len(set(names)) and len(proposals) <= 6)
    doc['categories'] = sorted({u['category'] for u in units} |
                              ({doc['text_classification']['category']} if 'text_classification' in doc else set()))
    if doc['safe_multiple_edit_document']:
        doc['categories'].append('valid_multiple_edits')
    doc['text_mentions_unsupported_modify_file'] = bool(re.search(r'"name"\s*:\s*"modify_file"', raw))
    doc['safe_edit_units'] = sum(u['safely_interpretable_edit'] for u in units)
    return doc


def analyze_saved(root):
    root = Path(root)
    sources, documents = [], []
    def read(name):
        path = root / name
        data = path.read_bytes()
        sources.append({'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()})
        return json.loads(data.decode('utf-8-sig'))
    initial = read('step33_preparation.json')['initial_files']
    for step in ('33', '35'):
        report = read(f'step{step}_workflow_report.json')
        for index, response in enumerate(report['model_responses']):
            doc = classify_message(response['message'], report['request']['authorized_files'], initial)
            doc.update(source=f'Step {step}', response_index=index)
            documents.append(doc)
    live = read('step36_live_comparison.json')
    for row in live['attempts']:
        for index, response in enumerate(row['workflow']['model_responses']):
            doc = classify_message(response['message'], row['request']['authorized_files'], row['initial_files'])
            doc.update(source='Step 36', model=row['model'], scenario=row['scenario'], response_index=index)
            documents.append(doc)
    units = Counter(u['category'] for d in documents for u in d['units'])
    texts = Counter(d['text_classification']['category'] for d in documents if 'text_classification' in d)
    return {'recorded_utc': timestamp(), 'mode': 'offline_data_only', 'proposal_execution': False,
            'classification_policy': 'Parse complete raw JSON only; never repair/extract fences or prose; validate against retained initial text; inspections do not modify it',
            'sources': sources, 'responses_analyzed': len(documents), 'unit_category_counts': dict(units),
            'unparseable_or_explanatory_response_counts': dict(texts),
            'safe_edit_units': sum(d['safe_edit_units'] for d in documents),
            'safe_multiple_edit_documents': sum(d['safe_multiple_edit_document'] for d in documents),
            'text_responses_mentioning_unsupported_modify_file': sum(d['text_mentions_unsupported_modify_file'] for d in documents),
            'new_protocol_auto_acceptance': 0,
            'eligibility_limitation': 'Potentially interpretable exact edits are not automatically authorized recovery. Historical data has no new version/changes envelope; no batch or proposal was dispatched.',
            'documents': documents}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path(__file__).parent / 'runs')
    args = parser.parse_args(argv)
    report = analyze_saved(args.runs)
    output = args.runs / 'step37_proposal_analysis.json'
    atomic_write(output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('documents', 'sources')}, indent=2))


if __name__ == '__main__':
    main()
