"""Explicit single-pass live benchmark; candidate execution is Docker-only.

The legacy static CLI and generic execution adapter remain disabled. This entry
point grants no tools to the model: it grades the final candidate independently,
after the unchanged six-call controller finishes, without functional feedback.
"""
import hashlib
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import uuid

from . import evaluate_functional as controller
from .execution_backend import PROBES, DockerExecutionBackend
from .docker_transport import PINNED_IMAGE
from .functional_harness import FunctionalHarness
from .functional_validation import CASE_ROOT, load_tasks
from .checkpoints import atomic_write, process_identity, task_states

# Step 29A: the historical verification failure is unresolved. A separate
# reviewed milestone is required before any live model evaluation resumes.
LIVE_EVALUATION_ENABLED = False

APPROVED_TASK_SCOPE_SHA256 = '452161a74014da7887051b9167c982885fe249047619abba3fe0196eb1cafa8e'
APPROVED_FIXTURES_SHA256 = 'eafa2f3f564372edf24947f71d019bf981c94cabbaafc7dd7263613ee59be5bb'


def fixture_hash():
    digest = hashlib.sha256()
    for path in sorted(CASE_ROOT.iterdir()):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class OneRunAuthorization:
    """Operator-issued, in-memory permission; not a general execution capability.

    Creation is allowed only after human approval. No persisted permit, environment
    variable or saved security report can create or renew this authorization.
    """
    def __init__(self):
        self.run_id = uuid.uuid4().hex
        self.state = 'unclaimed'
        self._harness = None
        self._hashes = protected_hashes()
        self._task_index = 0
        self._phase = 'model'

    def validate(self, harness):
        scope = hashlib.sha256(json.dumps(load_tasks(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (scope != APPROVED_TASK_SCOPE_SHA256 or fixture_hash() != APPROVED_FIXTURES_SHA256 or
                controller.syntax.MAX_CALLS != 6 or
                controller.syntax.alfha.MODEL != 'qwen3:4b' or protected_hashes() != self._hashes or
                not isinstance(harness.backend, DockerExecutionBackend) or harness.backend.image != PINNED_IMAGE):
            raise RuntimeError('One-run authorization scope/policy binding mismatch')

    def claim(self, harness):
        if self.state != 'unclaimed':
            raise RuntimeError('One-run authorization is already consumed or expired')
        self.state = 'active'
        self._harness = harness
        self.validate(harness)

    def task(self, harness, task_id, phase):
        if self.state != 'active' or harness is not self._harness:
            raise RuntimeError('No active authorization for this harness')
        self.validate(harness)
        tasks = load_tasks()
        if self._task_index >= len(tasks) or tasks[self._task_index]['id'] != task_id or phase != self._phase:
            raise RuntimeError('Unauthorized task, repetition or execution phase')
        if phase == 'model':
            self._phase = 'grade'
        else:
            self._task_index += 1
            self._phase = 'model'

    def expire(self):
        self.state = 'expired'

    def record(self):
        return {'run_id': self.run_id, 'state': self.state, 'persistent': False,
                'task_scope_sha256': APPROVED_TASK_SCOPE_SHA256, 'image': PINNED_IMAGE,
                'fixtures_sha256': APPROVED_FIXTURES_SHA256,
                'tasks_limit': 5, 'vectors_limit': 29, 'tool_calls_per_task': 6,
                'expires': 'benchmark completion, abort or process termination'}


def now():
    return datetime.now(timezone.utc).isoformat()


def security_ready(report):
    checks = report.get('security_checks', {})
    return (report.get('verified') is True and set(checks) == set(PROBES) and
            all(c.get('status') == 'passed' and c.get('evidence') for c in checks.values()))


def protected_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = [root / 'main.py', root / 'evaluations/evaluate_agent.py', Path(__file__),
             root / 'evaluations/verify_docker_isolation.py']
    paths += [root / 'evaluations' / name for name in (
        'evaluate_functional.py', 'functional_validation.py', 'functional_harness.py',
        'functional_worker.py', 'execution_backend.py', 'docker_transport.py',
        'compilation_worker.py', 'tool_feedback.py', 'checkpoints.py')]
    paths += sorted(p for p in CASE_ROOT.rglob('*') if p.is_file())
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def summarize(report):
    rows = report['results']
    grades = [r['worker'] for r in rows if 'worker' in r]
    complete = report['status'] == 'completed' and len(grades) == report['tasks_planned']
    return {
        'tasks_attempted': len(rows), 'tasks_graded': len(grades),
        'tasks_with_unknown_outcomes': [r['task'] for r in rows if 'worker' not in r],
        'telemetry_scope': 'completed controller returns only; partial progress is separate and never presumed zero',
        'tasks_passed': sum(g['passed'] is True for g in grades),
        'overall_task_success_rate': (sum(g['passed'] is True for g in grades) / report['tasks_planned']) if complete else None,
        'vectors_planned': report['vectors_planned'],
        'vectors_executed': sum(g.get('executed', 0) for g in grades),
        'vectors_passed': sum(g.get('passed_count', 0) for g in grades),
        'vectors_not_run': report['vectors_planned'] - sum(g.get('executed', 0) for g in grades),
        'model_tool_calls': sum(r.get('tool_calls', 0) for r in rows),
        'average_model_tool_calls': sum(r.get('tool_calls', 0) for r in rows) / len(rows) if rows else None,
        **{key: sum(r.get(key, 0) for r in rows) for key in (
            'model_requests', 'native_calls_requested', 'native_calls_dispatched',
            'recovered_json_calls', 'invalid_dispatched_calls', 'invalid_json_proposals',
            'retry_prompts', 'successful_edits')},
        'agent_syntax_verified': sum(r.get('verified_by_agent') is True for r in rows),
        'controller_syntax_valid': sum(r.get('syntax_valid') is True for r in rows),
        'grading_status_counts': {status: sum(g['status'] == status for g in grades)
                                 for status in sorted({g['status'] for g in grades})},
    }


def verify_boundary(harness, report, stage, task):
    """Retain the actual failure reason, rather than only a generic stop message."""
    verification = harness.backend.verify()
    report['verification_boundaries'].append({
        'timestamp_utc': now(), 'stage': stage, 'task': task,
        'accepted': bool(security_ready(verification)),
        'verification': verification,
    })
    return security_ready(verification)


def run_benchmark(*, chat_fn, harness, model_metadata, save=lambda report: None, authorization=None):
    tasks = load_tasks()
    report = {
        'schema_version': 1, 'mode': 'live_functional_benchmark', 'started_utc': now(),
        'model': controller.syntax.alfha.MODEL, 'model_metadata': model_metadata,
        'model_options': 'unchanged controller defaults', 'max_tool_calls_per_task': controller.syntax.MAX_CALLS,
        'attempts_per_task': 1, 'tasks_planned': len(tasks),
        'vectors_planned': sum(len(t['tests']) for t in tasks), 'results': [],
        'status': 'preflight', 'security_evidence': None, 'error': None,
        'verification_boundaries': [],
        'grading': 'independent host grader; expected outcomes never sent to candidate; no feedback or task retries',
        'protected_files_before': protected_hashes(),
        'run_id': authorization.run_id if isinstance(authorization, OneRunAuthorization) else uuid.uuid4().hex,
        'process': process_identity(), 'checkpoint_sequence': 0,
    }

    def checkpoint():
        report['checkpoint_sequence'] += 1
        report['checkpoint_utc'] = now()
        report['task_states'] = task_states(report, tasks)
        report['completed_results'] = [r for r in report['results'] if r.get('status') == 'completed' and 'worker' in r]
        report['in_progress_telemetry'] = [r for r in report['results'] if r not in report['completed_results']]
        report['telemetry_complete'] = not report['in_progress_telemetry']
        report['authorization'] = authorization.record() if isinstance(authorization, OneRunAuthorization) else {'state': 'not_granted'}
        report['summary'] = summarize(report)
        attempted = {r['task'] for r in report['results']}
        report['unattempted_tasks'] = [{'task': t['id'], 'status': 'not_run',
                                      'vectors_planned': len(t['tests'])}
                                     for t in tasks if t['id'] not in attempted]
        save(report)

    try:
        checkpoint()
        if not isinstance(authorization, OneRunAuthorization):
            raise RuntimeError('Live evaluation disabled pending review of the unresolved Step 29 verification failure')
        authorization.claim(harness)
        print('Running mandatory Docker isolation probes...', flush=True)
        report['security_evidence'] = harness.prepare()
        checkpoint()
        if not security_ready(report['security_evidence']):
            raise RuntimeError('Mandatory runtime isolation checks did not pass')
        report['status'] = 'running'
        for task in tasks:
            authorization.task(harness, task['id'], 'model')
            if protected_hashes() != report['protected_files_before']:
                raise RuntimeError('Protected implementation or fixture changed')
            if not verify_boundary(harness, report, 'before_model', task['id']):
                raise RuntimeError('Current execution identity is no longer verified')
            # Persist an in-progress record BEFORE invoking the model. Interrupted
            # attempts are visible and are never automatically resumed or retried.
            row = {'task': task['id'], 'attempt': 1, 'status': 'generating', 'started_utc': now()}
            report['results'].append(row)
            checkpoint()
            print(f"Model task: {task['id']} (one attempt, six-call budget)", flush=True)
            started = time.monotonic()
            def progress(snapshot):
                row['progress'] = snapshot
                checkpoint()

            generated = controller.one_functional_case(task['id'], chat_fn=chat_fn, progress=progress)
            row.update(generated)
            row.update(mode='live_functional_benchmark', status='grading', model_invoked=row['model_requests'] > 0)
            checkpoint()
            if row['tool_calls'] > controller.syntax.MAX_CALLS:
                raise RuntimeError('Controller exceeded tool-call budget')
            if row.get('error'):
                raise RuntimeError('Controller error; no grading/retry: ' + row['error'])
            authorization.task(harness, task['id'], 'grade')
            if not verify_boundary(harness, report, 'before_grading', task['id']):
                raise RuntimeError('Execution verification lost before grading')
            # Uses the existing protocol unchanged. This API itself never calls a
            # model; its nested model_invoked=False describes the grader only.
            graded = controller.grade_candidate_offline(task['id'], row['candidate_source'], harness)
            for key in ('worker', 'functional_tests', 'requested_change_confirmed', 'requested_change_status', 'verification_stages'):
                if key not in graded:
                    continue
                row[key] = graded[key]
            row['passed'] = graded['worker']['passed'] is True
            row.update(status='completed', duration_seconds=time.monotonic() - started, completed_utc=now())
            checkpoint()
            grade = row['worker']
            print(f"Result: {task['id']}: {grade['status']}; {grade['passed_count']}/{grade['planned']} vectors; {row['tool_calls']} calls", flush=True)
            if grade['status'] in ('blocked', 'execution_error', 'malformed_result', 'unexpected_output', 'output_limit',
                                   'runtime_error', 'result_error', 'timeout'):
                raise RuntimeError(f"Execution/grading failure: {task['id']}: {grade['status']}")
            if not verify_boundary(harness, report, 'after_grading', task['id']):
                raise RuntimeError('Execution verification lost after grading')
        report['status'] = 'completed'
    except Exception as exc:
        report.update(status='incomplete', error=f'{type(exc).__name__}: {exc}')
    except KeyboardInterrupt:
        report.update(status='interrupted', error='KeyboardInterrupt; attempt will not be resumed')
    finally:
        if isinstance(authorization, OneRunAuthorization):
            authorization.expire()
        report['protected_files_after'] = protected_hashes()
        report['protected_files_unchanged'] = report['protected_files_before'] == report['protected_files_after']
        if not report['protected_files_unchanged']:
            report.update(status='incomplete', error='Protected implementation or fixture changed')
        report['completed_utc'] = now()
        checkpoint()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-once', action='store_true',
                        help='After explicit human approval only: one fresh five-task/29-vector Docker benchmark')
    args = parser.parse_args(argv)
    if not args.authorize_once:
        print('BLOCKED: live evaluation disabled pending a separate isolation-verification review.', flush=True)
        return 2
    runs = controller.syntax.RUNS
    runs.mkdir(parents=True, exist_ok=True)
    output = runs / ('functional_live_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')

    def save(report):
        atomic_write(output, report)

    from .dependency_preflight import check_dependencies
    dependency_evidence = check_dependencies([controller.syntax.alfha.MODEL])
    if dependency_evidence['ready'] is not True:
        save({'status': 'preflight_failed', 'model_invoked': False, 'model_requests': 0,
              'failure_domain': 'infrastructure', 'dependency_preflight': dependency_evidence,
              'error': 'Required dependency unavailable; no live attempt started',
              'authorization': {'state': 'not_granted'}})
        print(f'Dependency preflight failed; report: {output}', flush=True)
        return 2
    try:
        import ollama
        # No inherited remote OLLAMA_HOST, downloads, or automatic service start.
        client = ollama.Client(host='http://127.0.0.1:11434')
        metadata = dict(dependency_evidence['checks']['ollama_models'][controller.syntax.alfha.MODEL]['evidence']['inventory'])
        metadata['endpoint'] = 'http://127.0.0.1:11434'
        metadata['dependency_preflight'] = dependency_evidence
    except Exception as exc:
        save({'status': 'preflight_failed', 'model_invoked': False, 'failure_domain': 'infrastructure',
              'dependency_preflight': dependency_evidence, 'error': f'{type(exc).__name__}: {exc}'})
        print(f'Model preflight failed; report: {output}', flush=True)
        return 2
    report = run_benchmark(chat_fn=client.chat, harness=FunctionalHarness(), model_metadata=metadata, save=save,
                           authorization=OneRunAuthorization())
    print(json.dumps(report['summary'], indent=2), flush=True)
    print(f'Report: {output}', flush=True)
    if report['error']:
        print(report['error'], flush=True)
    return 0 if report['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
