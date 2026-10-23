"""Resource-gated, serialized trusted regression runner; never runs live evals."""
import sys
import unittest
from resource_readiness import check_readiness, workload_guard

MODULES = ('test_agent test_evaluation_controller test_benchmark_reporting '
    'test_functional_evaluation test_execution_backend test_docker_transport '
    'test_functional_worker test_functional_benchmark test_runtime_diagnosis '
    'test_actionable_feedback test_checkpoint_integrity test_git_checkpoints '
    'test_multi_file_tasks test_coding_workflow test_tool_protocol test_dependency_preflight '
    'test_proposal_protocol test_proposal_analysis test_structured_preparation '
    'test_docker_readiness test_candidate_validation_preparation test_probe_stop '
    'test_string_policy test_normalize_scope test_structured_reliability '
    'test_structured_contracts test_focused_retest test_multiline_protocol '
    'test_interactive_review test_review_pilot').split()


def main():
    with workload_guard('regression'):
        readiness = check_readiness('regression')
        if not readiness['ready']:
            print('Regression preflight failed: ' + '; '.join(readiness['errors']))
            return 2
        print('Regression resource preflight passed; snapshot is not sustained stability proof.', flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(MODULES))
        return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
