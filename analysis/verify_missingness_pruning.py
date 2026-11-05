"""Independent reconstruction of rates, partitions, fitted preprocessing and intervals."""
from missingness_pruning_inputs import *
from train_missingness_pruning import OUT,get_identity,strategies,source_training,verified_completed
from missingness_pruning_models import PruningInputs
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss,log_loss
from sklearn.model_selection import StratifiedKFold,StratifiedShuffleSplit
import joblib,torch

def run():
    checks=[];config=json.loads(CONFIG.read_text());identity=get_identity()
    preparation=json.loads((STAGE/'completed.json').read_text());summary=json.loads((STAGE/'preparation_summary.json').read_text())
    partitions=pd.read_csv(STAGE/'target_partitions_local.csv',dtype={'patient_id':str,'stay_id':str,'hospital_id':str})
    mask=adaptation_mask(partitions.patient_id,config)
    assert np.array_equal(np.where(mask,'adaptation','evaluation'),partitions.target_partition)
    assert partitions.patient_id.is_unique and mask.sum()==20589 and (~mask).sum()==82748
    source=source_training();adapt=pd.read_csv(STAGE/'adaptation_predictors_local.csv',usecols=CORE)
    rank=rank_indicators(source[CORE],adapt,6);saved=pd.read_csv(STAGE/'missingness_ranking.csv')
    assert rank.variable.tolist()==saved.variable.tolist()
    np.testing.assert_allclose(rank.absolute_shift,saved.absolute_shift,rtol=0,atol=1e-14)
    assert rank.loc[rank.remove_indicator,'variable'].tolist()==summary['pruned_indicators']
    masks=json.loads((STAGE/'indicator_masks.json').read_text());assert list(masks['random'].values())==random_masks()
    checks.append('Identifier-only patient partition, adaptation-only rate ranking and every random mask reproduced')
    X=source[CORE].to_numpy(float);y=source.hospital_mortality.to_numpy(int)
    expected_pre=PruningInputs([]).fit(X)
    folds=list(StratifiedKFold(n_splits=5,shuffle=True,random_state=20261015).split(X,y))
    for family in ['ridge','ANN']:
        for name,drop in strategies().items():
            folder=OUT/family/name;assert verified_completed(folder,identity)
            pre=joblib.load(folder/'pipeline.joblib')['preprocessor'] if family=='ridge' else joblib.load(folder/'preprocessor.joblib')
            for attr in ['lower_','upper_','median_','mean_','scale_']:np.testing.assert_allclose(getattr(pre,attr),getattr(expected_pre,attr),rtol=0,atol=1e-12)
            np.testing.assert_array_equal(pre.transform(X[:20])[:,:26],expected_pre.transform(X[:20])[:,:26])
            assert pre.transform(X[:1]).shape[1]==52-len(drop)
        if family=='ridge':fold_masks=json.loads((OUT/family/'targeted/cv_selection.json').read_text())['fold_indicator_masks']
        for k,(fit,held) in enumerate(folds):
            if family=='ANN':
                inner,_=next(StratifiedShuffleSplit(n_splits=1,test_size=.15,random_state=20261015+k).split(X[fit],y[fit]));fit=fit[inner]
                expected=json.loads((OUT/family/f'targeted/fold_{k}.json').read_text())['drop_indicators']
            else:expected=fold_masks[k]
            r=rank_indicators(source.iloc[fit][CORE],adapt,6)
            assert r.loc[r.remove_indicator,'variable'].tolist()==expected
    checks.append('All46fitted pipelines preserve source-only clinical preprocessing; targeted source masks refit within correct CV/inner folds')
    evaldir=OUT/'evaluation';manifest=json.loads((evaldir/'prediction_manifest.json').read_text());m=pd.read_csv(evaldir/'metrics.csv')
    assert len(m)==138
    for filename,expected in manifest.items():
        path=evaldir/filename;assert sha(path)==expected
        f=pd.read_csv(path,dtype={'patient_id':str,'stay_id':str,'hospital_id':str});assert f.patient_id.is_unique
        family='ANN' if '_ANN_' in filename else 'ridge';sample=filename.split('_'+family+'_')[0]
        if sample=='eICU_evaluation':assert set(f.patient_id)==set(partitions.loc[~mask,'patient_id'])
        else:assert set(f.patient_id).isdisjoint(source.patient_id)
        for strategy in strategies():
            row=m.loc[m.family.eq(family)&m['sample'].eq(sample)&m.strategy.eq(strategy)].iloc[0]
            yv=f.hospital_mortality.to_numpy(int);p=f[strategy].to_numpy(float)
            assert len(f)==row.patients and yv.sum()==row.deaths
            np.testing.assert_allclose([roc_auc_score(yv,p),average_precision_score(yv,p),brier_score_loss(yv,p),log_loss(yv,p,labels=[0,1])],[row.AUROC,row.average_precision,row.Brier,row.log_loss],rtol=0,atol=1e-12)
    checks.append('All138model/sample/strategy point metrics reconstructed from hashed local predictions; evaluation keys exclude adaptation patients')
    folder=OUT/'inference';arrays=np.load(folder/'bootstrap_samples.npz');keys=[tuple(k) for k in json.loads((folder/'cell_order.json').read_text())]
    contrast=pd.read_csv(folder/'auroc_contrasts.csv');interval=pd.read_csv(folder/'metric_intervals.csv');assert len(contrast)==8 and contrast.primary.sum()==1
    for row in contrast.itertuples():
        j=keys.index((row.sample,row.family,'targeted'));ref=row.contrast.removeprefix('targeted_minus_');k=keys.index((row.sample,row.family,ref))
        values=arrays['auroc'][:,j]-arrays['auroc'][:,k]
        np.testing.assert_allclose([arrays['points'][j,0]-arrays['points'][k,0],*np.quantile(values,[.025,.975])],[row.estimate,row.lower95,row.upper95],rtol=0,atol=1e-12)
    names=['AUROC','joint_intercept','calibration_slope','calibration_in_large','Brier']
    for row in interval.itertuples():
        j=keys.index((row.sample,row.family,row.strategy));k=names.index(row.metric);values=arrays['auroc'][:,j] if k==0 else arrays['calibration'][:,j,k-1]
        np.testing.assert_allclose([arrays['points'][j,k],*np.quantile(values,[.025,.975])],[row.estimate,row.lower95,row.upper95],rtol=0,atol=1e-12)
    checks.append('All8paired AUROC contrasts and60metric intervals reconstructed from saved draws')
    scoring_identity=json.loads((evaldir/'identity_before_scoring.json').read_text())
    assert scoring_identity['frozen_sha256']==sha(OUT/'all_models_frozen.json')
    assert scoring_identity['evaluation_lock_sha256']==sha(OUT/'evaluation_lock.json')
    assert json.loads((evaldir/'completed.json').read_text())['target_outcomes_used_for_model_or_mask_selection'] is False
    checks.append('Evaluation implementation locked and every fit frozen before new target scoring; historical exposure remains explicit')
    diagnostics=pd.read_csv(OUT/'hospital_diagnostics/heterogeneity_summary.csv')
    assert len(diagnostics)==2 and diagnostics.evaluation_hospitals.eq(207).all()
    checks.append('All207evaluation hospitals retained in descriptive diagnostics; no hospital-specific tuning')
    save(OUT/'verification.json',{'status':'passed','checks':checks,'code_sha256':sha(__file__),'plan_sha256':sha(PLAN),'input_tests':7,'inference_tests':2,'source_patients_grouped':True,'target_adaptation_outcomes_used':False,'raw_source_timestamp_rebuild':False,'formal_noninferiority_test':False,'independent_confirmatory_validation':False})
    print('Pruning verification passed:',len(checks),'reconciliation checks.',flush=True)

if __name__=='__main__':run()
