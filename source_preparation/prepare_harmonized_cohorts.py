"""Prepare small eICU metadata files and the agreed cohort SQL, without a DB connection."""
import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parent.resolve()
SEED='landmark_transportability_hospital_selection_v1'

def priority(dataset,patient,hospitalization):
    return hashlib.sha256(f'{SEED}|{dataset}|{patient}|{hospitalization}'.encode('utf-8')).digest()

def prepare():
    folder=ROOT/'eicu_metadata_stage';folder.mkdir(exist_ok=True)
    metadata={}
    patients=[]
    for name in ['patient','hospital']:
        source=ROOT/'EICU-CRD'/(name+'.csv.gz')
        with gzip.open(source,'rt',encoding='utf-8',newline='') as handle:
            reader=csv.DictReader(handle);columns=reader.fieldnames;records=list(reader)
        if name=='patient':patients=records
        path=folder/(name+'.csv')
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=columns);writer.writeheader();writer.writerows(records)
        metadata[name]={'rows':len(records),'columns':columns,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    def column_type(col):
        if col.endswith('offset') or col in {'patientunitstayid','patienthealthsystemstayid','hospitalid','wardid','unitvisitnumber','hospitaldischargeyear'}:return 'bigint'
        if col in {'admissionheight','admissionweight','dischargeweight'}:return 'double precision'
        return 'text'
    signature=hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()
    lines=['\\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",
      "DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='eicu_landmark') AND to_regclass('eicu_landmark._metadata_import') IS NULL THEN RAISE EXCEPTION 'eicu_landmark exists without this import ledger; refusing modification'; END IF; END $$;",
      'CREATE SCHEMA IF NOT EXISTS eicu_landmark;',
      'CREATE TABLE IF NOT EXISTS eicu_landmark._metadata_import(table_name text PRIMARY KEY,signature text NOT NULL,row_count bigint NOT NULL);',
      f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM eicu_landmark._metadata_import WHERE signature<>'{signature}') THEN RAISE EXCEPTION 'eICU metadata manifest differs from committed import'; END IF; END $$;"]
    for name,entry in metadata.items():
        lines.extend([f"SELECT EXISTS(SELECT 1 FROM eicu_landmark._metadata_import WHERE table_name='{name}') AS already_loaded \\gset",'\\if :already_loaded','\\else'])
        cols=', '.join(f'"{c}" {column_type(c)}' for c in entry['columns'])
        lines.append(f'CREATE TABLE eicu_landmark.{name}({cols});')
        path=(folder/(name+'.csv')).as_posix().replace("'","''")
        lines.append(f"\\copy eicu_landmark.{name} FROM '{path}' WITH(FORMAT csv,HEADER true,NULL '')")
        key='patientunitstayid' if name=='patient' else 'hospitalid'
        lines.append(f'ALTER TABLE eicu_landmark.{name} ADD PRIMARY KEY({key});')
        lines.append(f"INSERT INTO eicu_landmark._metadata_import VALUES('{name}','{signature}',{entry['rows']});")
        lines.extend(['\\endif',f"DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.{name})<>{entry['rows']} THEN RAISE EXCEPTION 'eICU metadata row-count mismatch'; END IF; END $$;"])
    lines.append('CREATE INDEX IF NOT EXISTS patient_person_hospital_idx ON eicu_landmark.patient(uniquepid,patienthealthsystemstayid);')
    definitions=(ROOT/'05_harmonize_patient_contribution.sql').read_text(encoding='utf-8')
    begin=definitions.index('-- Begin MIMIC definitions')
    end=definitions.index('-- End cohort definitions')
    lines.append(definitions[begin:end])
    lines.extend(['COMMIT;','ANALYZE eicu_landmark.patient;','ANALYZE eicu_landmark.hospital;',definitions[definitions.index('-- Result 1:'):]])
    (folder/'import_and_harmonize.sql').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    expected=[]
    def number(x):
        try:return int(x)
        except (TypeError,ValueError):return None
    for h in [12,24,36,48]:
        selected={}
        for r in patients:
            age=r['age'].strip();adult=age=='> 89' or(age.isdigit() and int(age)>=18)
            u=number(r['unitdischargeoffset']);hd=number(r['hospitaldischargeoffset']);ha=number(r['hospitaladmitoffset'])
            if not adult or u is None or hd is None or ha is None or u<=h*60 or hd<=h*60:continue
            if r['unitdischargestatus'] not in ['Alive','Expired'] or r['hospitaldischargestatus'] not in ['Alive','Expired']:continue
            person=r['uniquepid'];hosp=r['patienthealthsystemstayid']
            order=(priority('eicu',person,hosp),int(hosp),-ha,int(r['patientunitstayid']))
            if person not in selected or order<selected[person][0]:selected[person]=(order,r)
        expected.append({'landmark_hours':h,'patients':len(selected),'hospital_deaths':sum(r['hospitaldischargestatus']=='Expired' for _,r in selected.values())})
    manifest={'seed':SEED,'selection_rule':'Eligibility first, fixed SHA256 hospital priority next, earliest eligible ICU within chosen hospital last','metadata':metadata,'expected_eicu_cohorts_preliminary':expected,'eicu_timing_audit':'eicu_metadata_audit_local.json','version':'hospital_priority_v1','status':'Prepared locally, SQL not yet run in PostgreSQL'}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'staged_bytes':sum(x['bytes'] for x in metadata.values()),'metadata_rows':{n:x['rows'] for n,x in metadata.items()},'expected_eicu_cohorts_preliminary':expected},indent=2))

if __name__=='__main__':prepare()
