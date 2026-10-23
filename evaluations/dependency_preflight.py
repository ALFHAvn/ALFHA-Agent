"""Read-only local dependency readiness. Never generates, pulls, or starts services."""
import argparse
import copy
import json
import http.client
import re
import socket
import time

import httpx

from .checkpoints import timestamp
from .docker_transport import (DockerTransport, IsolationError, PINNED_IMAGE,
                               bounded_command, metadata_object, invalid_constant)

TIMEOUT = 3.0
OUTPUT_LIMIT = 1024 * 1024


class DependencyError(RuntimeError):
    def __init__(self, category, message, evidence=None):
        super().__init__(message)
        self.category = category
        self.evidence = evidence


class DeadlineSocket(socket.socket):
    """Apply the same deadline to every header/body read, including drip feeds."""
    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Ollama metadata deadline exceeded')
        return remaining

    def recv_into(self, *args, **kwargs):
        self.settimeout(self.remaining())
        return super().recv_into(*args, **kwargs)

    def sendall(self, *args, **kwargs):
        self.settimeout(self.remaining())
        return super().sendall(*args, **kwargs)


class MetadataConnection(http.client.HTTPConnection):
    def __init__(self, deadline):
        super().__init__('127.0.0.1', 11434, timeout=TIMEOUT)
        self.deadline = deadline

    def connect(self):
        self.sock = DeadlineSocket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.deadline = self.deadline
        self.sock.settimeout(self.sock.remaining())
        self.sock.connect(('127.0.0.1', 11434))


