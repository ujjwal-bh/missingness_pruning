"""Post-review contrasts and label-free selector diagnostics; no model fitting."""
from pathlib import Path
import sys,json,hashlib,time,shutil
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'.model_runtime'))
from missingness_pruning_inputs import np,pd,CORE,CANDIDATES,sha
O=R/'model_results/missingness_pruning_2026_10_19_v1';F=R/'model_results/pruning_full_pipeline_2026_10_19_v1';S=R/'model_preparation/missingness_pruning_2026_10_19_v1';A=R/'model_results/pruning_focused_amendment_2026_10_29_v1'
CONTRASTS=[('targeted','keep_all'),('targeted','drop_all'),('drop_all','keep_all')]
def summary(x):
    x=np.asarray(x,float);assert len(x)>1 and np.isfinite(x).all()
    lo,hi=np.quantile(x,[.025,.975])
    return dict(mean=float(x.mean()),median=float(np.median(x)),bootstrap_SD=float(x.std(ddof=1)),negative_fraction=float((x<0).mean()),positive_fraction=float((x>0).mean()),tie_fraction=float((x==0).mean()),lower95=float(lo),upper95=float(hi),replicates=len(x))
def run():
    A.mkdir(exist_ok=True)
    identity={'protocol_sha256':sha(R/'pruning_focused_amendment_protocol_2026_10_29.md'),'code_sha256':sha(__file__),'original_verification':sha(O/'verification.json'),'refit_verification':sha(F/'independent_verification.json'),'original_metrics':sha(O/'evaluation/metrics.csv'),'fixed_draws':sha(O/'inference/bootstrap_samples.npz')}
    path=A/'identity_before_analysis.json'
    if path.exists():assert json.loads(path.read_text())==identity
    else:path.write_text(json.dumps(identity,indent=2))
    points=pd.read_csv(O/'evaluation/metrics.csv');saved=pd.read_csv(F/'replicate_contrasts.csv');verification=json.loads((F/'independent_verification.json').read_text())
    rows=[];draws=[]
    for fam in ['ridge','ANN']:
        checkpoints=[]
        for i in range(200):
            p=F/fam/f'replicate_{i:04d}.json';assert sha(p)==verification['checkpoint_hashes'][f'{fam}/{p.name}'];checkpoints.append(json.loads(p.read_text()))
        for sample in ['MIMIC_test','eICU_evaluation']:
            pp=points.loc[points.family.eq(fam)&points['sample'].eq(sample)].set_index('strategy')
            for numerator,reference in CONTRASTS:
                for metric in ['AUROC','average_precision','Brier','calibration_slope','calibration_in_large']:
                    x=np.array([c['metrics'][sample][numerator][metric]-c['metrics'][sample][reference][metric] for c in checkpoints])
                    if numerator=='drop_all':
                        a=saved.loc[saved.family.eq(fam)&saved['sample'].eq(sample)&saved.metric.eq(metric)&saved.reference.eq('keep_all')].sort_values('replicate').difference.to_numpy()
                        b=saved.loc[saved.family.eq(fam)&saved['sample'].eq(sample)&saved.metric.eq(metric)&saved.reference.eq('drop_all')].sort_values('replicate').difference.to_numpy()
                        np.testing.assert_allclose(x,a-b,atol=1e-12)
                    rows.append(dict(family=fam,sample=sample,numerator=numerator,reference=reference,metric=metric,original_estimate=float(pp.loc[numerator,metric]-pp.loc[reference,metric]),**summary(x)))
                    draws.extend(dict(family=fam,sample=sample,numerator=numerator,reference=reference,metric=metric,replicate=i,difference=float(v)) for i,v in enumerate(x))
    pd.DataFrame(rows).to_csv(A/'full_pipeline_all_anchor_contrasts.csv',index=False);pd.DataFrame(draws).to_csv(A/'full_pipeline_all_anchor_draws.csv',index=False)
    keys=[tuple(k) for k in json.loads((O/'inference/cell_order.json').read_text())];z=np.load(O/'inference/bootstrap_samples.npz',allow_pickle=False);fixed=[]
    for fam in ['ridge','ANN']:
        for sample in ['MIMIC_test','eICU_evaluation']:
            pp=points.loc[points.family.eq(fam)&points['sample'].eq(sample)].set_index('strategy')
            for numerator,reference in CONTRASTS:
                a=keys.index((sample,fam,numerator));b=keys.index((sample,fam,reference))
                for metric,j in [('AUROC',None),('calibration_intercept_joint',0),('calibration_slope',1),('calibration_in_large',2),('Brier',3)]:
                    x=z['auroc'][:,a]-z['auroc'][:,b] if j is None else z['calibration'][:,a,j]-z['calibration'][:,b,j]
                    fixed.append(dict(family=fam,sample=sample,numerator=numerator,reference=reference,metric=metric,original_estimate=float(pp.loc[numerator,metric]-pp.loc[reference,metric]),**summary(x)))
    pd.DataFrame(fixed).to_csv(A/'fixed_model_all_anchor_contrasts.csv',index=False)
    random=[]
    for fam in ['ridge','ANN']:
        for sample in ['MIMIC_test','eICU_evaluation']:
            p=points.loc[points.family.eq(fam)&points['sample'].eq(sample)].set_index('strategy');vals=p.loc[p.index.str.startswith('random_'),'AUROC'];target=float(p.loc['targeted','AUROC'])
            random.append(dict(family=fam,sample=sample,random_masks=len(vals),targeted_AUROC=target,random_mean_AUROC=float(vals.mean()),targeted_minus_random_mean=target-float(vals.mean()),masks_above_targeted=int((vals>target).sum()),masks_below_targeted=int((vals<target).sum()),masks_tied=int((vals==target).sum()),descriptive_rank_among_targeted_plus_20=int(1+(vals>target).sum())))
    pd.DataFrame(random).to_csv(A/'random_control_positions.csv',index=False)
    anchors=points.loc[points.strategy.isin(['keep_all','targeted','drop_all'])&points['sample'].isin(['MIMIC_test','eICU_evaluation'])];anchors.to_csv(A/'anchor_probability_context.csv',index=False)
    selector()
    files=[p for p in A.glob('*.csv')]
    (A/'completed.json').write_text(json.dumps({'status':'completed saved-fit contrasts and selection-only diagnostic','model_fitting':False,'target_outcomes_used_for_new_selection':False,'raw_database_audit':'pending local password entry; no result invented','outputs':{p.name:sha(p) for p in files}},indent=2))
    for n in ['pruning_focused_amendment.py','pruning_focused_amendment_protocol_2026_10_29.md']:shutil.copyfile(R/n,A/n)
    print(pd.DataFrame(rows).loc[lambda x:x.metric.eq('AUROC')&x['sample'].eq('eICU_evaluation'),['family','numerator','reference','original_estimate','median','bootstrap_SD','negative_fraction','lower95','upper95']].to_string(index=False),flush=True)
