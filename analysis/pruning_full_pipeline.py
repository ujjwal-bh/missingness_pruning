"""Paired full-pipeline bootstrap; restricted inputs remain local."""
from missingness_pruning_inputs import *
from missingness_pruning_models import PruningInputs
from revised_mimic_models import fit_ann,predict_ann
from train_missingness_pruning import ANN_CONFIG
from strengthen_calibration_uncertainty import WeightedCalibration
from sklearn.model_selection import StratifiedGroupKFold,StratifiedShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss,roc_auc_score,average_precision_score
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
import argparse,time,warnings,torch
from datetime import datetime,timezone

OUT=ROOT/'model_results/pruning_full_pipeline_2026_10_19_v1'
PROTOCOL=ROOT/'pruning_full_pipeline_protocol_2026_10_19.md'
N=200
STRATEGIES=['keep_all','targeted','drop_all']
CS=[1e-4,1e-3,.01,.1,1.,10.,100.,1000.,10000.]

def atomic(path,value):
    tmp=path.with_suffix('.tmp');save(tmp,value);tmp.replace(path)

def progress(message,**fields):
    row={'utc':datetime.now(timezone.utc).isoformat(),'message':message,**fields}
    with (OUT/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps(row),flush=True)

def grouped_folds(ids,y,seed):
    folds=list(StratifiedGroupKFold(5,shuffle=True,random_state=seed).split(ids,y,groups=ids))
    for a,b in folds:
        assert not set(ids[a])&set(ids[b])
        assert len(np.unique(y[a]))==len(np.unique(y[b]))==2
    return folds

def inner_stop(ids,y,fit,seed):
    unique,first=np.unique(ids[fit],return_index=True);labels=y[fit[first]]
    a,b=next(StratifiedShuffleSplit(n_splits=1,test_size=.15,random_state=seed).split(unique,labels))
    stop=fit[np.isin(ids[fit],unique[b])];inner=fit[np.isin(ids[fit],unique[a])]
    assert not set(ids[inner])&set(ids[stop]);return inner,stop

def target_indices(adapt_hosp,eval_hosp,rng):
    hospitals=np.unique(np.r_[adapt_hosp,eval_hosp]);a=[];e=[]
    ag={h:np.flatnonzero(adapt_hosp==h) for h in hospitals}
    eg={h:np.flatnonzero(eval_hosp==h) for h in hospitals}
    for h in hospitals[rng.integers(len(hospitals),size=len(hospitals))]:
        for groups,dest in [(ag,a),(eg,e)]:
            g=groups[h]
            if len(g):dest.append(g[rng.integers(len(g),size=len(g))])
    return np.concatenate(a),np.concatenate(e)

def load_inputs():
    hashes=json.loads((STAGE/'source_hashes.json').read_text())['features'];frames=[]
    for name in ['mimic_candidate_features.csv','eicu_candidate_features.csv']:
        path=ROOT/'model_preparation'/name;assert sha(path)==hashes[name]
        frames.append(read_predictors(path))
    source,target=frames
    source_train=source.loc[source.split.eq('train')].reset_index(drop=True)
    source_test=source.loc[source.split.eq('test')].reset_index(drop=True)
    config=json.loads(CONFIG.read_text());mask=adaptation_mask(target.patient_id,config)
    adapt=target.loc[mask].reset_index(drop=True);evaluation=target.loc[~mask].reset_index(drop=True)
    assert [len(x) for x in [source_train,source_test,adapt,evaluation]]==[37872,8149,20589,82748]
    # Only source fitting labels are needed until all replicate models are fitted.
    labels=pd.read_csv(ROOT/'model_preparation/mimic_candidate_features.csv',usecols=['patient_id','landmark_hours','hospital_mortality'],dtype={'patient_id':str})
    labels=labels.loc[labels.landmark_hours.eq(24)].set_index('patient_id').hospital_mortality
    return source_train,source_test,adapt,evaluation,labels.loc[source_train.patient_id].to_numpy(int)

def drop_for(strategy,X,adapt):
    if strategy=='keep_all':return []
    if strategy=='drop_all':return CORE.copy()
    return rank_indicators(pd.DataFrame(X,columns=CORE),adapt[CORE],6).loc[lambda f:f.remove_indicator,'variable'].tolist()

