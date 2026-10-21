"""Step 41 exact preserved-candidate plan. Data only; never invokes a worker."""
import hashlib
import json
from pathlib import Path

from .prepare_candidate_validation import prepare
from .normalize_profile import TASK_ID, SCOPE, SOURCE_HASHES
from .functional_harness import task_by_id, profile_hash
from .functional_validation import validate_source
from .docker_transport import PINNED_IMAGE
from .execution_backend import ContainerPolicy


def build_plan():
    root=Path(__file__).with_name('runs')
    evidence=prepare()
    prior=json.loads((root/'step39_preparation_review.json').read_text(encoding='utf-8'))
    step40_path=root/'step40_reference_integration.json'
    raw=step40_path.read_bytes(); step40=json.loads(raw)
    if (step40['status']!='completed' or len(step40['checks'])!=24 or
            not all(c['passed'] for c in step40['checks']) or not step40['isolation']['verified']):
        raise ValueError('Complete Step 40 reference/security evidence required')
    if evidence['original_run_sha256']!=prior['original_run_sha256']:
        raise ValueError('Original model evidence changed')
    task=task_by_id(TASK_ID,string_scope=SCOPE)
    if task['tests']!=prior['tasks']['B']['tests']:
        raise ValueError('Previously reviewed expected vectors changed')
    originals=json.loads((root/'step33_preparation.json').read_text(encoding='utf-8'))
    plan={'status':'pending_explicit_execution_approval','candidate_execution':False,'model_requests':0,
          'candidate_job_limit':3,'task_id':TASK_ID,'string_scope':SCOPE,'scope_disabled_by_default':True,
          'automatic_retries':0,'fresh_in_process_verification_required':True,
          'source_application':False,'generated_test_execution':False,'pinned_image':PINNED_IMAGE,
          'fixed_policy':ContainerPolicy().plan(PINNED_IMAGE),'task':task,
          'profile_sha256':profile_hash(),'original_run_sha256':evidence['original_run_sha256'],
          'step40_evidence_sha256':hashlib.sha256(raw).hexdigest(),
          'original_requirements':originals['request']['description'],
          'original_static_acceptance':originals['static_acceptance'],'candidates':[]}
    for candidate in evidence['candidates']:
        if candidate['scenario']!='B': continue
        if candidate['source_sha256'] not in SOURCE_HASHES:
            raise ValueError('Unapproved preserved source identity')
        checks=validate_source(candidate['source'],task)
        if not checks['static_policy_passed'] or candidate['policy']['static_policy_passed']:
            raise ValueError('Scoped acceptance/default rejection invariant failed')
        plan['candidates'].append({'original_attempt':candidate['attempt'],'model':candidate['model'],
            'source':candidate['source'],'source_sha256':candidate['source_sha256'],
            'default_policy':candidate['policy'],'scoped_policy':checks,'planned_vectors':len(task['tests']),
            'functional_status':'not_run','functional_passed':None,
            'staging_evidence_sha256':candidate['staging_evidence_sha256']})
    if len(plan['candidates'])!=3 or {c['source_sha256'] for c in plan['candidates']}!=SOURCE_HASHES:
        raise ValueError('Expected the three exact preserved implementations')
    # Preparation data must round-trip identically through its JSON review file.
    # This normalizes only the proposed policy manifest's empty host-mount tuple,
    # never runtime identity/verification evidence.
    return json.loads(json.dumps(plan,ensure_ascii=True,allow_nan=False))


if __name__=='__main__':
    print(json.dumps(build_plan(),ensure_ascii=True,indent=2))
