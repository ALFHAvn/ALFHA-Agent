"""Exact-context diagnostics; no live requests or candidate execution."""
import copy
import json
from pathlib import Path
import unittest

from git_checkpoints import SafetyError, _git
from proposal_protocol import (proposal_messages, validate_changes, ProposalValidationError,
                              _target_context_hint)
import test_coding_workflow as fixtures
import test_interactive_review as review_fixtures

SOURCE = 'from duration import format_duration\n\n\ndef test_zero():\n    assert format_duration(0) == "0:00"\n'
WRONG = ['from duration import format_duration', '', 'def test_zero():',
         '    assert format_duration(0) == "0:00"']


class ContextTests(unittest.TestCase):
    def request(self):
        return {'description':'Change A only', 'source_repository':str(Path.cwd()),
                'authorized_files':{'a.py':['read','modify']},
                'validation_requirements':{'static':True,'docker_execution':False}}

    def test_opt_in_preserves_every_source_element_and_legacy_default(self):
        req = self.request(); contents = {'a.py': SOURCE}
        original = copy.deepcopy(contents)
        default = proposal_messages(req, contents, allow_line_arrays=True)
        explicit = proposal_messages(req, contents, allow_line_arrays=True, include_source_lines=False)
        self.assertEqual(default, explicit)
        self.assertNotIn('initial_file_lines', json.loads(default[1]['content']))
        enabled = proposal_messages(req, contents, allow_line_arrays=True, include_source_lines=True)
        context = json.loads(enabled[1]['content'])
        self.assertEqual(context['initial_file_lines']['a.py'], SOURCE.split('\n'))
        self.assertEqual(context['initial_file_lines']['a.py'][1:3], ['', ''])
        self.assertEqual(context['initial_file_lines']['a.py'][-1], '')
        self.assertIn('Never collapse or omit', enabled[0]['content'])
        self.assertEqual(contents, original)

    def test_context_option_cannot_enable_protocol_or_expand_paths(self):
        for value in (1, None, 'yes'):
            with self.assertRaises(SafetyError):
                proposal_messages(self.request(), {'a.py':SOURCE}, allow_line_arrays=True,
                                  include_source_lines=value)
        with self.assertRaises(SafetyError):
            proposal_messages(self.request(), {'a.py':SOURCE}, include_source_lines=True)
        with self.assertRaises(SafetyError):
            proposal_messages(self.request(), {'outside.py':SOURCE}, allow_line_arrays=True,
                              include_source_lines=True)

    def test_saved_failure_shape_reports_missing_empty_line_without_repair(self):
        change = review_fixtures.line('a.py', WRONG, ['A = 2'])
        with self.assertRaises(ProposalValidationError) as caught:
            validate_changes([change], {'a.py':['read','modify']}, {'a.py':SOURCE}, allow_line_arrays=True)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic['code'], 'replacement_not_found')
        self.assertEqual(diagnostic['match_count'], 0)
        hint = diagnostic['context_hint']
        self.assertEqual((hint['source_start_line'],hint['source_end_line']), (1,5))
        self.assertEqual((hint['source_empty_lines'],hint['proposed_empty_lines']), (2,1))
        self.assertEqual(hint['source_line'], '')
        self.assertEqual(hint['proposed_line'], 'def test_zero():')
        self.assertIn('no whitespace normalization', diagnostic['message'])
        self.assertFalse(diagnostic['literal_backslash_n'])

    def test_correct_exact_target_remains_accepted(self):
        old = SOURCE.split('\n')
        change = review_fixtures.line('a.py',old, ['A = 2',''])
        self.assertEqual(validate_changes([change],{'a.py':['read','modify']}, {'a.py':SOURCE},
                                         allow_line_arrays=True), {'a.py':'A = 2\n'})

    def test_no_hint_for_nonunique_or_unbounded_context(self):
        target = '\n'.join(WRONG)
        self.assertIsNone(_target_context_hint(SOURCE + SOURCE, target))
        self.assertIsNone(_target_context_hint(SOURCE, 'missing\nend'))
        self.assertIsNone(_target_context_hint('x\n'*3000+'last', 'x\nlast'))
        self.assertIsNone(_target_context_hint(SOURCE, '\n'.join(['x']*201)))

    def test_ambiguity_and_unauthorized_paths_do_not_get_context(self):
        with self.assertRaises(ProposalValidationError) as caught:
            validate_changes([review_fixtures.line(old=['x'],new=['y'])],
                             {'a.py':['read','modify']}, {'a.py':'x\nx'}, allow_line_arrays=True)
        self.assertEqual(caught.exception.diagnostic['code'], 'ambiguous_replacement')
        self.assertNotIn('context_hint', caught.exception.diagnostic)
        with self.assertRaises(SafetyError) as caught:
            validate_changes([review_fixtures.line('outside.py',WRONG,['x'])],
                             {'a.py':['read','modify']}, {'outside.py':SOURCE}, allow_line_arrays=True)
        self.assertNotIsInstance(caught.exception, ProposalValidationError)


class ContextGitTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    request = fixtures.WorkflowTests.request
    run_mock = review_fixtures.ReviewTests.run_mock

    def test_missing_empty_line_rejects_both_files_and_retains_diagnostic(self):
        (self.root/'b.py').write_bytes(SOURCE.encode())
        _git(self.root,'add','b.py'); _git(self.root,'commit','--quiet','-m','Context fixture')
        result, calls = self.run_mock(review_fixtures.reply(review_fixtures.line(),
                                      review_fixtures.line('b.py',WRONG,['B = 3'])))
        self.assertEqual(result['accepted_changes'], [])
        self.assertEqual(result['combined_diff'], '')
        self.assertEqual(result['budget_used'], 2)
        self.assertEqual(result['rejected_changes'][0]['diagnostic']['context_hint']['source_empty_lines'],2)
        self.assertEqual(result['final_files']['a.py'],'A = 1\n')
        self.assertEqual(result['final_files']['b.py'], SOURCE)
        self.assertTrue(result['source_unchanged'])
        context = json.loads(calls[0]['messages'][1]['content'])
        self.assertEqual(context['initial_file_lines']['b.py'],SOURCE.split('\n'))
        self.assertEqual(result['prompt_version'],'v2-exact-source-lines-1')