def fit_strategy(family,strategy,X,y,ids,adapt,seed):
    folds=grouped_folds(ids,y,seed);final_drop=drop_for(strategy,X,adapt);details={'mask':final_drop}
    if family=='ridge':
        prepared=[]
        for fit,held in folds:
            pre=PruningInputs(drop_for(strategy,X[fit],adapt)).fit(X[fit])
            prepared.append((pre.transform(X[fit]),y[fit],pre.transform(X[held]),y[held]))
        scores=[]
        for C in CS:
            loss=[]
            for xf,yf,xh,yh in prepared:
                model=LogisticRegression(C=C,l1_ratio=0.,solver='newton-cholesky',max_iter=3000,tol=1e-7).fit(xf,yf)
                loss.append(log_loss(yh,model.predict_proba(xh)[:,1],labels=[0,1]))
            scores.append(float(np.mean(loss)))
        chosen=CS[int(np.argmin(scores))];pre=PruningInputs(final_drop).fit(X)
        model=LogisticRegression(C=chosen,l1_ratio=0.,solver='newton-cholesky',max_iter=3000,tol=1e-7).fit(pre.transform(X),y)
        details.update(selected_C=chosen,grid_logloss=scores)
        return pre,[model],details
    epochs=[]
    for k,(fit,held) in enumerate(folds):
        inner,stop=inner_stop(ids,y,fit,seed+k)
        pre=PruningInputs(drop_for(strategy,X[inner],adapt)).fit(X[inner])
        _,epoch,_=fit_ann(pre.transform(X[inner]),y[inner],ANN_CONFIG,seed+100+k,stop=(pre.transform(X[stop]),y[stop]))
        epochs.append(int(epoch))
    epoch=max(1,int(np.median(epochs)));pre=PruningInputs(final_drop).fit(X);tx=pre.transform(X)
    models=[fit_ann(tx,y,ANN_CONFIG,seed+1000+k,epochs=epoch)[0] for k in range(3)]
    details.update(fold_epochs=epochs,final_epochs=epoch)
    return pre,models,details

def score(y,p):
    c=WeightedCalibration(y,p).fit(np.ones(len(y)))
    return dict(AUROC=float(roc_auc_score(y,p)),average_precision=float(average_precision_score(y,p)),Brier=float(np.mean((y-p)**2)),calibration_slope=float(c[3]),calibration_in_large=float(c[4]))

def summarize():
    rows=[];masks=[]
    for family in ['ridge','ANN']:
        for r in range(N):
            path=OUT/family/f'replicate_{r:04d}.json'
            if not path.exists():return
            rep=json.loads(path.read_text())
            for sample in ['MIMIC_test','eICU_evaluation']:
                for reference in ['keep_all','drop_all']:
                    for metric in ['AUROC','average_precision','Brier','calibration_slope','calibration_in_large']:
                        rows.append(dict(family=family,replicate=r,sample=sample,reference=reference,metric=metric,difference=rep['metrics'][sample]['targeted'][metric]-rep['metrics'][sample][reference][metric]))
            masks.extend(dict(family=family,replicate=r,variable=v) for v in rep['fits']['targeted']['mask'])
    df=pd.DataFrame(rows);df.to_csv(OUT/'replicate_contrasts.csv',index=False)
    points=pd.read_csv(ROOT/'model_results/missingness_pruning_2026_10_19_v1/evaluation/metrics.csv')
    results=[]
    for keys,g in df.groupby(['family','sample','reference','metric']):
        family,sample,reference,metric=keys;p=points.loc[points.family.eq(family)&points['sample'].eq(sample)].set_index('strategy')
        lo,hi=np.quantile(g.difference,[.025,.975]);results.append(dict(zip(['family','sample','reference','metric'],keys),original_estimate=float(p.loc['targeted',metric]-p.loc[reference,metric]),bootstrap_mean=float(g.difference.mean()),lower95=float(lo),upper95=float(hi),replicates=len(g)))
    pd.DataFrame(results).to_csv(OUT/'full_pipeline_intervals.csv',index=False)
    pd.DataFrame(masks).groupby(['family','variable']).size().rename('selected_replicates').reset_index().to_csv(OUT/'mask_frequencies.csv',index=False)
    assert len(df)==2*N*2*2*5 and len(results)==40
    atomic(OUT/'completed.json',{'status':'completed','replicates_per_family':N,'historical_exposure':True,'confirmatory':False,'checks':'400 replicate checkpoints and 40 interval rows reconciled','outputs':{p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.suffix=='.csv'}})
    progress('Full-pipeline robustness completed',replicates_per_family=N)

