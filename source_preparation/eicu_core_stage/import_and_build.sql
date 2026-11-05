\set ON_ERROR_STOP on

BEGIN;

SET LOCAL client_encoding='UTF8';

CREATE TEMP TABLE expected_core_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;

\copy expected_core_cohorts FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/expected_cohorts.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF EXISTS(
 (SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_core_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort)
 UNION ALL
 (SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.primary_landmark_cohort EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM expected_core_cohorts)
 ) THEN RAISE EXCEPTION 'Local selection and database cohort differ'; END IF; END $$;

CREATE TEMP TABLE core_wal_baseline ON COMMIT DROP AS SELECT COALESCE(sum(size),0) AS bytes FROM pg_ls_waldir();

CREATE TABLE eicu_landmark.core_vitalperiodic_source_v1("vitalperiodicid" bigint,"patientunitstayid" bigint,"observationoffset" bigint,"temperature" double precision,"sao2" double precision,"heartrate" double precision,"respiration" double precision,"systemicsystolic" double precision,"systemicdiastolic" double precision,"systemicmean" double precision);

\copy eicu_landmark.core_vitalperiodic_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/vitalPeriodic.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF(SELECT count(*) FROM eicu_landmark.core_vitalperiodic_source_v1)<>58894477 THEN RAISE EXCEPTION 'Measurement import row-count mismatch'; END IF; END $$;

CREATE INDEX ON eicu_landmark.core_vitalperiodic_source_v1(patientunitstayid,observationoffset);

DO $$ BEGIN IF 2915636322+pg_database_size(current_database())+GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT bytes FROM core_wal_baseline),0)>90000000000 THEN RAISE EXCEPTION 'Core build storage estimate exceeds 90 GB'; END IF; END $$;

CREATE TABLE eicu_landmark.core_vitalaperiodic_source_v1("vitalaperiodicid" bigint,"patientunitstayid" bigint,"observationoffset" bigint,"noninvasivesystolic" double precision,"noninvasivediastolic" double precision,"noninvasivemean" double precision);

\copy eicu_landmark.core_vitalaperiodic_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/vitalAperiodic.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF(SELECT count(*) FROM eicu_landmark.core_vitalaperiodic_source_v1)<>11423101 THEN RAISE EXCEPTION 'Measurement import row-count mismatch'; END IF; END $$;

CREATE INDEX ON eicu_landmark.core_vitalaperiodic_source_v1(patientunitstayid,observationoffset);

DO $$ BEGIN IF 2915636322+pg_database_size(current_database())+GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT bytes FROM core_wal_baseline),0)>90000000000 THEN RAISE EXCEPTION 'Core build storage estimate exceeds 90 GB'; END IF; END $$;

CREATE TABLE eicu_landmark.core_lab_source_v1("labid" bigint,"patientunitstayid" bigint,"labresultoffset" bigint,"labtypeid" bigint,"labname" text,"labresult" double precision,"labresulttext" text,"labmeasurenamesystem" text,"labmeasurenameinterface" text,"labresultrevisedoffset" bigint);

\copy eicu_landmark.core_lab_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/lab.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF(SELECT count(*) FROM eicu_landmark.core_lab_source_v1)<>4541232 THEN RAISE EXCEPTION 'Measurement import row-count mismatch'; END IF; END $$;

CREATE INDEX ON eicu_landmark.core_lab_source_v1(patientunitstayid,labname,labresultoffset,labresultrevisedoffset);

DO $$ BEGIN IF 2915636322+pg_database_size(current_database())+GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT bytes FROM core_wal_baseline),0)>90000000000 THEN RAISE EXCEPTION 'Core build storage estimate exceeds 90 GB'; END IF; END $$;

CREATE TABLE eicu_landmark.core_features_candidate_v1 AS
SELECT c.uniquepid,c.patienthealthsystemstayid,c.patientunitstayid,c.hospitalid,c.landmark_hours,c.landmark_offset_minutes,c.hospital_mortality,
 LEAST(c.age_for_screening,90) AS age_capped_90,
 CASE WHEN p.gender='Female' THEN 1 WHEN p.gender='Male' THEN 0 END AS female,
 v0.value AS creatinine, v1.value AS bun, v2.value AS sodium, v3.value AS potassium, v4.value AS chloride, v5.value AS bicarbonate, v6.value AS glucose, v7.value AS hemoglobin, v8.value AS hematocrit, v9.value AS wbc, v10.value AS platelets, v11.value AS calcium_total, v12.value AS magnesium, v13.value AS phosphate, v14.value AS albumin, v15.value AS bilirubin_total, v16.value AS lactate, v17.value AS heart_rate, v18.value AS respiratory_rate, v19.value AS spo2, v20.value AS temperature, v21.value AS systolic_bp, v22.value AS diastolic_bp, v23.value AS mean_bp
