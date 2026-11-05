"""Paired fixed-score uncertainty and a Gaussian-probit coverage experiment."""
from evidence_amendment_common import *
import argparse
from scipy.special import ndtr, ndtri
from numpy.polynomial.legendre import leggauss

class WeightedAUC:
    def __init__(self,y,p):
        self.y=np.asarray(y,int);p=np.asarray(p,float)
        assert len(p)==len(self.y) and np.isfinite(p).all() and set(self.y)=={0,1}
        self.order=np.argsort(p,kind='stable');s=p[self.order];self.yy=self.y[self.order]
        self.starts=np.r_[0,np.flatnonzero(s[1:]!=s[:-1])+1]
    def __call__(self,w):
        w=np.asarray(w,float)[self.order]
        pos=np.add.reduceat(w*self.yy,self.starts);neg=np.add.reduceat(w*(1-self.yy),self.starts)
        den=pos.sum()*neg.sum()
        if den<=0:raise ValueError('Resample has only one outcome')
        return float(np.dot(pos,np.cumsum(neg)-.5*neg)/den)

def prepare(frames):
    sizes={};cells={};audit=[]
    for db in ['MIMIC','eICU']:
        combined=pd.concat([f for (d,_,_,_),f in frames.items() if d==db],ignore_index=True)
        people=pd.Index(sorted(combined.patient_id.unique()));hospitals=pd.Index(sorted(combined.hospital_id.unique()))
        sizes[db]=(len(people),len(hospitals))
        audit.append({'dataset':db,'patients':len(people),'hospitals':len(hospitals),'patients_crossing_hospitals':int(combined.groupby('patient_id').hospital_id.nunique().gt(1).sum())})
        for key,f in frames.items():
            if key[0]!=db:continue
            cells[key]=(WeightedAUC(f.hospital_mortality,f.predicted_mortality),people.get_indexer(f.patient_id),hospitals.get_indexer(f.hospital_id))
    return sizes,cells,audit

def summarize(samples,points,keys):
    rows=[]
    for name,family in sorted(set((k[2],k[3]) for k in keys)):
        positions={(db,h):keys.index((db,h,name,family)) for db in ['MIMIC','eICU'] for h in HOURS}
        gaps={h:samples[:,positions['MIMIC',h]]-samples[:,positions['eICU',h]] for h in HOURS}
        pointgap={h:points[positions['MIMIC',h]]-points[positions['eICU',h]] for h in HOURS}
        for h in [12,48]:
            v=gaps[h]-gaps[24];lo,hi=np.quantile(v,[.025,.975])
            rows.append({'feature_set':name,'family':family,'landmark_hours':h,'reference_hours':24,'gap_difference':pointgap[h]-pointgap[24],'lower95':lo,'upper95':hi})
    return rows

