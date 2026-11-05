import unittest
import tempfile,json
from pathlib import Path
from unittest.mock import patch
import pruning_full_pipeline as pipeline
from pruning_full_pipeline import np,grouped_folds,inner_stop,target_indices,drop_for,CORE,pd

class FullPipelineTests(unittest.TestCase):
    def test_bootstrap_duplicates_never_cross_folds_or_stopping(self):
        ids=np.repeat(np.arange(100),3);y=(ids%2).astype(int)
        for fit,held in grouped_folds(ids,y,17):
            self.assertFalse(set(ids[fit])&set(ids[held]))
            inner,stop=inner_stop(ids,y,fit,19)
            self.assertFalse(set(ids[inner])&set(ids[stop]))
            self.assertEqual(set(inner)|set(stop),set(fit))

    def test_paired_hospital_draws_and_missing_adaptation_site(self):
        ah=np.array(['a','a','b','b']);eh=np.array(['a','a','b','b'])
        a,e=target_indices(ah,eh,np.random.default_rng(23))
        self.assertEqual(sorted(ah[a].tolist()),sorted(eh[e].tolist()))
        a2,e2=target_indices(ah,eh,np.random.default_rng(23))
        np.testing.assert_array_equal(a,a2);np.testing.assert_array_equal(e,e2)
        a,e=target_indices(np.array(['a','a']),np.array(['a','b']),np.random.default_rng(1))
        self.assertTrue(np.all(a<2));self.assertTrue(np.all(e<2))

    def test_selector_refits_and_anchor_masks(self):
        x=np.ones((20,len(CORE)));a=pd.DataFrame(x.copy(),columns=CORE)
        eligible=sorted(set(CORE)-{'age_capped_90','female'})
        for c in eligible[:6]:a[c]=np.nan
        self.assertEqual(set(drop_for('targeted',x,a)),set(eligible[:6]))
        self.assertEqual(drop_for('keep_all',x,a),[])
        self.assertEqual(drop_for('drop_all',x,a),CORE)

    def test_final_summary_reconciles_all_replicates(self):
        with tempfile.TemporaryDirectory(dir=pipeline.ROOT,prefix='pruning_summary_test_') as tmp:
            out=Path(tmp)
            metrics={sample:{strategy:{metric:.5 for metric in ['AUROC','average_precision','Brier','calibration_slope','calibration_in_large']} for strategy in pipeline.STRATEGIES} for sample in ['MIMIC_test','eICU_evaluation']}
            for family in ['ridge','ANN']:
                (out/family).mkdir()
                for r in range(2):
                    (out/family/f'replicate_{r:04d}.json').write_text(json.dumps({'metrics':metrics,'fits':{'targeted':{'mask':[CORE[2]]}}}))
            with patch.object(pipeline,'OUT',out),patch.object(pipeline,'N',2):pipeline.summarize()
            results=pd.read_csv(out/'full_pipeline_intervals.csv')
            self.assertEqual(len(results),40)
            self.assertTrue(np.all(results.lower95==0));self.assertTrue(np.all(results.upper95==0))
            self.assertTrue((out/'completed.json').exists())

if __name__=='__main__':unittest.main()
