"""AST and bootstrap tests only; source strings never execute on the host."""
import ast
import unittest
from unittest.mock import patch
from pathlib import Path

from evaluations.functional_validation import validate_source
from evaluations.functional_harness import task_by_id, make_request, worker_program, profile_hash


class StringPolicyTests(unittest.TestCase):
    def checks(self, expression, setup='', task='step40_chain'):
        t = task_by_id(task)
        return validate_source(f'def {t["function"]}(value):\n{setup}    return {expression}\n', t)

    def test_valid_single_methods_and_two_orders(self):
        for value in ('value.strip()', 'value.lower()', 'value.strip().lower()', 'value.lower().strip()',
                      '" A ".strip()', 'value[0].strip().lower()'):
            with self.subTest(value=value):
                self.assertTrue(self.checks(value)['static_policy_passed'])

    def test_strip_not_enabled_for_preserved_normalize(self):
        c = validate_source('def normalize_tags(tags):\n    return [x.strip().lower() for x in tags]\n',
                            {'function': 'normalize_tags', 'parameters': ['tags']})
        self.assertFalse(c['static_policy_passed'])
        self.assertIn('Unsupported attribute: strip', c['diagnostics'])

    def test_strip_rejected_in_lower_only_profile(self):
        self.assertFalse(self.checks('value.strip()', task='step40_lower')['static_policy_passed'])

    def test_positional_keyword_and_star_arguments_rejected(self):
        for value in ('value.strip("x")', 'value.strip(chars="x")', 'value.lower("x")',
                      'value.lower(x=1)', 'value.strip(*value)', 'value.lower(**value)', 'str.strip(value)'):
            with self.subTest(value=value):
                self.assertFalse(self.checks(value)['static_policy_passed'])

    def test_unsupported_methods_and_dunder_attributes(self):
        for value in ('value.upper()', 'value.replace("a", "b")', 'value.__class__',
                      'value.strip().__class__', 'value.__getattribute__("strip")()'):
            self.assertFalse(self.checks(value)['static_policy_passed'])

    def test_dynamic_lookup_and_reflection_rejected(self):
        for value in ('getattr(value, "strip")()', 'getattr(value, "st" + "rip")()',
                      'eval("value.strip()")', 'globals()', '__alfha_string_method__(value, "strip")'):
            self.assertFalse(self.checks(value)['static_policy_passed'])

    def test_extracted_alias_rejected_even_for_allowed_builtin_name(self):
        c = self.checks('sum()', setup='    sum = value.strip\n')
        self.assertFalse(c['static_policy_passed'])
        self.assertIn('String methods must be called directly; attribute extraction is forbidden', c['diagnostics'])

    def test_obvious_nonstring_receivers_rejected(self):
        for value in ('1 .strip()', 'True.lower()', 'b"x".strip()', '[].strip()', '{}.lower()', '(1,).strip()'):
            self.assertFalse(self.checks(value)['static_policy_passed'])

    def test_unknown_receiver_requires_runtime_guard_not_static_type_claim(self):
        self.assertTrue(self.checks('value.strip()', setup='    value = 7\n')['static_policy_passed'])

    def test_nested_and_repeated_method_chains_rejected(self):
        for value in ('value.strip().lower().strip()', 'value.lower().lower()',
                      'value.strip().strip()', 'str(value).lower()', 'value.get("x").strip()',
                      'len(value).lower()', 'value.split().lower()'):
            self.assertFalse(self.checks(value)['static_policy_passed'])

    def test_imports_files_network_and_dynamic_execution_stay_rejected(self):
        for setup, expression in [('    import os\n', 'value'), ('', 'open("x")'),
                                  ('', '__import__("socket")'), ('', 'exec(value)')]:
            self.assertFalse(self.checks(expression, setup=setup)['static_policy_passed'])

    def test_bootstrap_carries_guard_and_policy_without_expected_results(self):
        req = make_request('step40_chain', 'def review_chain(value):\n    return value.strip().lower()\n')
        self.assertNotIn('expected', req)
        program = worker_program(req)
        ast.parse(program)
        self.assertIn('class _GuardStrings', program)
        self.assertIn('builtins.type(value) is not builtins.str', program)
        self.assertIn("STRING_METHODS=", program)

    def test_string_policy_changes_invalidate_grading_profile(self):
        old = Path.read_bytes; initial = profile_hash()
        def read(p):
            data = old(p)
            return data+b'\n# changed' if p.name=='string_policy.py' else data
        with patch.object(Path, 'read_bytes', read):
            self.assertNotEqual(initial, profile_hash())
