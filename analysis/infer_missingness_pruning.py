"""Primary paired inference and calibration diagnostics conditional on frozen fits."""
from missingness_pruning_inputs import *
from train_missingness_pruning import OUT,progress
from amendment_resampling import WeightedAUC
from strengthen_calibration_uncertainty import WeightedCalibration
from sklearn.metrics import roc_auc_score

def nested_patient_weights(groups,n,rng):
    """Resample whole hospital draws, then independently sample within each draw."""
    w=np.zeros(n,int)
    for j in rng.integers(len(groups),size=len(groups)):
        group=groups[j];sampled=group[rng.integers(len(group),size=len(group))];np.add.at(w,sampled,1)
    return w

def run():
    lock=json.loads((OUT/'evaluation_lock.json').read_text())
    for name,value in lock['code_and_plan_sha256'].items():assert sha(ROOT/name)==value
    directory=OUT/'evaluation';assert (directory/'completed.json').exists()
    target=OUT/'inference';target.mkdir(exist_ok=True)
    identity={'plan_sha256':sha(PLAN),'code_sha256':sha(__file__),'evaluation_completed_sha256':sha(directory/'completed.json'),'evaluation_lock_sha256':sha(OUT/'evaluation_lock.json')}
    if (target/'completed.json').exists():
        previous=json.loads((target/'completed.json').read_text());assert previous['identity']==identity
        for name,value in previous['outputs'].items():assert sha(target/name)==value
        return
    manifest=json.loads((directory/'prediction_manifest.json').read_text());frames={};cells={};points={};keys=[]
    for sample in ['MIMIC_test','eICU_evaluation']:
        for family in ['ridge','ANN']:
            filename=f'{sample}_{family}_predictions_local.csv';path=directory/filename;assert sha(path)==manifest[filename]
            f=pd.read_csv(path,dtype={'patient_id':str,'hospital_id':str});frames[sample,family]=f
            for strategy in ['keep_all','targeted','drop_all']:
                key=(sample,family,strategy);keys.append(key);calc=WeightedAUC(f.hospital_mortality,f[strategy]);cal=WeightedCalibration(f.hospital_mortality,f[strategy]);cells[key]=(calc,cal)
                points[key]=np.r_[calc(np.ones(len(f))),cal.fit(np.ones(len(f)))[[2,3,4]],np.mean((f.hospital_mortality-f[strategy])**2)]
                assert abs(points[key][0]-roc_auc_score(f.hospital_mortality,f[strategy]))<1e-12
    for sample in ['MIMIC_test','eICU_evaluation']:
        assert frames[sample,'ridge'][['patient_id','hospital_id','hospital_mortality']].equals(frames[sample,'ANN'][['patient_id','hospital_id','hospital_mortality']])
    ext=frames['eICU_evaluation','ridge'];hospital_groups=[np.flatnonzero(ext.hospital_id.to_numpy()==h) for h in sorted(ext.hospital_id.unique())]
    source_n=len(frames['MIMIC_test','ridge']);rng=np.random.default_rng(2026101908)
    auc_draws=np.empty((5000,len(keys)));cal_draws=[];attempts=kept=0
                                                                              
    while kept<5000:
        attempts+=1
        sw=np.bincount(rng.integers(source_n,size=source_n),minlength=source_n)
        tw=nested_patient_weights(hospital_groups,len(ext),rng)
        values=[];calibration=[]
        try:
            for key in keys:
                w=sw if key[0]=='MIMIC_test' else tw;calc,cal=cells[key];values.append(calc(w))
                if kept<2000:
                    c=cal.fit(w);f=frames[key[0],key[1]];p=f[key[2]].to_numpy(float);y=f.hospital_mortality.to_numpy(int)
                    calibration.append(np.r_[c[[2,3,4]],np.sum(w*(y-p)**2)/w.sum()])
        except ValueError:continue
        auc_draws[kept]=values
        if kept<2000:cal_draws.append(calibration)
        kept+=1
        if kept%500==0:progress('Pruning paired inference progress',replicates=kept)
    cal_draws=np.asarray(cal_draws);rows=[];contrasts=[]
    for j,key in enumerate(keys):
        sample,family,strategy=key
        for k,name in enumerate(['AUROC','joint_intercept','calibration_slope','calibration_in_large','Brier']):
            d=auc_draws[:,j] if k==0 else cal_draws[:,j,k-1];lo,hi=np.quantile(d,[.025,.975])
            rows.append({'sample':sample,'family':family,'strategy':strategy,'metric':name,'estimate':points[key][k],'lower95':lo,'upper95':hi,'replicates':len(d)})
        for reference in ['keep_all','drop_all']:
            if strategy!='targeted':continue
            r=keys.index((sample,family,reference));d=auc_draws[:,j]-auc_draws[:,r];lo,hi=np.quantile(d,[.025,.975])
            contrasts.append({'sample':sample,'family':family,'contrast':'targeted_minus_'+reference,'estimate':points[key][0]-points[sample,family,reference][0],'lower95':lo,'upper95':hi,'replicates':len(d),'primary':sample=='eICU_evaluation' and family=='ridge' and reference=='keep_all'})
    pd.DataFrame(rows).to_csv(target/'metric_intervals.csv',index=False);pd.DataFrame(contrasts).to_csv(target/'auroc_contrasts.csv',index=False)
    np.savez_compressed(target/'bootstrap_samples.npz',auroc=auc_draws,calibration=cal_draws,points=np.array([points[k] for k in keys]))
    save(target/'cell_order.json',keys)
    save(target/'completed.json',{'identity':identity,'outputs':{p.name:sha(p) for p in target.iterdir() if p.is_file() and p.name!='completed.json'},'status':'completed','AUROC_replicates':5000,'calibration_replicates':2000,'attempts':attempts,'conditional_on_fixed_models_and_pruning_mask':True,'primary_target_two_stage_hospital_patient':True,'random_controls_point_distribution_only':True})
    progress('Pruning primary inference completed')

if __name__=='__main__':run()
