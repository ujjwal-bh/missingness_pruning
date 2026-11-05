"""Prepare selected eICU neurological/support sources for mapping audits, not model fitting."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT/'eicu_extension_stage'
SCHEMAS = {
 'nurseCharting': ['nursingchartid','patientunitstayid','nursingchartoffset','nursingchartentryoffset','nursingchartcelltypecat','nursingchartcelltypevallabel','nursingchartcelltypevalname','nursingchartvalue'],
 'infusionDrug': ['infusiondrugid','patientunitstayid','infusionoffset','drugname','drugrate','infusionrate','drugamount','volumeoffluid','patientweight'],
 'treatment': ['treatmentid','patientunitstayid','treatmentoffset','treatmentstring'],
 'respiratoryCare': ['respcareid','patientunitstayid','respcarestatusoffset','currenthistoryseqnum','airwaytype','ventstartoffset','ventendoffset','priorventstartoffset','priorventendoffset'],
 'respiratoryCharting': ['respchartid','patientunitstayid','respchartoffset','respchartentryoffset','respcharttypecat','respchartvaluelabel','respchartvalue'],
}
OFFSETS = dict(zip(SCHEMAS,['nursingchartoffset','infusionoffset','treatmentoffset','respcarestatusoffset','respchartoffset']))

def generate(manifest):
    lines = [r'\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",
        'CREATE TEMP TABLE extension_expected_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;']
    csvpath = (ROOT/'eicu_core_stage/expected_cohorts.csv').as_posix().replace("'","''")
    lines += [f"\\copy extension_expected_cohorts FROM '{csvpath}' WITH(FORMAT csv,HEADER true,NULL '')",
        '''DO $$ BEGIN IF EXISTS(
(SELECT * FROM extension_expected_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v3)
UNION ALL
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v3 EXCEPT SELECT * FROM extension_expected_cohorts)
) THEN RAISE EXCEPTION 'Extension extraction cohort differs from candidate v3'; END IF; END $$;''']
    staged = sum(r['bytes'] for r in manifest['tables'].values())
    lines += [f"DO $$ BEGIN IF pg_database_size(current_database())+{staged}::bigint*6::bigint>90000000000::bigint THEN RAISE EXCEPTION 'Extension conservative storage estimate exceeds 90 GB'; END IF; END $$;"]
    extraction_order = [name for name in SCHEMAS if name!='nurseCharting']+['nurseCharting']
    for name in extraction_order:
        columns = SCHEMAS[name]
        table = 'eicu_landmark.extension_'+name.lower()+'_source_v1'
        id_columns = {'nursingchartid','patientunitstayid','infusiondrugid','treatmentid','respcareid','respchartid'}
        defs = ','.join(f'"{c}" '+('bigint' if c in id_columns or c.endswith('offset') or c=='currenthistoryseqnum' else 'text') for c in columns)
        path = (FOLDER/(name+'.csv')).as_posix().replace("'","''")
        lines += [f'CREATE TABLE {table}({defs});',f"\\copy {table} FROM '{path}' WITH(FORMAT csv,HEADER true,NULL '')",
            f"DO $$ BEGIN IF (SELECT count(*) FROM {table})<>{manifest['tables'][name]['rows']} THEN RAISE EXCEPTION 'Extension source import count mismatch: {name}'; END IF; END $$;",
            f'CREATE INDEX ON {table}(patientunitstayid,{OFFSETS[name]});',
            f"COMMENT ON TABLE {table} IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';"]
    lines += ['COMMIT;']
    for name in SCHEMAS:
        lines += [f'ANALYZE eicu_landmark.extension_{name.lower()}_source_v1;']
    lines += [(ROOT/'10_eicu_extension_source_audit.sql').read_text(encoding='utf-8'),
              (ROOT/'11_mimic_extension_source_audit.sql').read_text(encoding='utf-8')]
    (FOLDER/'import_and_audit.sql').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')

def prepare():
    FOLDER.mkdir(exist_ok=True)
    cohort_path = ROOT/'eicu_core_stage/expected_cohorts.csv'
    selected = set(pd.read_csv(cohort_path,usecols=['patientunitstayid'],dtype=str)['patientunitstayid'])
    signature = hashlib.sha256(cohort_path.read_bytes()).hexdigest()
    checkpoint = FOLDER/'manifest.json'
    saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'tables':{}}
    manifest = {'extraction_version':1,'cohort_sha256':signature,'tables':{}}
    extraction_order = [name for name in SCHEMAS if name!='nurseCharting']+['nurseCharting']
    for name in extraction_order:
        columns = SCHEMAS[name]
        source = ROOT/'EICU-CRD'/(name+'.csv.gz')
        target = FOLDER/(name+'.csv')
        fingerprint = {'source_bytes':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns}
        old = saved.get('tables',{}).get(name,{})
        if saved.get('extraction_version')==1 and saved.get('cohort_sha256')==signature and all(old.get(k)==v for k,v in fingerprint.items()) and target.exists() and old.get('bytes')==target.stat().st_size and old.get('output_mtime_ns')==target.stat().st_mtime_ns:
            manifest['tables'][name]=old
            print(f'{name}: reusing {old["rows"]:,} completed source rows',flush=True)
            continue
        scanned = retained = 0
        with gzip.open(source,'rt',encoding='utf-8',newline='') as handle,target.open('w',encoding='utf-8',newline='') as output:
            csv.writer(output).writerow(columns)
            for chunk in pd.read_csv(handle,usecols=columns,dtype=str,na_filter=False,chunksize=250000):
                scanned += len(chunk)
                offsets = pd.to_numeric(chunk[OFFSETS[name]],errors='coerce')
                mask = chunk['patientunitstayid'].isin(selected)&offsets.between(0,2880)
                kept = chunk.loc[mask,columns]
                if name=='nurseCharting':
                    labels = kept['nursingchartcelltypevallabel']+' '+kept['nursingchartcelltypevalname']
                    kept = kept.loc[labels.str.contains(r'glasgow|\bgcs\b|coma|sedation|\brass\b',case=False,regex=True)]
                kept.to_csv(output,index=False,header=False)
                retained += len(kept)
                output.flush()
                if sum(p.stat().st_size for p in FOLDER.glob('*.csv'))>10_000_000_000 or shutil.disk_usage(FOLDER).free<10_000_000_000:
                    raise RuntimeError('Extension extraction disk guard reached; no database import attempted.')
                if scanned%5000000==0:
                    print(f'{name}: {scanned:,} source rows scanned; {retained:,} retained',flush=True)
        manifest['tables'][name]=dict(fingerprint,source_rows_scanned=scanned,rows=retained,bytes=target.stat().st_size,output_mtime_ns=target.stat().st_mtime_ns,columns=columns)
        checkpoint.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(f'{name}: prepared {retained:,} rows',flush=True)
    checkpoint.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    generate(manifest)
    print('Extension source preparation complete. No final support features or models have been built.',flush=True)

if __name__=='__main__':
    prepare()
