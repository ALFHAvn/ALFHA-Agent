"""Offline structured replacement prototype. No model, execution, or source apply API."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import uuid

from coding_workflow import validate_request
from evaluations.checkpoints import atomic_write, timestamp
from git_checkpoints import SafetyError, MAX_FILE_BYTES, _safe_file
from multi_file_tasks import MultiFileTask, _text

MAX_OPERATIONS = 6
MAX_RESPONSE_BYTES = 65536


def proposal_schema(request):
    """Exact-path schema for a future reviewed adapter; grants no authority."""
    request = validate_request(request)
    if 'tool_policy' in request or any(set(ops) - {'read', 'modify'} or
            'modify' in ops and 'read' not in ops for ops in request['authorized_files'].values()):
        raise SafetyError('Use the separate existing-file replacement protocol explicitly')
    names = [name for name, ops in request['authorized_files'].items() if 'modify' in ops]
    if not names:
        raise SafetyError('Require at least one authorized modification target')
    return {'type': 'object', 'additionalProperties': False, 'required': ['version', 'changes'],
            'properties': {'version': {'type': 'integer', 'const': 1},
                'changes': {'type': 'array', 'minItems': 1, 'maxItems': MAX_OPERATIONS,
                    'items': {'type': 'object', 'additionalProperties': False,
                        'required': ['operation', 'filename', 'old_text', 'new_text'],
                        'properties': {'operation': {'type': 'string', 'const': 'replace_text'},
                            'filename': {'type': 'string', 'enum': names},
                            'old_text': {'type': 'string', 'minLength': 1},
                            'new_text': {'type': 'string'}}}}}}


def strict_json(text):
    try:
        size = len(text.encode('utf-8')) if isinstance(text, str) else MAX_RESPONSE_BYTES + 1
    except UnicodeError as exc:
        raise SafetyError('Response must be valid UTF-8 text') from exc
    if size > MAX_RESPONSE_BYTES:
        raise SafetyError('Require a UTF-8 JSON response of at most 65536 bytes')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON key: ' + key)
            obj[key] = value
        return obj
    def constant(value):
        raise ValueError('Nonstandard JSON constant: ' + value)
    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        raise SafetyError('Require one complete raw JSON document; no fences, prose or trailing proposals: ' + str(exc)) from exc


def envelope(text):
    document = strict_json(text)
    if (not isinstance(document, dict) or set(document) != {'version', 'changes'} or
            type(document['version']) is not int or document['version'] != 1 or
            not isinstance(document['changes'], list) or not document['changes']):
        raise SafetyError('Require exactly version=1 and a nonempty changes array')
    return document['changes']


def validate_changes(changes, authorization, contents):
    """Pure prevalidation/simulation. Never writes files or repairs model text."""
    prepared, seen = {}, set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'operation', 'filename', 'old_text', 'new_text'}:
            raise SafetyError('Each change requires exactly operation, filename, old_text, new_text')
        if any(not isinstance(value, str) for value in change.values()):
            raise SafetyError('All change fields must be strings')
        name = change['filename']
        if change['operation'] != 'replace_text':
            raise SafetyError('Only explicit replace_text is supported; no execution, creation or deletion')
        if name not in authorization or not {'read', 'modify'} <= set(authorization[name]):
            raise SafetyError('Exact filename and read/modify permissions required')
        if name in seen:
            raise SafetyError('Duplicate filename in batch; overlapping/sequential edits are ambiguous')
        seen.add(name)
        old, new = change['old_text'], change['new_text']
        if not old or old == new:
            raise SafetyError('old_text must be nonempty and replacement must change it')
        count = contents[name].count(old)
        if count != 1:
            raise SafetyError(f'Exact replacement requires one match; found {count}; use actual newlines and unique context')
        result = contents[name].replace(old, new, 1)
        encoded = result.encode('utf-8')
        if len(encoded) > MAX_FILE_BYTES:
            raise SafetyError('Result exceeds the existing file size limit')
        _text(encoded)
        prepared[name] = result
    return prepared


def run_proposals(request, responses):
    """Data-only mocked response sequence; live adapters are deliberately unsupported.

    Every declared change (even in a rejected batch) consumes an operation slot.
    Malformed envelopes consume one. Oversized batches exhaust the remaining
    slots and write nothing. At most six response documents are accepted as input.
    """
    request = validate_request(request)
    if 'tool_policy' in request:
        raise SafetyError('Native-tool recovery/inspection policies do not authorize this separate protocol')
    authorization = request['authorized_files']
    if any(set(ops) - {'read', 'modify'} or 'modify' in ops and 'read' not in ops for ops in authorization.values()):
        raise SafetyError('Prototype supports existing files with explicit read/modify or read-only permissions')
    if not isinstance(responses, (tuple, list)) or not 1 <= len(responses) <= MAX_OPERATIONS or any(not isinstance(x, str) for x in responses):
        raise SafetyError('Require one to six supplied response strings; no callable/live model adapter')
    try:
        json.dumps(request, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if any(len(response.encode('utf-8')) > MAX_RESPONSE_BYTES for response in responses):
            raise ValueError('Response exceeds 65536 bytes')
    except (UnicodeError, ValueError, TypeError) as exc:
        raise SafetyError('Require bounded UTF-8 request/response data') from exc
    required = request.get('required_changed_files', [n for n, ops in authorization.items() if 'modify' in ops])
    if not required:
        raise SafetyError('Require at least one explicitly authorized modification target')
    task = MultiFileTask.prepare(request['source_repository'], list(authorization))
    try:
        evidence = Path(tempfile.mkdtemp(prefix='alfha-proposal-report-')).resolve()
        if evidence.is_relative_to(task.source):
            evidence.rmdir()
            raise SafetyError('Evidence must be outside source repository')
    except BaseException:
        task.discard()
        raise
    output = evidence / 'report.json'
    report = {'schema_version': 1, 'protocol': 'explicit-replacements-v1', 'run_id': uuid.uuid4().hex,
              'started_utc': timestamp(), 'request': request, 'starting_commit': task.starting_commit,
              'budget': MAX_OPERATIONS, 'budget_used': 0, 'events': [], 'accepted_changes': [],
              'status': 'running', 'errors': [], 'source_application': False, 'model_invoked': False,
              'candidate_execution': 'disabled', 'functional_correctness': 'not_tested',
              'ready_for_human_review': False, 'report_path': str(output)}
    expected_contents = None
    def save():
        report['checkpoint_utc'] = timestamp()
        atomic_write(output, report)
    try:
        report['initial_files'] = {name: task.read_text(name) for name in authorization}
        expected_contents = copy.deepcopy(report['initial_files'])
        save()
        for response in responses:
            if report['budget_used'] == MAX_OPERATIONS:
                break
            event = {'response': response, 'status': 'pending', 'sequence': len(report['events']) + 1}
            report['events'].append(event)
            save()
            try:
                changes = envelope(response)
            except (SafetyError, UnicodeError) as exc:
                report['budget_used'] += 1
                event.update(status='rejected', error=str(exc), charged_operations=1)
                save()
                continue
            remaining = MAX_OPERATIONS - report['budget_used']
            charged = min(len(changes), remaining)
            report['budget_used'] += charged
            event.update(requested_operations=len(changes), charged_operations=charged)
            if len(changes) > remaining:
                event.update(status='rejected', error='Batch exceeds remaining six-operation budget; nothing staged')
                save()
                break
            try:
                review = task.inspect()
                if review['stale']:
                    raise SafetyError('Source state is stale; stop')
                contents = {name: task.read_text(name) for name in authorization}
                if contents != expected_contents:
                    event.update(status='rejected', error='Staging diverged from accepted replacements')
                    report['status'] = 'integrity_or_stale_failure'
                    save()
                    break
                prepared = validate_changes(changes, authorization, contents)
            except (SafetyError, OSError, UnicodeError, KeyError) as exc:
                event.update(status='rejected', error=str(exc))
                save()
                if task.report().get('integrity') == 'rejected' or task.report().get('stale'):
                    report['status'] = 'integrity_or_stale_failure'
                    break
                continue
            # All batch arguments and exact replacements were checked before any write.
            # Writes are not an OS transaction: a runtime failure preserves partial
            # staging evidence and stops, then discards only this owned workspace.
            event['status'] = 'staging'
            save()
            for name, content in prepared.items():
                if task.inspect()['stale'] or task.read_text(name) != contents[name]:
                    raise SafetyError('Source or staging changed after prevalidation')
                task.write_text(name, content)
                expected_contents[name] = content
                report['accepted_changes'].append({'filename': name, 'event': event['sequence'],
                    'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()})
                save()
            if task.inspect()['stale']:
                raise SafetyError('Source changed during staging')
            event['status'] = 'accepted'
            save()
        if report['status'] == 'running':
            report['status'] = 'prepared' if report['accepted_changes'] else 'no_changes'
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
        report['errors'].append('Interrupted; no restart or execution')
        if report['events'] and report['events'][-1]['status'] == 'staging':
            report['events'][-1].update(status='interrupted', outcome_unknown=True)
    except Exception as exc:
        report['status'] = 'staging_failed'
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        if report['events'] and report['events'][-1]['status'] == 'staging':
            report['events'][-1].update(status='staging_failed', partial_changes_possible=True, error=str(exc))
    finally:
        try:
            report['validation'] = task.validate()
            report['review'] = task.report()
            report['final_files'] = {name: task.read_text(name) for name in authorization}
            if expected_contents is not None and report['final_files'] != expected_contents:
                report['errors'].append('Candidate diverged from accepted replacements')
                if report['status'] not in ('staging_failed', 'interrupted'):
                    report['status'] = 'integrity_or_stale_failure'
            report['missing_required_changes'] = [n for n in required if n not in report['review'].get('modified_paths', [])]
            report['ready_for_human_review'] = bool(report['status'] == 'prepared' and report['validation']['passed'] and
                report['review'].get('ready_for_user_review') and not report['missing_required_changes'])
        except Exception as exc:
            report['errors'].append('Final validation/review: ' + str(exc))
            report['review'] = task.report()
            report['ready_for_human_review'] = False
        try:
            save()
        finally:
            try:
                task.discard()
                report['workspace_discarded'] = True
            except Exception as exc:
                report['workspace_discarded'] = False
                report['ready_for_human_review'] = False
                report['errors'].append('Cleanup refused/failed: ' + str(exc))
            report['completed_utc'] = timestamp()
            save()
    return report