def selector():
    # Frozen source rates; no source/evaluation outcomes or new model fits.
    completed=json.loads((S/'completed.json').read_text())
    for n in ['adaptation_predictors_local.csv','hospital_partition_counts_local.csv','missingness_ranking.csv']:assert sha(S/n)==completed['outputs'][n]
    adapt=pd.read_csv(S/'adaptation_predictors_local.csv',usecols=['hospital_id']+CANDIDATES,dtype={'hospital_id':str})
    inventory=pd.read_csv(S/'hospital_partition_counts_local.csv',dtype={'hospital_id':str});hosp=inventory.hospital_id.to_numpy();n_h=inventory.adaptation.to_numpy(int)
    groups=[np.flatnonzero(adapt.hospital_id.to_numpy()==h) for h in hosp];assert all(len(g)==n for g,n in zip(groups,n_h))
    missing=adapt[CANDIDATES].isna().to_numpy(np.int64);group_missing=np.array([missing[g].sum(axis=0) for g in groups]);n=len(missing);rank=pd.read_csv(S/'missingness_ranking.csv').set_index('variable');source=rank.loc[CANDIDATES,'source_missing'].to_numpy();base=set(rank.loc[rank.remove_indicator].index)
    names=np.array(CANDIDATES);count={m:np.zeros(len(names),int) for m in ['patient_only','hospital_mix_only','hospital_then_patient']};records=[];jaccard={m:[] for m in count};rng=np.random.default_rng(2026102907);B=2000
    for i in range(B):
        weights=rng.multinomial(n,np.full(n,1/n));patient=weights@missing/n
        hc=rng.multinomial(len(hosp),np.full(len(hosp),1/len(hosp)));total=int(hc@n_h);assert total>0
        cluster=hc@group_missing/total
        weighted=np.zeros(len(names),np.int64)
        for g,times in zip(groups,hc):
            if len(g) and times:weighted+=rng.multinomial(int(times)*len(g),np.full(len(g),1/len(g)))@missing[g]
        hierarchical=weighted/total
        for mode,rates in [('patient_only',patient),('hospital_mix_only',cluster),('hospital_then_patient',hierarchical)]:
            shift=abs(source-rates);selected=np.lexsort((names,-shift))[:6];count[mode][selected]+=1;chosen=set(names[selected]);jaccard[mode].append(len(chosen&base)/len(chosen|base))
            records.append(dict(replicate=i,mode=mode,adaptation_patients=n if mode=='patient_only' else total,selected='|'.join(sorted(chosen)),Jaccard=jaccard[mode][-1]))
        if (i+1)%250==0:print(f'Selection-only diagnostic {i+1}/{B}; no model fits.',flush=True)
    frequency=pd.DataFrame([dict(mode=mode,variable=v,selected_replicates=int(count[mode][j]),replicates=B,selection_frequency=count[mode][j]/B) for mode in count for j,v in enumerate(names)])
    frequency.to_csv(A/'selection_only_frequencies.csv',index=False);pd.DataFrame(records).to_csv(A/'selection_only_draws.csv',index=False)
    pd.DataFrame([dict(mode=m,mean_Jaccard=float(np.mean(x)),minimum_Jaccard=float(min(x)),exact_mask_fraction=float(np.mean(np.array(x)==1)),replicates=B,source_rates_resampled=False,model_fitting=False) for m,x in jaccard.items()]).to_csv(A/'selection_only_summary.csv',index=False)
    original=pd.read_csv(S/'missingness_ranking.csv');stability=pd.read_csv(S/'selector_stability.csv');full=pd.read_csv(F/'mask_frequencies.csv');full=full.loc[full.family.eq('ridge'),['variable','selected_replicates']].rename(columns={'selected_replicates':'full_pipeline_selected_of_200'})
    combined=original.merge(stability[['variable','selection_frequency']].rename(columns={'selection_frequency':'original_patient_bootstrap_selection_frequency'}),on='variable').merge(full,on='variable',how='left');combined['full_pipeline_selected_of_200']=combined.full_pipeline_selected_of_200.fillna(0).astype(int)
    for mode in count:combined=combined.merge(frequency.loc[frequency['mode'].eq(mode),['variable','selection_frequency']].rename(columns={'selection_frequency':mode+'_selection_frequency'}),on='variable')
    combined.to_csv(A/'all_24_shifts_and_selection_stability.csv',index=False)
if __name__=='__main__':run()
