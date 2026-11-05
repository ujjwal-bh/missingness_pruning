"""Stream selected eICU measurement windows into resumable local CSVs."""
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path
import pandas as pd
from prepare_harmonized_cohorts import priority

ROOT=Path(__file__).parent.resolve()

def selected_cohorts(records):
    result=[]
    def integer(s):
        try:return int(s)
        except (TypeError,ValueError):return None
    types={'Med-Surg ICU','CTICU','SICU','CCU-CTICU','MICU','Neuro ICU','Cardiac ICU','CSICU'}
    for hours in [12,24,36,48]:
        chosen={}
        for r in records:
            age=r['age'].strip();adult=age=='> 89' or(age.isdigit() and int(age)>=18)
            unit=integer(r['unitdischargeoffset']);hospital=integer(r['hospitaldischargeoffset']);admit=integer(r['hospitaladmitoffset'])
            if not adult or unit is None or hospital is None or admit is None or unit<=hours*60 or hospital<=hours*60:continue
            if r['unitdischargestatus'] not in ['Alive','Expired'] or r['hospitaldischargestatus'] not in ['Alive','Expired'] or r['unittype'] not in types:continue
            person=r['uniquepid'];hid=r['patienthealthsystemstayid']
            order=(priority('eicu',person,hid),int(hid),-admit,int(r['patientunitstayid']))
            if person not in chosen or order<chosen[person][0]:chosen[person]=(order,r)
        result.extend({'landmark_hours':hours,'uniquepid':p,'patientunitstayid':r['patientunitstayid'],'hospital_mortality':int(r['hospitaldischargestatus']=='Expired')} for p,(_,r) in chosen.items())
    return result

def prepare():
    folder=ROOT/'eicu_core_stage';folder.mkdir(exist_ok=True)
    cfg=json.loads((ROOT/'predictor_cleaning_rules_v1.json').read_text())
    config_hash=hashlib.sha256((ROOT/'predictor_cleaning_rules_v1.json').read_bytes()).hexdigest()
    with gzip.open(ROOT/'EICU-CRD/patient.csv.gz','rt',encoding='utf-8',newline='') as handle:cohorts=selected_cohorts(list(csv.DictReader(handle)))
    expected=json.loads((ROOT/'harmonized_cohorts_confirmed_2026_10_13.json').read_text())['primary_cohorts']
    for row in expected:
        if row['database']!='eICU':continue
        matched=[r for r in cohorts if r['landmark_hours']==row['landmark_hours']]
        assert len(matched)==row['patients'] and sum(r['hospital_mortality'] for r in matched)==row['hospital_deaths']
    cols=['landmark_hours','uniquepid','patientunitstayid','hospital_mortality']
    with (folder/'expected_cohorts.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=cols);writer.writeheader();writer.writerows(cohorts)
    selected={str(r['patientunitstayid']) for r in cohorts}
    labs={r['eicu_labname'] for r in cfg['variables'] if r['domain']=='laboratory'}
    checkpoint=folder/'completed_measurement_tables.json'
    done=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    schemas={
      'vitalPeriodic':['vitalperiodicid','patientunitstayid','observationoffset','temperature','sao2','heartrate','respiration','systemicsystolic','systemicdiastolic','systemicmean'],
      'vitalAperiodic':['vitalaperiodicid','patientunitstayid','observationoffset','noninvasivesystolic','noninvasivediastolic','noninvasivemean'],
      'lab':['labid','patientunitstayid','labresultoffset','labtypeid','labname','labresult','labresulttext','labmeasurenamesystem','labmeasurenameinterface','labresultrevisedoffset']}
    for name,columns in schemas.items():
        path=folder/(name+'.csv');source=ROOT/'EICU-CRD'/(name+'.csv.gz');st=source.stat()
        saved=done.get(name)
        if saved and saved['config_hash']==config_hash and saved['source_bytes']==st.st_size and saved['source_mtime_ns']==st.st_mtime_ns and path.exists() and path.stat().st_size==saved['bytes'] and path.stat().st_mtime_ns==saved['output_mtime_ns']:
            print(f'{name}: reusing {saved["rows"]:,} completed records',flush=True);continue
        count=scanned=0
        with path.open('w',encoding='utf-8',newline='') as output,gzip.open(source,'rt',encoding='utf-8',newline='') as handle:
            csv.writer(output).writerow(columns)
            for chunk in pd.read_csv(handle,usecols=columns,dtype=str,na_filter=False,chunksize=250000):
                scanned+=len(chunk)
                offset_col='labresultoffset' if name=='lab' else 'observationoffset'
                offsets=pd.to_numeric(chunk[offset_col],errors='coerce')
                mask=chunk['patientunitstayid'].isin(selected)&offsets.between(0,2880)
                if name=='lab':mask &= chunk['labname'].isin(labs)&((chunk['labtypeid']!='7')|(chunk['labname']=='lactate'))
                kept=chunk.loc[mask,columns]
                kept.to_csv(output,index=False,header=False)
                count+=len(kept);output.flush()
                if scanned%5000000==0:print(f'{name}: {scanned:,} source rows scanned; {count:,} retained',flush=True)
                if sum(p.stat().st_size for p in folder.glob('*.csv'))>60_000_000_000:raise RuntimeError('60 GB staging cap reached; no rows are silently sampled.')
                if shutil.disk_usage(folder).free<10_000_000_000:raise RuntimeError('Less than 10 GB free disk space.')
        done[name]={'rows':count,'columns':columns,'bytes':path.stat().st_size,'output_mtime_ns':path.stat().st_mtime_ns,'source_bytes':st.st_size,'source_mtime_ns':st.st_mtime_ns,'source_rows_scanned':scanned,'config_hash':config_hash}
        temp=checkpoint.with_suffix('.tmp');temp.write_text(json.dumps(done,indent=2));temp.replace(checkpoint)
        print(f'{name}: prepared {count:,} records',flush=True)
    manifest={'config_hash':config_hash,'tables':done,'expected_cohort_rows':len(cohorts),'selection':'hospital_priority_v1','status':'Raw candidate measurements prepared; feature verification pending'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    from build_eicu_candidate_features_sql import generate
    generate(folder,manifest,cfg)
    print('eICU source import and candidate feature SQL ready.',flush=True)

if __name__=='__main__':prepare()