def run(limit=None):
    OUT.mkdir(parents=True,exist_ok=True)
    identity={'protocol':sha(PROTOCOL),'code':{n:sha(ROOT/n) for n in ['pruning_full_pipeline.py','missingness_pruning_inputs.py','missingness_pruning_models.py','revised_mimic_models.py','train_missingness_pruning.py','strengthen_calibration_uncertainty.py']},'input_hashes':json.loads((STAGE/'source_hashes.json').read_text()),'replicates':N}
    path=OUT/'identity_before_fitting.json'
    if path.exists():assert json.loads(path.read_text())==identity,'Implementation changed; do not overwrite an existing run'
    else:atomic(path,identity)
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    train,test,adapt,evaluation,y=load_inputs();X=train[CORE].to_numpy(float)
    maximum=N if limit is None else min(N,limit)
    with warnings.catch_warnings(),threadpool_limits(limits=2):
        warnings.simplefilter('error',ConvergenceWarning)
        for family in ['ridge','ANN']:
            folder=OUT/family;folder.mkdir(exist_ok=True)
            for r in range(maximum):
                dest=folder/f'replicate_{r:04d}.json'
                if dest.exists():assert json.loads(dest.read_text())['identity']==identity;continue
                started=time.perf_counter();progress('Full-pipeline replicate started',family=family,replicate=r+1,total=N)
                rng=np.random.default_rng(2026102000+r);ids=rng.integers(len(train),size=len(train));si=rng.integers(len(test),size=len(test))
                ai,ei=target_indices(adapt.hospital_id.to_numpy(),evaluation.hospital_id.to_numpy(),rng)
                a=adapt.iloc[ai];fitted={};details={}
                for strategy in STRATEGIES:
                    pre,models,detail=fit_strategy(family,strategy,X[ids],y[ids],ids,a,20262000+r*10000)
                    fitted[strategy]=(pre,models);details[strategy]=detail
                    progress('Replicate strategy fitted',family=family,replicate=r+1,strategy=strategy)
                # Only evaluate after all three strategies are fitted; target adaptation outcomes never loaded.
                outputs={}
                for sample,frame,indices in [('MIMIC_test',test,si),('eICU_evaluation',evaluation,ei)]:
                    directory=ROOT/'model_results/missingness_pruning_2026_10_19_v1/evaluation'
                    filename=f'{sample}_ridge_predictions_local.csv'
                    manifest=json.loads((directory/'prediction_manifest.json').read_text());assert sha(directory/filename)==manifest[filename]
                    # Hashed evaluation-only label file contains no adaptation patients.
                    labels=pd.read_csv(directory/filename,usecols=['patient_id','hospital_mortality'],dtype={'patient_id':str}).set_index('patient_id').hospital_mortality
                    assert set(labels.index)==set(frame.patient_id)
                    yy=labels.loc[frame.patient_id].to_numpy(int)[indices];xx=frame[CORE].to_numpy(float)[indices];outputs[sample]={}
                    for strategy,(pre,models) in fitted.items():
                        tx=pre.transform(xx)
                        p=np.mean([m.predict_proba(tx)[:,1] if family=='ridge' else predict_ann(m,tx) for m in models],axis=0)
                        outputs[sample][strategy]=score(yy,p)
                atomic(dest,dict(identity=identity,replicate=r,family=family,fits=details,metrics=outputs,seconds=time.perf_counter()-started,training_seed=20262000+r*10000,draw_seed=2026102000+r))
                progress('Full-pipeline replicate completed',family=family,replicate=r+1,seconds=round(time.perf_counter()-started,1))
    summarize()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int);args=p.parse_args()
    try:run(args.limit)
    except Exception as e:
        if OUT.exists():atomic(OUT/'failed.json',{'utc':datetime.now(timezone.utc).isoformat(),'error':str(e),'type':type(e).__name__})
        raise
