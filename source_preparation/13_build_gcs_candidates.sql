\set ON_ERROR_STOP on

BEGIN;

SET LOCAL client_encoding='UTF8';

DO $$ BEGIN IF pg_database_size(current_database())>90000000000::bigint THEN RAISE EXCEPTION 'Database already exceeds 90 GB working guard'; END IF; END $$;

CREATE TABLE landmark_mimic48.gcs_assessment_candidate_v1 AS
WITH raw AS (SELECT x.stay_id AS stay_key,extract(epoch FROM(x.charttime-s.intime))/60.0 AS event_minutes,
CASE WHEN x.storetime IS NOT NULL THEN extract(epoch FROM(GREATEST(x.charttime,x.storetime)-s.intime))/60.0 END AS available_minutes,
CASE x.itemid WHEN 220739 THEN 'eye' WHEN 223900 THEN 'verbal' WHEN 223901 THEN 'motor' END AS component,
x.valuenum AS numeric_value,COALESCE(x.value,'') ~* '(unable|ETT|trach|intubat|sedat|medication)' AS unassessable
FROM landmark_mimic48.chartevents x
JOIN (SELECT DISTINCT i.stay_id,i.intime FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays i USING(stay_id)) s USING(stay_id)
WHERE x.itemid IN(220739,223900,223901) AND x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'), grouped AS (
SELECT stay_key,event_minutes,max(available_minutes) AS available_minutes,
count(*) FILTER(WHERE available_minutes IS NULL) AS unknown_availability_rows,
bool_or(unassessable) AS explicit_unassessable,min(numeric_value) FILTER(WHERE component='eye') AS eye_min,max(numeric_value) FILTER(WHERE component='eye') AS eye_max,min(numeric_value) FILTER(WHERE component='verbal') AS verbal_min,max(numeric_value) FILTER(WHERE component='verbal') AS verbal_max,min(numeric_value) FILTER(WHERE component='motor') AS motor_min,max(numeric_value) FILTER(WHERE component='motor') AS motor_max,min(numeric_value) FILTER(WHERE component='reported') AS reported_min,max(numeric_value) FILTER(WHERE component='reported') AS reported_max
FROM raw GROUP BY stay_key,event_minutes
), scored AS (
SELECT *,CASE WHEN NOT explicit_unassessable AND eye_min=eye_max AND eye_min BETWEEN 1 AND 4 AND eye_min=trunc(eye_min::numeric) AND verbal_min=verbal_max AND verbal_min BETWEEN 1 AND 5 AND verbal_min=trunc(verbal_min::numeric) AND motor_min=motor_max AND motor_min BETWEEN 1 AND 6 AND motor_min=trunc(motor_min::numeric) THEN eye_min+verbal_min+motor_min END AS component_total,
CASE WHEN NOT explicit_unassessable AND reported_min=reported_max AND reported_min BETWEEN 3 AND 15 AND reported_min=trunc(reported_min::numeric) THEN reported_min END AS reported_total
FROM grouped
)
SELECT *,component_total IS NOT NULL AND reported_total IS NOT NULL AND component_total<>reported_total AS component_reported_disagreement
FROM scored;
CREATE INDEX ON landmark_mimic48.gcs_assessment_candidate_v1(stay_key,event_minutes,available_minutes);
COMMENT ON TABLE landmark_mimic48.gcs_assessment_candidate_v1 IS 'Observed same-event GCS components; no normal defaults or component carry-forward; conservative whole-assessment availability; reported total separate; not frozen predictor set';

CREATE TABLE landmark_mimic48.gcs_features_candidate_v1 AS
SELECT c.*,g.component_total AS gcs_total_components,r.reported_total AS gcs_total_reported,
(extract(epoch FROM (c.landmark_time-s.intime))/60.0-g.event_minutes)/60.0 AS gcs_component_age_hours,
g.event_minutes AS gcs_component_event_minutes,g.available_minutes AS gcs_component_available_minutes,
a.explicit_unassessable AS gcs_latest_assessment_unassessable,
a.component_reported_disagreement AS gcs_latest_assessment_disagreement
FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays s USING(stay_id)
LEFT JOIN LATERAL(SELECT * FROM landmark_mimic48.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.stay_id AND x.event_minutes BETWEEN 0 AND extract(epoch FROM (c.landmark_time-s.intime))/60.0
AND x.unknown_availability_rows=0 AND x.available_minutes<=extract(epoch FROM (c.landmark_time-s.intime))/60.0 AND component_total IS NOT NULL
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) g ON true LEFT JOIN LATERAL(SELECT * FROM landmark_mimic48.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.stay_id AND x.event_minutes BETWEEN 0 AND extract(epoch FROM (c.landmark_time-s.intime))/60.0
AND x.unknown_availability_rows=0 AND x.available_minutes<=extract(epoch FROM (c.landmark_time-s.intime))/60.0 AND reported_total IS NOT NULL
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) r ON true LEFT JOIN LATERAL(SELECT * FROM landmark_mimic48.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.stay_id AND x.event_minutes BETWEEN 0 AND extract(epoch FROM (c.landmark_time-s.intime))/60.0
AND x.unknown_availability_rows=0 AND x.available_minutes<=extract(epoch FROM (c.landmark_time-s.intime))/60.0 AND true
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) a ON true;
ALTER TABLE landmark_mimic48.gcs_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,subject_id);
DO $$ BEGIN IF EXISTS(
SELECT 1 FROM landmark_mimic48.primary_landmark_cohort c FULL JOIN landmark_mimic48.gcs_features_candidate_v1 f USING(landmark_hours,subject_id)
WHERE c.subject_id IS NULL OR f.subject_id IS NULL OR c.stay_id IS DISTINCT FROM f.stay_id OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality
) THEN RAISE EXCEPTION 'GCS candidate cohort/outcome mismatch'; END IF;
IF EXISTS(SELECT 1 FROM landmark_mimic48.gcs_features_candidate_v1 WHERE gcs_total_components IS NOT NULL AND
(gcs_total_components NOT BETWEEN 3 AND 15 OR gcs_component_available_minutes>landmark_hours*60 OR gcs_component_event_minutes>landmark_hours*60 OR gcs_component_age_hours<0))
THEN RAISE EXCEPTION 'GCS candidate value/availability violation'; END IF; END $$;
COMMENT ON TABLE landmark_mimic48.gcs_features_candidate_v1 IS 'GCS-only candidate feature supplement; all cohort patients retained; component total comparable rule; reported total audit only; no imputation or model';

