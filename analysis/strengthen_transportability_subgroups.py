"""Frozen-score sensitivity analyses with paired multiway bootstrap."""
from transportability_bootstrap import R,OUT,HOURS,METRICS,WeightedMetrics,sha,np,pd,json
import argparse

BASE=OUT/'evidence_strengthening_v1'

def load_predictions():
    manifest=json.loads((OUT/'prediction_manifest.json').read_text());frames={}
    for db in ['MIMIC','eICU']:
        frames[db]={}
        for h in HOURS:
            path=OUT/f'{db}_{h}h_predictions_local.csv';assert sha(path)==manifest['prediction_sha256'][path.name]
            f=pd.read_csv(path,dtype={'patient_id':str,'stay_id':str,'hospital_id':str});assert f.patient_id.is_unique
            frames[db][h]=f
    return frames

def select(mode):
    frames=load_predictions();audit=[]
    metadata=None
    if mode in ['single_hospitalization','single_stay']:
        metadata=pd.read_csv(R/'evidence_strengthening_metadata/evaluation_metadata.csv',dtype={'patient_id':str,'stay_id':str})
        assert len(metadata)==319193 and not metadata.duplicated(['dataset','patient_id','landmark_hours']).any()
    for db in frames:
        if mode=='common_episode':
            matched=set(map(tuple,frames[db][12][['patient_id','stay_id','hospital_id']].to_numpy()))
            for h in [24,48]:matched &= set(map(tuple,frames[db][h][['patient_id','stay_id','hospital_id']].to_numpy()))
        if mode=='complete_vitals':
            filename='mimic_candidate_features.csv' if db=='MIMIC' else 'eicu_candidate_features.csv'
            raw=pd.read_csv(R/'model_preparation'/filename,dtype={'patient_id':str,'stay_id':str})
            raw=raw.loc[raw.split==('test' if db=='MIMIC' else 'external')]
        for h,original in list(frames[db].items()):
            if mode=='common_episode':
                keep=np.array([tuple(row) in matched for row in original[['patient_id','stay_id','hospital_id']].to_numpy()])
                f=original.loc[keep].copy()
            elif mode=='complete_vitals':
                vitals=['heart_rate','respiratory_rate','spo2','temperature','systolic_bp','diastolic_bp','mean_bp']
                available=raw.loc[raw.landmark_hours==h].set_index('patient_id').loc[original.patient_id]
                assert np.array_equal(available.stay_id.to_numpy(),original.stay_id.to_numpy())
                f=original.loc[available[vitals].notna().all(axis=1).to_numpy()].copy()
            else:
                m=metadata.loc[(metadata.dataset==db)&(metadata.landmark_hours==h)].set_index('patient_id').loc[original.patient_id]
                assert np.array_equal(m.stay_id.to_numpy(),original.stay_id.to_numpy()) and np.array_equal(m.hospital_mortality.to_numpy(),original.hospital_mortality.to_numpy())
                count='eligible_hospitalizations' if mode=='single_hospitalization' else 'eligible_stays'
                f=original.loc[(m[count]==1).to_numpy()].copy()
            assert f.patient_id.is_unique and set(f.hospital_mortality)=={0,1}
            audit.append({'dataset':db,'landmark_hours':h,'original_patients':len(original),'patients':len(f),'deaths':int(f.hospital_mortality.sum()),'retained_percent':100*len(f)/len(original),'mortality_percent':100*f.hospital_mortality.mean()})
            frames[db][h]=f
        if mode=='common_episode':
            reference=frames[db][12].set_index('patient_id')
            for h in [24,48]:
                other=frames[db][h].set_index('patient_id').loc[reference.index]
                assert np.array_equal(reference[['stay_id','hospital_id','hospital_mortality']].to_numpy(),other[['stay_id','hospital_id','hospital_mortality']].to_numpy())
    return frames,audit

