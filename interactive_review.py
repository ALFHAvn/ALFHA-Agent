"""One-response structured coding, isolated and review-only. No execution/apply API."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import uuid

from ollama import Client
from coding_workflow import MODEL, validate_request
from evaluations.checkpoints import atomic_write, timestamp
from evaluations.dependency_preflight import check_dependencies
from git_checkpoints import SafetyError, _source_snapshot
from multi_file_tasks import MultiFileTask
from proposal_protocol import (MAX_OPERATIONS, MAX_RESPONSE_BYTES, strict_json,
                               proposal_schema, proposal_messages, run_proposals)
from resource_readiness import check_readiness, workload_guard


def run_review(request, *, chat_fn=None):
    request = validate_request(request)
    schema = proposal_schema(request, allow_line_arrays=True)['oneOf'][1]
    if any('read' not in ops for ops in request['authorized_files'].values()):
        raise SafetyError('Review files require explicit read permission')
    source = Path(request['source_repository']).absolute()
    evidence = Path(tempfile.mkdtemp(prefix='alfha-review-report-')).resolve()
    if evidence.is_relative_to(source.resolve(strict=True)):
        evidence.rmdir(); raise SafetyError('Report must be outside the source repository')
    output = evidence / 'report.json'
    report = {'schema_version': 1, 'run_id': uuid.uuid4().hex, 'started_utc': timestamp(),
              'request': request, 'model': MODEL, 'protocol': 'replace-lines-v2-only',
              'status': 'preflight', 'model_requests': 0, 'budget': MAX_OPERATIONS,
              'budget_used': 0, 'accepted_changes': [], 'rejected_changes': [],
              'errors': [], 'incomplete_work': [], 'combined_diff': '', 'validation': None,
              'starting_commit': None, 'ready_for_human_review': False,
              'source_application': False, 'candidate_execution': 'disabled',
              'functional_correctness': 'not_tested', 'workspace_discarded': True,
              'report_path': str(output)}
    before, inspection = None, None
    def save():
        report['checkpoint_utc'] = timestamp(); atomic_write(output, report)
    save()
    try:
        with workload_guard('generation'):
            report['resource_preflight'] = check_readiness('generation'); save()
            if not report['resource_preflight']['ready']:
                report['status'] = 'resource_rejected'
                report['errors'].extend(report['resource_preflight']['errors']); return report
            report['dependency_preflight'] = check_dependencies([MODEL], require_docker=False); save()
            if not report['dependency_preflight']['ready']:
                report['status'] = 'dependency_rejected'
                report['errors'].append('Ollama API/model unavailable; no generation attempted'); return report
            # Pass the original path into the established root/link guard before
            # fingerprinting or reading repository content. Resolving first would
            # erase evidence of a user-supplied junction/symlink root.
            inspection = MultiFileTask.prepare(source, list(request['authorized_files']))
            before = copy.deepcopy(inspection.starting_snapshot)
            source = inspection.source
            report['workspace_discarded'] = False
            report['inspection_workspace'] = str(inspection.workspace)
            with inspection:
                report['starting_commit'] = inspection.starting_commit
                contents = {name: inspection.read_text(name) for name in request['authorized_files']}
                report['inspected_files'] = copy.deepcopy(contents)
            report['workspace_discarded'] = True
            if _source_snapshot(source) != before:
                raise SafetyError('Source changed during inspection; no generation authorized')
            messages = proposal_messages(request, contents, allow_line_arrays=True)
            payload = {'model': MODEL, 'stream': False, 'format': schema, 'messages': messages,
                       'options': {'temperature': 0, 'num_ctx': 8192}}
            if len(json.dumps(payload, ensure_ascii=True).encode()) > MAX_RESPONSE_BYTES:
                raise SafetyError('Authorized context exceeds the 65536-byte review request limit')
            report['payload'] = payload
            report['resource_before_generation'] = check_readiness('generation'); save()
            if not report['resource_before_generation']['ready']:
                report['status'] = 'resource_rejected'
                report['errors'].extend(report['resource_before_generation']['errors']); return report
            if _source_snapshot(source) != before:
                raise SafetyError('Source changed before generation')
            chat = chat_fn if chat_fn is not None else Client(host='http://127.0.0.1:11434',
                timeout=180, trust_env=False, follow_redirects=False).chat
            report.update(status='generating', model_requests=1); save()
            start = time.monotonic()
            try:
                response = chat(**copy.deepcopy(payload))
            finally:
                report['response_seconds'] = time.monotonic() - start
            report['raw_response'] = response.model_dump(mode='json'); save()
            text = response.message.content or ''
            report['raw_content'] = text
            report['resource_after_response'] = check_readiness('regression'); save()
            if not report['resource_after_response']['ready']:
                report['status'] = 'resource_rejected'
                report['errors'].extend(report['resource_after_response']['errors']); return report
            if response.message.tool_calls:
                report['budget_used'] = 1
                raise SafetyError('Native tool calls are forbidden in the structured review workflow')
            # Checking version here is necessary: opt-in parser also supports v1,
            # but this interactive mode authorizes only one version 2 document.
            report['budget_used'] = 1
            document = strict_json(text)
            if (not isinstance(document, dict) or type(document.get('version')) is not int or
                    document['version'] != 2):
                raise SafetyError('Require version=2 replace_lines; legacy fallback is not authorized')
            if isinstance(document.get('changes'), list):
                report['requested_operations'] = len(document['changes'])
            if _source_snapshot(source) != before:
                raise SafetyError('Source changed during generation; proposal was not staged')
            report.update(staging_attempted=True, workspace_discarded=False); save()
            staged = run_proposals(request, [text], allow_line_arrays=True)
            report['staging'] = staged
            report.update(status=staged['status'], budget_used=staged['budget_used'],
                accepted_changes=staged['accepted_changes'],
                rejected_changes=[e for e in staged['events'] if e['status'] == 'rejected'],
                combined_diff=staged.get('review', {}).get('diff', ''), validation=staged.get('validation'),
                final_files=staged.get('final_files', {}), workspace_discarded=staged['workspace_discarded'],
                ready_for_human_review=staged['ready_for_human_review'])
            report['errors'].extend(staged['errors'])
            report['missing_required_changes'] = staged.get('missing_required_changes', [])
            report['candidate_hashes'] = {name: hashlib.sha256(text.encode()).hexdigest()
                                          for name, text in report['final_files'].items()}
    except KeyboardInterrupt:
        report['status'] = 'interrupted'; report['errors'].append('Interrupted; no automatic retry or resume')
    except Exception as exc:
        report['status'] = 'rejected' if isinstance(exc, SafetyError) else 'failed'
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        if inspection is not None and not report.get('staging_attempted'):
            report['workspace_discarded'] = inspection.state == 'discarded'
        if before is not None:
            try:
                report['source_unchanged'] = _source_snapshot(source) == before
            except Exception as exc:
                report['source_unchanged'] = False; report['errors'].append('Source verification unavailable: ' + str(exc))
            if not report['source_unchanged']:
                report['status'] = 'stale'; report['ready_for_human_review'] = False
        if report['errors'] or report['rejected_changes'] or not report['workspace_discarded']:
            report['ready_for_human_review'] = False
        if not report['ready_for_human_review']:
            report['incomplete_work'].append('Request incomplete or rejected; inspect errors, missing changes and validation')
        report['completed_utc'] = timestamp(); save()
    return report


def display_review(report, emit=print):
    emit('Review only: original files are never updated; functional tests did not run.')
    emit(f"Status: {report['status']}; ready for human review: {report['ready_for_human_review']}")
    emit(f"Operations: {report['budget_used']}/{report['budget']}")
    emit(report['combined_diff'] or '(No staged diff)')
    for item in report['rejected_changes']:
        emit('Rejected: ' + item.get('error', 'Invalid proposal'))
    for item in report['errors'] + report['incomplete_work']:
        emit(item)
    emit('Static validation: ' + json.dumps(report['validation']))
    emit('Missing required changes: ' + json.dumps(report.get('missing_required_changes', [])))
    emit('Staging discarded: ' + str(report['workspace_discarded']))
    emit('Preserved report: ' + report['report_path'])


def main(input_fn=input, emit=print):
    """Explicit human opt-in; a CLI invocation grants no candidate execution."""
    emit('ALFHA structured review: existing tracked text files only; no source application.')
    try:
        source = input_fn('Absolute Git repository root: ').strip()
        description = input_fn('Coding request: ').strip()
        files = {}
        for prompt, ops in (('Files to read AND modify', ['read', 'modify']),
                            ('Additional read-only files', ['read'])):
            emit(prompt + ' — one exact relative path per line; blank ends selection:')
            while True:
                name = input_fn('Path: ').strip()
                if not name: break
                if name in files: raise SafetyError('Duplicate file selection')
                files[name] = list(ops)
        request = {'description': description, 'source_repository': source,
                   'authorized_files': files,
                   'validation_requirements': {'static': True, 'docker_execution': False}}
        validate_request(request); proposal_schema(request, allow_line_arrays=True)
        emit('Exact file authorization: ' + json.dumps(files))
        if input_fn('Generate exactly one local review proposal? Type yes: ').strip() != 'yes':
            emit('Cancelled; no generation or staging.'); return 0
        report = run_review(request); display_review(report, emit)
        return 0 if report['ready_for_human_review'] else 2
    except (SafetyError, ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
        emit('Review stopped: ' + str(exc)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
