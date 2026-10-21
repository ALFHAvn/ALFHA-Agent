"""Installed Ollama transport contract and deterministic recovery/phase tests."""
import json
import unittest
from pathlib import Path
import httpx
import ollama

from coding_protocol import parse_text, available_tools
from coding_workflow import TOOLS, SIGNATURES, validate_request
from git_checkpoints import SafetyError
import test_coding_workflow as workflow_tests
from test_coding_workflow import response


class SDKContractTests(unittest.TestCase):
    def test_installed_sdk_roundtrips_native_tools_and_named_results(self):
        captured = []
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'model': 'qwen3:4b', 'message': {
                'role': 'assistant', 'content': '', 'tool_calls': [
                    {'function': {'name': 'read_file', 'arguments': {'filename': 'a.py'}}}]}, 'done': True})
        client = ollama.Client(host='http://127.0.0.1:11434', transport=httpx.MockTransport(handle))
        result = client.chat(model='qwen3:4b', tools=TOOLS, stream=False,
                             messages=[{'role': 'tool', 'tool_name': 'read_file', 'content': 'data'}])
        self.assertEqual(result.model_dump(mode='json')['message']['tool_calls'][0]['function']['name'], 'read_file')
        self.assertEqual(captured[0]['messages'][0]['tool_name'], 'read_file')
        self.assertEqual(captured[0]['tools'][1]['function']['parameters']['required'], ['filename', 'old_text', 'new_text'])
        self.assertFalse(captured[0]['stream'])
        self.assertNotIn('format', captured[0])
        self.assertNotIn('think', captured[0])

    def test_parser_rejects_arrays_duplicate_keys_fences_and_extra_fields(self):
        for text in ('[]', '[{"name":"read_file","arguments":{}}]', '{',
                     '{"name":"a","name":"b","arguments":{}}',
                     '```json\n{"name":"read_file","arguments":{}}\n```',
                     '{"name":"read_file","arguments":{},"extra":1}'):
            kind, value, _ = parse_text(text)
            self.assertIn(kind, ('multiple', 'malformed'))
            self.assertIsNone(value)

    def test_phase_schemas_only_expose_relevant_operations_and_filename_enums(self):
        auth={'a.py':['read','modify'],'b.py':['read','modify'],'new.py':['create']}
        policy={'inspection_first':True,'single_json_recovery':False}
        tools,phase=available_tools(TOOLS,SIGNATURES,auth,policy,set())
        self.assertEqual(phase,'inspection')
        self.assertEqual([t['function']['name'] for t in tools],['read_file'])
        self.assertEqual(tools[0]['function']['parameters']['properties']['filename']['enum'],['a.py','b.py'])
        tools,phase=available_tools(TOOLS,SIGNATURES,auth,policy,{'a.py','b.py'})
        self.assertEqual(phase,'editing')
        self.assertNotIn('delete_file',[t['function']['name'] for t in tools])

    def test_recovery_flags_and_required_targets_must_be_explicit_valid_authority(self):
        request={'description':'task','source_repository':str(Path.cwd()),'authorized_files':{'a.py':['read','modify']},
                 'validation_requirements':{'static':True,'docker_execution':False}}
        for extra in ({'tool_policy':{'inspection_first':True,'single_json_recovery':1}},
                      {'required_changed_files':['outside.py']}):
            with self.assertRaises(SafetyError):
                validate_request({**request,**extra})