FROM eicu_landmark.primary_landmark_cohort c JOIN eicu_landmark.patient p USING(patientunitstayid)
LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='creatinine'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=150) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v0 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='BUN'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=300) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v1 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='sodium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=200) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v2 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='potassium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=30) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v3 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='chloride'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v4 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='bicarbonate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('meq/l','mmol/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v5 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='glucose'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v6 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='Hgb'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('g/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('g/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v7 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='Hct'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('%')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('%'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=100) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v8 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='WBC x 1000'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('10*3/ul','10^3/ul','10^9/l','k/mcl','k/mm3','k/ul','x10^3/ul','x10^9/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('10*3/ul','10^3/ul','10^9/l','k/mcl','k/mm3','k/ul','x10^3/ul','x10^9/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>=0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v9 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='platelets x 1000'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('10*3/ul','10^3/ul','10^9/l','k/mcl','k/mm3','k/ul','x10^3/ul','x10^9/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('10*3/ul','10^3/ul','10^9/l','k/mcl','k/mm3','k/ul','x10^3/ul','x10^9/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v10 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='calcium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v11 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='magnesium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v12 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='phosphate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v13 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='albumin'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('g/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('g/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>0 AND labresult<=10) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v14 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='total bilirubin'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mg/dl'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>=0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v15 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT labresultoffset AS event_offset,GREATEST(labresultoffset,labresultrevisedoffset) AS available_offset,1 AS source_priority,labresult AS value
FROM eicu_landmark.core_lab_source_v1 WHERE patientunitstayid=c.patientunitstayid AND labname='lactate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN('mmol/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN('mmol/l'))
AND labresult::text NOT IN('NaN','Infinity','-Infinity') AND labresult>=0 AND labresult<=10000) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v16 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,heartrate AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND heartrate::text NOT IN('NaN','Infinity','-Infinity') AND heartrate>0 AND heartrate<300) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v17 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,respiration AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND respiration::text NOT IN('NaN','Infinity','-Infinity') AND respiration>0 AND respiration<70) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v18 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,sao2 AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND sao2::text NOT IN('NaN','Infinity','-Infinity') AND sao2>0 AND sao2<=100) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v19 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,temperature AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND temperature::text NOT IN('NaN','Infinity','-Infinity') AND temperature>10 AND temperature<50) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v20 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,systemicsystolic AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND systemicsystolic::text NOT IN('NaN','Infinity','-Infinity') AND systemicsystolic>0 AND systemicsystolic<400 UNION ALL SELECT observationoffset,observationoffset,1,noninvasivesystolic FROM eicu_landmark.core_vitalaperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND noninvasivesystolic::text NOT IN('NaN','Infinity','-Infinity') AND noninvasivesystolic>0 AND noninvasivesystolic<400) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v21 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,systemicdiastolic AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND systemicdiastolic::text NOT IN('NaN','Infinity','-Infinity') AND systemicdiastolic>0 AND systemicdiastolic<300 UNION ALL SELECT observationoffset,observationoffset,1,noninvasivediastolic FROM eicu_landmark.core_vitalaperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND noninvasivediastolic::text NOT IN('NaN','Infinity','-Infinity') AND noninvasivediastolic>0 AND noninvasivediastolic<300) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v22 ON true LEFT JOIN LATERAL(SELECT avg(value) AS value,event_offset,available_offset,source_priority FROM(SELECT observationoffset AS event_offset,observationoffset AS available_offset,0 AS source_priority,systemicmean AS value FROM eicu_landmark.core_vitalperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND systemicmean::text NOT IN('NaN','Infinity','-Infinity') AND systemicmean>0 AND systemicmean<300 UNION ALL SELECT observationoffset,observationoffset,1,noninvasivemean FROM eicu_landmark.core_vitalaperiodic_source_v1 WHERE patientunitstayid=c.patientunitstayid AND observationoffset BETWEEN 0 AND c.landmark_offset_minutes AND noninvasivemean::text NOT IN('NaN','Infinity','-Infinity') AND noninvasivemean>0 AND noninvasivemean<300) x GROUP BY event_offset,available_offset,source_priority ORDER BY event_offset DESC,source_priority ASC,available_offset DESC LIMIT 1) v23 ON true;
ALTER TABLE eicu_landmark.core_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,uniquepid);
COMMENT ON TABLE eicu_landmark.core_features_candidate_v1 IS 'Candidate core features; manifest SHA256 a4e6accfc44125e81e34c319dec5eb87927e40f1ea7e552c6564a900438fa8ed; no imputation/scaling; source availability differences and remaining domains require evaluation';

