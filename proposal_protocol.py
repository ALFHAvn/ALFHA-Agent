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


class ProposalValidationError(SafetyError):
    """Compatible safety rejection with machine-readable corrective feedback."""
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic['message'])


def proposal_messages(request, contents, *, allow_line_arrays=False, include_source_lines=False):
    """Versioned future instructions; never rewrites frozen benchmark payloads.

    This creates data only. It grants no model calls, retries, or execution.
    """
    request = validate_request(request)
    if type(include_source_lines) is not bool or include_source_lines and not allow_line_arrays:
        raise SafetyError('Source-line context requires explicit version 2 line-array mode')
    proposal_schema(request, allow_line_arrays=allow_line_arrays)
    if (set(contents) != set(request['authorized_files']) or
            any(type(text) is not str for text in contents.values()) or
            any('read' not in ops for ops in request['authorized_files'].values())):
        raise SafetyError('Provide exact authorized readable file contents only')
    system = (
        'Return one raw JSON object with exactly version=1 and changes, not a JSON-encoded '
        'string or an array. Each change has exactly operation="replace_text", filename, '
        'old_text and new_text. Use only authorized existing paths and at most six '
        'operations, one replacement per file. Copy old_text from DECODED source text; '
        'it must match exactly once. Encode the response as JSON once. '
        'For two source lines, the correct JSON string is ' + json.dumps('first\nsecond') +
        '; it decodes to one actual newline. The different JSON string ' + json.dumps(r'first\nsecond') +
        ' decodes to literal backslash+n and will not match multiline source. '
        'Do not copy the escaped JSON display as literal source. Preserve indentation and '
        'trailing newlines. Never assume the controller will unescape or repair text. '
        'Complete every required file change and every requested test assertion. '
        'Preserve assertion operators, variable names, existing tests and required order. '
        'Object identity requires "assert result is not values"; "result != values" '
        'compares contents and is not equivalent. Do not weaken or substitute assertions. '
        'No prose, Markdown, tools, extra fields, creation, deletion or execution. '
        'All edits are prevalidated together; ambiguous or invalid batches write nothing. '
        'There is no automatic correction or retry. Static acceptance does not prove '
        'functional correctness. Changes remain isolated and review-only.'
    )
    if allow_line_arrays:
        system = (
            'Return one raw JSON object with exactly version=2 and changes. Each change '
            'has exactly operation="replace_lines", filename, old_lines and new_lines. '
            'Both line fields are arrays of strings without CR or LF characters. '
            'Join elements with exactly one LF between them; there is no implicit final LF. '
            'A final empty element represents a trailing LF; interior empty elements '
            'represent blank lines. new_lines=[] means empty replacement text; old_lines '
            'must join to nonempty text. Backslashes remain literal: never encode line '
            'separators as backslash+n. Copy source lines exactly, including indentation. '
            'Use only authorized existing paths, at most six operations and one replacement '
            'per file. The joined old_lines must match exactly once. No string-based '
            'fields, prose, Markdown, tools, creation, deletion or execution. All edits '
            'are prevalidated together; invalid batches write nothing. No repair or retry. '
            'Complete all required file changes and test assertions; preserve operators, '
            'names and order. Object identity requires "assert result is not values", '
            'not "result != values". Static checks do not prove functional correctness. '
            'Changes remain isolated and review-only.'
        )
    context = {'task': request['description'], 'authorized_files': request['authorized_files'],
               'required_changed_files': request.get('required_changed_files',
                   [name for name, ops in request['authorized_files'].items() if 'modify' in ops]),
               'initial_files': contents}
    if include_source_lines:
        system += (
            ' Copy contiguous elements from initial_file_lines into old_lines. '
            'Every empty string is significant: two consecutive empty strings mean '
            'two blank lines. Never collapse or omit them. Select a short unique '
            'target when possible, rather than retyping the entire file. The last '
            'empty element denotes a final LF. These arrays are exact LF splits, '
            'not normalized source; CR characters, if present, are retained. '
            'Do not copy line numbers or JSON display escaping into source lines.'
        )
        context['initial_file_lines'] = {name: text.split('\n') for name, text in contents.items()}
    return [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=True, indent=2)}]


