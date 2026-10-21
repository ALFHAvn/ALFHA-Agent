"""Preparation is data only: no model generation or candidate execution."""
import copy
import json
import unittest
from unittest.mock import patch

from evaluations.prepare_structured import BASELINE, build_plan
from proposal_protocol import validate_changes
from git_checkpoints import SafetyError


class PreparationTests(unittest.TestCase):
    def setUp(self):
        with patch('ollama.Client', side_effect=AssertionError('No model contact')):
            self.plan = build_plan()
        self.baseline = json.loads(BASELINE.read_text(encoding='utf-8'))

    def test_exact_six_requests_same_order_and_models(self):
        self.assertEqual([(x['payload']['model'], x['scenario']) for x in self.plan['model_requests']],
                         [(m, s) for m in self.baseline['models'] for s in ('A', 'B')])

    def test_payloads_identical_except_model_per_scenario(self):
        for scenario in ('A', 'B'):
            payloads = [copy.deepcopy(x['payload']) for x in self.plan['model_requests']
                        if x['scenario'] == scenario]
            for p in payloads:
                p.pop('model')
            self.assertEqual(payloads[0], payloads[1])
            self.assertEqual(payloads[1], payloads[2])

    def test_fixtures_acceptance_and_requirement_preserved(self):
        for key, old in self.baseline['scenarios'].items():
            new = self.plan['scenarios'][key]
            self.assertEqual(new['initial_files'], old['initial_files'])
            self.assertEqual(new['request_template']['description'],
                             old['request_template']['description'].split('Use actual tools to inspect and edit')[0].rstrip())
            self.assertEqual(new['request_template']['authorized_files'], old['request_template']['authorized_files'])
        self.assertEqual(self.plan['scenarios']['B']['acceptance'], self.baseline['scenarios']['B']['static_acceptance'])

    def test_schema_budget_paths_and_no_native_tools(self):
        for item in self.plan['model_requests']:
            p = item['payload']; schema = p['format']
            changes = schema['properties']['changes']
            self.assertEqual(changes['maxItems'], 6)
            self.assertFalse(schema['additionalProperties'])
            self.assertFalse(changes['items']['additionalProperties'])
            self.assertEqual(set(changes['items']['properties']['filename']['enum']),
                             set(self.plan['scenarios'][item['scenario']]['initial_files']))
            self.assertNotIn('tools', p)
            self.assertEqual(p['options'], self.baseline['chat_options'])

    def test_source_in_prompt_but_host_acceptance_not_in_payload(self):
        for item in self.plan['model_requests']:
            context = json.loads(item['payload']['messages'][1]['content'])
            self.assertEqual(context['initial_files'], self.plan['scenarios'][item['scenario']]['initial_files'])
            self.assertNotIn('expected_source', context)
            self.assertNotIn('source_repository', context)

    def test_plan_does_not_grant_authorization_or_retry(self):
        self.assertEqual(self.plan['status'], 'pending_explicit_live_approval')
        self.assertEqual(self.plan['controller']['automatic_retries'], 0)
        self.assertEqual(self.plan['controller']['candidate_execution'], 'disabled')
        self.assertEqual(build_plan(), self.plan)

    def test_original_syntax_repair_accepted_and_unauthorized_batch_rejected(self):
        s = self.plan['scenarios']['A']; name = 'syntax_target.py'
        change = dict(operation='replace_text', filename=name,
                      old_text=s['initial_files'][name], new_text=s['expected_source'])
        before = copy.deepcopy(s['initial_files'])
        self.assertEqual(validate_changes([change], s['request_template']['authorized_files'], before),
                         {name: s['expected_source']})
        with self.assertRaises(SafetyError):
            validate_changes([change, dict(change, filename='other.py')],
                             s['request_template']['authorized_files'], before)
        self.assertEqual(before, s['initial_files'])