# Reuse fixture helpers without inheriting/rerunning the 17 baseline tests.
class ProtocolWorkflowTests(unittest.TestCase):
    setUp = workflow_tests.WorkflowTests.setUp
    tearDown = workflow_tests.WorkflowTests.tearDown
    request = workflow_tests.WorkflowTests.request
    run_replies = workflow_tests.WorkflowTests.run_replies
    edits = workflow_tests.WorkflowTests.edits

    def policy_request(self, inspect=False, recover=True):
        request = self.request()
        request['tool_policy'] = {'inspection_first': inspect, 'single_json_recovery': recover}
        return request

    def proposal(self, name, arguments):
        return response(text=json.dumps({'name': name, 'arguments': arguments}))

    def test_valid_single_read_recovery_is_explicit_and_counted(self):
        r = self.run_replies([self.proposal('read_file', {'filename': 'a.py'}), self.edits(), response(text='Done')], self.policy_request())
        self.assertEqual(r['recovered_calls'], 1)
        self.assertEqual(r['successful_recoveries'], 1)
        self.assertEqual(r['budget_used'], 3)
        self.assertTrue(r['ready_for_human_review'])

    def test_single_edit_recovery_requires_prior_read(self):
        request = self.policy_request()
        request['required_changed_files'] = ['a.py']
        edit = {'filename': 'a.py', 'old_text': 'A = 1', 'new_text': 'A = 8'}
        r = self.run_replies([response(('read_file', {'filename': 'a.py'})), self.proposal('edit_file', edit), response(text='Done')], request)
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['budget_used'], 2)

    def test_uninspected_recovery_edit_rejected(self):
        r = self.run_replies([self.proposal('edit_file', {'filename': 'a.py', 'old_text': 'A = 1', 'new_text': 'A = 8'}), response(text='Done'), response(text='Done')], self.policy_request())
        self.assertEqual(r['recovered_calls'], 1)
        self.assertEqual(r['trace'][0]['status'], 'rejected')
        self.assertEqual(r['review']['modified_paths'], [])

    def test_multiple_proposals_never_dispatched_then_native_correction(self):
        text=json.dumps([{'name':'read_file','arguments':{'filename':'a.py'}}, {'name':'delete_file','arguments':{'filename':'b.py'}}])
        r=self.run_replies([response(text=text), self.edits(), response(text='Done')],self.policy_request())
        self.assertEqual(r['recovered_calls'],0)
        self.assertEqual(r['budget_used'],2)
        self.assertEqual(r['correction_prompts'],1)
        self.assertTrue(r['ready_for_human_review'])

    def test_malformed_json_and_empty_response_stop_after_one_reminder(self):
        r=self.run_replies([response(text='{'),response(text='')],self.policy_request())
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(r['budget_used'],0)
        self.assertEqual(r['model_requests'],2)

    def test_unauthorized_single_proposal_consumes_only_one_recovery(self):
        r=self.run_replies([self.proposal('read_file',{'filename':'outside.py'}),
                            self.proposal('read_file',{'filename':'a.py'}),response(text='Stopped')],self.policy_request())
        self.assertEqual(r['recovered_calls'],1)
        self.assertEqual(r['budget_used'],1)
        self.assertEqual(r['trace'][0]['status'],'rejected')

    def test_wrong_argument_names_and_nonmatching_edit_fail_closed(self):
        request=self.policy_request()
        r=self.run_replies([response(('read_file',{'filename':'a.py'})),
                            self.proposal('edit_file',{'filename':'a.py','content':'wrong'}),
                            response(('edit_file',{'filename':'a.py','old_text':'placeholder','new_text':'bad'})),
                            response(text='Stopped'),response(text='Stopped')],request)
        self.assertEqual(r['review']['modified_paths'],[])
        self.assertEqual(len(r['rejected_actions']),2)
        self.assertEqual(r['budget_used'],3)

    def test_inspection_phase_exposes_only_reads_and_rejects_early_edit(self):
        r=self.run_replies([response(('edit_file',{'filename':'a.py','old_text':'A = 1','new_text':'A = 8'})),
                            response(('read_file',{'filename':'a.py'}),('read_file',{'filename':'b.py'})),
                            self.edits(),response(text='Done')],self.policy_request(inspect=True))
        self.assertTrue(r['ready_for_human_review'])
        self.assertEqual(r['budget_used'],5)
        self.assertEqual(r['trace'][0]['status'],'rejected')

    def test_incomplete_multifile_changes_are_not_completion(self):
        r=self.run_replies([response(('edit_file',{'filename':'a.py','old_text':'A = 1','new_text':'A = 8'})),
                            response(text='Done'),response(text='Done')])
        self.assertEqual(r['status'],'incomplete')
        self.assertEqual(r['missing_required_changes'],['b.py'])
        self.assertFalse(r['ready_for_human_review'])

    def test_feedback_uses_installed_tool_name_field(self):
        self.run_replies([self.edits(),response(text='Done')])
        feedback=[m for m in self.messages[-1] if m.get('role')=='tool']
        self.assertEqual([m['tool_name'] for m in feedback],['edit_file','edit_file'])
        self.assertTrue(all('name' not in m for m in feedback))

    def test_recovered_call_shares_six_call_budget(self):
        r=self.run_replies([response(*[('read_file',{'filename':'a.py'})]*5),
                            self.proposal('read_file',{'filename':'b.py'})],self.policy_request())
        self.assertEqual(r['budget_used'],6)
        self.assertEqual(r['native_calls_requested'],5)
        self.assertEqual(r['recovered_calls'],1)
        self.assertEqual(r['status'],'budget_exhausted')


if __name__ == '__main__':
    unittest.main()
