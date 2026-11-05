"""Predictor-only loading and outcome-independent indicator selection."""
from pathlib import Path
import os,sys,json,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.model_runtime'))
for name in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ.setdefault(name,'2')
import numpy as np
import pandas as pd

CORE=json.loads((ROOT/'model_preparation/primary_predictor_scope_approved.json').read_text())['primary_predictors']
DEMOGRAPHICS=['age_capped_90','female']
CANDIDATES=sorted(set(CORE)-set(DEMOGRAPHICS))
CONFIG=ROOT/'missingness_pruning_protocol_v1.json'
PLAN=ROOT/'missingness_pruning_protocol_2026_10_19.md'
STAGE=ROOT/'model_preparation/missingness_pruning_2026_10_19_v1'
META=['dataset','patient_id','stay_id','hospital_id','landmark_hours','split']

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def adaptation_mask(patient_ids,config):
    prefix=config['target_partition_seed'];threshold=config['target_adaptation_threshold_unsigned32']
    return np.array([int.from_bytes(hashlib.sha256((prefix+str(p)).encode('utf-8')).digest()[:4],'big')<threshold for p in patient_ids])

def read_predictors(path):
    """Read only keys/predictors, never parse outcome columns; retain24h rows."""
    parts=[]
    for chunk in pd.read_csv(path,usecols=META+CORE,dtype={'patient_id':str,'stay_id':str,'hospital_id':str},chunksize=50000):
        part=chunk.loc[chunk.landmark_hours.eq(24)].copy()
        if len(part):parts.append(part)
    f=pd.concat(parts,ignore_index=True)
    if not f.patient_id.is_unique:raise ValueError('Prepared24h patient identifiers are not unique')
    if f[['patient_id','stay_id','hospital_id']].isna().any().any():raise ValueError('Missing partition keys')
    for c in CORE:
        try:f[c]=pd.to_numeric(f[c],errors='raise')
        except (ValueError,TypeError):raise ValueError('Prepared predictor is not numeric') from None
    return f

def rank_indicators(source,target,budget=6):
    """Reject identifiers/labels; output depends only on predictor missing masks."""
    for f in [source,target]:
        if f.columns.duplicated().any() or set(f.columns)!=set(CORE):
            raise ValueError('Selector accepts exactly the26predictor columns, without labels or identifiers')
        if not len(f):raise ValueError('Empty predictor sample')
    if not 0<budget<=len(CANDIDATES):raise ValueError('Invalid fixed pruning budget')
    sm=source[CANDIDATES].isna().mean();tm=target[CANDIDATES].isna().mean()
    rank=pd.DataFrame({'variable':CANDIDATES,'source_missing':sm.to_numpy(),'adaptation_missing':tm.to_numpy()})
    rank['absolute_shift']=abs(rank.adaptation_missing-rank.source_missing)
    rank=rank.sort_values(['absolute_shift','variable'],ascending=[False,True]).reset_index(drop=True)
    rank['rank']=np.arange(1,len(rank)+1);rank['remove_indicator']=rank['rank']<=budget
    return rank

def random_masks(count=20,budget=6,seed=2026101906):
    rng=np.random.default_rng(seed);seen=set();result=[]
    while len(result)<count:
        selected=tuple(sorted(rng.choice(CANDIDATES,size=budget,replace=False).tolist()))
        if selected not in seen:seen.add(selected);result.append(list(selected))
    return result
