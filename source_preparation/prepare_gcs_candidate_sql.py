"""Generate comparable observed-component GCS candidates, with separate reported-total audit."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
lines=[r'\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",
       "DO $$ BEGIN IF pg_database_size(current_database())>90000000000::bigint THEN RAISE EXCEPTION 'Database already exceeds 90 GB working guard'; END IF; END $$;"]
reports=[];quality=[]
for dataset,schema,person,stay,lm in [('MIMIC','landmark_mimic48','subject_id','stay_id',"extract(epoch FROM (c.landmark_time-s.intime))/60.0"),('eICU','eicu_landmark','uniquepid','patientunitstayid','c.landmark_offset_minutes')]:
    if dataset=='MIMIC':
        raw="""SELECT x.stay_id AS stay_key,extract(epoch FROM(x.charttime-s.intime))/60.0 AS event_minutes,
CASE WHEN x.storetime IS NOT NULL THEN extract(epoch FROM(GREATEST(x.charttime,x.storetime)-s.intime))/60.0 END AS available_minutes,
CASE x.itemid WHEN 220739 THEN 'eye' WHEN 223900 THEN 'verbal' WHEN 223901 THEN 'motor' END AS component,
x.valuenum AS numeric_value,COALESCE(x.value,'') ~* '(unable|ETT|trach|intubat|sedat|medication)' AS unassessable
FROM landmark_mimic48.chartevents x
JOIN (SELECT DISTINCT i.stay_id,i.intime FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays i USING(stay_id)) s USING(stay_id)
WHERE x.itemid IN(220739,223900,223901) AND x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'"""
    else:
        raw="""SELECT x.patientunitstayid AS stay_key,x.nursingchartoffset::double precision AS event_minutes,
CASE WHEN x.nursingchartentryoffset IS NOT NULL THEN GREATEST(x.nursingchartoffset,x.nursingchartentryoffset)::double precision END AS available_minutes,
CASE lower(x.nursingchartcelltypevalname) WHEN 'eyes' THEN 'eye' WHEN 'gcs eyes' THEN 'eye' WHEN 'verbal' THEN 'verbal' WHEN 'gcs verbal' THEN 'verbal' WHEN 'motor' THEN 'motor' WHEN 'gcs motor' THEN 'motor' WHEN 'gcs total' THEN 'reported' END AS component,
CASE WHEN length(btrim(x.nursingchartvalue))<=32 AND btrim(x.nursingchartvalue) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
THEN btrim(x.nursingchartvalue)::double precision END AS numeric_value,
COALESCE(x.nursingchartvalue,'') ~* '(unable|ETT|trach|intubat|sedat|medication)' AS unassessable
FROM eicu_landmark.extension_nursecharting_source_v1 x
WHERE lower(x.nursingchartcelltypevallabel)='glasgow coma score'
AND lower(x.nursingchartcelltypevalname) IN('eyes','gcs eyes','verbal','gcs verbal','motor','gcs motor','gcs total')
AND x.nursingchartoffset BETWEEN 0 AND 2880"""
    aggregates=[]
    for field in ['eye','verbal','motor','reported']:
        for op in ['min','max']:
            aggregates.append(f"{op}(numeric_value) FILTER(WHERE component='{field}') AS {field}_{op}")
    valid=lambda field,low,high:f"{field}_min={field}_max AND {field}_min BETWEEN {low} AND {high} AND {field}_min=trunc({field}_min::numeric)"
    component_valid=' AND '.join(valid(k,1,n) for k,n in [('eye',4),('verbal',5),('motor',6)])
    reported_valid=valid('reported',3,15)
    lines.append(f"""CREATE TABLE {schema}.gcs_assessment_candidate_v1 AS
WITH raw AS ({raw}), grouped AS (
SELECT stay_key,event_minutes,max(available_minutes) AS available_minutes,
count(*) FILTER(WHERE available_minutes IS NULL) AS unknown_availability_rows,
bool_or(unassessable) AS explicit_unassessable,{','.join(aggregates)}
FROM raw GROUP BY stay_key,event_minutes
), scored AS (
SELECT *,CASE WHEN NOT explicit_unassessable AND {component_valid} THEN eye_min+verbal_min+motor_min END AS component_total,
CASE WHEN NOT explicit_unassessable AND {reported_valid} THEN reported_min END AS reported_total
FROM grouped
)
SELECT *,component_total IS NOT NULL AND reported_total IS NOT NULL AND component_total<>reported_total AS component_reported_disagreement
FROM scored;
CREATE INDEX ON {schema}.gcs_assessment_candidate_v1(stay_key,event_minutes,available_minutes);
COMMENT ON TABLE {schema}.gcs_assessment_candidate_v1 IS 'Observed same-event GCS components; no normal defaults or component carry-forward; conservative whole-assessment availability; reported total separate; not frozen predictor set';""")
    join_stays=' JOIN landmark_mimic48.icustays s USING(stay_id)' if dataset=='MIMIC' else ''
    laterals=[]
    for alias,condition in [('g','component_total IS NOT NULL'),('r','reported_total IS NOT NULL'),('a','true')]:
        laterals.append(f"""LEFT JOIN LATERAL(SELECT * FROM {schema}.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.{stay} AND x.event_minutes BETWEEN 0 AND {lm}
AND x.unknown_availability_rows=0 AND x.available_minutes<={lm} AND {condition}
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) {alias} ON true""")
    lines.append(f"""CREATE TABLE {schema}.gcs_features_candidate_v1 AS
SELECT c.*,g.component_total AS gcs_total_components,r.reported_total AS gcs_total_reported,
({lm}-g.event_minutes)/60.0 AS gcs_component_age_hours,
g.event_minutes AS gcs_component_event_minutes,g.available_minutes AS gcs_component_available_minutes,
a.explicit_unassessable AS gcs_latest_assessment_unassessable,
a.component_reported_disagreement AS gcs_latest_assessment_disagreement
FROM {schema}.primary_landmark_cohort c{join_stays}
{' '.join(laterals)};
ALTER TABLE {schema}.gcs_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,{person});
DO $$ BEGIN IF EXISTS(
SELECT 1 FROM {schema}.primary_landmark_cohort c FULL JOIN {schema}.gcs_features_candidate_v1 f USING(landmark_hours,{person})
WHERE c.{person} IS NULL OR f.{person} IS NULL OR c.{stay} IS DISTINCT FROM f.{stay} OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality
) THEN RAISE EXCEPTION 'GCS candidate cohort/outcome mismatch'; END IF;
IF EXISTS(SELECT 1 FROM {schema}.gcs_features_candidate_v1 WHERE gcs_total_components IS NOT NULL AND
(gcs_total_components NOT BETWEEN 3 AND 15 OR gcs_component_available_minutes>landmark_hours*60 OR gcs_component_event_minutes>landmark_hours*60 OR gcs_component_age_hours<0))
THEN RAISE EXCEPTION 'GCS candidate value/availability violation'; END IF; END $$;
COMMENT ON TABLE {schema}.gcs_features_candidate_v1 IS 'GCS-only candidate feature supplement; all cohort patients retained; component total comparable rule; reported total audit only; no imputation or model';""")
    reports.append(f"SELECT '{dataset}' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,count(gcs_total_components) AS observed_component_totals,round(100.0*count(gcs_total_components)/count(*),2) AS component_percent,count(gcs_total_reported) AS observed_reported_totals,count(*) FILTER(WHERE gcs_latest_assessment_unassessable) AS latest_assessment_unassessable FROM {schema}.gcs_features_candidate_v1 GROUP BY landmark_hours")
    quality.append(f"SELECT '{dataset}' AS dataset,count(*) AS assessment_groups,count(*) FILTER(WHERE explicit_unassessable) AS explicit_unassessable_groups,count(*) FILTER(WHERE unknown_availability_rows>0) AS groups_with_unknown_availability,count(*) FILTER(WHERE component_reported_disagreement) AS component_reported_disagreements FROM {schema}.gcs_assessment_candidate_v1")
lines += ['COMMIT;']
for schema in ('landmark_mimic48','eicu_landmark'):
    lines += [f'ANALYZE {schema}.gcs_assessment_candidate_v1;',f'ANALYZE {schema}.gcs_features_candidate_v1;']
lines += ['\nUNION ALL\n'.join(reports)+' ORDER BY dataset,landmark_hours;','\nUNION ALL\n'.join(quality)+' ORDER BY dataset;']
(ROOT/'13_build_gcs_candidates.sql').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
print('Generated GCS candidate build for both databases; no PostgreSQL execution.')
