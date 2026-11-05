"""All source fits freeze before target outcome scoring; resumable verified cells."""
from missingness_pruning_inputs import *
from missingness_pruning_models import PruningInputs
from revised_mimic_models import fit_ann,predict_ann
import argparse,time,warnings,joblib,torch,sklearn
from datetime import datetime,timezone
from sklearn.model_selection import StratifiedKFold,StratifiedShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss,average_precision_score
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

OUT=ROOT/'model_results/missingness_pruning_2026_10_19_v1'
SEEDS=[20261016,20261017,20261018]
ANN_CONFIG={'lr':.001,'weight_decay':.00001,'dropout':.1,'batchnorm':True,'death_weight':1.}

def progress(message,**fields):
    OUT.mkdir(parents=True,exist_ok=True)
    row={'utc':datetime.now(timezone.utc).isoformat(),'message':message,**fields}
    with (OUT/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    print(message,json.dumps(fields),flush=True)

def get_identity():
    prep=json.loads((STAGE/'completed.json').read_text())
    assert prep['identity']['plan_sha256']==sha(PLAN) and prep['identity']['config_sha256']==sha(CONFIG)
    for name,value in prep['outputs'].items():assert sha(STAGE/name)==value
    return {'plan_sha256':sha(PLAN),'config_sha256':sha(CONFIG),'preparation_completed_sha256':sha(STAGE/'completed.json'),'code_sha256':{n:sha(ROOT/n) for n in ['train_missingness_pruning.py','missingness_pruning_models.py','missingness_pruning_inputs.py','revised_mimic_models.py']},'numpy':np.__version__,'pandas':pd.__version__,'torch':torch.__version__,'sklearn':sklearn.__version__,'historical_external_exposure':True}

def strategies():
    m=json.loads((STAGE/'indicator_masks.json').read_text())
    return {'keep_all':[],'targeted':m['targeted'],'drop_all':CORE,**m['random']}

def source_training():
    path=ROOT/'model_preparation/mimic_candidate_features.csv'
    inputs=json.loads((STAGE/'source_hashes.json').read_text())['features'];assert sha(path)==inputs[path.name]
    f=pd.read_csv(path,usecols=META+CORE+['hospital_mortality'],dtype={'patient_id':str,'stay_id':str,'hospital_id':str})
    f=f.loc[f.landmark_hours.eq(24)&f.split.eq('train')].reset_index(drop=True)
    assert len(f)==37872 and f.patient_id.is_unique and set(f.hospital_mortality)=={0,1}
    return f

def actual_drop(name,fitting_features,adaptation,nominal):
    if name!='targeted':return list(nominal)
    r=rank_indicators(fitting_features,adaptation,6)
    return r.loc[r.remove_indicator,'variable'].tolist()

def verified_completed(folder,identity):
    path=folder/'completed.json'
    if not path.exists():return False
    completed=json.loads(path.read_text());assert completed['identity']==identity
    for name,value in completed['outputs'].items():assert sha(folder/name)==value
    return True

def finish(folder,identity,**extra):
    save(folder/'completed.json',{'identity':identity,'outputs':{p.name:sha(p) for p in folder.iterdir() if p.is_file() and p.name!='completed.json'},**extra})

def train(family):
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    identity=get_identity();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'training_identity.json').exists():assert json.loads((OUT/'training_identity.json').read_text())==identity
    else:save(OUT/'training_identity.json',identity)
    f=source_training();X=f[CORE].to_numpy(float);y=f.hospital_mortality.to_numpy(int)
    adapt=pd.read_csv(STAGE/'adaptation_predictors_local.csv',usecols=CORE)
    assert len(adapt)==20589
    folds=list(StratifiedKFold(n_splits=5,shuffle=True,random_state=20261015).split(X,y))
    foldno=np.empty(len(y),int)
    for k,(_,held) in enumerate(folds):foldno[held]=k
    path=OUT/'source_training_folds_local.csv'
    if not path.exists():f[['patient_id','stay_id']].assign(cv_fold=foldno).to_csv(path,index=False)
    else:
        old=pd.read_csv(path,dtype={'patient_id':str});assert np.array_equal(old.patient_id,f.patient_id) and np.array_equal(old.cv_fold,foldno)
    for name,nominal in strategies().items():
        folder=OUT/family/name;folder.mkdir(parents=True,exist_ok=True)
        if verified_completed(folder,identity):continue
        before=time.perf_counter();progress('Pruning source fit started',family=family,strategy=name)
        final_drop=actual_drop(name,f[CORE],adapt,nominal)
        if name=='targeted':assert final_drop==nominal
        if family=='ridge':
            prepared=[];fold_masks=[]
            for fit,held in folds:
                drop=actual_drop(name,f.iloc[fit][CORE],adapt,nominal);fold_masks.append(drop)
                pre=PruningInputs(drop).fit(X[fit]);prepared.append((pre.transform(X[fit]),y[fit],pre.transform(X[held]),y[held]))
            scores=[]
            with warnings.catch_warnings(),threadpool_limits(limits=2):
                warnings.simplefilter('error',ConvergenceWarning)
                for C in [1e-4,1e-3,.01,.1,1.,10.,100.,1000.,10000.]:
                    losses=[]
                    for xf,yf,xh,yh in prepared:
                        model=LogisticRegression(C=C,l1_ratio=0.,solver='newton-cholesky',max_iter=3000,tol=1e-7).fit(xf,yf)
                        losses.append(float(log_loss(yh,model.predict_proba(xh)[:,1],labels=[0,1])))
                    scores.append({'C':C,'mean_fold_logloss':float(np.mean(losses)),'fold_logloss':losses})
                chosen=min(scores,key=lambda v:v['mean_fold_logloss'])
                pre=PruningInputs(final_drop).fit(X)
                model=LogisticRegression(C=chosen['C'],l1_ratio=0.,solver='newton-cholesky',max_iter=3000,tol=1e-7).fit(pre.transform(X),y)
            joblib.dump({'preprocessor':pre,'model':model},folder/'pipeline.joblib')
            save(folder/'cv_selection.json',{'grid':scores,'selected_C':chosen['C'],'fold_indicator_masks':fold_masks,'final_indicator_mask':final_drop})
        else:
            epochs=[];cv=[]
            for k,(fit,held) in enumerate(folds):
                meta=folder/f'fold_{k}.json';cache=folder/f'fold_{k}.npz'
                if meta.exists():
                    result=json.loads(meta.read_text());assert result['identity']==identity and result['cache_sha256']==sha(cache)
                    data=np.load(cache);assert np.array_equal(data['heldout_indices'],held)
                else:
                    inner,stop=next(StratifiedShuffleSplit(n_splits=1,test_size=.15,random_state=20261015+k).split(X[fit],y[fit]));inner=fit[inner];stop=fit[stop]
                    drop=actual_drop(name,f.iloc[inner][CORE],adapt,nominal)
                    pre=PruningInputs(drop).fit(X[inner])
                    model,epoch,trace=fit_ann(pre.transform(X[inner]),y[inner],ANN_CONFIG,SEEDS[0]+k,stop=(pre.transform(X[stop]),y[stop]))
                    p=predict_ann(model,pre.transform(X[held]));np.savez_compressed(cache,heldout_indices=held,p=p)
                    result={'identity':identity,'fold':k,'epoch':int(epoch),'fold_AP':float(average_precision_score(y[held],p)),'drop_indicators':drop,'trace':trace,'cache_sha256':sha(cache)}
                    save(meta,result)
                epochs.append(result['epoch']);cv.append(result)
                progress('Pruning ANN fold completed',strategy=name,fold=k,epoch=result['epoch'])
            epoch=max(1,int(np.median(epochs)));pre=PruningInputs(final_drop).fit(X);joblib.dump(pre,folder/'preprocessor.joblib')
            for seed in SEEDS:
                path=folder/f'model_seed_{seed}.pt'
                if path.exists():
                    cp=torch.load(path,map_location='cpu',weights_only=True)
                    assert cp['epochs']==epoch and cp['config']==ANN_CONFIG and cp['plan_sha256']==sha(PLAN)
                    continue
                model,_,trace=fit_ann(pre.transform(X),y,ANN_CONFIG,seed,epochs=epoch)
                torch.save({'state':model.state_dict(),'config':ANN_CONFIG,'epochs':epoch,'inputs':pre.transform(X[:1]).shape[1],'plan_sha256':sha(PLAN)},path)
                save(folder/f'trace_seed_{seed}.json',trace)
                progress('Pruning ANN final seed completed',strategy=name,seed=seed,epochs=epoch)
            save(folder/'cv_selection.json',{'folds':[{'fold':r['fold'],'epoch':r['epoch'],'AP':r['fold_AP'],'drop_indicators':r['drop_indicators']} for r in cv],'final_epochs':epoch,'final_drop_indicators':final_drop})
        finish(folder,identity,training_patients=len(f),drop_indicators=final_drop,target_outcomes_used=False,seconds=time.perf_counter()-before)
        progress('Pruning source strategy frozen',family=family,strategy=name,seconds=round(time.perf_counter()-before,1))
    save(OUT/f'{family}_completed.json',{'identity':identity,'strategies':list(strategies()),'source_fitting_only':True,'target_scoring_performed':False})
    progress('Pruning model family frozen',family=family,strategies=len(strategies()))
    if all((OUT/f'{fam}_completed.json').exists() for fam in ['ridge','ANN']):
        save(OUT/'all_models_frozen.json',{'identity':identity,'families':['ridge','ANN'],'strategies':list(strategies()),'target_outcomes_used':False,'frozen_utc':datetime.now(timezone.utc).isoformat()})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('family',choices=['ridge','ANN']);args=p.parse_args();train(args.family)
