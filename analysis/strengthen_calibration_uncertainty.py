"""Cluster-aware calibration diagnostics, not recalibrated prediction models."""
from strengthen_transportability_subgroups import BASE,load_predictions
from transportability_bootstrap import R,OUT,HOURS,np,pd,json,sha
from scipy.special import expit,logit

NAMES=['observed_mortality','mean_prediction','joint_intercept','slope','calibration_in_large']

class WeightedCalibration:
    def __init__(self,y,p):
        self.y=np.asarray(y,float);self.p=np.asarray(p,float);self.z=logit(np.clip(self.p,1e-7,1-1e-7))
        if np.ptp(self.z)==0:raise ValueError('Calibration slope is not identifiable for constant scores')
        edges=np.unique(np.quantile(self.p,np.linspace(0,1,11)))
        self.bin=np.searchsorted(edges[1:-1],self.p,side='left');self.bins=len(edges)-1
    def fit(self,weight,start=None):
        w=np.asarray(weight,float);total=w.sum();event=np.sum(w*self.y)
        if total<=0 or event<=0 or event>=total:raise ValueError('Calibration sample lacks both outcomes')
        z=self.z;y=self.y;b=np.array([0.,1.] if start is None else start[2:4],float)
        for _ in range(40):
            eta=b[0]+b[1]*z;q=expit(eta);res=w*(q-y)
            g=np.array([res.sum(),np.sum(res*z)])/total
            if np.max(np.abs(g))<2e-9:break
            curvature=w*q*(1-q);c0=curvature.sum();c1=np.sum(curvature*z);c2=np.sum(curvature*z*z)
            H=np.array([[c0,c1],[c1,c2]])/total
            try:step=np.linalg.solve(H,g)
            except np.linalg.LinAlgError:raise ValueError('Singular calibration fit')
            loss=np.sum(w*(np.logaddexp(0,eta)-y*eta))/total
            accepted=False
            for factor in [.5**i for i in range(16)]:
                candidate=b-factor*step;neweta=candidate[0]+candidate[1]*z
                newloss=np.sum(w*(np.logaddexp(0,neweta)-y*neweta))/total
                if np.isfinite(newloss) and newloss<=loss+1e-13:b=candidate;accepted=True;break
            if not accepted:raise ValueError('Calibration line search failed')
        else:raise ValueError('Calibration Newton iterations did not converge')
        offset=0. if start is None else float(start[4])
        for _ in range(40):
            q=expit(z+offset);g=np.sum(w*(q-y))/total
            if abs(g)<2e-10:break
            H=np.sum(w*q*(1-q))/total
            if H<=0:raise ValueError('Nonidentifiable calibration offset')
            offset-=np.clip(g/H,-5,5)
        else:raise ValueError('Calibration offset did not converge')
        return np.array([event/total,np.sum(w*self.p)/total,b[0],b[1],offset])
    def bin_rates(self,w):
        denominator=np.bincount(self.bin,weights=w,minlength=self.bins)
        numerator=np.bincount(self.bin,weights=w*self.y,minlength=self.bins)
        if (denominator<=0).any():raise ValueError('Empty weighted calibration bin')
        return numerator/denominator

