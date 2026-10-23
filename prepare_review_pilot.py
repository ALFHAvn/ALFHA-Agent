"""Prepare a fixed first-party pilot. Never contacts a model or executes code."""
import hashlib
import json
from pathlib import Path
import tempfile

from coding_workflow import validate_request
from evaluations.checkpoints import atomic_write, timestamp
from git_checkpoints import _git, _source_snapshot
from multi_file_tasks import MultiFileTask
from proposal_protocol import proposal_messages, proposal_schema

FIXTURES = Path(__file__).resolve().parent / 'pilots/time_report'
FILES = ('duration.py', 'test_duration.py', 'README.md')
DESCRIPTION = (
    'Improve the time-report formatter for nonnegative integer seconds. '
    'format_duration(seconds) returns total minutes, a colon, and exactly two '
    'second digits; minutes never wrap at an hour. Negative integers raise '
    'ValueError. Preserve the signature and the existing test_zero unchanged. '
    'In test_duration.py append test_boundaries containing exactly these assertions '
    'in order: format_duration(1) == "0:01"; format_duration(59) == "0:59"; '
    'format_duration(60) == "1:00"; format_duration(61) == "1:01"; '
    'format_duration(3600) == "60:00"; format_duration(3661) == "61:01". '
    'Then append test_negative using try/except ValueError with an explicit failing '
    'assertion if format_duration(-1) returns normally. No other test code or imports. '
    'Change both Python files only. README.md is read-only context. '
    'Other input types are outside scope. No dependencies, execution, or new files.'
)


def prepare():
    source = Path(tempfile.mkdtemp(prefix='alfha-time-report-pilot-')).resolve()
    _git(source, 'init', '--quiet', '--initial-branch=main', '--template=')
    contents = {}
    for name in FILES:
        data = (FIXTURES / name).read_bytes()
        contents[name] = data.decode('utf-8')
        (source / name).write_bytes(data)
    _git(source, 'add', '--all')
    _git(source, 'commit', '--quiet', '-m', 'First-party time-report pilot baseline')
    request = validate_request({'description': DESCRIPTION, 'source_repository': str(source),
        'authorized_files': {'duration.py': ['read', 'modify'],
                             'test_duration.py': ['read', 'modify'], 'README.md': ['read']},
        'required_changed_files': ['duration.py', 'test_duration.py'],
        'validation_requirements': {'static': True, 'docker_execution': False}})
    before = _source_snapshot(source)
    task = MultiFileTask.prepare(source, list(request['authorized_files']))
    with task:
        inspected = {name: task.read_text(name) for name in FILES}
    if _source_snapshot(source) != before or task.state != 'discarded' or inspected != contents:
        raise RuntimeError('Pilot source/inspection/cleanup verification failed')
    plan = {'schema_version': 1, 'prepared_utc': timestamp(), 'status': 'awaiting_approval',
        'generation_authorized': False, 'candidate_execution_authorized': False,
        'source_application': False, 'maximum_model_requests': 1, 'retries': 0,
        'operation_budget': 6, 'request': request, 'starting_snapshot': before,
        'inspection_discarded': True,
        'fixture_hashes': {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES},
        'payload': {'model': 'qwen3:4b', 'stream': False,
                    'format': proposal_schema(request, allow_line_arrays=True)['oneOf'][1],
                    'messages': proposal_messages(request, contents, allow_line_arrays=True),
                    'options': {'temperature': 0, 'num_ctx': 8192}}}
    # Keep evidence outside the source so it cannot affect source state checks.
    output = Path(tempfile.mkdtemp(prefix='alfha-pilot-plan-')).resolve() / 'plan.json'
    atomic_write(output, plan)
    return output, plan


if __name__ == '__main__':
    output, plan = prepare()
    print(json.dumps({'plan': str(output), 'source': plan['request']['source_repository'],
                      'status': plan['status'], 'generation_requests': 0}, indent=2))