def ollama_metadata(method, path, payload=None):
    if (method, path) not in {('GET', '/api/tags'), ('POST', '/api/show')}:
        raise DependencyError('unauthorized_operation', 'Only read-only model metadata is permitted')
    deadline = time.monotonic() + TIMEOUT
    data = bytearray()
    # Fixed loopback TCP: no DNS, proxy environment, or redirect following.
    connection = MetadataConnection(deadline)
    try:
        connection.request(method, path, body=None if payload is None else json.dumps(payload).encode(),
                           headers={'Content-Type': 'application/json', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        try:
            if response.status != 200:
                raise DependencyError('http_error', f'Ollama metadata HTTP {response.status}',
                                      {'status_code': response.status, 'path': path})
            while True:
                if time.monotonic() > deadline:
                    raise DependencyError('timeout', 'Ollama metadata deadline exceeded')
                chunk = response.read1(min(65536, OUTPUT_LIMIT + 1 - len(data)))
                if not chunk:
                    if response.length not in (None, 0):
                        raise DependencyError('incomplete_metadata', 'Ollama response ended before Content-Length')
                    break
                if len(data) + len(chunk) > OUTPUT_LIMIT:
                    raise DependencyError('output_limit', 'Ollama metadata response exceeds limit')
                data.extend(chunk)
        finally:
            response.close()
    finally:
        connection.close()
    try:
        return json.loads(data, object_pairs_hook=metadata_object, parse_constant=invalid_constant)
    except (ValueError, TypeError) as exc:
        raise DependencyError('malformed_metadata', 'Ollama metadata is not unambiguous JSON',
                              {'response_excerpt': bytes(data[:512]).decode('utf-8', errors='replace')}) from exc


def readonly_docker_command(argv, *, timeout, input_bytes=b'', limit=65536):
    allowed = (['context', 'inspect', 'desktop-linux'], ['info', '--format', '{{json .}}'],
               ['image', 'inspect', PINNED_IMAGE])
    if (len(argv) < 4 or argv[1:3] != ['--context', 'desktop-linux'] or
            argv[3:] not in allowed or input_bytes):
        raise DependencyError('unauthorized_operation', 'Only fixed read-only Docker metadata commands are permitted')
    return bounded_command(argv, timeout=min(timeout, TIMEOUT), limit=min(limit, OUTPUT_LIMIT))


def failed(exc):
    if isinstance(exc, IsolationError):
        return {'status': 'failed', 'category': exc.failure['category'],
                'message': str(exc), 'evidence': copy.deepcopy(exc.failure)}
    category = (exc.category if isinstance(exc, DependencyError) else
                'timeout' if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else
                'unavailable' if isinstance(exc, (OSError, httpx.TransportError)) else 'invalid_evidence')
    return {'status': 'failed', 'category': category, 'message': f'{type(exc).__name__}: {exc}',
            'evidence': getattr(exc, 'evidence', None)}


def check_dependencies(models=('qwen3:4b',), *, metadata=ollama_metadata, docker_factory=None, require_docker=True):
    """Data only; readiness is not authorization or isolation verification.

    Each HTTP request shares a 3-second connect/header/body deadline. Each Docker command has
    a 3-second process timeout plus the transport's bounded pipe teardown.
    No readiness retry, model load, inference, container create or image pull.
    """
    if (not isinstance(models, (tuple, list)) or not 1 <= len(models) <= 3 or
            any(not isinstance(m, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+', m)
                for m in models) or len(set(models)) != len(models)):
        raise ValueError('Require one to three unique explicit local model tags')
    if type(require_docker) is not bool:
        raise ValueError('require_docker must be Boolean')
    report = {'schema_version': 1, 'started_utc': timestamp(), 'ready': False,
              'failure_domain': 'infrastructure', 'read_only': True, 'model_invoked': False,
              'required_models': list(models), 'required_image': PINNED_IMAGE,
              'timeout_seconds_per_operation': TIMEOUT, 'checks': {},
              'isolation_verified': False, 'execution_authorized': False}
    checks = report['checks']
    checks['ollama_models'] = {m: {'status': 'not_checked', 'message': 'Ollama API not ready'} for m in models}
    try:
        tags = metadata('GET', '/api/tags')
        entries = tags.get('models') if isinstance(tags, dict) else None
        if not isinstance(entries, list) or any(not isinstance(m, dict) or
                not isinstance(m.get('model'), str) or not isinstance(m.get('digest'), str) or
                not re.fullmatch(r'[a-f0-9]{64}', m['digest']) for m in entries):
            raise DependencyError('invalid_schema', 'Incomplete Ollama model inventory', tags)
        names = [m['model'] for m in entries]
        if len(names) != len(set(names)):
            raise DependencyError('invalid_schema', 'Duplicate model inventory entries', tags)
        checks['ollama_api'] = {'status': 'passed', 'endpoint': 'http://127.0.0.1:11434', 'evidence': tags}
        for model in models:
            try:
                entry = next((m for m in entries if m['model'] == model), None)
                if entry is None:
                    raise DependencyError('model_missing', f'Required model is not installed: {model}')
                details = metadata('POST', '/api/show', {'model': model})
                capabilities = details.get('capabilities') if isinstance(details, dict) else None
                if (not isinstance(capabilities, list) or 'tools' not in capabilities or
                        any(not isinstance(capability, str) for capability in capabilities) or
                        'completion' not in capabilities or not isinstance(details.get('template'), str) or
                        not details['template'].strip()):
                    raise DependencyError('model_incompatible', 'Tools/completion/template evidence required', details)
                checks['ollama_models'][model] = {'status': 'passed', 'evidence': {
                    'inventory': entry, 'capabilities': capabilities, 'template': details['template'],
                    'parameters': details.get('parameters'), 'details': details.get('details')}}
            except Exception as exc:
                checks['ollama_models'][model] = failed(exc)
    except Exception as exc:
        checks['ollama_api'] = failed(exc)
    if not require_docker:
        checks['docker_engine'] = checks['docker_image'] = {'status': 'not_required',
            'message': 'Static review only; Docker was not contacted and execution is unauthorized'}
        report['required_image'] = None
        report['docker_metadata_audit'] = []
        report['ready'] = (checks['ollama_api']['status'] == 'passed' and
                           all(c['status'] == 'passed' for c in checks['ollama_models'].values()))
        report['failure_domain'] = None if report['ready'] else 'infrastructure'
        report['completed_utc'] = timestamp()
        return report
    transport = None
    checks['docker_image'] = {'status': 'not_checked', 'message': 'Docker engine not ready'}
    try:
        transport = (docker_factory() if docker_factory else
                     DockerTransport(command_runner=readonly_docker_command))
        identity = transport.preflight()
        checks['docker_engine'] = {'status': 'passed', 'evidence': identity}
        checks['docker_image'] = {'status': 'passed', 'evidence': {
            'image': identity['image'], 'image_id': identity['image_id']}}
    except Exception as exc:
        failure = failed(exc)
        operation = exc.failure.get('operation') if isinstance(exc, IsolationError) else None
        if isinstance(operation, list) and operation[:1] == ['image']:
            checks['docker_engine'] = {'status': 'passed', 'message': 'Context and engine checks completed before image check'}
            checks['docker_image'] = failure
        else:
            checks['docker_engine'] = failure
    report['docker_metadata_audit'] = copy.deepcopy(transport.audit) if transport is not None else []
    report['ready'] = (all(checks[k]['status'] == 'passed' for k in ('ollama_api', 'docker_engine', 'docker_image')) and
                       all(c['status'] == 'passed' for c in checks['ollama_models'].values()))
    report['failure_domain'] = None if report['ready'] else 'infrastructure'
    report['completed_utc'] = timestamp()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='append', help='Required explicit installed tag; repeat at most three times')
    parser.add_argument('--verify-docker-inventory', action='store_true',
                        help='Poll engine readiness before one mandatory inventory; grants no execution permission')
    parser.add_argument('--readiness-timeout', type=float, default=20.0)
    args = parser.parse_args(argv)
    readiness = None
    if args.verify_docker_inventory:
        from .docker_readiness import check_docker_readiness
        readiness = check_docker_readiness(readiness_timeout=args.readiness_timeout)
        if not readiness['ready']:
            print(json.dumps({'ready': False, 'failure_domain': 'infrastructure',
                              'docker_readiness': readiness, 'model_invoked': False,
                              'execution_authorized': False, 'isolation_verified': False}, indent=2))
            return 2
    report = check_dependencies(args.model or ['qwen3:4b'])
    if readiness is not None:
        report['docker_readiness'] = readiness
    print(json.dumps(report, indent=2))
    return 0 if report['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
