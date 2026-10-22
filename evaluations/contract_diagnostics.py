"""Trusted static test-contract diagnostics. Never imports or executes source."""
import ast


def test_contract(expected_source, actual_source, filename):
    """Explain the existing whole-AST equality rule; do not replace that rule."""
    expected = ast.parse(expected_source)
    try:
        actual = ast.parse(actual_source)
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        return {'status': 'failed', 'passed': False, 'diagnostics': [
            {'code': 'test_parse_error', 'filename': filename,
             'message': f'{filename}: test source cannot be parsed: {type(exc).__name__}'}]}
    equal = ast.dump(expected) == ast.dump(actual)
    diagnostics = []
    actual_functions = {}
    for node in actual.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            actual_functions.setdefault(node.name, []).append(node)
    for function in expected.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        matches = actual_functions.get(function.name, [])
        if len(matches) != 1:
            diagnostics.append({'code': 'missing_test_function' if not matches else 'duplicate_test_function',
                'filename': filename, 'function': function.name,
                'message': f'{filename}: require exactly one {function.name} test function; found {len(matches)}.'})
            continue
        target = matches[0]
        required = [node for node in function.body if isinstance(node, ast.Assert)]
        observed = [node for node in target.body if isinstance(node, ast.Assert)]
        used = set()
        for index, assertion in enumerate(required):
            key = ast.dump(assertion)
            if index < len(observed) and ast.dump(observed[index]) == key:
                used.add(index)
                continue
            found = next((i for i, node in enumerate(observed) if i not in used and ast.dump(node) == key), None)
            expected_text = ast.unparse(assertion)
            if found is not None:
                used.add(found)
                code = 'assertion_order_mismatch'
                message = f'Expected assertion {index+1} in required order: {expected_text}.'
                actual_text = ast.unparse(observed[index]) if index < len(observed) else None
            else:
                # Same operands make an operator substitution unambiguous.
                test = assertion.test
                wrong = next((node for node in observed if isinstance(test, ast.Compare) and
                    isinstance(node.test, ast.Compare) and
                    ast.dump(test.left) == ast.dump(node.test.left) and
                    [ast.dump(x) for x in test.comparators] == [ast.dump(x) for x in node.test.comparators] and
                    [type(x) for x in test.ops] != [type(x) for x in node.test.ops]), None)
                actual_text = ast.unparse(wrong) if wrong is not None else None
                code = 'assertion_operator_mismatch' if wrong is not None else 'missing_assertion'
                message = f'Require {expected_text}; found {actual_text}.' if wrong is not None else f'Missing required assertion: {expected_text}.'
                if wrong is not None and any(isinstance(op, ast.IsNot) for op in test.ops):
                    message += ' Use is not for object identity; != compares values and does not prove a fresh object.'
            diagnostics.append({'code': code, 'filename': filename, 'function': function.name,
                'assertion_index': index+1, 'expected': expected_text, 'actual': actual_text,
                'message': f'{filename} / {function.name}: {message}'})
    if not equal:
        diagnostics.append({'code': 'test_ast_contract_mismatch', 'filename': filename,
            'message': f'{filename}: full test AST differs from the required contract; preserve imports, assignments, assertion order and operators; remove unsupported extra code.'})
    return {'status': 'passed' if equal else 'failed', 'passed': equal, 'diagnostics': diagnostics}
