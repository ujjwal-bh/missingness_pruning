"""Reconstruct all full-pipeline summaries from immutable aggregate checkpoints."""
from missingness_pruning_inputs import ROOT,CORE,CANDIDATES,np,pd,json,sha,save
from collections import Counter

def main():
    out=ROOT/'model_results/pruning_full_pipeline_2026_10_19_v1'
    identity=json.loads((out/'identity_before_fitting.json').read_text())
    assert sha(ROOT/'pruning_full_pipeline_protocol_2026_10_19.md')==identity['protocol']
    for n,v in identity['code'].items():assert sha(ROOT/n)==v
    completed=json.loads((out/'completed.json').read_text());assert completed['status']=='completed' and completed['replicates_per_family']==200
    for n,v in completed['outputs'].items():assert sha(out/n)==v
    original=ROOT/'model_results/missingness_pruning_2026_10_19_v1/evaluation'
    manifest=json.loads((original/'completed.json').read_text())['outputs']
    assert sha(original/'metrics.csv')==manifest['metrics.csv']
    points=pd.read_csv(original/'metrics.csv');rows=[];masks=[];hashes={};fits=[]
    for family in ['ridge','ANN']:
        for r in range(200):
            path=out/family/f'replicate_{r:04d}.json';rep=json.loads(path.read_text())
            assert rep['identity']==identity and rep['replicate']==r and rep['family']==family
            assert rep['draw_seed']==2026102000+r and rep['training_seed']==20262000+r*10000
            hashes[f'{family}/{path.name}']=sha(path)
            mask=rep['fits']['targeted']['mask'];assert len(mask)==len(set(mask))==6 and set(mask)<=set(CANDIDATES)
            assert rep['fits']['keep_all']['mask']==[] and rep['fits']['drop_all']['mask']==CORE
            masks.extend(dict(family=family,variable=v) for v in mask)
            for strategy,fit in rep['fits'].items():
                if family=='ridge':
                    grid=fit['grid_logloss'];assert len(grid)==9 and np.isfinite(grid).all()
                    assert fit['selected_C']==[1e-4,1e-3,.01,.1,1.,10.,100.,1000.,10000.][int(np.argmin(grid))]
                    fits.append(dict(family=family,replicate=r,strategy=strategy,selected_C=fit['selected_C'],final_epochs=None))
                else:
                    assert len(fit['fold_epochs'])==5 and all(1<=e<=100 for e in fit['fold_epochs'])
                    assert fit['final_epochs']==max(1,int(np.median(fit['fold_epochs'])))
                    fits.append(dict(family=family,replicate=r,strategy=strategy,selected_C=None,final_epochs=fit['final_epochs']))
            for sample,strategies in rep['metrics'].items():
                assert sample in ['MIMIC_test','eICU_evaluation']
                for strategy,m in strategies.items():
                    assert np.isfinite(list(m.values())).all()
                    for metric in ['AUROC','average_precision','Brier']:assert 0<=m[metric]<=1
                for reference in ['keep_all','drop_all']:
                    for metric in ['AUROC','average_precision','Brier','calibration_slope','calibration_in_large']:
                        rows.append(dict(family=family,replicate=r,sample=sample,reference=reference,metric=metric,difference=strategies['targeted'][metric]-strategies[reference][metric]))
    rebuilt=pd.DataFrame(rows);saved=pd.read_csv(out/'replicate_contrasts.csv')
    keys=['family','replicate','sample','reference','metric']
    a=rebuilt.sort_values(keys).reset_index(drop=True);b=saved.sort_values(keys).reset_index(drop=True)
    assert len(a)==8000 and a[keys].equals(b[keys]);np.testing.assert_allclose(a.difference,b.difference,atol=1e-14,rtol=0)
    intervals=pd.read_csv(out/'full_pipeline_intervals.csv');assert len(intervals)==40;signs=[]
    for row in intervals.itertuples():
        group=a.loc[a.family.eq(row.family)&a['sample'].eq(row.sample)&a.reference.eq(row.reference)&a.metric.eq(row.metric)]
        assert len(group)==row.replicates==200
        lo,hi=np.quantile(group.difference,[.025,.975]);p=points.loc[points.family.eq(row.family)&points['sample'].eq(row.sample)].set_index('strategy')
        expected=p.loc['targeted',row.metric]-p.loc[row.reference,row.metric]
        np.testing.assert_allclose([row.lower95,row.upper95,row.bootstrap_mean,row.original_estimate],[lo,hi,group.difference.mean(),expected],atol=1e-13,rtol=0)
        signs.append(dict(family=row.family,sample=row.sample,reference=row.reference,metric=row.metric,positive=int((group.difference>0).sum()),negative=int((group.difference<0).sum()),ties=int((group.difference==0).sum())))
    expected=pd.DataFrame(masks).groupby(['family','variable']).size().rename('selected_replicates').reset_index()
    pd.testing.assert_frame_equal(expected,pd.read_csv(out/'mask_frequencies.csv'))
    pd.DataFrame(signs).to_csv(out/'contrast_sign_frequencies.csv',index=False)
    pd.DataFrame(fits).to_csv(out/'fitting_choices.csv',index=False)
    save(out/'independent_verification.json',dict(status='passed',replicate_checkpoints=400,reconstructed_contrasts=8000,reconstructed_interval_rows=40,source_fit_choices_checked=1200,code_sha256=sha(__file__),checkpoint_hashes=hashes,checks=['protocol and model code identity','original metric integrity and original estimates','400 complete paired checkpoint identities and seeds','ridge grid winners and ANN epoch medians','8000 saved contrasts and 40 percentile intervals reconstructed','both families mask frequencies reconstructed'],limitations='Summary and checkpoint reconciliation, not independent reproduction of every model fit; 200-draw percentile tails approximate; historical dataset exposure remains.'))
    print(intervals.loc[intervals.metric.eq('AUROC')].to_string(index=False));print('Verification passed: 400 checkpoints, 8000 contrasts, 40 intervals, 1200 fit choices.')

if __name__=='__main__':main()
