"""Run historical method tests using a temporary, entirely synthetic workspace."""
from pathlib import Path
import argparse
import itertools
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from prepare_workspace import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-path', type=Path, action='append', default=[])
    args = parser.parse_args()
    for path in args.runtime_path:
        sys.path.insert(0, str(path.resolve()))
    with tempfile.TemporaryDirectory(prefix='pruning_methods_') as temp:
        work = prepare(Path(temp) / 'work', code_only=True)
        sys.path.insert(0, str(work))
        import pandas as pd
        import pruning_full_pipeline as pipeline
        metrics = ['AUROC', 'average_precision', 'Brier', 'calibration_slope', 'calibration_in_large']
        rows = [dict(sample=sample, family=family, strategy=strategy, **{m: 0.5 for m in metrics})
                for sample, family, strategy in itertools.product(
                    ['MIMIC_test', 'eICU_evaluation'], ['ridge', 'ANN'], ['keep_all', 'targeted', 'drop_all'])]
        fixture = work / 'model_results/missingness_pruning_2026_10_19_v1/evaluation'
        fixture.mkdir(parents=True)
        pd.DataFrame(rows).to_csv(fixture / 'metrics.csv', index=False)
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'test_missingness_pruning_inputs', 'test_pruning_inference', 'test_pruning_full_pipeline'])
        with patch.object(pipeline, 'ROOT', work):
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
        print(json.dumps({'status': 'passed', 'tests': result.testsRun,
                          'fixture': 'invented metrics and patient arrays only', 'model_training': False}))


if __name__ == '__main__':
    main()
