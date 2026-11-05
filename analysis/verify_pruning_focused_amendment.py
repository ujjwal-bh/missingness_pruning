"""Separate numerical checker in the same AI-assisted workflow; no external review."""
from pathlib import Path
import sys,json
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'.model_runtime'))
import numpy as np,pandas as pd
from missingness_pruning_inputs import CANDIDATES,sha
A=R/'model_results/pruning_focused_amendment_2026_10_29_v1';F=R/'model_results/pruning_full_pipeline_2026_10_19_v1';O=R/'model_results/missingness_pruning_2026_10_19_v1';S=R/'model_preparation/missingness_pruning_2026_10_19_v1'
def run():
    done=json.loads((A/'completed.json').read_text())
    for n,h in done['outputs'].items():assert sha(A/n)==h
    point=pd.read_csv(O/'evaluation/metrics.csv');summary=pd.read_csv(A/'full_pipeline_all_anchor_contrasts.csv');draws=pd.read_csv(A/'full_pipeline_all_anchor_draws.csv');old=pd.read_csv(F/'replicate_contrasts.csv')
    assert len(summary)==60 and len(draws)==12000
    for r in summary.itertuples():
        x=draws.loc[draws.family.eq(r.family)&draws['sample'].eq(r.sample)&draws.numerator.eq(r.numerator)&draws.reference.eq(r.reference)&draws.metric.eq(r.metric)].sort_values('replicate').difference.to_numpy()
        assert len(x)==200
        expected=[]
        for i in range(200):
            c=json.loads((F/r.family/f'replicate_{i:04d}.json').read_text());expected.append(c['metrics'][r.sample][r.numerator][r.metric]-c['metrics'][r.sample][r.reference][r.metric])
        np.testing.assert_allclose(x,expected,atol=1e-12)
        p=point.loc[point.family.eq(r.family)&point['sample'].eq(r.sample)].set_index('strategy')
        np.testing.assert_allclose(r.original_estimate,p.loc[r.numerator,r.metric]-p.loc[r.reference,r.metric],atol=1e-12)
        np.testing.assert_allclose([r.mean,r.median,r.bootstrap_SD,r.lower95,r.upper95,r.negative_fraction,r.positive_fraction],[x.mean(),np.median(x),x.std(ddof=1),*np.quantile(x,[.025,.975]),(x<0).mean(),(x>0).mean()],atol=1e-12)
    z=np.load(O/'inference/bootstrap_samples.npz',allow_pickle=False);keys=json.loads((O/'inference/cell_order.json').read_text());fixed=pd.read_csv(A/'fixed_model_all_anchor_contrasts.csv');assert len(fixed)==60
    lookup={'calibration_intercept_joint':0,'calibration_slope':1,'calibration_in_large':2,'Brier':3}
    for r in fixed.itertuples():
        a=keys.index([r.sample,r.family,r.numerator]);b=keys.index([r.sample,r.family,r.reference]);x=z['auroc'][:,a]-z['auroc'][:,b] if r.metric=='AUROC' else z['calibration'][:,a,lookup[r.metric]]-z['calibration'][:,b,lookup[r.metric]]
        np.testing.assert_allclose([r.mean,r.median,r.bootstrap_SD,r.lower95,r.upper95],[x.mean(),np.median(x),x.std(ddof=1),*np.quantile(x,[.025,.975])],atol=1e-12)
    rank=pd.read_csv(S/'missingness_ranking.csv');base=set(rank.loc[rank.remove_indicator,'variable']);records=pd.read_csv(A/'selection_only_draws.csv');freq=pd.read_csv(A/'selection_only_frequencies.csv');stab=pd.read_csv(A/'selection_only_summary.csv');assert len(records)==6000
    for mode,g in records.groupby('mode'):
        assert len(g)==2000 and g.replicate.nunique()==2000;sets=[set(x.split('|')) for x in g.selected];assert all(len(x)==6 and x<=set(CANDIDATES) for x in sets)
        jac=np.array([len(x&base)/len(x|base) for x in sets]);np.testing.assert_allclose(jac,g.Jaccard,atol=1e-12)
        for r in freq.loc[freq['mode'].eq(mode)].itertuples():assert r.selected_replicates==sum(r.variable in x for x in sets)
        s=stab.loc[stab['mode'].eq(mode)].iloc[0];np.testing.assert_allclose([s.mean_Jaccard,s.minimum_Jaccard,s.exact_mask_fraction],[jac.mean(),jac.min(),(jac==1).mean()],atol=1e-12)
    result={'status':'passed','checker_provenance':'separate script within same AI-assisted workflow; not independent external review','full_pipeline_contrast_rows':60,'full_pipeline_draws':12000,'fixed_model_contrast_rows':60,'selection_only_draws':6000,'source_model_refitting':False,'harmonization_audit_status':'completed and reconciled; see harmonization_verification.json','code_sha256':sha(__file__)}
    (A/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':run()

