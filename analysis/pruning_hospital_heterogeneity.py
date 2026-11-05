"""Descriptive hospital checks with frozen scores; no site selection or tuning."""
from missingness_pruning_inputs import *
from train_missingness_pruning import OUT
from sklearn.metrics import roc_auc_score

def run():
    assert (OUT/'evaluation/completed.json').exists()
    rows=[];summaries=[]
    manifest=json.loads((OUT/'evaluation/prediction_manifest.json').read_text())
    for family in ['ridge','ANN']:
        path=OUT/f'evaluation/eICU_evaluation_{family}_predictions_local.csv';assert sha(path)==manifest[path.name]
        f=pd.read_csv(path,dtype={'hospital_id':str})
        for hospital,part in f.groupby('hospital_id'):
            y=part.hospital_mortality.to_numpy(int)
            for strategy in ['keep_all','targeted','drop_all']:
                p=part[strategy].to_numpy(float);valid=len(np.unique(y))==2
                rows.append({'family':family,'hospital_id':hospital,'strategy':strategy,'patients':len(part),'deaths':int(y.sum()),'AUROC':roc_auc_score(y,p) if valid else np.nan,'Brier':float(np.mean((p-y)**2)),'mean_prediction':float(p.mean()),'observed_mortality':float(y.mean()),'AUROC_estimable':valid})
        data=pd.DataFrame([r for r in rows if r['family']==family]);wide=data.pivot(index='hospital_id',columns='strategy',values='AUROC');delta=(wide.targeted-wide.keep_all).dropna()
        summaries.append({'family':family,'evaluation_hospitals':len(wide),'hospitals_with_both_outcomes':len(delta),'hospitals_without_estimable_AUROC':int((wide.keep_all.isna()).sum()),'hospitals_targeted_higher_AUROC':int(delta.gt(0).sum()),'hospitals_targeted_lower_AUROC':int(delta.lt(0).sum()),'hospitals_equal_AUROC':int(delta.eq(0).sum()),'median_hospital_AUROC_difference':float(delta.median()),'q25_difference':float(delta.quantile(.25)),'q75_difference':float(delta.quantile(.75))})
    folder=OUT/'hospital_diagnostics';folder.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(folder/'hospital_metrics_local.csv',index=False);pd.DataFrame(summaries).to_csv(folder/'heterogeneity_summary.csv',index=False)
    save(folder/'completed.json',{'code_sha256':sha(__file__),'evaluation_manifest_sha256':sha(OUT/'evaluation/prediction_manifest.json'),'status':'descriptive completed','hospitals_selected_for_primary':False,'hospital_specific_models_fitted':False})
    print('Descriptive hospital diagnostics completed; all evaluation hospitals retained.',flush=True)

if __name__=='__main__':run()
