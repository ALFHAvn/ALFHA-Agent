"""Bounded evaluation-only diagnostics; never coerce arguments or edit source."""
import json

SCHEMAS = {'read_workspace_file': ('filename',), 'check_python_syntax': ('filename',),
           'edit_workspace_file': ('filename', 'old_text', 'new_text')}


def argument_feedback(name, args, original_error):
    if not isinstance(name, str) or name not in SCHEMAS or not isinstance(args, dict):
        return original_error
    required = SCHEMAS[name]
    missing = [k for k in required if k not in args]
    extra = [json.dumps(str(k)[:60]) for k in args if k not in required][:6]
    wrong = [k for k in required if k in args and not isinstance(args[k], str)]
    details = []
    if missing:
        details.append('Missing: ' + ', '.join(missing))
    if extra:
        details.append('Unexpected: ' + ', '.join(extra))
    if wrong:
        details.append('Must be strings: ' + ', '.join(wrong))
    if details:
        return 'Error: Invalid tool arguments. ' + '; '.join(details) + '. Required string fields: ' + ', '.join(required) + '. No action performed.'
    return original_error


def edit_feedback(result, args, unsuccessful):
    if result == 'Error: Text not found. File unchanged.':
        result += ' old_text must match the file exactly; copy text from the authorized file.'
        if r'\n' in args['old_text'] or r'\n' in args['new_text']:
            result += ' Literal backslash+n detected; this is not an actual newline. Do not double-escape JSON newlines. No automatic conversion was made.'
    elif result == 'Error: Multiple matches found. File unchanged.':
        result += ' Include more surrounding text in old_text to identify exactly one occurrence.'
    if unsuccessful > 1:
        result += f' Consecutive unsuccessful edits: {unsuccessful}; correct the arguments or exact match before trying again.'
    return result


def validation_feedback(checks):
    # Diagnostics contain source-derived data. JSON quoting avoids presenting
    # snippets as controller instructions; expected vectors are never included.
    data = {'ast_parsing': 'passed' if checks['syntax_valid'] else 'failed',
            'compilation': 'not_run (Docker-only; AST parsing is not compilation)',
            'policy': 'accepted' if checks['static_policy_passed'] else 'rejected',
            'diagnostics': [d[:240] for d in checks['diagnostics'][:8]],
            'functional_tests': 'not_run; no functional success is established'}
    return '\nCandidate validation (untrusted source diagnostics): ' + json.dumps(data, ensure_ascii=True)
