"""Paired patient / crossed patient-hospital resampling of frozen predictions."""
from pathlib import Path
import sys,json,hashlib
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'.model_runtime'))
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss

OUT=R/'model_results/transportability_core_ANN_2026_10_17_v1'
HOURS=[12,24,48];METRICS=['AUROC','average_precision','Brier']

class WeightedMetrics:
    def __init__(self,y,p):
        self.y=np.asarray(y,int);self.p=np.asarray(p,float)
        self.order=np.argsort(self.p,kind='stable');s=self.p[self.order]
        self.start=np.r_[0,np.flatnonzero(s[1:]!=s[:-1])+1]
    def calculate(self,weight):
        w=np.asarray(weight,float);yy=self.y[self.order];ww=w[self.order]
        positive=np.add.reduceat(ww*yy,self.start);negative=np.add.reduceat(ww*(1-yy),self.start)
        P=positive.sum();N=negative.sum()
        if P<=0 or N<=0:raise ValueError('Bootstrap sample lacks both classes')
        auc=np.sum(positive*(np.cumsum(negative)-.5*negative))/(P*N)
        tp=np.cumsum(positive[::-1]);tot=tp+np.cumsum(negative[::-1])
        precision=np.divide(tp,tot,out=np.zeros_like(tp),where=tot>0)
        ap=np.sum(positive[::-1]*precision)/P
        brier=np.sum(w*(self.y-self.p)**2)/(P+N)
        return np.array([auc,ap,brier])

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    if (OUT/'joint_bootstrap_samples.npz').exists():raise FileExistsError('Preserve completed bootstrap; do not overwrite.')
    manifest=json.loads((OUT/'prediction_manifest.json').read_text());frames={};samplers={};audit={}
    for db in ['MIMIC','eICU']:
        frames[db]={}
        for h in HOURS:
            path=OUT/f'{db}_{h}h_predictions_local.csv';assert sha(path)==manifest['prediction_sha256'][path.name]
            f=pd.read_csv(path,dtype={'patient_id':str,'hospital_id':str})
            assert f.patient_id.is_unique and f.hospital_id.notna().all()
            frames[db][h]=f
        combined=pd.concat(list(frames[db].values()),ignore_index=True)
        patients=pd.Index(sorted(combined.patient_id.unique()));hospitals=pd.Index(sorted(combined.hospital_id.unique()))
        audit[db]={'union_patients':len(patients),'union_hospitals':len(hospitals),'patients_changing_hospital':int((combined.groupby('patient_id').hospital_id.nunique()>1).sum())}
        samplers[db]={'patients':len(patients),'hospitals':len(hospitals),'cells':{}}
        for h,f in frames[db].items():
            calculator=WeightedMetrics(f.hospital_mortality,f.predicted_mortality)
            check=calculator.calculate(np.ones(len(f)))
            np.testing.assert_allclose(check,[roc_auc_score(f.hospital_mortality,f.predicted_mortality),average_precision_score(f.hospital_mortality,f.predicted_mortality),brier_score_loss(f.hospital_mortality,f.predicted_mortality)],atol=1e-12)
            samplers[db]['cells'][h]=(calculator,patients.get_indexer(f.patient_id),hospitals.get_indexer(f.hospital_id))
    points=np.array([[samplers[db]['cells'][h][0].calculate(np.ones(len(frames[db][h]))) for h in HOURS] for db in ['MIMIC','eICU']])
    streams=[np.random.default_rng(s) for s in np.random.SeedSequence(20261017).spawn(3)]
    samples=np.empty((5000,2,3,3));kept=0;attempts=0
    (OUT/'bootstrap_identity.json').write_text(json.dumps({'code_sha256':sha(Path(__file__)),'plan_sha256':sha(R/'transportability_analysis_lock_2026_10_17.md'),'seed':20261017,'replicates':5000,'cluster_audit':audit,'prediction_manifest_sha256':sha(OUT/'prediction_manifest.json')},indent=2))
    while kept<5000:
        attempts+=1
        nm=samplers['MIMIC']['patients'];ne=samplers['eICU']['patients'];nh=samplers['eICU']['hospitals']
        mw=np.bincount(streams[0].integers(nm,size=nm),minlength=nm)
        ew=np.bincount(streams[1].integers(ne,size=ne),minlength=ne)
        hw=np.bincount(streams[2].integers(nh,size=nh),minlength=nh)
        values=np.empty((2,3,3))
        try:
            for d,db in enumerate(['MIMIC','eICU']):
                for j,h in enumerate(HOURS):
                    calculator,person,hospital=samplers[db]['cells'][h]
                    weights=mw[person] if db=='MIMIC' else ew[person]*hw[hospital]
                    values[d,j]=calculator.calculate(weights)
        except ValueError:continue
        samples[kept]=values;kept+=1
        if kept%500==0:print('Joint paired bootstrap',kept,'/5000',flush=True)
    gaps=points[0]-points[1];bgaps=samples[:,0]-samples[:,1]
    rows=[];gaprows=[];contrasts=[]
    for d,db in enumerate(['MIMIC','eICU']):
        for j,h in enumerate(HOURS):
            for k,metric in enumerate(METRICS):
                low,high=np.quantile(samples[:,d,j,k],[.025,.975]);rows.append({'dataset':db,'landmark_hours':h,'metric':metric,'estimate':points[d,j,k],'lower95':low,'upper95':high})
    for j,h in enumerate(HOURS):
        for k,metric in enumerate(METRICS):
            low,high=np.quantile(bgaps[:,j,k],[.025,.975]);gaprows.append({'landmark_hours':h,'metric':metric,'internal_minus_external':gaps[j,k],'lower95':low,'upper95':high})
    for j,h in [(0,12),(2,48)]:
        for k,metric in enumerate(METRICS):
            delta=bgaps[:,j,k]-bgaps[:,1,k];low,high=np.quantile(delta,[.025,.975]);a,b=np.quantile(delta,[.0125,.9875])
            contrasts.append({'landmark_hours':h,'reference_hours':24,'metric':metric,'gap_difference':gaps[j,k]-gaps[1,k],'lower95':low,'upper95':high,'lower_multiplicity_adjusted':a if metric=='AUROC' else None,'upper_multiplicity_adjusted':b if metric=='AUROC' else None})
    pd.DataFrame(rows).to_csv(OUT/'metric_intervals.csv',index=False);pd.DataFrame(gaprows).to_csv(OUT/'transportability_gaps.csv',index=False);pd.DataFrame(contrasts).to_csv(OUT/'landmark_gap_contrasts.csv',index=False)
    np.savez_compressed(OUT/'joint_bootstrap_samples.npz',samples=samples,points=points,hours=HOURS,metric_names=METRICS)
    (OUT/'bootstrap_completed.json').write_text(json.dumps({'status':'Completed approximate paired cluster-aware AUROC/AP/Brier inference','retained':kept,'attempts':attempts,'training_uncertainty_included':False,'calibration_parameter_intervals_computed':False,'causal_eligibility_effect_estimated':False},indent=2))
    print(pd.DataFrame(gaprows).to_string(index=False),flush=True);print(pd.DataFrame(contrasts).to_string(index=False),flush=True)

if __name__=='__main__':main()
