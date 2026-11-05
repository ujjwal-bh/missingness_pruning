"""Local-only data access and immutable experiment identities for the amendment."""
from pathlib import Path
import sys, os, json, hashlib, platform
R = Path(__file__).resolve().parent
for folder in ['.model_runtime', '.ann_runtime']:
    sys.path.insert(0, str(R / folder))
for key in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS']:
    os.environ.setdefault(key, '2')
import numpy as np
import pandas as pd

BASE = R / 'model_results/evidence_amendment_2026_10_19_v1'
PLAN = R / 'evidence_amendment_2026_10_19.md'
OLD = R / 'model_results/revised_mimic_ann_ridge_2026_10_16_v1'
PRIMARY = R / 'model_results/transportability_core_ANN_2026_10_17_v1'
HOURS = [12, 24, 48]
SEEDS = [20261016, 20261017, 20261018]
FEATURES = json.loads((R/'model_preparation/primary_predictor_scope_approved.json').read_text())['primary_predictors']
VITALS = ['heart_rate', 'respiratory_rate', 'spo2', 'temperature', 'systolic_bp', 'diastolic_bp', 'mean_bp']
SETS = {'full': (FEATURES, True), 'no_indicators': (FEATURES, False),
        'vitals': (['age_capped_90', 'female'] + VITALS, True)}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')

def identity(code):
    return {'plan_sha256': sha(PLAN), 'code_sha256': sha(code),
            'common_code_sha256': sha(__file__), 'python': platform.python_version(),
            'exploratory': True, 'historical_external_exposure': True}

def load_frames():
    verified = json.loads((R/'model_preparation/export_verification_confirmed_2026_10_15.json').read_text())
    frames = {}
    for db, name in [('MIMIC','mimic_candidate_features.csv'), ('eICU','eicu_candidate_features.csv')]:
        path = R/'model_preparation'/name
        assert sha(path) == verified['inputs'][name]['sha256'], 'Prepared export changed'
        f = pd.read_csv(path, dtype={'patient_id':str, 'stay_id':str, 'hospital_id':str})
        assert len(f)==verified['inputs'][name]['rows'] and not f.duplicated(['patient_id','landmark_hours']).any()
        frames[db] = f.loc[f.landmark_hours.isin(HOURS)].copy()
    assert frames['MIMIC'].groupby('patient_id').split.nunique().eq(1).all()
    return frames

def progress(message, **fields):
    from datetime import datetime, timezone
    BASE.mkdir(parents=True, exist_ok=True)
    row = {'utc':datetime.now(timezone.utc).isoformat(), 'message':message, **fields}
    with (BASE/'progress.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(row)+'\n')
    print(message, json.dumps(fields), flush=True)

def check_completed(folder, code):
    path = folder/'completed.json'
    if not path.exists(): return False
    old = json.loads(path.read_text())
    assert old['identity']==identity(code), 'Completed work identity changed'
    for name, value in old['outputs'].items(): assert sha(folder/name)==value, 'Completed output changed'
    return True

def finish(folder, code, **extra):
    outputs = {p.name:sha(p) for p in folder.iterdir() if p.is_file() and p.name!='completed.json'}
    save(folder/'completed.json', {'identity':identity(code), 'outputs':outputs, **extra})
