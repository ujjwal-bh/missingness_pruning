"""Behavior tests for leakage barriers, deterministic masks and partition grouping."""
from missingness_pruning_inputs import *
import unittest,io

class PruningInputs(unittest.TestCase):
    def samples(self):
        a=pd.DataFrame(np.ones((80,len(CORE))),columns=CORE);b=a.copy()
        for j,c in enumerate(CANDIDATES):b.loc[:j,c]=np.nan
        return a,b
    def test_deterministic_ranking_under_row_and_column_permutation(self):
        a,b=self.samples();r=rank_indicators(a,b)
        other=rank_indicators(a.sample(frac=1,random_state=1)[list(reversed(CORE))],b.sample(frac=1,random_state=2))
        pd.testing.assert_frame_equal(r,other)
        self.assertEqual(int(r.remove_indicator.sum()),6)
    def test_labels_and_identifiers_rejected_at_selector_boundary(self):
        a,b=self.samples()
        for col in ['hospital_mortality','patient_id','outcome','death']:
            with self.assertRaises(ValueError):rank_indicators(a,b.assign(**{col:0}))
    def test_loader_ignores_poisoned_outcome_values(self):
        a,b=self.samples();meta={'dataset':'eICU','patient_id':[str(i) for i in range(len(b))],'stay_id':[str(i+100) for i in range(len(b))],'hospital_id':'test','landmark_hours':24,'split':'external'}
        x=pd.concat([pd.DataFrame(meta),b],axis=1)
        one=io.StringIO(x.assign(hospital_mortality=0).to_csv(index=False))
        two=io.StringIO(x.assign(hospital_mortality='OUTCOME_MUST_NOT_BE_PARSED').to_csv(index=False))
        first=read_predictors(one);second=read_predictors(two)
        self.assertNotIn('hospital_mortality',first.columns);pd.testing.assert_frame_equal(first,second)
        pd.testing.assert_frame_equal(rank_indicators(a,first[CORE]),rank_indicators(a,second[CORE]))
    def test_partition_is_patient_stable_and_label_independent(self):
        config=json.loads(CONFIG.read_text());ids=['synthetic_'+str(i) for i in range(1000)]
        x=adaptation_mask(ids,config);y=adaptation_mask(ids[::-1],config)[::-1]
        np.testing.assert_array_equal(x,y);self.assertTrue(.14<x.mean()<.26)
        self.assertEqual(adaptation_mask(['repeat','repeat'],config)[0],adaptation_mask(['repeat','repeat'],config)[1])
    def test_random_controls_have_fixed_budget_and_unique_masks(self):
        masks=random_masks();self.assertEqual(masks,random_masks());self.assertEqual(len({tuple(x) for x in masks}),20)
        self.assertTrue(all(len(x)==len(set(x))==6 and set(x).issubset(CANDIDATES) for x in masks))
    def test_ties_have_explicit_alphabetical_order(self):
        a,_=self.samples();r=rank_indicators(a,a)
        self.assertEqual(r.loc[r.remove_indicator,'variable'].tolist(),CANDIDATES[:6])

    def test_pruning_changes_only_explicit_flags(self):
        from missingness_pruning_models import PruningInputs
        a,b=self.samples();X=a.to_numpy(float);V=b.to_numpy(float)
        full=PruningInputs([]).fit(X);pruned=PruningInputs(CANDIDATES[:6]).fit(X)
        all_values=full.transform(V);selected=pruned.transform(V)
        np.testing.assert_array_equal(all_values[:,:26],selected[:,:26])
        self.assertEqual(selected.shape[1],46)
        np.testing.assert_array_equal(full.median_,pruned.median_)

if __name__=='__main__':unittest.main()
