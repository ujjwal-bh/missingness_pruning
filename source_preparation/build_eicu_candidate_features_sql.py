"""SQL for equivalent eICU core candidates without a large unpivot/sort."""
from pathlib import Path
import hashlib
import json

def generate(folder,manifest,cfg):
    folder=folder.resolve();signature=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    schema='eicu_landmark';remaining=sum(r['bytes'] for r in manifest['tables'].values())
    lines=['\\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",
     'CREATE TEMP TABLE expected_core_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;',
     f"\\copy expected_core_cohorts FROM '{(folder/'expected_cohorts.csv').as_posix()}' WITH(FORMAT csv,HEADER true,NULL '')",
     '''DO $$ BEGIN IF EXISTS(
 (SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_core_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort)
 UNION ALL
 (SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_core_cohorts)
 ) THEN RAISE EXCEPTION 'Local selection and database cohort differ'; END IF; END $$;''',
     'CREATE TEMP TABLE core_wal_baseline ON COMMIT DROP AS SELECT COALESCE(sum(size),0) AS bytes FROM pg_ls_waldir();']
    def budget():
        return f"DO $$ BEGIN IF {remaining}+pg_database_size(current_database())+GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT bytes FROM core_wal_baseline),0)>90000000000 THEN RAISE EXCEPTION 'Core build storage estimate exceeds 90 GB'; END IF; END $$;"
    def typ(col):
        if col.endswith('id') or col.endswith('offset'):return 'bigint'
        if col in {'labname','labresulttext','labmeasurenamesystem','labmeasurenameinterface'}:return 'text'
        return 'double precision'
    for name,r in manifest['tables'].items():
        table='core_'+name.lower()+'_source_v1'
        lines.append(f'CREATE TABLE {schema}.{table}('+','.join(f'"{c}" {typ(c)}' for c in r['columns'])+');')
        lines.append(f"\\copy {schema}.{table} FROM '{(folder/(name+'.csv')).as_posix()}' WITH(FORMAT csv,HEADER true,NULL '')")
        lines.append(f"DO $$ BEGIN IF(SELECT count(*) FROM {schema}.{table})<>{r['rows']} THEN RAISE EXCEPTION 'Measurement import row-count mismatch'; END IF; END $$;")
        offset='labresultoffset' if name=='lab' else 'observationoffset'
        keys=f'patientunitstayid,{offset}' if name!='lab' else 'patientunitstayid,labname,labresultoffset,labresultrevisedoffset'
        lines.append(f'CREATE INDEX ON {schema}.{table}({keys});');lines.append(budget())
    aliases={};lateral=[];features=[]
    vital_columns={'heart_rate':('heartrate',None),'respiratory_rate':('respiration',None),'spo2':('sao2',None),'temperature':('temperature',None),'systolic_bp':('systemicsystolic','noninvasivesystolic'),'diastolic_bp':('systemicdiastolic','noninvasivediastolic'),'mean_bp':('systemicmean','noninvasivemean')}
    for i,r in enumerate(cfg['variables']):
        alias=f'v{i}';name=r['variable'];lo='>=' if r['lower_inclusive'] else '>';hi='<=' if r['upper_inclusive'] else '<'
        bounds=lambda value:f"{value}::text NOT IN('NaN','Infinity','-Infinity') AND {value}{lo}{r['lower_bound']} AND {value}{hi}{r['upper_bound']}"
        if r['domain']=='vital':
            periodic,aperiodic=vital_columns[name]
            sources=[f"SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,{periodic} AS value FROM {schema}.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND {bounds(periodic)}"]
            if aperiodic:sources.append(f"SELECT observationoffset,observationoffset,1,{aperiodic} FROM {schema}.core_vitalaperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND {bounds(aperiodic)}")
            body=' UNION ALL '.join(sources)
        else:
            units=r['units_accepted_mimic'][:]
            if name in ['wbc','platelets']:units+=['k/mcl','k/mm3','10*3/ul','x10^3/ul','x10^9/l']
            unit_list=','.join("'%s'"%u for u in sorted(set(units)))
            norm=lambda column:f"lower(regexp_replace(replace(COALESCE({column},''),'µ','u'),'[[:space:]]','','g'))"
            body=f"""SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM {schema}.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='{r['eicu_labname']}'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND {norm('labmeasurenamesystem')} IN({unit_list})
AND (COALESCE(labmeasurenameinterface,'')='' OR {norm('labmeasurenameinterface')} IN({unit_list}))
AND {bounds('labresult')}"""
        query=f"SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM({body}) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1"
        lateral.append(f'LEFT JOIN LATERAL({query}) {alias} ON true');features.append(f'{alias}.value AS {name}')
    lines.append(f'''CREATE TABLE {schema}.core_features_candidate_v1 AS
SELECT c.uniquepid,c.patienthealthsystemstayid,c.patientunitstayid,c.hospitalid,c.landmark_hours,c.landmark_offset_minutes,c.hospital_mortality,
 LEAST(c.age_for_screening,90) AS age_capped_90,
 CASE WHEN p.gender='Female' THEN 1 WHEN p.gender='Male' THEN 0 END AS female,
 {', '.join(features)}
FROM {schema}.primary_landmark_cohort c JOIN {schema}.patient p USING(patientunitstayid)
{' '.join(lateral)};
ALTER TABLE {schema}.core_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,uniquepid);
COMMENT ON TABLE {schema}.core_features_candidate_v1 IS 'Candidate core features; manifest SHA256 {signature}; no imputation/scaling; source availability differences and remaining domains require evaluation';''')
    lines.extend([f'''DO $$ BEGIN IF EXISTS(
SELECT 1 FROM {schema}.primary_landmark_cohort c FULL JOIN {schema}.core_features_candidate_v1 f USING(uniquepid,landmark_hours)
WHERE c.uniquepid IS NULL OR f.uniquepid IS NULL OR c.patientunitstayid<>f.patientunitstayid OR c.hospital_mortality<>f.hospital_mortality
) THEN RAISE EXCEPTION 'Features do not match primary cohort'; END IF; END $$;''',budget(),'COMMIT;',f'ANALYZE {schema}.core_features_candidate_v1;',
    f'-- Result 1\nSELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM {schema}.core_features_candidate_v1 GROUP BY landmark_hours ORDER BY landmark_hours;'])
    coverage='\nUNION ALL\n'.join(f"SELECT landmark_hours,'{r['variable']}' AS variable,count(*) AS patients,count({r['variable']}) AS observed_patients,round(100.0*count({r['variable']})/count(*),2) AS observed_percent FROM {schema}.core_features_candidate_v1 GROUP BY landmark_hours" for r in cfg['variables'])
    lines.append('-- Result 2\n'+coverage+' ORDER BY landmark_hours,variable;')
    lines.append(f'''-- Result 3: lab unit compatibility by observed source pair, before screening.
SELECT labname,labmeasurenamesystem,labmeasurenameinterface,count(*) AS observations,
 count(*) FILTER(WHERE labresultrevisedoffset<labresultoffset) AS entry_before_sample
FROM {schema}.core_lab_source_v1 GROUP BY labname,labmeasurenamesystem,labmeasurenameinterface
ORDER BY labname,observations DESC;''')
    (folder/'import_and_build.sql').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    root=Path(__file__).parent;folder=root/'eicu_core_stage'
    generate(folder,json.loads((folder/'manifest.json').read_text()),json.loads((root/'predictor_cleaning_rules_v1.json').read_text()))
