"""Repeat the unchanged Step 25 evaluation; retain raw model responses and metrics."""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    from .evaluate_agent import CASES, RUNS, MAX_CALLS, alfha, one_case, sha256, parse_proposal, validate_call
except ImportError:
    from evaluate_agent import CASES, RUNS, MAX_CALLS, alfha, one_case, sha256, parse_proposal, validate_call


def summarize(results):
    def stats(rows):
        total = len(rows)
        passed = sum(r['passed'] for r in rows)
        return {
            'attempts': total, 'passed': passed,
            'success_rate': passed / total if total else None,
            'average_model_tool_calls': sum(r['tool_calls'] for r in rows) / total if total else None,
            'average_native_calls_dispatched': sum(r['native_calls_dispatched'] for r in rows) / total if total else None,
            'average_native_calls_requested': sum(r['native_calls_requested'] for r in rows) / total if total else None,
            'native_calls_dispatched': sum(r['native_calls_dispatched'] for r in rows),
            'recovered_json_calls': sum(r['recovered_json_calls'] for r in rows),
            'agent_verified': sum(r['verified_by_agent'] for r in rows),
            'controller_verified': sum(r['verified_by_controller'] for r in rows),
            'successful_edits': sum(r['successful_edits'] for r in rows),
            'retry_prompts': sum(r['retry_prompts'] for r in rows),
            'invalid_dispatched_calls': sum(r['invalid_dispatched_calls'] for r in rows),
            'invalid_json_proposals': sum(r['invalid_json_proposals'] for r in rows),
        }
    return {'overall': stats(results), 'per_case': {
        name: stats([r for r in results if r['case'] == name])
        for name in sorted({r['case'] for r in results})}}


def proposal_observations(responses, filename, initially_valid):
    """Reporting only: inspect all responses, even after recovery is exhausted."""
    proposals = []
    for index, response in enumerate(responses):
        message = response['message']
        text = message.get('content') or ''
        if not message.get('tool_calls') and any(token in text for token in (
                '"name"', '"arguments"', '"filename"', '"old_text"', '"new_text"', '```json')):
            try:
                proposal = parse_proposal(text)
                reason = validate_call(proposal['name'], proposal['arguments'], filename, initially_valid)
            except (ValueError, TypeError) as exc:
                reason = str(exc)
            proposals.append({'response_index': index, 'validation_error': reason})
    return proposals


def measured_case(case):
    responses, retry_prompts = [], set()
    requests = 0

    def observed_chat(**kwargs):
        nonlocal requests
        requests += 1
        for index, message in enumerate(kwargs['messages']):
            if isinstance(message, dict) and message.get('role') == 'system' and index > 0:
                retry_prompts.add(index)
        response = alfha.chat(**kwargs)
        responses.append(response.model_dump(mode='json'))
        return response

    start = time.monotonic()
    result = one_case(case, chat_fn=observed_chat)
    proposals = proposal_observations(responses, case.name, result['initial_syntax_valid'])
    result.update({
        'duration_seconds': time.monotonic() - start,
        'model_responses': responses, 'model_requests': requests,
        'json_proposal_observations': proposals,
        'invalid_json_proposals': sum(p['validation_error'] is not None for p in proposals),
        'retry_prompts': len(retry_prompts),
        'native_calls_requested': sum(len(r['message'].get('tool_calls') or []) for r in responses),
        'native_calls_dispatched': sum(c['origin'] == 'tool_interface' for c in result['trace']),
        'recovered_json_calls': sum(c['origin'] == 'json_recovery' for c in result['trace']),
        'invalid_dispatched_calls': sum(c['result'].startswith('Error:') for c in result['trace']),
        'rejected_recovery_attempts': sum(not r['accepted'] for r in result['recoveries']),
    })
    return result


def main():
    cases = sorted(CASES.glob('*.py'))
    if len(cases) != 3 or MAX_CALLS != 6:
        raise SystemExit('Expected existing three-case suite and six-call budget')
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = RUNS / f'reliability_{stamp}.json'
    report = {
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'model': alfha.MODEL, 'repetitions': 5, 'max_calls_per_case': MAX_CALLS,
        'case_sha256': {c.name: sha256(c) for c in cases},
        'metric_notes': {
            'model_tool_calls': 'Dispatched native calls plus parsed JSON recovery calls; same six-call budget as Step 25. Rejected batches are requested, not dispatched.',
            'retry_prompts': 'Additional system prompts actually sent to the model; no transport retries added.',
            'rejected_recovery_attempts': 'Includes ordinary prose rejected by the existing JSON parser; inspect raw responses to distinguish prose from invalid JSON proposals.',
        },
        'results': [],
    }
    for repetition in range(1, 6):
        for case in cases:
            print(f'Run {repetition}/5: {case.name}', flush=True)
            result = measured_case(case)
            result['repetition'] = repetition
            report['results'].append(result)
            report['summary'] = summarize(report['results'])
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f"  {'PASS' if result['passed'] else 'FAIL'} calls={result['tool_calls']} error={result['error']}", flush=True)
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print(f'Report: {output}')


if __name__ == '__main__':
    main()