def clinical(ablation=False):
    target=BASE/('measurement_uncertainty' if ablation else 'resampling_comparison');target.mkdir(parents=True,exist_ok=True)
    if check_completed(target,__file__):return
    frames={};hashes={}
    if ablation:
        directory=BASE/'measurement/evaluation';manifest=json.loads((directory/'prediction_manifest.json').read_text())
        combinations=[(name,fam) for name in SETS for fam in ['ridge','ANN']]
    else:
        directory=PRIMARY;manifest=json.loads((directory/'prediction_manifest.json').read_text())['prediction_sha256'];combinations=[('full','ANN')]
    for db in ['MIMIC','eICU']:
        for h in HOURS:
            reference=None
            for name,family in combinations:
                filename=f'{db}_{h}h_{name}_{family}_local.csv' if ablation else f'{db}_{h}h_predictions_local.csv'
                path=directory/filename;assert sha(path)==manifest[filename]
                f=pd.read_csv(path,dtype={'patient_id':str,'stay_id':str,'hospital_id':str});assert f.patient_id.is_unique
                if reference is None:reference=f[['patient_id','stay_id','hospital_id','hospital_mortality']].copy()
                else:assert reference.equals(f[['patient_id','stay_id','hospital_id','hospital_mortality']])
                frames[db,h,name,family]=f;hashes[filename]=sha(path)
    sizes,cells,audit=prepare(frames);keys=list(cells)
    points=np.array([cells[k][0](np.ones(len(frames[k]))) for k in keys]);rows=[]
    for method in (['crossed'] if ablation else ['patient','hospital','crossed']):
        rng=np.random.default_rng(2026101901);draws=np.empty((2000,len(keys)));kept=attempts=0
        nm=sizes['MIMIC'][0];ne,nh=sizes['eICU']
        while kept<2000:
            attempts+=1
            mw=np.bincount(rng.integers(nm,size=nm),minlength=nm)
            ew=np.bincount(rng.integers(ne,size=ne),minlength=ne)
            hw=np.bincount(rng.integers(nh,size=nh),minlength=nh)
            values=[]
            try:
                for key in keys:
                    calc,pid,hid=cells[key]
                    if key[0]=='MIMIC':w=mw[pid]
                    elif method=='patient':w=ew[pid]
                    elif method=='hospital':w=hw[hid]
                    else:w=ew[pid]*hw[hid]
                    values.append(calc(w))
            except ValueError:continue
            draws[kept]=values;kept+=1
            if kept%500==0:progress('Fixed-score bootstrap progress',task='measurement' if ablation else 'original',method=method,replicates=kept)
        rows.extend([{**r,'method':method,'replicates':kept,'attempts':attempts} for r in summarize(draws,points,keys)])
        if ablation:
            # Paired difference in the landmark contrast relative to its full-input parent.
            extra=[]
            for fam in ['ridge','ANN']:
                def contrast(name):
                    ids={ (d,h):keys.index((d,h,name,fam)) for d in ['MIMIC','eICU'] for h in [24,48] }
                    vals=draws[:,ids['MIMIC',48]]-draws[:,ids['eICU',48]]-draws[:,ids['MIMIC',24]]+draws[:,ids['eICU',24]]
                    point=points[ids['MIMIC',48]]-points[ids['eICU',48]]-points[ids['MIMIC',24]]+points[ids['eICU',24]]
                    return vals,point
                ref,rp=contrast('full')
                for name in ['no_indicators','vitals']:
                    val,pt=contrast(name);lo,hi=np.quantile(val-ref,[.025,.975])
                    extra.append({'family':fam,'feature_set':name,'contrast':'48-minus24 gap contrast minus full-input counterpart','difference':pt-rp,'lower95':lo,'upper95':hi})
            pd.DataFrame(extra).to_csv(target/'paired_ablation_differences.csv',index=False)
        np.savez_compressed(target/f'{method}_samples.npz',samples=draws,points=points)
    pd.DataFrame(rows).to_csv(target/'gap_contrast_intervals.csv',index=False)
    pd.DataFrame(audit).to_csv(target/'cluster_structure.csv',index=False)
    save(target/'input_hashes.json',hashes);save(target/'cell_order.json',keys)
    finish(target,__file__,replicates_per_method=2000,conditional_on_fitted_models=True)
    progress('Fixed-score uncertainty completed',task='measurement' if ablation else 'original')

def theoretical_auc(rho,prevalence,n=400):
    """Probit population AUC via deterministic conditional-normal quadrature."""
    nodes,weights=leggauss(n);u=(nodes+1)/2;w=weights/2;c=1-prevalence
    positive=ndtri(c+u*prevalence);negative=ndtri(u*c)
    probs=ndtr(rho*(positive[:,None]-negative[None,:])/np.sqrt(2*(1-rho*rho)))
    return float(w@probs@w)

def simulated_sample(rng,crossed):
    result={}
    for db,n in [('MIMIC',600),('eICU',1200)]:
        x=rng.normal(size=n);u=rng.normal(size=n);eps=rng.normal(size=n)
        hosps=40 if db=='eICU' else 1;v=rng.normal(size=hosps) if db=='eICU' else np.zeros(1)
        initial=rng.integers(hosps,size=n);other=rng.integers(hosps,size=n);change=rng.uniform(size=n)
        selection=rng.uniform(size=n)
        for j,h in enumerate(HOURS):
            hospital=np.where(change<(.12*j if crossed and db=='eICU' else 0),other,initial)
            a=1.;b=.4 if db=='eICU' else 0.;beta=([1.1,1.05,.8] if db=='eICU' else [1.5,1.5,1.4])[j]
            delta=.8 if db=='eICU' else 0.;gamma=.5;prevalence=[.10,.12,.15][j]
            sd=np.sqrt(beta*beta+gamma*gamma+delta*delta+1)
            latent=beta*x+gamma*u+delta*v[hospital]+eps
            y=(latent>ndtri(1-prevalence)*sd).astype(int);score=a*x+b*v[hospital]
            keep=selection<[1.,.85,.65][j];ids=np.flatnonzero(keep)
            result[db,h,'simulation','fixed_score']=pd.DataFrame({'patient_id':ids.astype(str),'hospital_id':hospital[keep].astype(str),'hospital_mortality':y[keep],'predicted_mortality':ndtr(score[keep])})
    return result

