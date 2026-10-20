"""Data-only benchmark persistence/inspection. Never creates execution permits."""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, report):
    """Old checkpoint survives serialization/write/replace failure.

    fsync flushes file contents; directory durability across power loss remains
    filesystem-dependent, particularly on Windows. A leftover temp is never read.
    """
    path = Path(path)
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def process_identity(pid=None):
    """PID plus creation identity prevents PID reuse from implying a live owner."""
    pid = os.getpid() if pid is None else pid
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return {'pid': pid, 'state': 'dead' if ctypes.get_last_error() == 87 else 'unknown'}
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
            if not kernel.GetProcessTimes(handle, *map(ctypes.byref, (created, exited, system, user))):
                return {'pid': pid, 'state': 'unknown'}
            return {'pid': pid, 'state': 'observed',
                    'creation_id': str((created.dwHighDateTime << 32) | created.dwLowDateTime)}
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
    try:
        # Linux start ticks, after the parenthesized process name.
        value = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
        return {'pid': pid, 'state': 'observed', 'creation_id': value}
    except FileNotFoundError:
        return {'pid': pid, 'state': 'dead'}
    except (OSError, IndexError):
        return {'pid': pid, 'state': 'unknown'}


def task_states(report, tasks):
    rows = {row['task']: row for row in report['results']}
    states = []
    for task in tasks:
        row = rows.get(task['id'])
        completed = bool(row and row.get('status') == 'completed' and isinstance(row.get('worker'), dict))
        state = ('completed' if completed else 'interrupted' if report['status'] in ('incomplete', 'interrupted')
                 else 'running') if row else 'pending'
        states.append({'task': task['id'], 'state': state,
                       'phase': row.get('status') if row else None,
                       'telemetry_complete': completed,
                       'vectors_planned': len(task['tests'])})
    return states


def inspect_checkpoint(path, *, probe=process_identity):
    """Return a separate observation, never mutate the evidence or resume a run.

    Even a matching live process is only evidence about liveness, not authority.
    Missing/malformed data is never interpreted as a successful outcome.
    """
    try:
        original = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(original, dict) or not isinstance(original.get('results'), list):
            raise ValueError('Missing results list')
        for key in ('process', 'authorization', 'summary'):
            if key in original and not isinstance(original[key], dict):
                raise ValueError('Malformed ' + key)
        for key in ('tasks_planned', 'vectors_planned'):
            if key in original and (type(original[key]) is not int or original[key] < 0):
                raise ValueError('Malformed ' + key)
        if 'unattempted_tasks' in original and not isinstance(original['unattempted_tasks'], list):
            raise ValueError('Malformed unattempted tasks')
        if not isinstance(original.get('task_states', []), list) or any(not isinstance(s, dict) for s in original.get('task_states', [])):
            raise ValueError('Malformed task states')
        rows = original['results']
        names = [r['task'] for r in rows]
        if any(not isinstance(n, str) for n in names) or len(names) != len(set(names)):
            raise ValueError('Invalid or duplicate tasks')
        for row in rows:
            if 'worker' in row:
                grade = row['worker']
                if (not isinstance(grade, dict) or type(grade.get('passed')) is not bool or
                        any(type(grade.get(k)) is not int or grade[k] < 0
                            for k in ('planned', 'executed', 'passed_count')) or
                        not grade['passed_count'] <= grade['executed'] <= grade['planned']):
                    raise ValueError('Malformed grading outcome')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'invalid_checkpoint', 'error': f'{type(exc).__name__}: {exc}',
                'execution_authorized': False, 'resumable': False}
    result = copy.deepcopy(original)
    owner = original.get('process', {})
    try:
        observed = probe(owner['pid']) if type(owner.get('pid')) is int and 0 < owner['pid'] <= 0xffffffff else {'state': 'unknown'}
    except (OSError, ValueError, OverflowError):
        observed = {'state': 'unknown'}
    same = bool(owner.get('creation_id') and observed.get('creation_id') == owner['creation_id'])
    liveness = 'matching_process' if same else 'terminated_or_reused' if observed.get('state') == 'dead' or observed.get('creation_id') else 'unknown'
    active = original.get('status') in ('running', 'preflight') or original.get('authorization', {}).get('state') == 'active'
    result['inspection'] = {'observed_utc': timestamp(), 'owner_liveness': liveness,
                            'execution_authorized': False, 'resumable': False,
                            'source_status': original.get('status'),
                            'effective_authorization': 'expired_by_process_termination' if active and liveness == 'terminated_or_reused' else 'not_granted_by_inspection'}
    if active and not same:
        result['status'] = 'interrupted'
    completed, progress = [], []
    for row in result['results']:
        if row.get('status') == 'completed' and isinstance(row.get('worker'), dict):
            completed.append(row)
        else:
            progress.append(row)
    result['completed_results'] = completed
    result['in_progress_telemetry'] = progress
    result['outcomes_unknown'] = [r['task'] for r in progress]
    result['source_summary'] = result.get('summary', {})
    result['summary'] = dict(result['source_summary'])
    result['summary'].update(tasks_graded=len(completed),
                             tasks_attempted=len(rows),
                             tasks_passed=sum(r['worker']['passed'] for r in completed),
                             vectors_executed=sum(r['worker']['executed'] for r in completed),
                             vectors_passed=sum(r['worker']['passed_count'] for r in completed))
    if 'vectors_planned' in result:
        if result['vectors_planned'] < result['summary']['vectors_executed']:
            return {'status': 'invalid_checkpoint', 'error': 'Recorded execution exceeds planned vectors',
                    'execution_authorized': False, 'resumable': False}
        result['summary']['vectors_without_recorded_execution'] = result['vectors_planned'] - result['summary']['vectors_executed']
        result['summary']['vectors_not_run'] = result['summary']['vectors_without_recorded_execution']
    if active or progress or len(completed) != result.get('tasks_planned'):
        result['summary']['overall_task_success_rate'] = None
    # Derive states from actual outcomes, never trust a saved "completed" label
    # that has no grading outcome. Legacy reports have no task_states ledger.
    completed_names = {r['task'] for r in completed}
    result['task_states'] = [
        {'task': row['task'], 'state': 'completed' if row['task'] in completed_names
         else 'running' if same and active else 'interrupted', 'phase': row.get('status')}
        for row in result['results']]
    for state in original.get('task_states', original.get('unattempted_tasks', [])):
        if isinstance(state, dict) and state.get('task') not in names:
            result['task_states'].append({'task': state.get('task'), 'state': 'pending', 'phase': None})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    print(json.dumps(inspect_checkpoint(args.path), indent=2))


if __name__ == '__main__':
    main()
