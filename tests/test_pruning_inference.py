"""Synthetic numerical checks for the new single-landmark inference design."""
from missingness_pruning_inputs import np
from infer_missingness_pruning import nested_patient_weights
from amendment_resampling import WeightedAUC
from strengthen_calibration_uncertainty import WeightedCalibration
from sklearn.metrics import roc_auc_score
import unittest

class PruningInference(unittest.TestCase):
    def test_nested_draw_matches_independent_explicit_sample(self):
        groups=[np.array([0,1]),np.array([2,3,4]),np.array([5])]
        actual=nested_patient_weights(groups,6,np.random.default_rng(12))
        rng=np.random.default_rng(12);sample=[]
        for j in rng.integers(3,size=3):
            g=groups[j];sample.extend(g[rng.integers(len(g),size=len(g))].tolist())
        np.testing.assert_array_equal(actual,np.bincount(sample,minlength=6))
        self.assertTrue((actual>=0).all())
    def test_weighted_pairing_matches_expanded_rows(self):
        y=np.array([0,1,0,1,0,1]);p=np.array([.1,.4,.2,.7,.5,.9]);w=np.array([1,2,0,2,1,3])
        ids=np.repeat(np.arange(len(y)),w)
        self.assertAlmostEqual(WeightedAUC(y,p)(w),roc_auc_score(y[ids],p[ids]),places=13)
        np.testing.assert_allclose(WeightedCalibration(y,p).fit(w),WeightedCalibration(y[ids],p[ids]).fit(np.ones(len(ids))),atol=1e-7)

if __name__=='__main__':unittest.main()
