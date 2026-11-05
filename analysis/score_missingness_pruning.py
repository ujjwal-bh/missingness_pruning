"""Evaluate every frozen strategy; target labels accessible only after freeze gate."""
from missingness_pruning_inputs import *
from train_missingness_pruning import OUT,SEEDS,strategies,get_identity,verified_completed,progress
from revised_mimic_models import MortalityANN,predict_ann,metrics
from strengthen_calibration_uncertainty import WeightedCalibration
import joblib,torch
from sklearn.metrics import roc_auc_score,average_precision_score

def run():
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    lock=json.loads((OUT/'evaluation_lock.json').read_text())
    for name,value in lock['code_and_plan_sha256'].items():assert sha(ROOT/name)==value, 'Evaluation implementation changed after lock'
    frozen=OUT/'all_models_frozen.json'
    assert frozen.exists(), 'No evaluation until both model families and all strategies are frozen'
    identity=get_identity();assert json.loads(frozen.read_text())['identity']==identity
    target=OUT/'evaluation';target.mkdir(exist_ok=True)
    expected={'training_identity':identity,'code_sha256':sha(__file__),'frozen_sha256':sha(frozen),'evaluation_lock_sha256':sha(OUT/'evaluation_lock.json')}
    if (target/'completed.json').exists():
        previous=json.loads((target/'completed.json').read_text());assert previous['identity']==expected
        for name,value in previous['outputs'].items():assert sha(target/name)==value
        return
    if (target/'identity_before_scoring.json').exists():assert json.loads((target/'identity_before_scoring.json').read_text())==expected
    else:save(target/'identity_before_scoring.json',expected)
    partitions=pd.read_csv(STAGE/'target_partitions_local.csv',dtype={'patient_id':str,'stay_id':str,'hospital_id':str})
    eval_keys=partitions.loc[partitions.target_partition.eq('evaluation')].set_index('patient_id')
    frames={}
    for db,filename in [('MIMIC','mimic_candidate_features.csv'),('eICU','eicu_candidate_features.csv')]:
        path=ROOT/'model_preparation'/filename
        expected_hash=json.loads((STAGE/'source_hashes.json').read_text())['features'][filename];assert sha(path)==expected_hash
        f=pd.read_csv(path,usecols=META+CORE+['hospital_mortality'],dtype={'patient_id':str,'stay_id':str,'hospital_id':str})
        f=f.loc[f.landmark_hours.eq(24)].copy()
        if db=='MIMIC':
            for split in ['validation','test']:frames['MIMIC_'+split]=f.loc[f.split.eq(split)].reset_index(drop=True)
        else:
            f=f.loc[f.patient_id.isin(eval_keys.index)].reset_index(drop=True)
            assert len(f)==82748 and set(f.patient_id)==set(eval_keys.index)
            keys=eval_keys.loc[f.patient_id]
            assert np.array_equal(keys.stay_id.to_numpy(),f.stay_id.to_numpy()) and np.array_equal(keys.hospital_id.to_numpy(),f.hospital_id.to_numpy())
            frames['eICU_evaluation']=f
    rows=[];seedrows=[];manifests={}
    def get_metrics(y,p):
        row=metrics(y,p);cal=WeightedCalibration(y,p).fit(np.ones(len(y)))
        row.update(calibration_intercept_joint=cal[2],calibration_slope=cal[3],calibration_in_large=cal[4],calibration_diagnostic_converged=True)
        return row
    for family in ['ridge','ANN']:
        for sample,frame in frames.items():
            output=frame[['patient_id','stay_id','hospital_id','hospital_mortality']].copy();X=frame[CORE].to_numpy(float);y=frame.hospital_mortality.to_numpy(int)
            assert frame.patient_id.is_unique and set(y)=={0,1}
            for name in strategies():
                folder=OUT/family/name;assert verified_completed(folder,identity)
                if family=='ridge':
                    state=joblib.load(folder/'pipeline.joblib');p=state['model'].predict_proba(state['preprocessor'].transform(X))[:,1]
                else:
                    pre=joblib.load(folder/'preprocessor.joblib');tx=pre.transform(X);members=[]
                    for seed in SEEDS:
                        cp=torch.load(folder/f'model_seed_{seed}.pt',map_location='cpu',weights_only=True)
                        cfg=cp['config'];model=MortalityANN(cp['inputs'],cfg['dropout'],cfg['batchnorm']);model.load_state_dict(cp['state']);model.eval()
                        one=predict_ann(model,tx);members.append(one)
                        seedrows.append({'family':family,'sample':sample,'strategy':name,'seed':seed,'AUROC':float(roc_auc_score(y,one)),'average_precision':float(average_precision_score(y,one))})
                    p=np.mean(members,axis=0)
                assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all();output[name]=p
                rows.append({'family':family,'sample':sample,'strategy':name,**get_metrics(y,p)})
            path=target/f'{sample}_{family}_predictions_local.csv';output.to_csv(path,index=False);manifests[path.name]=sha(path)
            progress('All pruning strategies evaluated on paired patients',family=family,sample=sample,patients=len(frame))
    pd.DataFrame(rows).to_csv(target/'metrics.csv',index=False);pd.DataFrame(seedrows).to_csv(target/'ANN_seed_metrics.csv',index=False)
    save(target/'prediction_manifest.json',manifests)
    save(target/'completed.json',{'identity':expected,'outputs':{p.name:sha(p) for p in target.iterdir() if p.is_file() and p.name!='completed.json'},'status':'All source and target evaluation completed','target_outcomes_used_for_model_or_mask_selection':False,'adaptation_outcomes_used':False})
    progress('Pruning evaluation completed',cells=len(rows))

if __name__=='__main__':run()