def simulation():
    target=BASE/'coverage_simulation';target.mkdir(parents=True,exist_ok=True)
    if check_completed(target,__file__):return
    auc={};reference=[]
    for db in ['MIMIC','eICU']:
        for j,h in enumerate(HOURS):
            beta=([1.1,1.05,.8] if db=='eICU' else [1.5,1.5,1.4])[j];b=.4 if db=='eICU' else 0.;delta=.8 if db=='eICU' else 0.
            rho=(beta+b*delta)/np.sqrt((1+b*b)*(beta*beta+.25+delta*delta+1))
            prev=[.10,.12,.15][j];value=theoretical_auc(rho,prev,400);fine=theoretical_auc(rho,prev,800)
            assert abs(value-fine)<2e-5, 'Population reference quadrature not sufficiently converged'
            auc[db,h]=fine;reference.append({'dataset':db,'landmark_hours':h,'rho':rho,'prevalence':prev,'population_AUROC':fine,'quadrature_refinement_difference':fine-value})
    truth=(auc['MIMIC',48]-auc['eICU',48])-(auc['MIMIC',24]-auc['eICU',24])
    pd.DataFrame(reference).to_csv(target/'population_reference.csv',index=False)
    records=[]
    for design in ['nested','crossed']:
        rng=np.random.default_rng(2026101902 if design=='nested' else 2026101903)
        for repeat in range(200):
            frames=simulated_sample(rng,design=='crossed');sizes,cells,audit=prepare(frames);keys=list(cells)
            point=np.array([cells[k][0](np.ones(len(frames[k]))) for k in keys])
            idx={(db,h):keys.index((db,h,'simulation','fixed_score')) for db in ['MIMIC','eICU'] for h in [24,48]}
            estimate=point[idx['MIMIC',48]]-point[idx['eICU',48]]-point[idx['MIMIC',24]]+point[idx['eICU',24]]
            draws={m:[] for m in ['patient','hospital','crossed']};nm=sizes['MIMIC'][0];ne,nh=sizes['eICU']
            attempts=0
            while min(map(len,draws.values()))<299:
                attempts+=1
                if attempts>1000:raise RuntimeError('Excessive failed simulation resamples')
                mw=np.bincount(rng.integers(nm,size=nm),minlength=nm);ew=np.bincount(rng.integers(ne,size=ne),minlength=ne);hw=np.bincount(rng.integers(nh,size=nh),minlength=nh)
                for method in draws:
                    if len(draws[method])>=299:continue
                    values={}
                    try:
                        for (db,h),i in idx.items():
                            calc,pid,hid=cells[keys[i]]
                            w=mw[pid] if db=='MIMIC' else ew[pid] if method=='patient' else hw[hid] if method=='hospital' else ew[pid]*hw[hid]
                            values[db,h]=calc(w)
                    except ValueError:continue
                    draws[method].append(values['MIMIC',48]-values['eICU',48]-values['MIMIC',24]+values['eICU',24])
            for method,values in draws.items():
                lo,hi=np.quantile(values,[.025,.975]);records.append({'design':design,'repeat':repeat,'method':method,'estimate':estimate,'truth':truth,'lower95':lo,'upper95':hi,'covers':int(lo<=truth<=hi)})
            if (repeat+1)%50==0:progress('Coverage simulation progress',design=design,datasets=repeat+1)
    data=pd.DataFrame(records);data.to_csv(target/'replicate_results.csv',index=False)
    summary=data.groupby(['design','method']).agg(datasets=('covers','size'),coverage=('covers','mean'),mean_lower=('lower95','mean'),mean_upper=('upper95','mean')).reset_index()
    summary['coverage_MCSE']=np.sqrt(summary.coverage*(1-summary.coverage)/summary.datasets)
    summary['mean_interval_width']=summary.mean_upper-summary.mean_lower
    summary.to_csv(target/'coverage_summary.csv',index=False)
    finish(target,__file__,datasets_per_design=200,bootstrap_per_dataset=299,simulation_only=True,truth=truth,not_general_proof_of_coverage=True)
    progress('Coverage simulation completed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['original','ablation','simulation']);args=p.parse_args()
    simulation() if args.stage=='simulation' else clinical(args.stage=='ablation')
