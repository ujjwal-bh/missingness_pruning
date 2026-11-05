"""Generate aggregate SELECT-only audit SQL; never connect or request credentials."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent;A=R/'model_results/pruning_focused_amendment_2026_10_29_v1';A.mkdir(exist_ok=True)
rules={r['variable']:r for r in json.loads((R/'predictor_cleaning_rules_v1.json').read_text())['variables']};aliases=json.loads((R/'eicu_lab_unit_alias_rules_v2.json').read_text())['variables'];V=['phosphate','magnesium','lactate','albumin','platelets','bicarbonate']
def lit(x):return "'"+str(x).replace("'","''")+"'"
def arr(x):return 'ARRAY['+','.join(lit(v) for v in x)+']::text[]'
def hash32(expr):return '('+'+'.join(f'get_byte({expr},{i})::bigint*{256**(3-i)}::bigint' for i in range(4))+')'
def query(db):
    mimic=db=='MIMIC';schema='landmark_mimic48' if mimic else 'eicu_landmark';feature='core_features_candidate_v1' if mimic else 'core_features_candidate_v3'
    h=hash32("sha256(convert_to('"+('landmark_model_split_v1|mimic|' if mimic else 'missingness_pruning_adaptation_v1|eicu|')+"'||"+('c.subject_id::text' if mimic else 'c.uniquepid')+",'UTF8'))")
    filt=h+('<3006477107::bigint' if mimic else '<858993459::bigint')
    if mimic:
        keys=f"SELECT c.subject_id,c.hadm_id,c.stay_id AS key,s.intime,c.landmark_time FROM {schema}.primary_landmark_cohort c JOIN {schema}.icustays s USING(subject_id,hadm_id,stay_id) WHERE c.landmark_hours=24 AND {filt}"
    else:keys=f"SELECT c.patientunitstayid AS key FROM {schema}.primary_landmark_cohort c WHERE c.landmark_hours=24 AND {filt}"
    mapping=[]
    for v in V:
        r=rules[v];mapping.append('('+','.join([lit(v),'ARRAY['+','.join(map(str,r['mimic_itemids']))+']::bigint[]',lit(r['eicu_labname']),str(r['lower_bound']),str(r['upper_bound']),str(r['lower_inclusive']).lower(),str(r['upper_inclusive']).lower(),arr(r['units_accepted_mimic']),arr(aliases[v]['accepted_normalized_units'])])+')')
    maps='VALUES '+','.join(mapping)
    if mimic:
        raw="""SELECT k.key,m.variable,(x.hadm_id IS NULL OR x.hadm_id=k.hadm_id) AS link_ok,
 x.valuenum IS NOT NULL AND x.valuenum::text NOT IN('NaN','Infinity','-Infinity') AS finite_ok,
 lower(regexp_replace(COALESCE(x.valueuom,''),'\\s','','g'))=ANY(m.mimic_units) AS unit_ok,
 x.storetime IS NOT NULL AND GREATEST(x.charttime,x.storetime)<=k.landmark_time AS available_ok,
 (CASE WHEN m.low_inclusive THEN x.valuenum>=m.low ELSE x.valuenum>m.low END) AND (CASE WHEN m.high_inclusive THEN x.valuenum<=m.high ELSE x.valuenum<m.high END) AS bounds_ok,
 (x.storetime IS NULL) AS missing_availability,
 (x.storetime IS NOT NULL AND GREATEST(x.charttime,x.storetime)>k.landmark_time) AS late_availability
 FROM k JOIN landmark_mimic48.labevents x ON x.subject_id=k.subject_id AND x.charttime BETWEEN k.intime AND k.landmark_time
 JOIN m ON x.itemid=ANY(m.itemids)"""
    else:
        norm=lambda c:"lower(regexp_replace(replace(COALESCE("+c+",''),'µ','u'),'[[:space:]]','','g'))"
        raw=f"""SELECT k.key,m.variable,true AS link_ok,
 x.labresult IS NOT NULL AND x.labresult::text NOT IN('NaN','Infinity','-Infinity') AS finite_ok,
 {norm('x.labmeasurenamesystem')}=ANY(m.eicu_units) AND (COALESCE(x.labmeasurenameinterface,'')='' OR {norm('x.labmeasurenameinterface')}=ANY(m.eicu_units)) AS unit_ok,
 x.labresultrevisedoffset IS NOT NULL AND GREATEST(x.labresultoffset,x.labresultrevisedoffset)<=1440 AS available_ok,
 (CASE WHEN m.low_inclusive THEN x.labresult>=m.low ELSE x.labresult>m.low END) AND (CASE WHEN m.high_inclusive THEN x.labresult<=m.high ELSE x.labresult<m.high END) AS bounds_ok,
 (x.labresultrevisedoffset IS NULL) AS missing_availability,
 (x.labresultrevisedoffset IS NOT NULL AND GREATEST(x.labresultoffset,x.labresultrevisedoffset)>1440) AS late_availability
 FROM k JOIN eicu_landmark.core_lab_source_v1 x ON x.patientunitstayid=k.key AND x.labresultoffset BETWEEN 0 AND 1440
 JOIN m ON x.labname=m.labname"""
    idcol='stay_id' if mimic else 'patientunitstayid';flagvals=','.join('('+lit(v)+',f.'+v+' IS NOT NULL)' for v in V)
    return f"""WITH k AS MATERIALIZED ({keys}),
 m(variable,itemids,labname,low,high,low_inclusive,high_inclusive,mimic_units,eicu_units) AS ({maps}),
 raw AS MATERIALIZED ({raw}),
 g AS (SELECT key,variable,count(*) AS events,
 bool_or(link_ok) AS linked,bool_or(link_ok AND finite_ok) AS numeric,
 bool_or(link_ok AND finite_ok AND unit_ok) AS units,
 bool_or(link_ok AND finite_ok AND unit_ok AND available_ok) AS timely,
 bool_or(link_ok AND finite_ok AND unit_ok AND available_ok AND bounds_ok) AS valid,
 count(*) FILTER(WHERE link_ok AND missing_availability) AS missing_availability_events,
 count(*) FILTER(WHERE link_ok AND late_availability) AS late_availability_events FROM raw GROUP BY key,variable),
 features AS (SELECT k.key,x.variable,x.observed FROM k JOIN {schema}.{feature} f ON f.{idcol}=k.key AND f.landmark_hours=24 CROSS JOIN LATERAL(VALUES {flagvals})x(variable,observed))
 SELECT {lit(db)} AS dataset,{lit('source_training' if mimic else 'target_adaptation')} AS sample,m.variable,
 count(*) AS patients,{37872 if mimic else 20589} AS expected_patients,
 count(*) FILTER(WHERE g.events>0) AS any_imported_event_patients,
 count(*) FILTER(WHERE g.linked) AS linked_event_patients,
 count(*) FILTER(WHERE g.numeric) AS finite_numeric_patients,
 count(*) FILTER(WHERE g.units) AS compatible_unit_patients,
 count(*) FILTER(WHERE g.timely) AS available_by_24h_patients,
 count(*) FILTER(WHERE g.valid) AS screened_available_patients,
 count(*) FILTER(WHERE f.observed) AS final_observed_patients,
 count(*) FILTER(WHERE COALESCE(g.valid,false) IS DISTINCT FROM f.observed OR f.observed IS NULL) AS feature_presence_mismatches,
 COALESCE(sum(g.events),0) AS imported_event_rows,
 COALESCE(sum(g.missing_availability_events),0) AS missing_availability_event_rows,
 COALESCE(sum(g.late_availability_events),0) AS late_availability_event_rows
 FROM k CROSS JOIN m LEFT JOIN g ON g.key=k.key AND g.variable=m.variable LEFT JOIN features f ON f.key=k.key AND f.variable=m.variable GROUP BY m.variable ORDER BY m.variable"""
sql=['\\set ON_ERROR_STOP on','BEGIN READ ONLY;',"SET LOCAL client_encoding='UTF8';","SET LOCAL statement_timeout='0';"]
for db in ['MIMIC','eICU']:
    output=(A/(db+'_harmonization_funnel.csv')).as_posix().replace("'","''")
    sql.append("\\copy ("+' '.join(query(db).split())+") TO '"+output+"' WITH(FORMAT csv,HEADER true)")
sql+=['COMMIT;'];p=R/'16_pruning_top6_harmonization_audit.sql';p.write_text('\n'.join(sql)+'\n',encoding='utf-8')
ps=r'''$ErrorActionPreference='Stop'
$psqlPath='C:\Program Files\PostgreSQL\18\bin\psql.exe'
$sqlPath=Join-Path $PSScriptRoot '16_pruning_top6_harmonization_audit.sql'
Write-Host 'Read-only audit of six laboratory predictors in imported source tables. No model fitting or database changes.'
Write-Host 'Enter the postgres password locally. Only aggregate counts are exported.'
& $psqlPath -X -W -h localhost -p 5432 -U postgres -d landmark_research -v ON_ERROR_STOP=1 -f $sqlPath
if($LASTEXITCODE -ne 0){throw 'Read-only audit failed; preserve the error and report it.'}
$folder=Join-Path $PSScriptRoot 'model_results/pruning_focused_amendment_2026_10_29_v1'
foreach($name in @('MIMIC_harmonization_funnel.csv','eICU_harmonization_funnel.csv')){
 Write-Host $name
 Get-Content -LiteralPath (Join-Path $folder $name)
}
Write-Host 'Send these aggregate counts only. This audit cannot see records excluded before import or infer a clinical reason for missingness.'
'''
(R/'run_pruning_harmonization_audit.ps1').write_text(ps,encoding='utf-8')
assert all(not any(token in q.upper() for token in ['CREATE TABLE','INSERT INTO','UPDATE ','DELETE FROM','DROP TABLE']) for q in sql)
print('Prepared SELECT-only SQL and local password-prompt runner. Audit not executed.')
