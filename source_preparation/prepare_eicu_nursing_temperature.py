"""Stream explicitly labelled nursing temperature; generate additive candidate v3 SQL."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT/'eicu_temperature_stage'
COLS = ['nursingchartid','patientunitstayid','nursingchartoffset','nursingchartentryoffset',
        'nursingchartcelltypecat','nursingchartcelltypevallabel','nursingchartcelltypevalname','nursingchartvalue']

def generate(manifest):
    path = (FOLDER/'nursing_temperature.csv').as_posix().replace("'", "''")
    cohort_path = (ROOT/'eicu_core_stage/expected_cohorts.csv').as_posix().replace("'", "''")
    cfg = json.loads((ROOT/'predictor_cleaning_rules_v1.json').read_text())
    fixed = ['uniquepid','patienthealthsystemstayid','patientunitstayid','hospitalid','landmark_hours',
             'landmark_offset_minutes','hospital_mortality','age_capped_90','female']
    columns = [f'c.{x}' for x in fixed]
    columns += ['t.value AS temperature' if r['variable']=='temperature' else 'c.'+r['variable'] for r in cfg['variables']]
    unchanged = fixed+[r['variable'] for r in cfg['variables'] if r['variable']!='temperature']
    comparisons = ' OR '.join(f'a.{x} IS DISTINCT FROM b.{x}' for x in unchanged)
    sql = r"""\set ON_ERROR_STOP on
BEGIN;
SET LOCAL client_encoding='UTF8';
CREATE TEMP TABLE expected_temperature_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;
"""
    sql += f"\\copy expected_temperature_cohorts FROM '{cohort_path}' WITH(FORMAT csv,HEADER true,NULL '')\n"
    sql += f"DO $$ BEGIN IF pg_database_size(current_database())+{manifest['bytes']}::bigint*6::bigint>90000000000::bigint THEN RAISE EXCEPTION 'Temperature build conservative storage estimate exceeds 90 GB'; END IF; END $$;\n"
    sql += """DO $$ BEGIN IF EXISTS(
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_temperature_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v2)
UNION ALL
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v2 EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_temperature_cohorts)
) THEN RAISE EXCEPTION 'Temperature extraction cohort does not match candidate v2'; END IF; END $$;
CREATE TABLE eicu_landmark.nursing_temperature_source_v1(
nursingchartid bigint,patientunitstayid bigint,nursingchartoffset bigint,nursingchartentryoffset bigint,
nursingchartcelltypecat text,nursingchartcelltypevallabel text,nursingchartcelltypevalname text,nursingchartvalue text);
"""
    sql += f"\\copy eicu_landmark.nursing_temperature_source_v1 FROM '{path}' WITH(FORMAT csv,HEADER true,NULL '')\n"
    sql += f"DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.nursing_temperature_source_v1)<>{manifest['retained_rows']} THEN RAISE EXCEPTION 'Temperature source row count mismatch'; END IF; END $$;\n"
    sql += """CREATE INDEX ON eicu_landmark.nursing_temperature_source_v1(patientunitstayid,nursingchartoffset,nursingchartentryoffset);