def run(mode):
    target=BASE/mode;target.mkdir(parents=True,exist_ok=False)
    frames,audit=select(mode);samplers={}
    for db in frames:
        combined=pd.concat(list(frames[db].values()),ignore_index=True)
        people=pd.Index(sorted(combined.patient_id.unique()));hospitals=pd.Index(sorted(combined.hospital_id.unique()))
        samplers[db]={'people':len(people),'hospitals':len(hospitals),'cells':{}}
        for h,f in frames[db].items():
            samplers[db]['cells'][h]=(WeightedMetrics(f.hospital_mortality,f.predicted_mortality),people.get_indexer(f.patient_id),hospitals.get_indexer(f.hospital_id))
    point=np.array([[samplers[db]['cells'][h][0].calculate(np.ones(len(frames[db][h]))) for h in HOURS] for db in ['MIMIC','eICU']])
    seeds={'common_episode':20261019,'complete_vitals':20261020,'single_hospitalization':20261022,'single_stay':20261023};seed=seeds[mode]
    (target/'identity.json').write_text(json.dumps({'code_sha256':sha(__file__),'metric_code_sha256':sha(R/'transportability_bootstrap.py'),'plan_sha256':sha(R/'evidence_strengthening_lock_2026_10_17.md'),'seed':seed,'replicates':5000,'model_fitting':False,'interpretation':'Exploratory sensitivity; conditional on frozen models'},indent=2))
    pd.DataFrame(audit).to_csv(target/'population_audit.csv',index=False)
    print(mode,'population audit',pd.DataFrame(audit).to_string(index=False),flush=True)
    rng=[np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(3)];samples=np.empty((5000,2,3,3));kept=0;attempts=0
    while kept<5000:
        attempts+=1
        nm=samplers['MIMIC']['people'];ne=samplers['eICU']['people'];nh=samplers['eICU']['hospitals']
        mw=np.bincount(rng[0].integers(nm,size=nm),minlength=nm);ew=np.bincount(rng[1].integers(ne,size=ne),minlength=ne);hw=np.bincount(rng[2].integers(nh,size=nh),minlength=nh)
        values=np.empty((2,3,3))
        try:
            for d,db in enumerate(['MIMIC','eICU']):
                for j,h in enumerate(HOURS):
                    calc,pid,hid=samplers[db]['cells'][h];values[d,j]=calc.calculate(mw[pid] if db=='MIMIC' else ew[pid]*hw[hid])
        except ValueError:continue
        samples[kept]=values;kept+=1
        if kept%1000==0:print(mode,'bootstrap',kept,'/5000',flush=True)
    pointgap=point[0]-point[1];gap=samples[:,0]-samples[:,1];rows=[];metrics=[];contrasts=[]
    for d,db in enumerate(['MIMIC','eICU']):
        for j,h in enumerate(HOURS):
            for k,name in enumerate(METRICS):
                low,high=np.quantile(samples[:,d,j,k],[.025,.975]);metrics.append({'dataset':db,'landmark_hours':h,'metric':name,'estimate':point[d,j,k],'lower95':low,'upper95':high})
    for j,h in enumerate(HOURS):
        for k,name in enumerate(METRICS):
            low,high=np.quantile(gap[:,j,k],[.025,.975]);rows.append({'landmark_hours':h,'metric':name,'internal_minus_external':pointgap[j,k],'lower95':low,'upper95':high})
            if h!=24:
                low,high=np.quantile(gap[:,j,k]-gap[:,1,k],[.025,.975]);contrasts.append({'landmark_hours':h,'reference_hours':24,'metric':name,'gap_difference':pointgap[j,k]-pointgap[1,k],'lower95':low,'upper95':high})
    pd.DataFrame(metrics).to_csv(target/'metric_intervals.csv',index=False);pd.DataFrame(rows).to_csv(target/'transportability_gaps.csv',index=False);pd.DataFrame(contrasts).to_csv(target/'gap_contrasts.csv',index=False)
    np.savez_compressed(target/'bootstrap_samples.npz',samples=samples,points=point)
    (target/'completed.json').write_text(json.dumps({'status':'completed','retained':kept,'attempts':attempts,'exploratory':True,'model_fitting':False},indent=2))
    print(mode,'completed',pd.DataFrame(contrasts).loc[lambda x:x.metric=='AUROC'].to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['common_episode','complete_vitals','single_hospitalization','single_stay']);args=p.parse_args();run(args.mode)
