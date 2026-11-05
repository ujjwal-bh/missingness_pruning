"""Prepare final candidate audit/local exports and outcome-independent patient splits."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
FOLDER=ROOT/'model_preparation'; FOLDER.mkdir(exist_ok=True)
cfg=json.loads((ROOT/'predictor_cleaning_rules_v1.json').read_text())
core=['age_capped_90','female']+[r['variable'] for r in cfg['variables']]
assert len(core)==26 and len(set(core))==26
extra=['gcs_total_components','gcs_total_reported','gcs_component_age_hours','gcs_latest_assessment_unassessable']
support=['vasopressor_documented','invasive_ventilation_documented','rrt_documented','ambiguous_ventilation_documented']
selects=[]
for dataset,schema,table,person,stay in [('MIMIC','landmark_mimic48','core_features_candidate_v1','subject_id','stay_id'),('eICU','eicu_landmark','core_features_candidate_v3','uniquepid','patientunitstayid')]:
    hospital="'MIMIC'::text" if dataset=='MIMIC' else 'c.hospitalid::text'
    score="""CASE WHEN get_byte(patient_hash,0)::bigint*16777216+get_byte(patient_hash,1)::bigint*65536+get_byte(patient_hash,2)::bigint*256+get_byte(patient_hash,3)<3006477107::bigint THEN 'train'
WHEN get_byte(patient_hash,0)::bigint*16777216+get_byte(patient_hash,1)::bigint*65536+get_byte(patient_hash,2)::bigint*256+get_byte(patient_hash,3)<3650722201::bigint THEN 'validation' ELSE 'test' END""" if dataset=='MIMIC' else "'external'::text"
    from_c=f"(SELECT *,sha256(convert_to('landmark_model_split_v1|mimic|'||{person}::text,'UTF8')) AS patient_hash FROM {schema}.{table})" if dataset=='MIMIC' else f'{schema}.{table}'
    selects.append(f"""SELECT '{dataset}'::text AS dataset,c.{person}::text AS patient_id,c.{stay}::bigint AS stay_id,{hospital} AS hospital_id,
c.landmark_hours,c.hospital_mortality,{score} AS split,
{','.join('c.'+x for x in core)},{','.join('g.'+x for x in extra)},{','.join('d.'+x for x in support)}
FROM {from_c} c
JOIN {schema}.gcs_features_candidate_v1 g ON c.{person}=g.{person} AND c.landmark_hours=g.landmark_hours
JOIN {schema}.support_documentation_features_candidate_v1 d ON c.{person}=d.{person} AND c.landmark_hours=d.landmark_hours
WHERE c.{stay}=g.{stay} AND c.{stay}=d.{stay} AND c.hospital_mortality=g.hospital_mortality AND c.hospital_mortality=d.hospital_mortality""")
sql=[r'\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",'CREATE TEMP TABLE model_candidate_export ON COMMIT DROP AS\n'+'\nUNION ALL\n'.join(selects)+';',
    'ALTER TABLE model_candidate_export ADD PRIMARY KEY(dataset,landmark_hours,patient_id);',
    """DO $$ BEGIN IF EXISTS(
(SELECT 'MIMIC'::text AS dataset,landmark_hours,subject_id::text AS patient_id,stay_id,hospital_mortality FROM landmark_mimic48.primary_landmark_cohort
 UNION ALL SELECT 'eICU',landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort
 EXCEPT SELECT dataset,landmark_hours,patient_id,stay_id,hospital_mortality FROM model_candidate_export)
UNION ALL
(SELECT dataset,landmark_hours,patient_id,stay_id,hospital_mortality FROM model_candidate_export
 EXCEPT (SELECT 'MIMIC'::text,landmark_hours,subject_id::text,stay_id,hospital_mortality FROM landmark_mimic48.primary_landmark_cohort
 UNION ALL SELECT 'eICU',landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort))
) THEN RAISE EXCEPTION 'Model export differs from confirmed primary cohorts'; END IF;
IF EXISTS(SELECT 1 FROM model_candidate_export GROUP BY dataset,patient_id HAVING count(DISTINCT split)>1)
THEN RAISE EXCEPTION 'Patient split crosses partitions'; END IF;
IF EXISTS(SELECT 1 FROM model_candidate_export WHERE hospital_mortality NOT IN(0,1) OR hospital_mortality IS NULL)
THEN RAISE EXCEPTION 'Invalid outcome'; END IF; END $$;""",
    "\\echo 'F1 Cohort and patient split counts; external outcomes are not used for tuning'",
    'SELECT dataset,landmark_hours,split,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM model_candidate_export GROUP BY dataset,landmark_hours,split ORDER BY dataset,landmark_hours,split;']
checks=[]
for name in core+['gcs_total_components']:
    checks.append(f"SELECT dataset,landmark_hours,'{name}'::text AS variable,count(*) AS patients,count({name}) AS observed_patients,min({name}) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY {name}) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY {name}) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY {name}) AS p99,max({name}) AS maximum,count(*) FILTER(WHERE {name}::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours")
sql+= ["\\echo 'F2 Candidate distributions and missingness; descriptive source audit only'",'\nUNION ALL\n'.join(checks)+' ORDER BY dataset,landmark_hours,variable;']
for dataset,filename in [('MIMIC','mimic_candidate_features.csv'),('eICU','eicu_candidate_features.csv')]:
    path=(FOLDER/filename).as_posix().replace("'","''")
    sql.append(f"\\copy (SELECT * FROM model_candidate_export WHERE dataset='{dataset}' ORDER BY landmark_hours,patient_id) TO '{path}' WITH(FORMAT csv,HEADER true,NULL '')")
sql+=['COMMIT;']
(ROOT/'15_final_feature_audit_and_export.sql').write_text('\n\n'.join(sql)+'\n',encoding='utf-8')
manifest={'status':'Prepared; live audit/export pending; primary predictor decision not yet locked',
 'core_predictors':core,'candidate_supplement_fields':extra+support,
 'split_seed':'landmark_model_split_v1','split_rule':'SHA256 UTF8 landmark_model_split_v1|mimic|patient_id, first 32 bits unsigned, thresholds floor(0.70*2^32) and floor(0.85*2^32)',
 'split_targets':{'train':0.70,'validation':0.15,'test':0.15},'external':'All eICU patients; no external tuning',
 'excluded_from_predictors':['dataset','patient_id','stay_id','hospital_id','landmark_hours','hospital_mortality','split'],
 'purpose':'Local candidate snapshot export; no imputation, scaling, fitting or scoring'}
scope_path=FOLDER/'primary_predictor_scope_approved.json'
if scope_path.exists():
    scope=json.loads(scope_path.read_text(encoding='utf-8'))
    assert scope['primary_predictors']==core
    manifest['status']='Primary 26-concept scope approved; live final audit/export and subsequent preprocessing lock pending'
    manifest['primary_predictor_scope_approved']=scope
(FOLDER/'preparation_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Prepared final feature audit/export with fixed patient-level splits; no model fitted.')
