"""Step 42 data-only preparation, mocked responses and real temporary Git."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from evaluations.structured_reliability import (build_plan, static_assessment,
    assess_response, summarize, digest)
from git_checkpoints import _git, _source_snapshot, SafetyError
import test_coding_workflow as fixtures


class ReliabilityPlanTests(unittest.TestCase):
    def setUp(self):
        with patch('ollama.Client', side_effect=AssertionError('No model')):
            self.plan = build_plan()

    def test_twelve_unique_round_robin_attempts(self):
        attempts = self.plan['attempts']
        self.assertEqual(len(attempts), 12)
        self.assertEqual(len({a['id'] for a in attempts}), 12)
        self.assertEqual([a['round'] for a in attempts], [1]*4+[2]*4+[3]*4)

    def test_models_settings_and_budget_fixed(self):
        for a in self.plan['attempts']:
            p = a['payload']
            self.assertEqual(p['model'], 'qwen3:4b')
            self.assertEqual(p['options'], {'temperature': 0, 'seed': 41+a['round'], 'num_ctx': 8192})
            self.assertNotIn('tools', p)
            self.assertEqual(p['format']['properties']['changes']['maxItems'], 6)
        self.assertEqual(self.plan['controller']['retries'], 0)

    def test_context_excludes_host_answers(self):
        for a in self.plan['attempts']:
            c = json.loads(a['payload']['messages'][1]['content'])
            self.assertEqual(set(c), {'task', 'authorized_files', 'initial_files'})
            self.assertNotIn('reference_source', c)
            self.assertEqual(set(c['initial_files']), set(c['authorized_files']))

    def test_repeat_payloads_only_seed_changes(self):
        for task in self.plan['tasks']:
            payloads = [copy.deepcopy(a['payload']) for a in self.plan['attempts'] if a['task']==task['id']]
            for p in payloads: p['options'].pop('seed')
            self.assertEqual(payloads[0], payloads[1]); self.assertEqual(payloads[1], payloads[2])

    def test_fixed_vectors_and_no_execution_authorization(self):
        self.assertEqual([len(t['functional_profile']['tests']) for t in self.plan['tasks']], [6,5,7,5])
        self.assertEqual(self.plan['docker_scope']['maximum_vectors'], 69)
        self.assertFalse(self.plan['candidate_execution_authorized'])
        self.assertFalse(self.plan['model_generation_authorized'])
        self.assertIsNone(self.plan['docker_scope']['string_scope'])

    def test_plan_is_stable_and_matches_manifest(self):
        self.assertEqual(build_plan(), self.plan)
        path = Path('evaluations/step42_plan.json')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), self.plan)

    def test_independent_static_reference_contracts(self):
        for t in self.plan['tasks']:
            files = dict(t['initial_files']); files[t['module']] = t['reference_source']
            if t.get('test_file'): files[t['test_file']] = t['expected_test_source']
            self.assertTrue(static_assessment(t, files)['completed'])
            self.assertFalse(static_assessment(t, t['initial_files'])['completed'])

    def test_static_does_not_claim_semantics(self):
        t = self.plan['tasks'][1]
        files = {t['module']: 'def sum_even(numbers):\n    return 999\n'}
        r = static_assessment(t, files)
        self.assertTrue(r['completed'])
        self.assertEqual(r['semantic_correctness'], 'not_established_by_static_checks')

    def test_test_contract_rejects_extra_code_or_removed_assertions(self):
        t = self.plan['tasks'][2]
        files = {t['module']: t['reference_source'], t['test_file']: t['expected_test_source']+'skip = True\n'}
        self.assertFalse(static_assessment(t, files)['completed'])
        files[t['test_file']] = t['expected_test_source'].replace('assert clamp(7, 3, 3) == 3', 'pass')
        self.assertFalse(static_assessment(t, files)['completed'])

    def test_missing_parse_invalid_unauthorized_and_wrong_signature(self):
        t = self.plan['tasks'][0]
        for files in ({}, {t['module']: 'return ('}, {t['module']: t['reference_source'], 'evil.py': ''},
                      {t['module']: 'def wrong(value):\n    return value + 1\n'}):
            self.assertFalse(static_assessment(t, files)['completed'])

    def test_partial_summary_does_not_count_unattempted_as_failures(self):
        empty = summarize([]); self.assertIsNone(empty['static_rate'])
        a = self.plan['attempts'][0]
        r = summarize([{'attempt_id': a['id'], 'task': a['task'], 'static_task_completed': True}])
        self.assertEqual((r['attempted'], r['unattempted'], r['static_rate']), (1,11,1.0))
        self.assertIsNone(r['functional_rate'])

    def test_summary_rejects_duplicate_mismatch_and_unknown(self):
        a = self.plan['attempts'][0]
        row = {'attempt_id': a['id'], 'task': a['task'], 'static_task_completed': True}
        for rows in ([row,row], [dict(row, task='other')], [dict(row,attempt_id='unknown')],
                     [dict(row,static_task_completed='yes')]):
            with self.assertRaises(ValueError): summarize(rows)

    def test_interrupted_outcome_stays_unknown(self):
        a = self.plan['attempts'][0]
        r = summarize([{'attempt_id': a['id'], 'task': a['task'], 'static_task_completed': None}])
        self.assertEqual((r['attempted'], r['static_unknown'], r['static_known']), (1,1,0))
        self.assertIsNone(r['static_rate'])


class ReliabilityStagingTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown

    def stage(self, task_index, transform=None):
        t = build_plan()['tasks'][task_index]
        for name, text in t['initial_files'].items(): (self.root/name).write_bytes(text.encode())
        _git(self.root, 'add', '--all'); _git(self.root, 'commit', '--quiet', '-m', 'Reliability fixture')
        changes = [{'operation':'replace_text','filename':name,'old_text':text,
            'new_text': t['reference_source'] if name==t['module'] else t['expected_test_source']}
            for name,text in t['initial_files'].items()]
        raw = json.dumps({'version':1,'changes':changes})
        if transform: raw = transform(raw)
        before = _source_snapshot(self.root)
        with patch('ollama.Client', side_effect=AssertionError('No generation')), patch(
                'evaluations.functional_harness.FunctionalHarness.run', side_effect=AssertionError('No execution')):
            r = assess_response(t['id'], self.root, raw)
        self.reports.append(Path(r['staging']['report_path']))
        self.assertEqual(before, _source_snapshot(self.root))
        self.assertTrue(r['cleanup_verified']); self.assertTrue(r['source_unchanged'])
        self.assertEqual(r['functional']['status'], 'not_run')
        self.assertIsNone(r['model_response_seconds'])
        self.assertEqual(json.loads(Path(r['assessment_path']).read_text(encoding='utf-8')), r)
        return r

    def test_one_file_syntax(self):
        r = self.stage(0); self.assertTrue(r['static_task_completed']); self.assertEqual(r['successful_edits'],1)

    def test_one_file_edge_task(self):
        self.assertTrue(self.stage(1)['static_task_completed'])

    def test_two_file_clamp(self):
        r = self.stage(2); self.assertTrue(r['static_task_completed']); self.assertEqual(r['successful_edits'],2)

    def test_two_file_order_and_preservation(self):
        self.assertTrue(self.stage(3)['static_task_completed'])

    def test_unauthorized_batch_cannot_partially_write(self):
        r = self.stage(2, lambda s: s.replace('test_clamp.py', '../evil.py'))
        self.assertFalse(r['proposal_valid']); self.assertEqual(r['successful_edits'],0)

    def test_nonmatching_batch_cannot_partially_write(self):
        def change(s):
            d=json.loads(s);d['changes'][1]['old_text']='missing';return json.dumps(d)
        r=self.stage(2,change);self.assertEqual(r['successful_edits'],0)

    def test_malformed_and_over_budget(self):
        r=self.stage(0,lambda s: s+' extra');self.assertEqual(r['budget_used'],1)
        self.assertFalse(r['static_task_completed'])

    def test_over_budget_document(self):
        def more(s):
            d=json.loads(s);d['changes']*=7;return json.dumps(d)
        r=self.stage(0,more);self.assertEqual(r['budget_used'],6);self.assertEqual(r['successful_edits'],0)

    def test_fixture_mismatch_blocks_before_staging(self):
        with self.assertRaises(SafetyError), patch('evaluations.structured_reliability.run_proposals',side_effect=AssertionError('No staging')):
            assess_response('syntax',self.root,'{}')

