import unittest
from unittest.mock import patch

from ollama import ChatResponse
from evaluations import benchmark_reliability as bench


class BenchmarkReportingTests(unittest.TestCase):
    def test_empty_summary(self):
        self.assertIsNone(bench.summarize([])['overall']['success_rate'])

    def test_real_call_and_retry_counts(self):
        replies = iter([
            ChatResponse(message={'role': 'assistant', 'content': 'I will inspect it.'}),
            ChatResponse(message={'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'check_python_syntax', 'arguments': {'filename': 'valid_code.py'}}}
            ]}),
            ChatResponse(message={'role': 'assistant', 'content': 'Done.'}),
        ])
        with patch.object(bench.alfha, 'chat', side_effect=lambda **kw: next(replies)):
            result = bench.measured_case(bench.CASES / 'valid_code.py')
        self.assertTrue(result['passed'])
        self.assertEqual(result['model_requests'], 3)
        self.assertEqual(result['retry_prompts'], 1)
        self.assertEqual(result['native_calls_requested'], 1)
        self.assertEqual(result['native_calls_dispatched'], 1)
        self.assertEqual(result['recovered_json_calls'], 0)
        summary = bench.summarize([result])
        self.assertEqual(summary['overall']['success_rate'], 1)
        self.assertEqual(summary['overall']['average_model_tool_calls'], 1)

    def test_transport_failure_recorded(self):
        with patch.object(bench.alfha, 'chat', side_effect=ConnectionError('offline')):
            result = bench.measured_case(bench.CASES / 'valid_code.py')
        self.assertFalse(result['passed'])
        self.assertEqual(result['model_requests'], 1)
        self.assertEqual(result['model_responses'], [])

    def test_invalid_json_proposal_retained(self):
        replies = iter([
            ChatResponse(message={'role': 'assistant', 'content': '{"name":"execute_python","arguments":{}}'}),
            ChatResponse(message={'role': 'assistant', 'content': 'Unable to continue.'}),
        ])
        with patch.object(bench.alfha, 'chat', side_effect=lambda **kw: next(replies)):
            result = bench.measured_case(bench.CASES / 'missing_parenthesis.py')
        self.assertFalse(result['passed'])
        self.assertEqual(result['invalid_json_proposals'], 1)
        self.assertEqual(result['rejected_recovery_attempts'], 1)
        self.assertEqual(result['model_requests'], 2)
        self.assertIn('Only edit proposals', result['json_proposal_observations'][0]['validation_error'])

    def test_bare_arguments_are_invalid_proposals(self):
        replies = iter([
            ChatResponse(message={'role': 'assistant', 'content': '{"filename":"missing_parenthesis.py","old_text":"x","new_text":"y"}'}),
            ChatResponse(message={'role': 'assistant', 'content': 'Unable to continue.'}),
        ])
        with patch.object(bench.alfha, 'chat', side_effect=lambda **kw: next(replies)):
            result = bench.measured_case(bench.CASES / 'missing_parenthesis.py')
        self.assertEqual(result['invalid_json_proposals'], 1)
        self.assertEqual(result['tool_calls'], 0)


if __name__ == '__main__':
    unittest.main()
