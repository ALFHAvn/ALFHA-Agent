"""Step 43 mocked proposals, static diagnostics and disposable real Git."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_coding_workflow as fixtures
from evaluations.structured_reliability import build_plan, static_assessment, assess_response
from evaluations.contract_diagnostics import test_contract as contract_check
from proposal_protocol import (proposal_messages, validate_changes, strict_json,
                               ProposalValidationError, proposal_schema)
from git_checkpoints import SafetyError, _git, _source_snapshot


def change(name, old, new):
    return {'operation': 'replace_text', 'filename': name, 'old_text': old, 'new_text': new}


class ContractDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.task = build_plan()['tasks'][3]
        self.expected = self.task['expected_test_source']
        self.filename = self.task['test_file']

    def contract(self, text):
        return contract_check(self.expected, text, self.filename)

    def test_wrong_operator_names_exact_expected_and_actual(self):
        result = self.contract(self.expected.replace('result is not values', 'result != values'))
        row = next(d for d in result['diagnostics'] if d['code']=='assertion_operator_mismatch')
        self.assertEqual(row['expected'], 'assert result is not values')
        self.assertEqual(row['actual'], 'assert result != values')
        self.assertEqual(row['function'], 'test_input')
        self.assertIn('identity', row['message']); self.assertFalse(result['passed'])

    def test_missing_assertion(self):
        result = self.contract(self.expected.replace('    assert result is not values\n', ''))
        self.assertIn('assert result is not values', [d.get('expected') for d in result['diagnostics']])
        self.assertIn('missing_assertion', [d['code'] for d in result['diagnostics']])

    def test_assertion_elsewhere_does_not_satisfy_contract(self):
        text = self.expected.replace('    assert result is not values\n', '')
        result = self.contract(text+'\ndef another():\n    assert result is not values\n')
        self.assertTrue(any(d['code']=='missing_assertion' and d['function']=='test_input' for d in result['diagnostics']))

    def test_assertion_order_stays_strict(self):
        text = self.expected.replace('    assert result == [5]\n    assert values == [5, 5, 5]',
                                     '    assert values == [5, 5, 5]\n    assert result == [5]')
        result = self.contract(text)
        self.assertFalse(result['passed'])
        self.assertIn('assertion_order_mismatch', [d['code'] for d in result['diagnostics']])

    def test_compliant_formatting_has_no_false_errors(self):
        result = self.contract(self.expected.replace('[5, 5, 5]', '[5,5,5]'))
        self.assertTrue(result['passed']); self.assertEqual(result['diagnostics'], [])

    def test_extra_code_rejected_despite_all_assertions(self):
        result = self.contract(self.expected+'\nunique_order = lambda x: []\n')
        self.assertFalse(result['passed'])
        self.assertIn('test_ast_contract_mismatch', [d['code'] for d in result['diagnostics']])

    def test_missing_duplicate_or_async_function_cannot_pass(self):
        for text in (self.expected.replace('test_input', 'other'),
                     self.expected+'\ndef test_input():\n    pass\n',
                     self.expected.replace('def test_input', 'async def test_input')):
            self.assertFalse(self.contract(text)['passed'])

    def test_missing_or_unparseable_tests(self):
        for text in (None, 'def broken(:'):
            result = self.contract(text)
            self.assertFalse(result['passed']); self.assertEqual(result['diagnostics'][0]['code'], 'test_parse_error')

    def test_implementation_static_and_test_contract_are_separate(self):
        files = {self.task['module']: self.task['reference_source'], self.filename:
                 self.expected.replace('result is not values', 'result != values')}
        result = static_assessment(self.task, files)
        self.assertTrue(result['implementation_static']['passed'])
        self.assertEqual(result['implementation_static']['functional_correctness'], 'not_tested')
        self.assertFalse(result['generated_test_contract']['passed']); self.assertFalse(result['completed'])

    def test_no_test_requirement_is_not_claimed_as_test_pass(self):
        t=build_plan()['tasks'][0]; r=static_assessment(t,{t['module']:t['reference_source']})
        self.assertEqual(r['generated_test_contract']['status'], 'not_required')
        self.assertIsNone(r['generated_test_contract']['passed'])


class ProposalFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.auth={'a.py':['read','modify']}
        self.request={'description':'Change a.py only; preserve exact assertions.',
            'source_repository':str(Path('DISPOSABLE').absolute()),'authorized_files':self.auth,
            'validation_requirements':{'static':True,'docker_execution':False}}

    def test_instruction_examples_decode_differently(self):
        contents={'a.py':'first\nsecond'}; before=copy.deepcopy(contents)
        with patch('ollama.Client', side_effect=AssertionError('No generation')):
            messages=proposal_messages(self.request,contents)
        text=messages[0]['content']
        self.assertIn(json.dumps('first\nsecond'),text)
        self.assertIn(json.dumps(r'first\nsecond'),text)
        self.assertNotEqual(json.loads(json.dumps('first\nsecond')), json.loads(json.dumps(r'first\nsecond')))
        self.assertIn('assert result is not values',text);self.assertIn('!=',text)
        self.assertEqual(contents,before)
        self.assertEqual(proposal_schema(self.request)['properties']['changes']['maxItems'],6)

    def test_instruction_builder_rejects_unreadable_or_extra_content(self):
        for contents in ({'outside.py':'x'}, {'a.py':1}, {'a.py':'x','extra.py':'y'}):
            with self.assertRaises(SafetyError):proposal_messages(self.request,contents)

    def test_valid_multiline_edits(self):
        source={'a.py':'A = 1\nB = 2\n'}
        result=validate_changes([change('a.py',source['a.py'],'A = 3\nB = 4\n')],self.auth,source)
        self.assertEqual(result['a.py'],'A = 3\nB = 4\n');self.assertEqual(source['a.py'],'A = 1\nB = 2\n')

    def test_literal_newline_mismatch_is_not_transformed(self):
        source={'a.py':'A = 1\nB = 2\n'}; before=copy.deepcopy(source)
        with self.assertRaises(ProposalValidationError) as cm:
            validate_changes([change('a.py',r'A = 1\nB = 2\n','A = 3\n')],self.auth,source)
        d=cm.exception.diagnostic
        self.assertEqual((d['code'],d['field'],d['filename'],d['match_count']),('replacement_not_found','old_text','a.py',0))
        self.assertTrue(d['literal_backslash_n']);self.assertEqual(d['actual_newline_count'],0)
        self.assertIn('encode the response once',str(cm.exception));self.assertEqual(source,before)

    def test_legitimate_literal_escapes_are_not_rejected(self):
        old=r'PATTERN = "a\nb"';new=r'PATTERN = "a\nc"'
        self.assertEqual(validate_changes([change('a.py',old,new)],self.auth,{'a.py':old+'\n'}),{'a.py':new+'\n'})

    def test_ambiguous_matches_do_not_choose_a_location(self):
        source={'a.py':'A = 1\nA = 1\n'}
        with self.assertRaises(ProposalValidationError) as cm:
            validate_changes([change('a.py','A = 1','A = 2')],self.auth,source)
        self.assertEqual(cm.exception.diagnostic['code'],'ambiguous_replacement')
        self.assertEqual(cm.exception.diagnostic['match_count'],2)

    def test_duplicate_keys_and_text_salvage_stay_rejected(self):
        for text in ('{"version":1,"version":1}', '```json\n{}\n```', '{} trailing'):
            with self.assertRaises(SafetyError):strict_json(text)

    def test_historical_plans_unchanged(self):
        from evaluations.prepare_structured import build_plan as legacy_plan
        self.assertEqual(legacy_plan(),json.loads(Path('evaluations/step38_plan.json').read_text(encoding='utf-8')))
        self.assertEqual(build_plan(),json.loads(Path('evaluations/step42_plan.json').read_text(encoding='utf-8')))


class ContractStagingTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def run_case(self, transform=None):
        t=build_plan()['tasks'][3]
        for name,text in t['initial_files'].items():(self.root/name).write_bytes(text.encode())
        _git(self.root,'add','--all');_git(self.root,'commit','--quiet','-m','Step 43 fixture')
        changes=[change(name,text,t['reference_source'] if name==t['module'] else t['expected_test_source'])
                 for name,text in t['initial_files'].items()]
        if transform:changes=transform(changes)
        before=_source_snapshot(self.root)
        with patch('ollama.Client',side_effect=AssertionError('No model')),patch(
                'evaluations.functional_harness.FunctionalHarness.run',side_effect=AssertionError('No execution')):
            r=assess_response(t['id'],self.root,json.dumps({'version':1,'changes':changes}))
        self.reports.append(Path(r['staging']['report_path']))
        self.assertEqual(before,_source_snapshot(self.root));self.assertTrue(r['cleanup_verified'])
        self.assertFalse(r['feedback_delivered_to_model']);self.assertEqual(r['functional']['status'],'not_run')
        return r

    def test_compliant_two_file_task(self):
        r=self.run_case();self.assertTrue(r['static_task_completed'])
        self.assertEqual(r['successful_edits'],2);self.assertEqual(r['feedback'],[])

    def test_wrong_operator_report_is_specific(self):
        def wrong(changes):
            changes[1]['new_text']=changes[1]['new_text'].replace('result is not values','result != values');return changes
        r=self.run_case(wrong);self.assertFalse(r['static_task_completed'])
        self.assertTrue(r['static']['implementation_static']['passed'])
        self.assertIn('assertion_operator_mismatch',[d['code'] for d in r['feedback']])

    def test_partial_multifile_task_reports_missing_work(self):
        r=self.run_case(lambda c:c[:1]);self.assertEqual(r['successful_edits'],1)
        self.assertFalse(r['static_task_completed'])
        self.assertTrue(any(d['code']=='required_file_unchanged' and d['filename']=='test_unique_order.py' for d in r['feedback']))

    def test_literal_newline_rejection_preserves_entire_batch(self):
        def escaped(c):c[1]['old_text']=c[1]['old_text'].replace('\n',r'\n');return c
        r=self.run_case(escaped);self.assertEqual(r['successful_edits'],0)
        self.assertEqual(r['budget_used'],2)
        self.assertTrue(r['staging']['events'][0]['diagnostic']['literal_backslash_n'])
        self.assertEqual(r['staging']['initial_files'],r['staging']['final_files'])

    def test_unauthorized_batch_still_writes_nothing(self):
        def outside(c):c[1]['filename']='outside.py';return c
        r=self.run_case(outside);self.assertEqual(r['successful_edits'],0)
        self.assertIn('proposal_rejected',[d['code'] for d in r['feedback']])


class ProvenanceAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        task=build_plan()['tasks'][3]
        files={task['module']:task['reference_source'],task['test_file']:
               task['expected_test_source'].replace('result is not values','result != values')}
        content=json.dumps({'version':1,'changes':[change(task['test_file'],
            task['initial_files'][task['test_file']],files[task['test_file']])]})
        saved={'message':{'content':content}}
        self.snapshot=self.root/'snapshot.json'
        self.snapshot.write_text(json.dumps({'files':files,'sha256':{
            n:hashlib.sha256(t.encode()).hexdigest() for n,t in files.items()}}),encoding='utf-8')
        self.report={'plan':{'tasks':[task]},'attempts':[{'attempt_id':'fake','task':task['id'],
            'raw_content':content,'raw_response':saved,'candidate_files':files,
            'candidate_snapshot_path':str(self.snapshot),'payload':{'messages':[{},
                {'content':json.dumps({'task':task['description'],'initial_files':task['initial_files']})}]}}]}
        (self.root/'step42_fake_response.json').write_text(json.dumps(saved),encoding='utf-8')
        self.save()

    def save(self):
        (self.root/'step42_live_results.json').write_text(json.dumps(self.report),encoding='utf-8')

    def test_archive_and_parser_evidence_is_data_only(self):
        from evaluations.analyze_step42_contracts import analyze
        with patch('ollama.Client',side_effect=AssertionError('No model')):
            r=analyze(self.root)
        self.assertTrue(r['rows'][0]['independent_decoder_agrees'])
        self.assertTrue(r['rows'][0]['identity_requirement_present_in_request'])
        self.assertFalse(r['rows'][0]['contract']['passed'])
        self.assertTrue(any('HTTP' in x for x in r['limitations']))

    def test_inconsistent_archive_and_bad_snapshot_fail_closed(self):
        from evaluations.analyze_step42_contracts import analyze
        self.report['attempts'][0]['raw_content']='{}';self.save()
        with self.assertRaises(ValueError):analyze(self.root)
        self.report['attempts'][0]['raw_content']=self.report['attempts'][0]['raw_response']['message']['content'];self.save()
        snap=json.loads(self.snapshot.read_text(encoding='utf-8'));snap['sha256'][next(iter(snap['sha256']))]='0'*64
        self.snapshot.write_text(json.dumps(snap),encoding='utf-8')
        with self.assertRaises(ValueError):analyze(self.root)