DO $$ BEGIN IF EXISTS(
SELECT 1 FROM eicu_landmark.primary_landmark_cohort c FULL JOIN eicu_landmark.core_features_candidate_v1 f USING(uniquepid,landmark_hours)
WHERE c.uniquepid IS NULL OR f.uniquepid IS NULL OR c.patientunitstayid<>f.patientunitstayid OR c.hospital_mortality<>f.hospital_mortality
) THEN RAISE EXCEPTION 'Features do not match primary cohort'; END IF; END $$;

DO $$ BEGIN IF 2915636322+pg_database_size(current_database())+GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT bytes FROM core_wal_baseline),0)>90000000000 THEN RAISE EXCEPTION 'Core build storage estimate exceeds 90 GB'; END IF; END $$;

COMMIT;

ANALYZE eicu_landmark.core_features_candidate_v1;

-- Result 1
SELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours ORDER BY landmark_hours;

-- Result 2
SELECT landmark_hours,'creatinine' AS variable,count(*) AS patients,count(creatinine) AS observed_patients,round(100.0*count(creatinine)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bun' AS variable,count(*) AS patients,count(bun) AS observed_patients,round(100.0*count(bun)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'sodium' AS variable,count(*) AS patients,count(sodium) AS observed_patients,round(100.0*count(sodium)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'potassium' AS variable,count(*) AS patients,count(potassium) AS observed_patients,round(100.0*count(potassium)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'chloride' AS variable,count(*) AS patients,count(chloride) AS observed_patients,round(100.0*count(chloride)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bicarbonate' AS variable,count(*) AS patients,count(bicarbonate) AS observed_patients,round(100.0*count(bicarbonate)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'glucose' AS variable,count(*) AS patients,count(glucose) AS observed_patients,round(100.0*count(glucose)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'hemoglobin' AS variable,count(*) AS patients,count(hemoglobin) AS observed_patients,round(100.0*count(hemoglobin)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'hematocrit' AS variable,count(*) AS patients,count(hematocrit) AS observed_patients,round(100.0*count(hematocrit)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'wbc' AS variable,count(*) AS patients,count(wbc) AS observed_patients,round(100.0*count(wbc)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'platelets' AS variable,count(*) AS patients,count(platelets) AS observed_patients,round(100.0*count(platelets)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'calcium_total' AS variable,count(*) AS patients,count(calcium_total) AS observed_patients,round(100.0*count(calcium_total)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'magnesium' AS variable,count(*) AS patients,count(magnesium) AS observed_patients,round(100.0*count(magnesium)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'phosphate' AS variable,count(*) AS patients,count(phosphate) AS observed_patients,round(100.0*count(phosphate)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'albumin' AS variable,count(*) AS patients,count(albumin) AS observed_patients,round(100.0*count(albumin)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bilirubin_total' AS variable,count(*) AS patients,count(bilirubin_total) AS observed_patients,round(100.0*count(bilirubin_total)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'lactate' AS variable,count(*) AS patients,count(lactate) AS observed_patients,round(100.0*count(lactate)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'heart_rate' AS variable,count(*) AS patients,count(heart_rate) AS observed_patients,round(100.0*count(heart_rate)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'respiratory_rate' AS variable,count(*) AS patients,count(respiratory_rate) AS observed_patients,round(100.0*count(respiratory_rate)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'spo2' AS variable,count(*) AS patients,count(spo2) AS observed_patients,round(100.0*count(spo2)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'temperature' AS variable,count(*) AS patients,count(temperature) AS observed_patients,round(100.0*count(temperature)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'systolic_bp' AS variable,count(*) AS patients,count(systolic_bp) AS observed_patients,round(100.0*count(systolic_bp)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'diastolic_bp' AS variable,count(*) AS patients,count(diastolic_bp) AS observed_patients,round(100.0*count(diastolic_bp)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'mean_bp' AS variable,count(*) AS patients,count(mean_bp) AS observed_patients,round(100.0*count(mean_bp)/count(*),2) AS observed_percent FROM eicu_landmark.core_features_candidate_v1 GROUP BY landmark_hours ORDER BY landmark_hours,variable;

-- Result 3: lab unit compatibility by observed source pair, before screening.
SELECT labname,labmeasurenamesystem,labmeasurenameinterface,count(*) AS observations,
 count(*) FILTER(WHERE labresultrevisedoffset<labresultoffset) AS entry_before_sample
FROM eicu_landmark.core_lab_source_v1 GROUP BY labname,labmeasurenamesystem,labmeasurenameinterface
ORDER BY labname,observations DESC;
