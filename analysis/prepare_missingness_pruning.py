"""Prepare and audit a label-free adaptation rule; no model fitting or scoring."""
from missingness_pruning_inputs import *
import shutil,platform
from datetime import datetime,timezone

def audit_values(f,group,rules):
    rows=[]
    for c in CORE:
        values=f[c].to_numpy(float);observed=values[~np.isnan(values)]
        nonfinite=int(np.isinf(observed).sum())
        if c=='age_capped_90':outside=int(((observed<18)|(observed>90)).sum())
        elif c=='female':outside=int((~np.isin(observed,[0,1])).sum())
        else:
            rule=rules[c];lo=rule['lower_bound'];hi=rule['upper_bound']
            outside=int(((observed<lo if rule['lower_inclusive'] else observed<=lo)|(observed>hi if rule['upper_inclusive'] else observed>=hi)).sum())
        rows.append({'sample':group,'variable':c,'patients':len(f),'observed':len(observed),'missing_percent':100*np.isnan(values).mean(),'nonfinite':nonfinite,'outside_existing_screen':outside,'minimum':float(observed.min()) if len(observed) else None,'maximum':float(observed.max()) if len(observed) else None})
    if any(r['nonfinite'] or r['outside_existing_screen'] for r in rows):raise ValueError('Reference predictor validity audit failed; inspect aggregate rules before any model training')
    if group=='source_training' and any(r['observed']==0 for r in rows):raise ValueError('Source training predictor has no observations')
    return rows

