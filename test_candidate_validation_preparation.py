"""Step 39 preparation only; no model, worker or Docker execution."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from evaluations.prepare_candidate_validation import tasks, prepare, digest, MODELS
from evaluations.functional_validation import validate_source
from evaluations.functional_harness import task_by_id, make_request, FunctionalHarness, profile_hash
from evaluations.preserved_tasks import preserved_task


class CandidatePreparationTests(unittest.TestCase):
    def test_original_examples_and_extra_checks_are_explicit(self):
        t = tasks()['B']
        self.assertEqual(len(t['tests']), 12)
        by_name = {x['name']: x for x in t['tests']}
        self.assertEqual(by_name['discards_empty']['args'], [['', '   ', '\t']])
        self.assertEqual(by_name['deduplicates_in_order']['expected'], ['blue', 'red', 'green'])
        self.assertIn('returned list is not the supplied input list, including empty input', t['assertions'])

    def test_policy_not_extended_for_strip(self):
        source = 'def normalize_tags(tags):\n    return [tag.strip().lower() for tag in tags]\n'
        checks = validate_source(source, tasks()['B'])
        self.assertFalse(checks['static_policy_passed'])
        self.assertIn('Unsupported attribute: strip', checks['diagnostics'])

    def test_add_one_language_policy_accepted_without_execution(self):
        self.assertTrue(validate_source('def add_one(value):\n    return value + 1\n', tasks()['A'])['static_policy_passed'])
        self.assertEqual(len(tasks()['A']['tests']), 6)

    def evidence(self, root):
        attempts = []
        for index in range(1, 7):
            s = 'A' if index % 2 else 'B'
            files = ({'syntax_target.py': 'def add_one(value):\n    return value + 1\n'} if s == 'A' else
                     {'tag_utils.py': 'def normalize_tags(tags):\n    return [x.strip() for x in tags]\n',
                      'test_tag_utils.py': 'DO_NOT_EXECUTE = True\n'})
            stage = {'status': 'prepared', 'workspace_discarded': True, 'final_files': files,
                     'review': {'modified_paths': list(files), 'per_file': [
                         {'filename': name, 'sha256': digest(text.encode())} for name, text in files.items()]},
                     'accepted_changes': [{'filename': name, 'sha256': digest(text.encode())} for name, text in files.items()]}
            (root/f'step38b_{index:02d}_{s}_staging.json').write_text(json.dumps(stage), encoding='utf-8')
            attempts.append({'index': index, 'model': MODELS[(index-1)//2], 'scenario': s,
                             'status': 'completed', 'candidate_files': copy.deepcopy(files), 'staging_report': stage})
        plan = Path('evaluations/step38_plan.json').read_bytes()
        live = {'status': 'completed', 'attempts': attempts, 'plan_sha256': digest(plan), 'run_id': 'offline-test'}
        (root/'step38b_live_comparison.json').write_text(json.dumps(live), encoding='utf-8')
        return live

    def test_snapshot_preservation_and_no_execution_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.evidence(root)
            with patch('ollama.Client', side_effect=AssertionError('No model')):
                result = prepare(root)
            self.assertEqual(len(result['candidates']), 6)
            self.assertEqual(len(result['associated_test_snapshots']), 3)
            self.assertTrue(all(not x['execution_permitted'] for x in result['candidates']))
            self.assertEqual(sum(x['worker_task_registered'] for x in result['candidates']), 3)
            self.assertEqual(sum(x['policy']['static_policy_passed'] for x in result['candidates']), 3)

    def test_missing_snapshots_not_reconstructed_from_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); live = self.evidence(root)
            live['attempts'][0].pop('candidate_files')
            (root/'step38b_live_comparison.json').write_text(json.dumps(live), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'no reconstruction'):
                prepare(root)

    def test_tampered_final_hash_rejected_even_when_snapshots_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); live = self.evidence(root)
            row = live['attempts'][0]; row['candidate_files']['syntax_target.py'] += '# altered\n'
            row['staging_report']['final_files'] = row['candidate_files']
            (root/'step38b_01_A_staging.json').write_text(json.dumps(row['staging_report']), encoding='utf-8')
            (root/'step38b_live_comparison.json').write_text(json.dumps(live), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash'):
                prepare(root)

    def test_independent_record_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.evidence(root)
            (root/'step38b_01_A_staging.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'record mismatch'):
                prepare(root)

    def test_fixed_registration_does_not_change_canonical_suite_or_accept_other_tasks(self):
        from evaluations.functional_validation import load_tasks
        self.assertEqual(len(load_tasks()), 5)
        self.assertEqual(sum(len(t['tests']) for t in load_tasks()), 29)
        with self.assertRaises(ValueError): task_by_id('step39_normalize_tags')
        with self.assertRaises(ValueError): task_by_id('arbitrary_task')
        value = preserved_task('step39_add_one'); value['tests'][0]['expected'] = -99
        self.assertEqual(task_by_id('step39_add_one')['tests'][0]['expected'], 1)

    def test_registered_request_excludes_expected_and_report_paths(self):
        request = make_request('step39_add_one', 'def add_one(value):\n    return value + 1\n')
        self.assertEqual(request['function'], 'add_one')
        self.assertEqual(request['vectors'], [{'args': [v]} for v in [0, 1, -1, 41, -8, 1000000]])
        self.assertNotIn('expected', json.dumps(request))
        with self.assertRaises(ValueError):
            make_request('step39_add_one', 'import os\ndef add_one(value):\n    return value + 1\n')

    def test_registered_task_still_cannot_execute_without_current_verification(self):
        from unittest.mock import Mock
        backend = Mock(); backend.verify.return_value = {'verified': False}
        harness = FunctionalHarness(backend)
        result = harness.run('step39_add_one', 'def add_one(value):\n    return value + 1\n')
        self.assertEqual(result['status'], 'blocked')
        backend.run_verified_worker.assert_not_called()

    def test_new_trusted_profile_is_bound_by_existing_profile_hash(self):
        original = Path.read_bytes
        baseline = profile_hash()
        def read(path):
            data = original(path)
            return data + b'\n# changed' if path.name == 'preserved_tasks.py' else data
        with patch.object(Path, 'read_bytes', read):
            self.assertNotEqual(baseline, profile_hash())
