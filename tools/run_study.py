"""Execute an explicit study stage in an external private workspace."""
from pathlib import Path
import argparse
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
STEPS = {
    'prepare': [('prepare_missingness_pruning.py',)],
    'train': [('train_missingness_pruning.py', 'ridge'), ('train_missingness_pruning.py', 'ANN')],
    'evaluate': [('score_missingness_pruning.py',), ('pruning_hospital_heterogeneity.py',),
                 ('infer_missingness_pruning.py',), ('verify_missingness_pruning.py',)],
    'robustness': [('pruning_full_pipeline.py',), ('verify_pruning_full_pipeline.py',)],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=STEPS)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work == REPO or work.is_relative_to(REPO):
        raise ValueError('Study outputs must remain outside the repository.')
    if not (work / 'PRIVATE_WORKSPACE_DO_NOT_PUBLISH.txt').is_file():
        raise ValueError('First create the private workspace using prepare_workspace.py.')
    steps = list(STEPS[args.stage])
    if args.stage == 'evaluate':
        lock = work / 'model_results/missingness_pruning_2026_10_19_v1/evaluation_lock.json'
        if not lock.exists():
            steps.insert(0, ('lock_pruning_evaluation.py',))
    for command in steps:
        print('Running: ' + ' '.join(command), flush=True)
        subprocess.run([sys.executable, '-u', *command], cwd=work, check=True)


if __name__ == '__main__':
    main()