def _target_context_hint(current, old):
    """Bounded diagnostic only, using unique exact boundary lines. Never repairs."""
    proposed = old.split('\n', 200)
    source = current.split('\n', 2000)[:2000]
    if len(proposed) > 200 or not proposed[0] or not proposed[-1]:
        return None
    starts = [i for i, line in enumerate(source) if line == proposed[0]]
    ends = [i for i, line in enumerate(source) if line == proposed[-1]]
    if len(starts) != 1 or len(ends) != 1:
        return None
    start, end = starts[0], ends[0]
    if not start <= end < start + 200:
        return None
    actual = source[start:end + 1]
    if actual == proposed:
        return None
    mismatch = next((i for i in range(min(len(actual), len(proposed)))
                     if actual[i] != proposed[i]), min(len(actual), len(proposed)))
    return {'source_start_line': start + 1, 'source_end_line': end + 1,
            'first_differing_offset': mismatch,
            'source_line': actual[mismatch][:160] if mismatch < len(actual) else None,
            'proposed_line': proposed[mismatch][:160] if mismatch < len(proposed) else None,
            'source_empty_lines': actual.count(''), 'proposed_empty_lines': proposed.count(''),
            'scope': 'Unique exact boundary lines; diagnostic only, no normalized match or repair'}


def proposal_schema(request, *, allow_line_arrays=False):
    """Exact-path schema for a future reviewed adapter; grants no authority."""
    _line_option(allow_line_arrays)
    request = validate_request(request)
    if 'tool_policy' in request or any(set(ops) - {'read', 'modify'} or
            'modify' in ops and 'read' not in ops for ops in request['authorized_files'].values()):
        raise SafetyError('Use the separate existing-file replacement protocol explicitly')
    names = [name for name, ops in request['authorized_files'].items() if 'modify' in ops]
    if not names:
        raise SafetyError('Require at least one authorized modification target')
    legacy = {'type': 'object', 'additionalProperties': False, 'required': ['version', 'changes'],
            'properties': {'version': {'type': 'integer', 'const': 1},
                'changes': {'type': 'array', 'minItems': 1, 'maxItems': MAX_OPERATIONS,
                    'items': {'type': 'object', 'additionalProperties': False,
                        'required': ['operation', 'filename', 'old_text', 'new_text'],
                        'properties': {'operation': {'type': 'string', 'const': 'replace_text'},
                            'filename': {'type': 'string', 'enum': names},
                            'old_text': {'type': 'string', 'minLength': 1},
                            'new_text': {'type': 'string'}}}}}}
    if not allow_line_arrays:
        return legacy
    lines = copy.deepcopy(legacy)
    lines['properties']['version']['const'] = 2
    item = lines['properties']['changes']['items']
    item['required'] = ['operation', 'filename', 'old_lines', 'new_lines']
    item['properties'] = {
        'operation': {'type': 'string', 'const': 'replace_lines'},
        'filename': {'type': 'string', 'enum': names},
        'old_lines': {'type': 'array', 'minItems': 1,
                      'items': {'type': 'string', 'pattern': r'^[^\r\n]*$(?![\s\S])'}},
        'new_lines': {'type': 'array',
                      'items': {'type': 'string', 'pattern': r'^[^\r\n]*$(?![\s\S])'}}}
    return {'oneOf': [legacy, lines]}


def _line_option(value):
    if type(value) is not bool:
        raise SafetyError('allow_line_arrays must be an explicit boolean')


def _line_text(value, field):
    if (type(value) is not list or any(type(line) is not str or '\r' in line or '\n' in line
                                      for line in value)):
        raise SafetyError(field + ' must be an array of strings without CR or LF')
    return '\n'.join(value)


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


