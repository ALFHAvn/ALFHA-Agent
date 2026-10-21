"""Step 41 scoped policy/host grading test doubles; never executes source."""
import ast
import hashlib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from evaluations import normalize_profile as profile
from evaluations import string_policy
from evaluations.functional_validation import validate_source
from evaluations.functional_harness import (task_by_id, make_request, worker_program, grade_execution,
                                           FunctionalHarness, profile_hash)
from evaluations.prepare_candidate_validation import tasks
import test_functional_worker as wire

REFERENCE = 'def normalize_tags(tags):\n    return [item.strip().lower() for item in tags]\n# test double only\n'


class NormalizeScopeTests(unittest.TestCase):
    def task(self): return task_by_id(profile.TASK_ID, string_scope=profile.SCOPE)
    def known(self, source=REFERENCE):
        return patch.object(string_policy, 'NORMALIZE_HASHES', {hashlib.sha256(source.encode()).hexdigest()})

    def test_scope_absent_disabled_and_unknown_scope_rejected(self):
        for scope in (None, '', True, 'other'):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                task_by_id(profile.TASK_ID, string_scope=scope)

    def test_other_task_cannot_borrow_scope(self):
        with self.assertRaises(ValueError): task_by_id('sum_even', string_scope=profile.SCOPE)

    def test_unapproved_source_hash_fails_closed(self):
        result = validate_source(REFERENCE, self.task())
        self.assertFalse(result['static_policy_passed'])
        self.assertIn('Invalid string scope, function contract or preserved source hash', result['diagnostics'])
        with self.assertRaises(ValueError): make_request(profile.TASK_ID, REFERENCE, string_scope=profile.SCOPE)

    def test_hash_matched_source_accepted_only_with_explicit_scope(self):
        with self.known():
            self.assertTrue(validate_source(REFERENCE, self.task())['static_policy_passed'])
            default = {'function': 'normalize_tags', 'parameters': ['tags']}
            self.assertFalse(validate_source(REFERENCE, default)['static_policy_passed'])
            self.assertFalse(validate_source(REFERENCE+'\n', self.task())['static_policy_passed'])

    def test_scope_also_binds_exact_function_contract(self):
        with self.known():
            task = self.task(); task['parameters'] = ['other']
            self.assertFalse(validate_source(REFERENCE, task)['static_policy_passed'])

    def test_syntax_restrictions_cannot_be_bypassed_even_if_hash_trusted(self):
        for expression in ('tags.strip(chars="x")', 'getattr(tags,"strip")()',
                           'tags.strip().lower().strip()', 'tags.__class__', '__alfha_string_method__(tags,"strip")'):
            source = 'def normalize_tags(tags):\n    return '+expression+'\n'
            with self.subTest(expression=expression), self.known(source):
                self.assertFalse(validate_source(source, self.task())['static_policy_passed'])

    def test_request_excludes_expected_values_and_profile_assertions(self):
        with self.known(): req = make_request(profile.TASK_ID, REFERENCE, string_scope=profile.SCOPE)
        self.assertEqual(req['string_scope'], profile.SCOPE)
        self.assertTrue(all(set(v)=={'args'} for v in req['vectors']))
        self.assertNotIn('require_new_list', req)
        with self.known(): program = worker_program(req)
        ast.parse(program)
        self.assertIn('scoped_normalize_allowed', program)
        self.assertIn('hashlib.sha256(source.encode', program)
        self.assertIn('NORMALIZE_HASHES=', program)

    def request(self):
        with self.known(): return make_request(profile.TASK_ID, REFERENCE, string_scope=profile.SCOPE)

    def test_synthetic_correct_results_host_grading(self):
        request=self.request(); task=self.task()
        result=grade_execution(task, request, wire.raw_output(wire.stream(request, task)))
        self.assertTrue(result['passed']); self.assertEqual(result['passed_count'],12)

    def test_input_alias_cannot_pass_even_for_empty_list(self):
        request=self.request(); task=self.task(); frames=wire.stream(request,task)
        frames[2]['new_list']=False
        grade=grade_execution(task,request,wire.raw_output(frames))
        self.assertFalse(grade['passed']); self.assertFalse(grade['results'][0]['result_identity_valid'])
        self.assertEqual(grade['passed_count'],11)

    def test_mutated_input_cannot_pass(self):
        request=self.request(); task=self.task(); frames=wire.stream(request,task)
        frames[2]['args_after']=[['changed']]
        grade=grade_execution(task,request,wire.raw_output(frames))
        self.assertFalse(grade['results'][0]['arguments_unchanged'])

    def test_wrong_return_type_rejected_by_host(self):
        request=self.request(); task=self.task(); frames=wire.stream(request,task)
        frames[2]['value']={}; frames[2]['new_list']=False
        grade=grade_execution(task,request,wire.raw_output(frames))
        self.assertFalse(grade['results'][0]['value_matches'])

    def test_fixed_vectors_preserve_step39_proposal(self):
        self.assertEqual(self.task()['tests'],tasks()['B']['tests'])
        self.assertEqual(len(profile.SOURCE_HASHES),3)
        self.assertTrue(all(len(h)==64 for h in profile.SOURCE_HASHES))
        task=self.task();task['tests'][0]['expected'].append('changed')
        self.assertEqual(self.task()['tests'][0]['expected'],[])

    def test_scope_does_not_remove_current_verification_requirement(self):
        backend=Mock();backend.verify.return_value={'verified':False}
        with self.known(): result=FunctionalHarness(backend).run(profile.TASK_ID,REFERENCE,string_scope=profile.SCOPE)
        self.assertEqual(result['status'],'blocked');backend.run_verified_worker.assert_not_called()

    def test_new_profile_file_is_bound_by_profile_hash(self):
        old=Path.read_bytes; before=profile_hash()
        def read(path):
            data=old(path)
            return data+b'\n# changed' if path.name=='normalize_profile.py' else data
        with patch.object(Path,'read_bytes',read):self.assertNotEqual(before,profile_hash())

    def test_worker_contract_rejects_missing_scope_even_without_strip(self):
        request={'task_id':profile.TASK_ID,'function':'normalize_tags','parameters':['tags'],
                 'source':'def normalize_tags(tags):\n    return tags\n'}
        for scope in (None,False,'other'):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                string_policy.worker_task_contract(dict(request,string_scope=scope))
        with self.assertRaises(ValueError):string_policy.worker_task_contract(request)

    def test_worker_contract_rechecks_hash_and_rejects_scope_on_other_tasks(self):
        request=self.request()
        with self.known():
            self.assertEqual(string_policy.worker_task_contract(request)['string_scope'],profile.SCOPE)
            with self.assertRaises(ValueError):
                string_policy.worker_task_contract(dict(request,source=REFERENCE+'\n'))
            with self.assertRaises(ValueError):
                string_policy.worker_task_contract(dict(request,task_id='sum_even'))