def run():
    config=json.loads(CONFIG.read_text());STAGE.mkdir(parents=True,exist_ok=True)
    identity={'plan_sha256':sha(PLAN),'config_sha256':sha(CONFIG),'code_sha256':sha(__file__),'helper_sha256':sha(ROOT/'missingness_pruning_inputs.py')}
    if (STAGE/'completed.json').exists():
        completed=json.loads((STAGE/'completed.json').read_text());assert completed['identity']==identity
        for name,value in completed['outputs'].items():assert sha(STAGE/name)==value
        print('Verified existing label-free preparation; no changes or model fitting.',flush=True);return
    previous=STAGE/'identity_before_preparation.json'
    if previous.exists():assert json.loads(previous.read_text())==identity
    else:save(previous,identity)
    verified=json.loads((ROOT/'model_preparation/export_verification_confirmed_2026_10_15.json').read_text())
    provenance=json.loads((ROOT/'model_results/transportability_core_ANN_2026_10_17_v1/evidence_strengthening_v1/external_audit/completed.json').read_text())
    for name,value in provenance['source_sha256'].items():assert sha(ROOT/name)==value, 'Reference source-rule provenance changed'
    frames={};hashes={}
    for db,filename in [('MIMIC','mimic_candidate_features.csv'),('eICU','eicu_candidate_features.csv')]:
        path=ROOT/'model_preparation'/filename;hashes[filename]=sha(path)
        assert hashes[filename]==verified['inputs'][filename]['sha256']
        frames[db]=read_predictors(path)
        assert set(frames[db].dataset)=={db}
    source=frames['MIMIC'];target=frames['eICU'];assert len(source)==54266 and len(target)==103337
    assert set(source.split)=={'train','validation','test'} and set(target.split)=={'external'}
    train=source.loc[source.split.eq('train')].copy();assert len(train)==37872
    mask=adaptation_mask(target.patient_id,config);adapt=target.loc[mask].copy()
    partitions=target[META].copy();partitions['target_partition']=np.where(mask,'adaptation','evaluation')
    assert set(partitions.loc[mask,'patient_id']).isdisjoint(partitions.loc[~mask,'patient_id'])
    partitions.to_csv(STAGE/'target_partitions_local.csv',index=False)
    adapt[META+CORE].to_csv(STAGE/'adaptation_predictors_local.csv',index=False)
    # Drop evaluation predictors before any feature distribution or rule computation.
    del target,frames
    rules={r['variable']:r for r in json.loads((ROOT/'predictor_cleaning_rules_v1.json').read_text())['variables']}
    audit=audit_values(train,'source_training',rules)+audit_values(adapt,'target_adaptation',rules)
    pd.DataFrame(audit).to_csv(STAGE/'predictor_validity_audit.csv',index=False)
    rank=rank_indicators(train[CORE],adapt[CORE],config['pruning_budget'])
    rank.to_csv(STAGE/'missingness_ranking.csv',index=False)
    masks=random_masks(config['random_masks'],config['pruning_budget'],config['random_seed'])
    primary=rank.loc[rank.remove_indicator,'variable'].tolist()
    save(STAGE/'indicator_masks.json',{'keep_all':[],'targeted':primary,'drop_all':CORE,'random':{f'random_{k:02d}':v for k,v in enumerate(masks)}})
                                                                                         
    sm=train[CANDIDATES].isna().to_numpy(float);tm=adapt[CANDIDATES].isna().to_numpy(float)
    rng=np.random.default_rng(config['stability_seed']);rates=[];freq=np.zeros(len(CANDIDATES),int);overlap=[]
    primary_set=set(primary)
    for b in range(config['stability_replicates']):
        sw=np.bincount(rng.integers(len(sm),size=len(sm)),minlength=len(sm));tw=np.bincount(rng.integers(len(tm),size=len(tm)),minlength=len(tm))
        delta=np.abs(sw@sm/len(sm)-tw@tm/len(tm))
        order=np.lexsort((np.array(CANDIDATES),-delta));chosen=order[:config['pruning_budget']]
        freq[chosen]+=1;selected=set(np.array(CANDIDATES)[chosen]);overlap.append(len(selected&primary_set)/len(selected|primary_set));rates.append(delta)
    rates=np.asarray(rates);stability=[]
    for j,c in enumerate(CANDIDATES):
        lo,hi=np.quantile(rates[:,j],[.025,.975]);stability.append({'variable':c,'selection_frequency':freq[j]/config['stability_replicates'],'shift_lower95':lo,'shift_upper95':hi})
    pd.DataFrame(stability).to_csv(STAGE/'selector_stability.csv',index=False)
    hospitals=partitions.groupby(['hospital_id','target_partition']).size().unstack(fill_value=0)
    hospitals.to_csv(STAGE/'hospital_partition_counts_local.csv')
    hospital_summary={'hospitals_in_cohort':len(hospitals),'hospitals_with_adaptation':int(hospitals.adaptation.gt(0).sum()),'hospitals_with_evaluation':int(hospitals.evaluation.gt(0).sum()),'adaptation_patients_min_per_represented_hospital':int(hospitals.loc[hospitals.adaptation.gt(0),'adaptation'].min()),'adaptation_patients_median_per_hospital':float(hospitals.adaptation.median())}
    summary={'source_training_patients':len(train),'source_validation_patients':int(source.split.eq('validation').sum()),'source_test_patients':int(source.split.eq('test').sum()),'target_adaptation_patients':int(mask.sum()),'target_evaluation_patients':int((~mask).sum()),'hospitals':hospital_summary,'pruned_indicators':primary,'remaining_input_columns':46,'stability_replicates':config['stability_replicates'],'mean_selected_set_Jaccard':float(np.mean(overlap)),'minimum_Jaccard':float(np.min(overlap)),'source_and_target_outcomes_parsed':False,'target_evaluation_missingness_used':False,'historical_label_exposure_erased':False,'raw_timestamp_reaudit_performed':False,'clinical_plausibility_certified':False,'reference_hash_and_numeric_checks':'passed','model_fitting_or_scoring':False,'scope':'pooled eICU target adaptation; not hospital-specific deployment validation'}
    save(STAGE/'preparation_summary.json',summary)
    save(STAGE/'source_hashes.json',{'features':hashes,'reference_provenance':provenance['source_sha256']})
    for name in [PLAN.name,CONFIG.name,'missingness_pruning_inputs.py','prepare_missingness_pruning.py']:
        shutil.copyfile(ROOT/name,STAGE/name)
    outputs={p.name:sha(p) for p in STAGE.iterdir() if p.is_file() and p.name!='completed.json'}
    save(STAGE/'completed.json',{'identity':identity,'outputs':outputs,'status':'label-free partition/selection/reference audit completed; no models trained','utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__})
    print(json.dumps(summary,indent=2),flush=True)
    print(rank[['variable','source_missing','adaptation_missing','absolute_shift','remove_indicator']].head(8).to_string(index=False),flush=True)

if __name__=='__main__':run()