-- Convert only strictly numeric text; Celsius is explicit in the field label.
CREATE TABLE eicu_landmark.nursing_temperature_groups_v1 AS
WITH parsed AS (
SELECT *,CASE WHEN length(btrim(nursingchartvalue))<=32 AND btrim(nursingchartvalue) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
THEN btrim(nursingchartvalue)::double precision END AS numeric_value
FROM eicu_landmark.nursing_temperature_source_v1
), converted AS (
SELECT *,CASE WHEN nursingchartcelltypevalname='Temperature (C)' THEN numeric_value
WHEN nursingchartcelltypevalname='Temperature (F)' THEN (numeric_value-32)/1.8 END AS celsius
FROM parsed
), grouped AS (
SELECT patientunitstayid,nursingchartoffset AS event_offset,
GREATEST(nursingchartoffset,nursingchartentryoffset) AS available_offset,
count(*) AS source_rows,
avg(celsius) FILTER(WHERE nursingchartcelltypevalname='Temperature (C)' AND celsius>10 AND celsius<50) AS value_c,
avg(celsius) FILTER(WHERE nursingchartcelltypevalname='Temperature (F)' AND celsius>10 AND celsius<50) AS value_f
FROM converted WHERE nursingchartentryoffset IS NOT NULL
GROUP BY patientunitstayid,nursingchartoffset,GREATEST(nursingchartoffset,nursingchartentryoffset)
)
SELECT *,value_c IS NOT NULL AND value_f IS NOT NULL AND abs(value_c-value_f)>0.2 AS paired_unit_disagreement,
CASE WHEN value_c IS NOT NULL AND value_f IS NOT NULL AND abs(value_c-value_f)>0.2 THEN NULL
ELSE COALESCE(value_c,value_f) END AS value
FROM grouped;
CREATE INDEX ON eicu_landmark.nursing_temperature_groups_v1(patientunitstayid,event_offset,available_offset);
"""
    sql += 'CREATE TABLE eicu_landmark.core_features_candidate_v3 AS\nSELECT '+','.join(columns)+"""
