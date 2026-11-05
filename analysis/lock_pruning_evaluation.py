"""Record the scoring/inference implementation before new target performance."""
from missingness_pruning_inputs import *
from datetime import datetime,timezone
out=ROOT/'model_results/missingness_pruning_2026_10_19_v1'
assert not (out/'evaluation').exists(), 'Evaluation already started; cannot create a retrospective implementation lock'
names=['score_missingness_pruning.py','infer_missingness_pruning.py','amendment_resampling.py','strengthen_calibration_uncertainty.py','missingness_pruning_protocol_2026_10_19.md','missingness_pruning_protocol_v1.json','missingness_pruning_evaluation_clarifications_2026_10_19.md']
value={'code_and_plan_sha256':{n:sha(ROOT/n) for n in names},'historical_target_outcomes_previously_examined':True,'new_targeted_rule_performance_examined':False,'primary':'ridge targeted minus keep-all target-evaluation AUROC','primary_AUROC_replicates':5000,'secondary_calibration_replicates':2000,'random_controls':'all20point metrics and their empirical spread; no formal random-algorithm superiority test','locked_utc':datetime.now(timezone.utc).isoformat()}
path=out/'evaluation_lock.json'
if path.exists():
    prior=json.loads(path.read_text());assert prior['code_and_plan_sha256']==value['code_and_plan_sha256']
else:save(path,value)
print('Scoring and inference implementation locked before new target evaluation.',flush=True)
