\set ON_ERROR_STOP on
BEGIN;
SET LOCAL client_encoding='UTF8';
CREATE TEMP TABLE expected_temperature_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;
\copy expected_temperature_cohorts FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/expected_cohorts.csv' WITH(FORMAT csv,HEADER true,NULL '')
DO $$ BEGIN IF pg_database_size(current_database())+283449500*6>90000000000 THEN RAISE EXCEPTION 'Temperature build conservative storage estimate exceeds 90 GB'; END IF; END $$;
DO $$ BEGIN IF EXISTS(
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_temperature_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v2)
UNION ALL
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v2 EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_temperature_cohorts)
) THEN RAISE EXCEPTION 'Temperature extraction cohort does not match candidate v2'; END IF; END $$;
CREATE TABLE eicu_landmark.nursing_temperature_source_v1(
nursingchartid bigint,patientunitstayid bigint,nursingchartoffset bigint,nursingchartentryoffset bigint,
nursingchartcelltypecat text,nursingchartcelltypevallabel text,nursingchartcelltypevalname text,nursingchartvalue text);
\copy eicu_landmark.nursing_temperature_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_temperature_stage/nursing_temperature.csv' WITH(FORMAT csv,HEADER true,NULL '')
DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.nursing_temperature_source_v1)<>3871621 THEN RAISE EXCEPTION 'Temperature source row count mismatch'; END IF; END $$;
CREATE INDEX ON eicu_landmark.nursing_temperature_source_v1(patientunitstayid,nursingchartoffset,nursingchartentryoffset);
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
CREATE TABLE eicu_landmark.core_features_candidate_v3 AS
SELECT c.uniquepid,c.patienthealthsystemstayid,c.patientunitstayid,c.hospitalid,c.landmark_hours,c.landmark_offset_minutes,c.hospital_mortality,c.age_capped_90,c.female,c.creatinine,c.bun,c.sodium,c.potassium,c.chloride,c.bicarbonate,c.glucose,c.hemoglobin,c.hematocrit,c.wbc,c.platelets,c.calcium_total,c.magnesium,c.phosphate,c.albumin,c.bilirubin_total,c.lactate,c.heart_rate,c.respiratory_rate,c.spo2,t.value AS temperature,c.systolic_bp,c.diastolic_bp,c.mean_bp
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
DO $$ BEGIN IF EXISTS(
SELECT 1 FROM eicu_landmark.core_features_candidate_v2 a FULL JOIN eicu_landmark.core_features_candidate_v3 b USING(landmark_hours,uniquepid)
WHERE a.uniquepid IS NULL OR b.uniquepid IS NULL OR a.uniquepid IS DISTINCT FROM b.uniquepid OR a.patienthealthsystemstayid IS DISTINCT FROM b.patienthealthsystemstayid OR a.patientunitstayid IS DISTINCT FROM b.patientunitstayid OR a.hospitalid IS DISTINCT FROM b.hospitalid OR a.landmark_hours IS DISTINCT FROM b.landmark_hours OR a.landmark_offset_minutes IS DISTINCT FROM b.landmark_offset_minutes OR a.hospital_mortality IS DISTINCT FROM b.hospital_mortality OR a.age_capped_90 IS DISTINCT FROM b.age_capped_90 OR a.female IS DISTINCT FROM b.female OR a.creatinine IS DISTINCT FROM b.creatinine OR a.bun IS DISTINCT FROM b.bun OR a.sodium IS DISTINCT FROM b.sodium OR a.potassium IS DISTINCT FROM b.potassium OR a.chloride IS DISTINCT FROM b.chloride OR a.bicarbonate IS DISTINCT FROM b.bicarbonate OR a.glucose IS DISTINCT FROM b.glucose OR a.hemoglobin IS DISTINCT FROM b.hemoglobin OR a.hematocrit IS DISTINCT FROM b.hematocrit OR a.wbc IS DISTINCT FROM b.wbc OR a.platelets IS DISTINCT FROM b.platelets OR a.calcium_total IS DISTINCT FROM b.calcium_total OR a.magnesium IS DISTINCT FROM b.magnesium OR a.phosphate IS DISTINCT FROM b.phosphate OR a.albumin IS DISTINCT FROM b.albumin OR a.bilirubin_total IS DISTINCT FROM b.bilirubin_total OR a.lactate IS DISTINCT FROM b.lactate OR a.heart_rate IS DISTINCT FROM b.heart_rate OR a.respiratory_rate IS DISTINCT FROM b.respiratory_rate OR a.spo2 IS DISTINCT FROM b.spo2 OR a.systolic_bp IS DISTINCT FROM b.systolic_bp OR a.diastolic_bp IS DISTINCT FROM b.diastolic_bp OR a.mean_bp IS DISTINCT FROM b.mean_bp
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