FROM eicu_landmark.core_features_candidate_v2 c
LEFT JOIN LATERAL (
SELECT avg(value) AS value,event_offset,available_offset,source_priority
FROM (
SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,temperature AS value
FROM eicu_landmark.core_vitalperiodic_source_v1
WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes
AND temperature>10 AND temperature<50 AND temperature::text NOT IN('NaN','Infinity','-Infinity')
UNION ALL
SELECT event_offset,available_offset,1 AS source_priority,value
FROM eicu_landmark.nursing_temperature_groups_v1
WHERE patientunitstayid=c.patientunitstayid AND event_offset BETWEEN 0 AND c.landmark_offset_minutes
AND available_offset<=c.landmark_offset_minutes AND value IS NOT NULL
) x
GROUP BY event_offset,available_offset,source_priority
ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1
) t ON true;
ALTER TABLE eicu_landmark.core_features_candidate_v3 ADD PRIMARY KEY(landmark_hours,uniquepid);
"""
    sql += f"""DO $$ BEGIN IF EXISTS(
SELECT 1 FROM eicu_landmark.core_features_candidate_v2 a FULL JOIN eicu_landmark.core_features_candidate_v3 b USING(landmark_hours,uniquepid)
WHERE a.uniquepid IS NULL OR b.uniquepid IS NULL OR {comparisons}
) THEN RAISE EXCEPTION 'Cohort, outcome or non-temperature feature changed'; END IF;
IF EXISTS(SELECT 1 FROM eicu_landmark.core_features_candidate_v2 a JOIN eicu_landmark.core_features_candidate_v3 b USING(landmark_hours,uniquepid)
WHERE a.temperature IS NOT NULL AND b.temperature IS NULL) THEN RAISE EXCEPTION 'Previously observed temperature lost'; END IF;
END $$;
COMMENT ON TABLE eicu_landmark.core_features_candidate_v3 IS 'Candidate v3 adds explicitly labelled nursing temperature; both event/entry times by landmark; Celsius preferred for paired forms, disagreement >0.2C excluded; latest event then monitor priority on ties; no imputation or model';
COMMIT;
ANALYZE eicu_landmark.nursing_temperature_source_v1;
ANALYZE eicu_landmark.nursing_temperature_groups_v1;
ANALYZE eicu_landmark.core_features_candidate_v3;
SELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths
FROM eicu_landmark.core_features_candidate_v3 GROUP BY landmark_hours ORDER BY landmark_hours;
SELECT b.landmark_hours,count(*) AS patients,count(a.temperature) AS observed_v2,count(b.temperature) AS observed_v3,
round(100.0*count(b.temperature)/count(*),2) AS temperature_observed_percent_v3,
count(*) FILTER(WHERE a.temperature IS DISTINCT FROM b.temperature) AS changed_temperature_values
FROM eicu_landmark.core_features_candidate_v2 a JOIN eicu_landmark.core_features_candidate_v3 b USING(landmark_hours,uniquepid)
GROUP BY b.landmark_hours ORDER BY b.landmark_hours;
SELECT nursingchartcelltypevalname,count(*) AS source_rows,
count(*) FILTER(WHERE nursingchartentryoffset IS NULL) AS missing_entry_time,
count(*) FILTER(WHERE nursingchartentryoffset<nursingchartoffset) AS entry_before_event,
count(*) FILTER(WHERE nursingchartentryoffset>2880) AS entry_after_48_hours,
count(*) FILTER(WHERE NOT (btrim(COALESCE(nursingchartvalue,'')) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$')) AS nonnumeric
FROM eicu_landmark.nursing_temperature_source_v1 GROUP BY nursingchartcelltypevalname ORDER BY nursingchartcelltypevalname;
SELECT count(*) AS event_availability_groups,count(*) FILTER(WHERE paired_unit_disagreement) AS paired_unit_disagreements,
count(*) FILTER(WHERE value IS NOT NULL) AS valid_groups FROM eicu_landmark.nursing_temperature_groups_v1;
"""
    (FOLDER/'import_and_build_temperature.sql').write_text(sql,encoding='utf-8')

def prepare():
    FOLDER.mkdir(exist_ok=True)
    source = ROOT/'EICU-CRD/nurseCharting.csv.gz'
    cohort = ROOT/'eicu_core_stage/expected_cohorts.csv'
    selected = set(pd.read_csv(cohort,usecols=['patientunitstayid'],dtype=str)['patientunitstayid'])
    fingerprint = {'source_bytes':source.stat().st_size,'source_mtime_ns':source.stat().st_mtime_ns,
                   'cohort_sha256':hashlib.sha256(cohort.read_bytes()).hexdigest(),'extraction_version':1}
    checkpoint = FOLDER/'manifest.json'
    target = FOLDER/'nursing_temperature.csv'
    saved = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    if all(saved.get(k)==v for k,v in fingerprint.items()) and target.exists() and target.stat().st_size==saved.get('bytes') and target.stat().st_mtime_ns==saved.get('output_mtime_ns'):
        print('Reusing completed temperature extraction.',flush=True)
        generate(saved)
        return
    scanned = retained = 0
    with gzip.open(source,'rt',encoding='utf-8',newline='') as handle,target.open('w',encoding='utf-8',newline='') as output:
        csv.writer(output).writerow(COLS)
        for chunk in pd.read_csv(handle,usecols=COLS,dtype=str,na_filter=False,chunksize=250000):
            scanned += len(chunk)
            offsets = pd.to_numeric(chunk['nursingchartoffset'],errors='coerce')
            mask = chunk['patientunitstayid'].isin(selected)&offsets.between(0,2880)&(chunk['nursingchartcelltypevallabel']=='Temperature')&chunk['nursingchartcelltypevalname'].isin(['Temperature (C)','Temperature (F)'])
            kept = chunk.loc[mask,COLS]
            kept.to_csv(output,index=False,header=False)
            retained += len(kept)
            output.flush()
            if target.stat().st_size>10_000_000_000 or shutil.disk_usage(FOLDER).free<10_000_000_000:
                raise RuntimeError('Temperature preparation disk guard reached; no database import attempted.')
            if scanned%5000000==0:
                print(f'nurseCharting: {scanned:,} source rows scanned; {retained:,} temperature rows retained',flush=True)
    manifest = dict(fingerprint,source_rows_scanned=scanned,retained_rows=retained,bytes=target.stat().st_size,
                    output_mtime_ns=target.stat().st_mtime_ns,columns=COLS)
    checkpoint.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    generate(manifest)
    print(f'Temperature preparation complete: {retained:,} source rows retained. No database rows imported by Python.',flush=True)

if __name__=='__main__':
    prepare()