def envelope(text, *, allow_line_arrays=False):
    _line_option(allow_line_arrays)
    document = strict_json(text)
    if (not isinstance(document, dict) or set(document) != {'version', 'changes'} or
            type(document['version']) is not int or document['version'] not in
            ((1, 2) if allow_line_arrays else (1,)) or
            not isinstance(document['changes'], list) or not document['changes']):
        raise SafetyError('Require exactly version=1 and a nonempty changes array')
    if document['version'] == 2:
        if any(not isinstance(change, dict) or set(change) !=
               {'operation', 'filename', 'old_lines', 'new_lines'} or
               change['operation'] != 'replace_lines' for change in document['changes']):
            raise SafetyError('version=2 requires only explicit replace_lines changes')
    elif any(isinstance(change, dict) and
             (change.get('operation') == 'replace_lines' or
              'old_lines' in change or 'new_lines' in change) for change in document['changes']):
        raise SafetyError('Line arrays require opt-in and version=2; mixed representations rejected')
    return document['changes']


def validate_changes(changes, authorization, contents, *, allow_line_arrays=False):
    """Pure prevalidation/simulation. Never writes files or repairs model text."""
    _line_option(allow_line_arrays)
    prepared, seen = {}, set()
    if (any(isinstance(c, dict) and c.get('operation') == 'replace_lines' for c in changes)
            and any(not isinstance(c, dict) or c.get('operation') != 'replace_lines' for c in changes)):
        raise SafetyError('Mixed string and line-array batches are not supported')
    for change in changes:
        if isinstance(change, dict) and change.get('operation') == 'replace_lines':
            if not allow_line_arrays or set(change) != {'operation', 'filename', 'old_lines', 'new_lines'}:
                raise SafetyError('Explicit opt-in and exactly operation, filename, old_lines, new_lines required')
            change = {'operation': 'replace_text', 'filename': change['filename'],
                      'old_text': _line_text(change['old_lines'], 'old_lines'),
                      'new_text': _line_text(change['new_lines'], 'new_lines')}
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
            literal = '\\n' in old
            message = f'{name}: old_text exact replacement requires one match; found {count}. '
            if count > 1:
                message += 'Ambiguous replacement; copy a larger unique region. Nothing was applied.'
            elif literal:
                message += ('old_text contains literal backslash+n. JSON "\\n" decodes to a newline; '
                            'JSON "\\\\n" decodes to backslash+n. Use actual newlines: copy decoded source and encode '
                            'the response once; no unescaping or repair is performed.')
            else:
                message += 'Copy the exact decoded source, including indentation and newlines; nothing was applied.'
            hint = _target_context_hint(contents[name], old) if count == 0 else None
            if hint is not None:
                message += (f' Unique boundary-line context at source lines '
                            f'{hint["source_start_line"]}-{hint["source_end_line"]}: '
                            f'{hint["source_empty_lines"]} empty source lines versus '
                            f'{hint["proposed_empty_lines"]} in the target. '
                            'Preserve every empty line; no whitespace normalization is performed.')
            diagnostic = {'code': 'ambiguous_replacement' if count > 1 else 'replacement_not_found',
                'filename': name, 'field': 'old_text', 'match_count': count,
                'literal_backslash_n': literal, 'actual_newline_count': old.count('\n'),
                'message': message}
            if hint is not None:
                diagnostic['context_hint'] = hint
            raise ProposalValidationError(diagnostic)
        result = contents[name].replace(old, new, 1)
        encoded = result.encode('utf-8')
        if len(encoded) > MAX_FILE_BYTES:
            raise SafetyError('Result exceeds the existing file size limit')
        _text(encoded)
        prepared[name] = result
    return prepared


def run_proposals(request, responses, *, allow_line_arrays=False):
    """Data-only mocked response sequence; live adapters are deliberately unsupported.

    Every declared change (even in a rejected batch) consumes an operation slot.
    Malformed envelopes consume one. Oversized batches exhaust the remaining
    slots and write nothing. At most six response documents are accepted as input.
    """
    _line_option(allow_line_arrays)
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
    if allow_line_arrays:
        report.update(protocol='explicit-replacements-v1+lines-v2', allow_line_arrays=True)
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
                changes = envelope(response, allow_line_arrays=allow_line_arrays)
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
                prepared = validate_changes(changes, authorization, contents,
                                            allow_line_arrays=allow_line_arrays)
            except (SafetyError, OSError, UnicodeError, KeyError) as exc:
                event.update(status='rejected', error=str(exc))
                if isinstance(exc, ProposalValidationError):
                    event['diagnostic'] = copy.deepcopy(exc.diagnostic)
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
