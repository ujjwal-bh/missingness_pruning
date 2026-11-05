"""Reconstruct the focused amendment using only the shareable aggregate archive."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parent.parent;A=P/'aggregate_results/focused_amendment'
def main():
    full=pd.read_csv(A/'full_pipeline_all_anchor_contrasts.csv');draws=pd.read_csv(A/'full_pipeline_all_anchor_draws.csv');old=pd.read_csv(P/'aggregate_results/full_pipeline/replicate_contrasts.csv')
    val='difference' if 'difference' in old else 'delta'
    assert len(full)==60 and len(draws)==12000
    for r in full.itertuples():
        group=old.loc[old.family.eq(r.family)&old['sample'].eq(r.sample)&old.metric.eq(r.metric)]
        a=group.loc[group.reference.eq('keep_all')].sort_values('replicate')[val].to_numpy();b=group.loc[group.reference.eq('drop_all')].sort_values('replicate')[val].to_numpy()
        x=a-b if r.numerator=='drop_all' else (a if r.reference=='keep_all' else b)
        np.testing.assert_allclose([x.mean(),np.median(x),x.std(ddof=1),*np.quantile(x,[.025,.975]),(x<0).mean(),(x>0).mean()],[r.mean,r.median,r.bootstrap_SD,r.lower95,r.upper95,r.negative_fraction,r.positive_fraction],atol=1e-12)
    fixed=pd.read_csv(A/'fixed_model_all_anchor_contrasts.csv');keys=json.loads((P/'aggregate_results/original/inference/cell_order.json').read_text());auc=pd.read_csv(P/'aggregate_results/original/inference/fixed_model_AUROC_draws.csv');cal=pd.read_csv(P/'aggregate_results/original/inference/fixed_model_calibration_draws.csv')
    for r in fixed.itertuples():
        i=keys.index([r.sample,r.family,r.numerator]);j=keys.index([r.sample,r.family,r.reference]);metric='joint_intercept' if r.metric=='calibration_intercept_joint' else r.metric
        x=(auc[f'cell_{i}']-auc[f'cell_{j}']).to_numpy() if r.metric=='AUROC' else (cal[f'cell_{i}__{metric}']-cal[f'cell_{j}__{metric}']).to_numpy()
        np.testing.assert_allclose([x.mean(),np.median(x),x.std(ddof=1),*np.quantile(x,[.025,.975])],[r.mean,r.median,r.bootstrap_SD,r.lower95,r.upper95],atol=1e-12)
    masks=pd.read_csv(A/'selection_only_draws.csv');freq=pd.read_csv(A/'selection_only_frequencies.csv');summary=pd.read_csv(A/'selection_only_summary.csv');ranking=pd.read_csv(P/'aggregate_results/preparation/missingness_ranking.csv');base=set(ranking.loc[ranking.remove_indicator,'variable'])
    for mode,g in masks.groupby('mode'):
        sets=[set(s.split('|')) for s in g.selected];assert len(sets)==2000 and all(len(s)==6 for s in sets);jac=np.array([len(s&base)/len(s|base) for s in sets]);np.testing.assert_allclose(jac,g.Jaccard,atol=1e-12)
        for r in freq.loc[freq['mode'].eq(mode)].itertuples():assert r.selected_replicates==sum(r.variable in s for s in sets)
        r=summary.loc[summary['mode'].eq(mode)].iloc[0];np.testing.assert_allclose([jac.mean(),(jac==1).mean()],[r.mean_Jaccard,r.exact_mask_fraction],atol=1e-12)
    for db,n,col in [('MIMIC',37872,'source_missing'),('eICU',20589,'adaptation_missing')]:
        funnel=pd.read_csv(A/(db+'_harmonization_funnel.csv'));assert len(funnel)==6
        for r in funnel.itertuples():
            assert r.patients==r.expected_patients==n and r.feature_presence_mismatches==0
            expected=ranking.loc[ranking.variable.eq(r.variable),col].iloc[0];np.testing.assert_allclose(1-r.final_observed_patients/n,expected,atol=1e-12)
    print(json.dumps({'status':'passed','uses_only_packaged_aggregate_files':True,'full_pipeline_summaries_rederived':60,'fixed_model_summaries_rederived':60,'selector_draws_checked':6000,'harmonization_checks':12,'new_model_fits':0}))
if __name__=='__main__':main()
