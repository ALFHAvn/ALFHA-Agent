"""Step 44 data-only preparation and mocked-response Git staging tests."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_coding_workflow as fixtures
from git_checkpoints import _git, _source_snapshot, SafetyError
from proposal_protocol import proposal_messages, validate_changes, ProposalValidationError
from evaluations.prepare_focused_retest import (build_plan, assess_attempt,
    summarize_attempts, duplication_report)
from evaluations.structured_reliability import request_for


class FocusedPlanTests(unittest.TestCase):
    def setUp(self):
        with patch('ollama.Client', side_effect=AssertionError('No model requests')):
            self.plan=build_plan()
        self.old=json.loads(Path('evaluations/step42_plan.json').read_text(encoding='utf-8'))

    def test_six_exact_ordered_attempts(self):
        self.assertEqual([a['attempt_id'] for a in self.plan['attempts']],
                         [f'step44-r{n}-{t}' for n in (1,2,3) for t in ('bounds','stable_unique')])

    def test_system_is_only_payload_difference(self):
        for a in self.plan['attempts']:
            old=next(x for x in self.old['attempts'] if x['id']==a['baseline_attempt_id'])
            modified=copy.deepcopy(a['payload']); modified['messages'][0]=old['payload']['messages'][0]
            self.assertEqual(modified,old['payload'])
            self.assertNotEqual(a['payload']['messages'][0],old['payload']['messages'][0])

    def test_exact_step43_instructions_are_used(self):
        for a in self.plan['attempts']:
            t=next(t for t in self.plan['tasks'] if t['id']==a['task'])
            generated=proposal_messages(request_for(t,'DISPOSABLE'),t['initial_files'])
            self.assertEqual(a['payload']['messages'][0],generated[0])
            self.assertNotIn('required_changed_files',json.loads(a['payload']['messages'][1]['content']))

    def test_tasks_fixtures_expected_results_and_permissions_unchanged(self):
        self.assertEqual(self.plan['tasks'],[t for t in self.old['tasks'] if t['id'] in ('bounds','stable_unique')])
        for a in self.plan['attempts']:
            context=json.loads(a['payload']['messages'][1]['content'])
            self.assertEqual(list(context['authorized_files'].values()),[['read','modify'],['read','modify']])
            self.assertNotIn('expected_test_source',context);self.assertNotIn('functional_profile',context)

    def test_controller_options_budget_and_seeds_unchanged(self):
        self.assertEqual(self.plan['controller'],self.old['controller'])
        for a in self.plan['attempts']:
            self.assertEqual(a['payload']['options'],{'temperature':0,'seed':41+a['round'],'num_ctx':8192})
            self.assertEqual(a['payload']['format']['properties']['changes']['maxItems'],6)
            self.assertEqual(a['payload']['model'],'qwen3:4b');self.assertNotIn('tools',a['payload'])

    def test_plan_stable_matches_review_file_and_grants_no_authority(self):
        self.assertEqual(self.plan,build_plan())
        self.assertEqual(self.plan,json.loads(Path('evaluations/step44_plan.json').read_text(encoding='utf-8')))
        self.assertFalse(self.plan['generation_authorized']);self.assertFalse(self.plan['candidate_execution_authorized'])
        self.assertFalse(self.plan['source_application']);self.assertEqual(self.plan['maximum_generation_requests'],6)

    def test_diagnostics_exercised_literal_escape(self):
        t=self.plan['tasks'][0];name=t['module'];old=t['initial_files'][name]
        with self.assertRaises(ProposalValidationError) as cm:
            validate_changes([{'operation':'replace_text','filename':name,'old_text':old.replace('\n',r'\n'),
                               'new_text':t['reference_source']}],request_for(t,'DISPOSABLE')['authorized_files'],t['initial_files'])
        self.assertEqual(cm.exception.diagnostic['code'],'replacement_not_found')
        self.assertTrue(cm.exception.diagnostic['literal_backslash_n'])

    def test_exact_duplicates_and_historical_matches_are_separate(self):
        ids=[x['attempt_id'] for x in self.plan['attempts']]
        r=duplication_report([{'attempt_id':ids[0],'raw_response':'same'},
                              {'attempt_id':ids[2],'raw_response':'same'},
                              {'attempt_id':ids[4],'raw_response':'same '}],{'old-1':'same','old-2':'same'})
        self.assertEqual(r['analyzed_new_records'],3);self.assertEqual(r['distinct_response_texts'],2)
        self.assertEqual(len(r['exact_new_duplicate_groups']),1)
        self.assertEqual(r['historical_matches'][0]['historical_exact_matches'],['old-1','old-2'])
        self.assertEqual(r['historical_matches'][2]['historical_exact_matches'],[])
        self.assertTrue(r['does_not_prove_live_generation'])

    def test_unknown_responses_are_not_grouped_as_duplicates(self):
        ids=[x['attempt_id'] for x in self.plan['attempts']]
        r=duplication_report([{'attempt_id':ids[0],'raw_response':None},
                              {'attempt_id':ids[1],'raw_response':None}],{})
        self.assertEqual(r['unknown_response_slots'],2);self.assertEqual(r['exact_new_duplicate_groups'],[])

    def test_recurring_failures_count_each_attempt_once(self):
        ids=[x['attempt_id'] for x in self.plan['attempts']]
        rows=[{'attempt_id':k,'raw_response':'{}','feedback':[{'code':'replacement_not_found'}]*2} for k in (ids[0],ids[2])]
        r=duplication_report(rows,{})
        self.assertEqual(r['recurring_failure_patterns'],[{'code':'replacement_not_found','attempt_ids':[ids[0],ids[2]]}])

    def test_historical_and_duplicate_attempt_ids_rejected(self):
        key=self.plan['attempts'][0]['attempt_id'];row={'attempt_id':key,'raw_response':'{}'}
        for rows in ([row,row],[dict(row,attempt_id='r1-bounds')]):
            with self.assertRaises(ValueError):duplication_report(rows,{})

    def test_valid_json_is_not_complete_task_success(self):
        a=self.plan['attempts'][0]
        r=summarize_attempts([{'attempt_id':a['attempt_id'],'task':a['task'],'round':a['round'],
            'complete_static_task':False,'proposal_valid':True,'successful_edits':1}])
        self.assertEqual((r['valid_proposals'],r['complete_static_passed'],r['unattempted']),(1,0,5))
        self.assertFalse(r['interactive_integration_authorized'])

    def test_interrupted_unknown_results_not_invented(self):
        a=self.plan['attempts'][0]
        r=summarize_attempts([{'attempt_id':a['attempt_id'],'task':a['task'],'round':a['round'],
            'complete_static_task':None}])
        self.assertIsNone(r['complete_static_rate']);self.assertEqual(r['complete_static_unknown'],1)
        self.assertEqual(r['unattempted'],5)

    def test_summaries_reject_duplicate_mismatch_and_bad_types(self):
        a=self.plan['attempts'][0];row={'attempt_id':a['attempt_id'],'task':a['task'],'round':a['round'],'complete_static_task':True}
        for rows in ([row,row],[dict(row,task='other')],[dict(row,round=3)],
                     [dict(row,complete_static_task='yes')],[dict(row,successful_edits=7)]):
            with self.assertRaises(ValueError):summarize_attempts(rows)


class FocusedStagingTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def run_case(self, task_id, transform=None):
        p=build_plan();t=next(t for t in p['tasks'] if t['id']==task_id)
        for name,text in t['initial_files'].items():(self.root/name).write_bytes(text.encode())
        _git(self.root,'add','--all');_git(self.root,'commit','--quiet','-m','Focused fixture')
        changes=[{'operation':'replace_text','filename':name,'old_text':text,
                  'new_text':t['reference_source'] if name==t['module'] else t['expected_test_source']}
                 for name,text in t['initial_files'].items()]
        if transform:changes=transform(changes)
        before=_source_snapshot(self.root)
        with patch('ollama.Client',side_effect=AssertionError('No model')),patch(
                'evaluations.functional_harness.FunctionalHarness.run',side_effect=AssertionError('No execution')):
            r=assess_attempt('step44-r1-'+task_id,self.root,json.dumps({'version':1,'changes':changes}))
        self.reports.append(Path(r['report_path']))
        self.assertEqual(before,_source_snapshot(self.root));self.assertTrue(r['assessment']['cleanup_verified'])
        self.assertEqual(r['response_origin'],'supplied_offline_data');self.assertFalse(r['model_invoked'])
        self.assertEqual(json.loads(Path(r['report_path']).read_text(encoding='utf-8')),r)
        self.assertEqual(r['functional_status'],'not_run')
        return r

    def test_clamp_full_multiline_contract(self):
        r=self.run_case('bounds');self.assertTrue(r['complete_static_task']);self.assertEqual(r['successful_edits'],2)
        self.assertTrue(all(x['old_actual_newlines']>0 and not x['old_literal_backslash_n'] for x in r['multiline_observations']))

    def test_dedup_operator_failure_not_hidden_by_successful_edits(self):
        def wrong(c):c[1]['new_text']=c[1]['new_text'].replace('result is not values','result != values');return c
        r=self.run_case('stable_unique',wrong)
        self.assertTrue(r['proposal_valid']);self.assertTrue(r['implementation_static']['passed'])
        self.assertFalse(r['generated_test_contract']['passed']);self.assertFalse(r['complete_static_task'])
        self.assertIn('assertion_operator_mismatch',[d['code'] for d in r['feedback']])

    def test_literal_escapes_rejected_without_repair(self):
        def escaped(c):c[0]['old_text']=c[0]['old_text'].replace('\n',r'\n');return c
        r=self.run_case('bounds',escaped)
        self.assertFalse(r['proposal_valid']);self.assertEqual(r['successful_edits'],0)
        self.assertTrue(r['multiline_observations'][0]['old_literal_backslash_n'])
        self.assertEqual(r['budget_used'],2)

    def test_fully_compliant_dedup(self):
        r=self.run_case('stable_unique');self.assertTrue(r['complete_static_task'])
        self.assertTrue(r['generated_test_contract']['passed']);self.assertEqual(len(r['candidate_sha256']),2)

    def test_unknown_attempt_cannot_stage(self):
        with self.assertRaises(SafetyError),patch('evaluations.prepare_focused_retest.assess_response',side_effect=AssertionError('No staging')):
            assess_attempt('r1-bounds',self.root,'{}')
