"""Dataset-free numerical reconstruction of the packaged aggregate evidence."""
from pathlib import Path
import json,hashlib,sys
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parent.parent
def main():
    f=P/'aggregate_results/full_pipeline';o=P/'aggregate_results/original'
    ints=pd.read_csv(f/'full_pipeline_intervals.csv');con=pd.read_csv(f/'replicate_contrasts.csv')
    assert len(ints)==40 and len(con)==8000
    # Detect field names from the recorded schema, not guessed column order.
    value='difference' if 'difference' in con else 'delta'
    if value not in con:raise AssertionError('Unexpected contrast schema: '+','.join(con.columns))
    for r in ints.itertuples():
        x=con.loc[con.family.eq(r.family)&con['sample'].eq(r.sample)&con.reference.eq(r.reference)&con.metric.eq(r.metric),value].to_numpy()
        assert len(x)==200 and np.isfinite(x).all()
        np.testing.assert_allclose([np.mean(x),*np.quantile(x,[.025,.975])],[r.bootstrap_mean,r.lower95,r.upper95],atol=1e-12,rtol=1e-9)
    points=pd.read_csv(o/'evaluation/metrics.csv')
    keys=json.loads((o/'inference/cell_order.json').read_text())
    auc=pd.read_csv(o/'inference/fixed_model_AUROC_draws.csv');cal=pd.read_csv(o/'inference/fixed_model_calibration_draws.csv')
    fixed=pd.read_csv(o/'inference/metric_intervals.csv')
    for r in fixed.itertuples():
        j=keys.index([r.sample,r.family,r.strategy]);values=auc[f'cell_{j}'] if r.metric=='AUROC' else cal[f'cell_{j}__{r.metric}']
        np.testing.assert_allclose(np.quantile(values,[.025,.975]),[r.lower95,r.upper95],atol=1e-10)
    contrasts=pd.read_csv(o/'inference/auroc_contrasts.csv')
    for r in contrasts.itertuples():
        a=keys.index([r.sample,r.family,'targeted']);b=keys.index([r.sample,r.family,r.contrast.removeprefix('targeted_minus_')])
        np.testing.assert_allclose(np.quantile(auc[f'cell_{a}']-auc[f'cell_{b}'],[.025,.975]),[r.lower95,r.upper95],atol=1e-10)
    for r in ints.itertuples():
        a=points.loc[points.family.eq(r.family)&points['sample'].eq(r.sample)&points.strategy.eq('targeted')].iloc[0]
        b=points.loc[points.family.eq(r.family)&points['sample'].eq(r.sample)&points.strategy.eq(r.reference)].iloc[0]
        np.testing.assert_allclose(a[r.metric]-b[r.metric],r.original_estimate,atol=1e-12)
    ident=json.loads((f/'independent_verification.json').read_text())
    for rel,digest in ident['checkpoint_hashes'].items():
        p=f/'checkpoints'/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,rel
    assert len(list((f/'checkpoints').rglob('replicate_*.json')))==400
    rank=pd.read_csv(P/'aggregate_results/preparation/missingness_ranking.csv')
    np.testing.assert_allclose(abs(rank.source_missing-rank.adaptation_missing),rank.absolute_shift,atol=1e-14)
    assert rank.loc[rank.remove_indicator,'variable'].tolist()==['phosphate','magnesium','lactate','albumin','platelets','bicarbonate']
    manifest=P/'SHA256SUMS.json'
    if manifest.exists():
        for rel,digest in json.loads(manifest.read_text(encoding='utf-8-sig')).items():assert hashlib.sha256((P/rel).read_bytes()).hexdigest()==digest,rel
    print(json.dumps({'status':'passed','full_pipeline_interval_rows_rederived':40,'fixed_model_metric_intervals_rederived':60,'fixed_model_AUROC_contrasts_rederived':8,'paired_contrasts':8000,'checkpoint_hashes':400,'anchor_differences':40,'selector_ranking':'passed','manifest_checked':manifest.exists()}))
if __name__=='__main__':main()
