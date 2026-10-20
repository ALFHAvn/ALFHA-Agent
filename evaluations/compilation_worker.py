"""Trusted container-only compilation diagnostic. Candidate code is never invoked."""
import json
import os
import sys


def compilation_main(request_json):
    if sys.platform != 'linux' or os.getuid() != 65534 or not os.path.exists('/.dockerenv'):
        raise RuntimeError('Compilation requires the restricted Linux container')
    request = json.loads(request_json)
    if (set(request) != {'version', 'request_id', 'task_id', 'source'} or request['version'] != 1 or
            type(request['source']) is not str or len(request['source'].encode('utf-8')) > 100000):
        raise ValueError('Invalid compilation request')
    result = {'kind': 'compilation_result', 'version': 1, 'request_id': request['request_id'],
              'task_id': request['task_id'], 'status': 'passed', 'error': None}
    try:
        compile(request['source'], '<candidate>', 'exec')
    except BaseException as exc:
        result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc)[:512])
    sys.stdout.write(json.dumps(result, allow_nan=False) + '\n')