CREATE TABLE eicu_landmark.gcs_assessment_candidate_v1 AS
WITH raw AS (SELECT x.patientunitstayid AS stay_key,x.nursingchartoffset::double precision AS event_minutes,
CASE WHEN x.nursingchartentryoffset IS NOT NULL THEN GREATEST(x.nursingchartoffset,x.nursingchartentryoffset)::double precision END AS available_minutes,
CASE lower(x.nursingchartcelltypevalname) WHEN 'eyes' THEN 'eye' WHEN 'gcs eyes' THEN 'eye' WHEN 'verbal' THEN 'verbal' WHEN 'gcs verbal' THEN 'verbal' WHEN 'motor' THEN 'motor' WHEN 'gcs motor' THEN 'motor' WHEN 'gcs total' THEN 'reported' END AS component,
CASE WHEN length(btrim(x.nursingchartvalue))<=32 AND btrim(x.nursingchartvalue) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
THEN btrim(x.nursingchartvalue)::double precision END AS numeric_value,
COALESCE(x.nursingchartvalue,'') ~* '(unable|ETT|trach|intubat|sedat|medication)' AS unassessable
FROM eicu_landmark.extension_nursecharting_source_v1 x
WHERE lower(x.nursingchartcelltypevallabel)='glasgow coma score'
AND lower(x.nursingchartcelltypevalname) IN('eyes','gcs eyes','verbal','gcs verbal','motor','gcs motor','gcs total')
AND x.nursingchartoffset BETWEEN 0 AND 2880), grouped AS (
SELECT stay_key,event_minutes,max(available_minutes) AS available_minutes,
count(*) FILTER(WHERE available_minutes IS NULL) AS unknown_availability_rows,
bool_or(unassessable) AS explicit_unassessable,min(numeric_value) FILTER(WHERE component='eye') AS eye_min,max(numeric_value) FILTER(WHERE component='eye') AS eye_max,min(numeric_value) FILTER(WHERE component='verbal') AS verbal_min,max(numeric_value) FILTER(WHERE component='verbal') AS verbal_max,min(numeric_value) FILTER(WHERE component='motor') AS motor_min,max(numeric_value) FILTER(WHERE component='motor') AS motor_max,min(numeric_value) FILTER(WHERE component='reported') AS reported_min,max(numeric_value) FILTER(WHERE component='reported') AS reported_max
FROM raw GROUP BY stay_key,event_minutes
), scored AS (
SELECT *,CASE WHEN NOT explicit_unassessable AND eye_min=eye_max AND eye_min BETWEEN 1 AND 4 AND eye_min=trunc(eye_min::numeric) AND verbal_min=verbal_max AND verbal_min BETWEEN 1 AND 5 AND verbal_min=trunc(verbal_min::numeric) AND motor_min=motor_max AND motor_min BETWEEN 1 AND 6 AND motor_min=trunc(motor_min::numeric) THEN eye_min+verbal_min+motor_min END AS component_total,
CASE WHEN NOT explicit_unassessable AND reported_min=reported_max AND reported_min BETWEEN 3 AND 15 AND reported_min=trunc(reported_min::numeric) THEN reported_min END AS reported_total
FROM grouped
)
SELECT *,component_total IS NOT NULL AND reported_total IS NOT NULL AND component_total<>reported_total AS component_reported_disagreement
FROM scored;
CREATE INDEX ON eicu_landmark.gcs_assessment_candidate_v1(stay_key,event_minutes,available_minutes);
COMMENT ON TABLE eicu_landmark.gcs_assessment_candidate_v1 IS 'Observed same-event GCS components; no normal defaults or component carry-forward; conservative whole-assessment availability; reported total separate; not frozen predictor set';

