"""Mocked generation and real disposable Git; no live requests or execution."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from ollama import ChatResponse
import test_coding_workflow as fixtures
from git_checkpoints import SafetyError, _source_snapshot
import interactive_review as review
import resource_readiness as resources
from evaluations.dependency_preflight import check_dependencies


def line(name='a.py', old=None, new=None):
    return {'operation': 'replace_lines', 'filename': name,
            'old_lines': ['A = 1', ''] if old is None else old,
            'new_lines': ['A = 3', ''] if new is None else new}


def reply(*changes, version=2):
    return ChatResponse(message={'role': 'assistant', 'content': json.dumps({'version': version, 'changes': list(changes)})})


class ResourceTests(unittest.TestCase):
    def sample(self):
        return {'physical_total': 16*resources.GIB, 'physical_available': 8*resources.GIB,
                'commit_limit': 26*resources.GIB, 'commit_used': 12*resources.GIB,
                'other_python_processes': []}

    def check(self, value):
        return resources.check_readiness(sampler=lambda: value, pause=lambda _: None)

    def test_three_valid_samples_and_no_stability_claim(self):
        report = self.check(self.sample())
        self.assertTrue(report['ready']); self.assertEqual(len(report['samples']), 3)
        self.assertFalse(report['stability_guaranteed'])

    def test_low_ram_or_commit_fails_closed(self):
        for field, value in (('physical_available', 1), ('commit_used', 25*resources.GIB)):
            sample=self.sample();sample[field]=value
            report=self.check(sample)
            self.assertFalse(report['ready']);self.assertIn('Insufficient memory',report['errors'][0])

    def test_missing_invalid_or_inconsistent_memory(self):
        for value in (None, {}, {'commit_limit':True}, dict(self.sample(), commit_used=-1),
                      dict(self.sample(), physical_available=30*resources.GIB),
                      dict(self.sample(), other_python_processes=None)):
            self.assertFalse(self.check(value)['ready'])

    def test_unavailable_snapshot(self):
        with patch.object(resources,'memory_snapshot',side_effect=OSError('No evidence')):
            self.assertFalse(resources.check_readiness()['ready'])

    def test_later_sample_pressure_is_not_ignored(self):
        samples=iter([self.sample(),dict(self.sample(),physical_available=0)])
        self.assertFalse(resources.check_readiness(sampler=lambda:next(samples),pause=lambda _:None)['ready'])

    def test_competing_job_blocks_readiness(self):
        self.assertFalse(self.check(dict(self.sample(),other_python_processes=[{'pid':99}]))['ready'])

    def test_mutual_exclusion_and_release(self):
        # Fresh local test lock; OS mutex remains reentrant under the outer
        # trusted regression runner, with no actual competing work performed.
        with patch.object(resources,'_local',threading.Lock()), patch.object(resources,'other_python_processes',return_value=[]):
            with resources.workload_guard('generation'):
                with self.assertRaises(SafetyError):
                    with resources.workload_guard('docker'):pass
            with self.assertRaisesRegex(RuntimeError,'controlled'):
                with resources.workload_guard('generation'):raise RuntimeError('controlled')
            with resources.workload_guard('regression'):pass

    def test_static_dependencies_do_not_contact_docker(self):
        def metadata(method,path,payload=None):
            if path=='/api/tags':return {'models':[{'model':'qwen3:4b','digest':'a'*64}]}
            return {'capabilities':['completion','tools'],'template':'template'}
        result=check_dependencies(metadata=metadata,require_docker=False,
                                  docker_factory=lambda:(_ for _ in ()).throw(AssertionError('No Docker')))
        self.assertTrue(result['ready']);self.assertEqual(result['checks']['docker_engine']['status'],'not_required')
        self.assertFalse(result['execution_authorized']);self.assertFalse(result['isolation_verified'])

    def test_real_docker_exclusion_fails_closed_before_commands(self):
        from evaluations.docker_transport import DockerTransport, bounded_command, IsolationError
        transport=object.__new__(DockerTransport);transport.runner=bounded_command
        with patch.object(resources,'workload_guard',side_effect=SafetyError('busy')),\
             patch.object(transport,'_run_controlled',side_effect=AssertionError('No Docker')):
            with self.assertRaises(IsolationError) as caught:transport.run_controlled('trusted reference')
        self.assertEqual(caught.exception.failure['category'],'workload_unavailable')


class ReviewTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown
    request=fixtures.WorkflowTests.request

    def run_mock(self, response, request=None, resources_ok=True, action=None, readiness_reports=None):
        before=_source_snapshot(self.root);calls=[]
        def chat(**payload):
            calls.append(payload)
            self.assertEqual(payload['model'],'qwen3:4b')
            self.assertEqual(payload['format']['properties']['version']['const'],2)
            self.assertNotIn('tools',payload)
            if action:action()
            if isinstance(response,BaseException):raise response
            return response
        with patch.object(review,'check_readiness',side_effect=readiness_reports,return_value={'ready':resources_ok,'errors':[] if resources_ok else ['Low commit']}),\
             patch.object(review,'check_dependencies',return_value={'ready':True}),\
             patch.object(review,'workload_guard',side_effect=lambda _:nullcontext()),\
             patch.object(review,'Client',side_effect=AssertionError('No live model')):
            result=review.run_review(request or self.request(),chat_fn=chat)
        self.reports.append(Path(result['report_path']))
        self.assertEqual(json.loads(self.reports[-1].read_bytes()),result)
        if not action:self.assertEqual(before,_source_snapshot(self.root))
        self.assertTrue(result['workspace_discarded'])
        self.assertLessEqual(len(calls),1)
        self.assertFalse(result['source_application'])
        return result,calls

    def test_one_file_success(self):
        req=self.request();req['authorized_files']={'a.py':['read','modify']}
        result,calls=self.run_mock(reply(line()),req)
        self.assertTrue(result['ready_for_human_review']);self.assertEqual(len(calls),1)
        self.assertIn('+A = 3',result['combined_diff']);self.assertEqual(result['budget_used'],1)

    def test_two_file_success_and_retained_hashes(self):
        result,_=self.run_mock(reply(line(),line('b.py',['B = 2',''],['B = 3',''])))
        self.assertTrue(result['ready_for_human_review']);self.assertEqual(len(result['candidate_hashes']),2)
        self.assertEqual(result['validation']['passed'],True)

    def test_default_client_is_loopback_without_proxy_or_redirects(self):
        before=_source_snapshot(self.root)
        with patch.object(review,'check_readiness',return_value={'ready':True,'errors':[]}),\
             patch.object(review,'check_dependencies',return_value={'ready':True}),\
             patch.object(review,'workload_guard',side_effect=lambda _:nullcontext()),\
             patch.object(review,'Client') as client:
            client.return_value.chat.return_value=reply(line(),line('b.py',['B = 2',''],['B = 3','']))
            result=review.run_review(self.request())
        self.reports.append(Path(result['report_path']))
        client.assert_called_once_with(host='http://127.0.0.1:11434',timeout=180,trust_env=False,follow_redirects=False)
        client.return_value.chat.assert_called_once()
        self.assertTrue(result['ready_for_human_review']);self.assertEqual(before,_source_snapshot(self.root))

    def test_read_only_file_is_context_not_edit_target(self):
        req=self.request();req['authorized_files']['b.py']=['read']
        result,calls=self.run_mock(reply(line()),req)
        self.assertTrue(result['ready_for_human_review'])
        self.assertIn('b.py',json.loads(calls[0]['messages'][1]['content'])['initial_files'])
        result,_=self.run_mock(reply(line('b.py',['B = 2'],['B = 3'])),req)
        self.assertFalse(result['ready_for_human_review']);self.assertEqual(result['accepted_changes'],[])

    def test_unauthorized_second_path_rejects_batch_atomically(self):
        result,_=self.run_mock(reply(line(),line('../outside.py')))
        self.assertEqual(result['accepted_changes'],[]);self.assertEqual(result['combined_diff'],'')
        self.assertEqual(result['budget_used'],2)

    def test_invalid_array_rejects_entire_batch(self):
        result,_=self.run_mock(reply(line(),line('b.py',['B = 2',''],[None])))
        self.assertEqual(result['accepted_changes'],[]);self.assertFalse(result['ready_for_human_review'])

    def test_missing_and_ambiguous_replacements(self):
        result,_=self.run_mock(reply(line(old=['missing'])))
        self.assertIn('found 0',result['rejected_changes'][0]['error'])
        from git_checkpoints import _git
        (self.root/'a.py').write_bytes(b'A = 1\nA = 1\n')
        _git(self.root,'add','a.py');_git(self.root,'commit','--quiet','-m','Ambiguous fixture')
        result,_=self.run_mock(reply(line(old=['A = 1'],new=['A = 2'])))
        self.assertIn('found 2',result['rejected_changes'][0]['error'])

    def test_six_operation_cap_no_partial_edits(self):
        result,_=self.run_mock(reply(*[line() for _ in range(7)]))
        self.assertEqual(result['budget_used'],6);self.assertEqual(result['accepted_changes'],[])

    def test_legacy_version_rejected_without_fallback(self):
        result,_=self.run_mock(reply(line(),version=1))
        self.assertEqual(result['status'],'rejected');self.assertNotIn('staging',result)

    def test_malformed_text_and_native_calls_never_dispatch(self):
        for response in (ChatResponse(message={'role':'assistant','content':'not json'}),
                         ChatResponse(message={'role':'assistant','content':'','tool_calls':[{'function':{'name':'run','arguments':{}}}]})):
            result,_=self.run_mock(response)
            self.assertEqual(result['status'],'rejected');self.assertEqual(result['accepted_changes'],[])

    def test_partial_task_and_invalid_syntax_not_complete(self):
        result,_=self.run_mock(reply(line()))
        self.assertFalse(result['ready_for_human_review']);self.assertEqual(result['missing_required_changes'],['b.py'])
        result,_=self.run_mock(reply(line(new=['def broken('])))
        self.assertFalse(result['validation']['passed']);self.assertFalse(result['ready_for_human_review'])

    def test_resource_failure_has_no_generation_or_staging(self):
        with patch.object(review.MultiFileTask,'prepare',side_effect=AssertionError('No staging')):
            result,calls=self.run_mock(reply(line()),resources_ok=False)
        self.assertEqual(calls,[]);self.assertEqual(result['status'],'resource_rejected')

    def test_pressure_after_inspection_prevents_generation(self):
        result,calls=self.run_mock(reply(line()),readiness_reports=[{'ready':True,'errors':[]},
            {'ready':False,'errors':['Commit headroom fell']}])
        self.assertEqual(calls,[]);self.assertEqual(result['status'],'resource_rejected')

    def test_pressure_after_response_prevents_staging(self):
        with patch.object(review,'run_proposals',side_effect=AssertionError('No staging')):
            result,calls=self.run_mock(reply(line()),readiness_reports=[{'ready':True,'errors':[]}]*2+
                [{'ready':False,'errors':['Memory pressure after response']}])
        self.assertEqual(len(calls),1);self.assertNotIn('staging',result)
        self.assertEqual(result['status'],'resource_rejected')

    def test_inspection_error_still_discards_owned_workspace(self):
        with patch.object(review.MultiFileTask,'read_text',side_effect=SafetyError('controlled read failure')):
            result,calls=self.run_mock(reply(line()))
        self.assertEqual(calls,[]);self.assertEqual(result['status'],'rejected')

    def test_root_authorization_precedes_source_fingerprinting(self):
        with patch.object(review.MultiFileTask,'prepare',side_effect=SafetyError('Root/link rejected')),\
             patch.object(review,'_source_snapshot',side_effect=AssertionError('No unvalidated fingerprint')):
            result,calls=self.run_mock(reply(line()))
        self.assertEqual(calls,[]);self.assertEqual(result['status'],'rejected')

    def test_interruption_preserves_evidence_without_retry(self):
        result,calls=self.run_mock(KeyboardInterrupt())
        self.assertEqual(result['status'],'interrupted');self.assertEqual(len(calls),1)
        self.assertFalse(result['ready_for_human_review'])

    def test_source_change_during_generation_rejects_proposal(self):
        result,_=self.run_mock(reply(line()),action=lambda:(self.root/'a.py').write_text('A = 9\n'))
        self.assertEqual(result['status'],'stale');self.assertNotIn('staging',result)
        self.assertEqual((self.root/'a.py').read_text(),'A = 9\n')

    def test_invalid_authorization_before_preflight(self):
        req=self.request();req['authorized_files']['a.py']=['modify']
        with patch.object(review,'check_readiness',side_effect=AssertionError('No preflight')),self.assertRaises(SafetyError):
            review.run_review(req)

    def test_cli_cancel_never_generates(self):
        answers=iter([str(self.root),'Fix A','a.py','','','no'])
        with patch.object(review,'run_review',side_effect=AssertionError('No request')):
            self.assertEqual(review.main(lambda _:next(answers),lambda _:None),0)

    def test_cli_report_display(self):
        result,_=self.run_mock(reply(line()))
        output=[];review.display_review(result,output.append)
        self.assertTrue(any('Missing required changes' in x for x in output))
        self.assertTrue(any('Preserved report' in x for x in output))


class EntryPointTests(unittest.TestCase):
    def test_default_entrypoint_preserves_legacy(self):
        import main
        with patch.object(main,'main',return_value=0) as legacy,patch.object(review,'main',side_effect=AssertionError('No review')):
            self.assertEqual(main.cli([]),0);legacy.assert_called_once_with()

    def test_review_entrypoint_routes_only_to_review(self):
        import main
        with patch.object(main,'main',side_effect=AssertionError('No legacy')),patch.object(review,'main',return_value=0) as routed:
            self.assertEqual(main.cli(['--review']),0);routed.assert_called_once_with()

    def test_extra_review_flags_cannot_fall_back_to_legacy(self):
        import main
        with patch.object(main,'main',side_effect=AssertionError('No legacy')),patch.object(review,'main',side_effect=AssertionError('No review')):
            self.assertEqual(main.cli(['--review','--apply']),2)

    def test_unknown_flags_never_start_generation(self):
        import main
        with patch.object(main,'main',side_effect=AssertionError('No legacy')),patch.object(review,'main',side_effect=AssertionError('No review')):
            self.assertEqual(main.cli(['--unknown']),2)


if __name__=='__main__':unittest.main()