def main():
    target=BASE/'calibration_uncertainty';target.mkdir(parents=True,exist_ok=False)
    frames=load_predictions();samplers={};points=np.empty((2,3,5));bins={}
    previous=pd.read_csv(OUT/'point_metrics.csv');previous=previous.loc[previous.model=='equal_ensemble']
    for d,db in enumerate(['MIMIC','eICU']):
        combined=pd.concat(list(frames[db].values()),ignore_index=True);people=pd.Index(sorted(combined.patient_id.unique()));hospitals=pd.Index(sorted(combined.hospital_id.unique()))
        samplers[db]={'people':len(people),'hospitals':len(hospitals),'cells':{}}
        for j,h in enumerate(HOURS):
            f=frames[db][h];calc=WeightedCalibration(f.hospital_mortality,f.predicted_mortality)
            point=calc.fit(np.ones(len(f)));points[d,j]=point
            row=previous.loc[(previous.dataset==db)&(previous.landmark_hours==h)].iloc[0]
            np.testing.assert_allclose(point,[row.observed_mortality,row.mean_prediction,row.calibration_intercept_joint,row.calibration_slope,row.calibration_in_large],rtol=0,atol=2e-5)
            assert calc.bins==10
            samplers[db]['cells'][h]=(calc,people.get_indexer(f.patient_id),hospitals.get_indexer(f.hospital_id))
            bins[db,h]=pd.DataFrame({'bin':np.arange(10),'patients':np.bincount(calc.bin,minlength=10),'predicted':np.bincount(calc.bin,weights=calc.p,minlength=10)/np.bincount(calc.bin,minlength=10),'observed':calc.bin_rates(np.ones(len(f)))})
    (target/'identity.json').write_text(json.dumps({'code_sha256':sha(__file__),'plan_sha256':sha(R/'evidence_strengthening_lock_2026_10_17.md'),'replicates':2000,'seed':20261021,'prediction_changes':False,'diagnostic_fits_only':True,'point_estimates_match_previous':True},indent=2))
    samples=np.empty((2000,2,3,5));bsbins=np.empty((2000,2,3,10));rng=[np.random.default_rng(s) for s in np.random.SeedSequence(20261021).spawn(3)]
    kept=0;attempts=0;failures={}
    while kept<2000:
        attempts+=1
        nm=samplers['MIMIC']['people'];ne=samplers['eICU']['people'];nh=samplers['eICU']['hospitals']
        mw=np.bincount(rng[0].integers(nm,size=nm),minlength=nm);ew=np.bincount(rng[1].integers(ne,size=ne),minlength=ne);hw=np.bincount(rng[2].integers(nh,size=nh),minlength=nh)
        values=np.empty((2,3,5));bv=np.empty((2,3,10))
        try:
            for d,db in enumerate(['MIMIC','eICU']):
                for j,h in enumerate(HOURS):
                    calc,pid,hid=samplers[db]['cells'][h];w=mw[pid] if db=='MIMIC' else ew[pid]*hw[hid]
                    values[d,j]=calc.fit(w,start=points[d,j]);bv[d,j]=calc.bin_rates(w)
        except ValueError as e:
            failures[str(e)]=failures.get(str(e),0)+1
            if attempts>2100:raise RuntimeError('Excess calibration failures; investigate instead of discarding more replicates')
            continue
        samples[kept]=values;bsbins[kept]=bv;kept+=1
        if kept%100==0:print('Calibration bootstrap',kept,'/2000',flush=True)
    rows=[];contrasts=[]
    for d,db in enumerate(['MIMIC','eICU']):
        for j,h in enumerate(HOURS):
            for k,name in enumerate(NAMES):
                low,high=np.quantile(samples[:,d,j,k],[.025,.975]);rows.append({'dataset':db,'landmark_hours':h,'metric':name,'estimate':points[d,j,k],'lower95':low,'upper95':high})
            b=bins[db,h];b['observed_lower95']=np.quantile(bsbins[:,d,j],.025,axis=0);b['observed_upper95']=np.quantile(bsbins[:,d,j],.975,axis=0);b.to_csv(target/f'{db}_{h}h_calibration_bins.csv',index=False)
    difference=samples[:,1]-samples[:,0];pointdiff=points[1]-points[0]
    for j,h in enumerate(HOURS):
        for k,name in enumerate(NAMES):
            low,high=np.quantile(difference[:,j,k],[.025,.975]);contrasts.append({'landmark_hours':h,'metric':name,'external_minus_internal':pointdiff[j,k],'lower95':low,'upper95':high})
    pd.DataFrame(rows).to_csv(target/'calibration_intervals.csv',index=False);pd.DataFrame(contrasts).to_csv(target/'external_minus_internal.csv',index=False)
    np.savez_compressed(target/'bootstrap_samples.npz',samples=samples,points=points,bin_observed=bsbins,metric_names=NAMES)
    (target/'completed.json').write_text(json.dumps({'status':'completed','retained':kept,'attempts':attempts,'failures':failures,'conditional_on_frozen_models':True,'pointwise_bin_intervals':True,'simultaneous_curve_bands':False,'prediction_changes':False},indent=2))
    print('Calibration bootstrap completed',flush=True)

if __name__=='__main__':main()