CREATE TABLE eicu_landmark.gcs_features_candidate_v1 AS
SELECT c.*,g.component_total AS gcs_total_components,r.reported_total AS gcs_total_reported,
(c.landmark_offset_minutes-g.event_minutes)/60.0 AS gcs_component_age_hours,
g.event_minutes AS gcs_component_event_minutes,g.available_minutes AS gcs_component_available_minutes,
a.explicit_unassessable AS gcs_latest_assessment_unassessable,
a.component_reported_disagreement AS gcs_latest_assessment_disagreement
FROM eicu_landmark.primary_landmark_cohort c
LEFT JOIN LATERAL(SELECT * FROM eicu_landmark.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.patientunitstayid AND x.event_minutes BETWEEN 0 AND c.landmark_offset_minutes
AND x.unknown_availability_rows=0 AND x.available_minutes<=c.landmark_offset_minutes AND component_total IS NOT NULL
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) g ON true LEFT JOIN LATERAL(SELECT * FROM eicu_landmark.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.patientunitstayid AND x.event_minutes BETWEEN 0 AND c.landmark_offset_minutes
AND x.unknown_availability_rows=0 AND x.available_minutes<=c.landmark_offset_minutes AND reported_total IS NOT NULL
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) r ON true LEFT JOIN LATERAL(SELECT * FROM eicu_landmark.gcs_assessment_candidate_v1 x
WHERE x.stay_key=c.patientunitstayid AND x.event_minutes BETWEEN 0 AND c.landmark_offset_minutes
AND x.unknown_availability_rows=0 AND x.available_minutes<=c.landmark_offset_minutes AND true
ORDER BY x.event_minutes DESC,x.available_minutes DESC LIMIT 1) a ON true;
ALTER TABLE eicu_landmark.gcs_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,uniquepid);
DO $$ BEGIN IF EXISTS(
SELECT 1 FROM eicu_landmark.primary_landmark_cohort c FULL JOIN eicu_landmark.gcs_features_candidate_v1 f USING(landmark_hours,uniquepid)
WHERE c.uniquepid IS NULL OR f.uniquepid IS NULL OR c.patientunitstayid IS DISTINCT FROM f.patientunitstayid OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality
) THEN RAISE EXCEPTION 'GCS candidate cohort/outcome mismatch'; END IF;
IF EXISTS(SELECT 1 FROM eicu_landmark.gcs_features_candidate_v1 WHERE gcs_total_components IS NOT NULL AND
(gcs_total_components NOT BETWEEN 3 AND 15 OR gcs_component_available_minutes>landmark_hours*60 OR gcs_component_event_minutes>landmark_hours*60 OR gcs_component_age_hours<0))
THEN RAISE EXCEPTION 'GCS candidate value/availability violation'; END IF; END $$;
COMMENT ON TABLE eicu_landmark.gcs_features_candidate_v1 IS 'GCS-only candidate feature supplement; all cohort patients retained; component total comparable rule; reported total audit only; no imputation or model';

COMMIT;

ANALYZE landmark_mimic48.gcs_assessment_candidate_v1;

ANALYZE landmark_mimic48.gcs_features_candidate_v1;

ANALYZE eicu_landmark.gcs_assessment_candidate_v1;

ANALYZE eicu_landmark.gcs_features_candidate_v1;

SELECT 'MIMIC' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,count(gcs_total_components) AS observed_component_totals,round(100.0*count(gcs_total_components)/count(*),2) AS component_percent,count(gcs_total_reported) AS observed_reported_totals,count(*) FILTER(WHERE gcs_latest_assessment_unassessable) AS latest_assessment_unassessable FROM landmark_mimic48.gcs_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT 'eICU' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,count(gcs_total_components) AS observed_component_totals,round(100.0*count(gcs_total_components)/count(*),2) AS component_percent,count(gcs_total_reported) AS observed_reported_totals,count(*) FILTER(WHERE gcs_latest_assessment_unassessable) AS latest_assessment_unassessable FROM eicu_landmark.gcs_features_candidate_v1 GROUP BY landmark_hours ORDER BY dataset,landmark_hours;

SELECT 'MIMIC' AS dataset,count(*) AS assessment_groups,count(*) FILTER(WHERE explicit_unassessable) AS explicit_unassessable_groups,count(*) FILTER(WHERE unknown_availability_rows>0) AS groups_with_unknown_availability,count(*) FILTER(WHERE component_reported_disagreement) AS component_reported_disagreements FROM landmark_mimic48.gcs_assessment_candidate_v1
UNION ALL
SELECT 'eICU' AS dataset,count(*) AS assessment_groups,count(*) FILTER(WHERE explicit_unassessable) AS explicit_unassessable_groups,count(*) FILTER(WHERE unknown_availability_rows>0) AS groups_with_unknown_availability,count(*) FILTER(WHERE component_reported_disagreement) AS component_reported_disagreements FROM eicu_landmark.gcs_assessment_candidate_v1 ORDER BY dataset;
