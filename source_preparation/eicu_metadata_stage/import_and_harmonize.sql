\set ON_ERROR_STOP on
BEGIN;
SET LOCAL client_encoding='UTF8';
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='eicu_landmark') AND to_regclass('eicu_landmark._metadata_import') IS NULL THEN RAISE EXCEPTION 'eicu_landmark exists without this import ledger; refusing modification'; END IF; END $$;
CREATE SCHEMA IF NOT EXISTS eicu_landmark;
CREATE TABLE IF NOT EXISTS eicu_landmark._metadata_import(table_name text PRIMARY KEY,signature text NOT NULL,row_count bigint NOT NULL);
DO $$ BEGIN IF EXISTS(SELECT 1 FROM eicu_landmark._metadata_import WHERE signature<>'b9ea23764485a11e20323d384bc630bc92ad58e037e7844cf5b3643a6fec58b4') THEN RAISE EXCEPTION 'eICU metadata manifest differs from committed import'; END IF; END $$;
SELECT EXISTS(SELECT 1 FROM eicu_landmark._metadata_import WHERE table_name='patient') AS already_loaded \gset
\if :already_loaded
\else
CREATE TABLE eicu_landmark.patient("patientunitstayid" bigint, "patienthealthsystemstayid" bigint, "gender" text, "age" text, "ethnicity" text, "hospitalid" bigint, "wardid" bigint, "apacheadmissiondx" text, "admissionheight" double precision, "hospitaladmittime24" text, "hospitaladmitoffset" bigint, "hospitaladmitsource" text, "hospitaldischargeyear" bigint, "hospitaldischargetime24" text, "hospitaldischargeoffset" bigint, "hospitaldischargelocation" text, "hospitaldischargestatus" text, "unittype" text, "unitadmittime24" text, "unitadmitsource" text, "unitvisitnumber" bigint, "unitstaytype" text, "admissionweight" double precision, "dischargeweight" double precision, "unitdischargetime24" text, "unitdischargeoffset" bigint, "unitdischargelocation" text, "unitdischargestatus" text, "uniquepid" text);
\copy eicu_landmark.patient FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_metadata_stage/patient.csv' WITH(FORMAT csv,HEADER true,NULL '')
ALTER TABLE eicu_landmark.patient ADD PRIMARY KEY(patientunitstayid);
INSERT INTO eicu_landmark._metadata_import VALUES('patient','b9ea23764485a11e20323d384bc630bc92ad58e037e7844cf5b3643a6fec58b4',200859);
\endif
DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.patient)<>200859 THEN RAISE EXCEPTION 'eICU metadata row-count mismatch'; END IF; END $$;
SELECT EXISTS(SELECT 1 FROM eicu_landmark._metadata_import WHERE table_name='hospital') AS already_loaded \gset
\if :already_loaded
\else
CREATE TABLE eicu_landmark.hospital("hospitalid" bigint, "numbedscategory" text, "teachingstatus" text, "region" text);
\copy eicu_landmark.hospital FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_metadata_stage/hospital.csv' WITH(FORMAT csv,HEADER true,NULL '')
ALTER TABLE eicu_landmark.hospital ADD PRIMARY KEY(hospitalid);
INSERT INTO eicu_landmark._metadata_import VALUES('hospital','b9ea23764485a11e20323d384bc630bc92ad58e037e7844cf5b3643a6fec58b4',208);
\endif
DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.hospital)<>208 THEN RAISE EXCEPTION 'eICU metadata row-count mismatch'; END IF; END $$;
CREATE INDEX IF NOT EXISTS patient_person_hospital_idx ON eicu_landmark.patient(uniquepid,patienthealthsystemstayid);
-- Begin MIMIC definitions
-- Preserve the audited chronological primary rule INCLUDING the six-case exclusion.
CREATE OR REPLACE VIEW landmark_mimic48.sensitivity_primary_cohort_chronological AS
SELECT * FROM (
 SELECT e.*,row_number() OVER(PARTITION BY subject_id,landmark_hours
 ORDER BY landmark_time,stay_id) AS eligible_stay_number
 FROM landmark_mimic48.landmark_eligibility e
 WHERE eligible_still_in_icu IS TRUE AND EXISTS(
  SELECT 1 FROM landmark_mimic48.admissions a
  WHERE a.subject_id=e.subject_id AND a.hadm_id=e.hadm_id
   AND (a.deathtime<a.admittime) IS NOT TRUE
 )
) ranked WHERE eligible_stay_number=1;

-- Hash depends ONLY on a fixed seed, dataset and identifiers, never outcomes.
-- A patient can move to the next-priority eligible hospital at a later landmark.
CREATE OR REPLACE VIEW landmark_mimic48.primary_landmark_cohort AS
SELECT * FROM (
 SELECT e.*,row_number() OVER(PARTITION BY subject_id,landmark_hours ORDER BY
  sha256(convert_to(concat_ws('|','landmark_transportability_hospital_selection_v1',
       'mimic',subject_id::text,hadm_id::text),'UTF8')),
  hadm_id,landmark_time,stay_id) AS eligible_stay_number
 FROM landmark_mimic48.landmark_eligibility e
 WHERE eligible_still_in_icu IS TRUE AND EXISTS(
  SELECT 1 FROM landmark_mimic48.admissions a
  WHERE a.subject_id=e.subject_id AND a.hadm_id=e.hadm_id
   AND (a.deathtime<a.admittime) IS NOT TRUE
 )
) ranked WHERE eligible_stay_number=1;
-- End MIMIC definitions

CREATE OR REPLACE VIEW eicu_landmark.landmark_eligibility AS
SELECT p.patientunitstayid,p.patienthealthsystemstayid,p.uniquepid,p.hospitalid,
 l.hours AS landmark_hours,l.hours*60 AS landmark_offset_minutes,
 CASE WHEN trim(p.age)='> 89' THEN 91
      WHEN trim(p.age)~'^[0-9]+$' THEN trim(p.age)::integer END AS age_for_screening,
 (p.hospitaldischargestatus='Expired')::integer AS hospital_mortality,
 (CASE WHEN trim(p.age)='> 89' THEN true
       WHEN trim(p.age)~'^[0-9]+$' THEN trim(p.age)::integer>=18 ELSE false END)
 AND p.unitdischargeoffset>l.hours*60
 AND p.hospitaldischargeoffset>l.hours*60
 AND p.hospitaladmitoffset IS NOT NULL
 AND p.unitdischargestatus IN('Alive','Expired')
 AND p.hospitaldischargestatus IN('Alive','Expired')
 AND p.unittype IN('Med-Surg ICU','CTICU','SICU','CCU-CTICU','MICU','Neuro ICU','Cardiac ICU','CSICU')
 AS eligible_still_in_icu,
 p.hospitaladmitoffset,p.unitvisitnumber
FROM eicu_landmark.patient p
CROSS JOIN(VALUES(12),(24),(36),(48)) l(hours);

-- Larger hospitaladmitoffset means earlier ICU entry WITHIN a hospitalization.
-- Ties use identifiers only to make equal-time ordering deterministic.
CREATE OR REPLACE VIEW eicu_landmark.primary_landmark_cohort AS
SELECT * FROM (
 SELECT e.*,row_number() OVER(PARTITION BY uniquepid,landmark_hours ORDER BY
  sha256(convert_to(concat_ws('|','landmark_transportability_hospital_selection_v1',
       'eicu',uniquepid,patienthealthsystemstayid::text),'UTF8')),
  patienthealthsystemstayid,hospitaladmitoffset DESC,patientunitstayid)
  AS eligible_stay_number
 FROM eicu_landmark.landmark_eligibility e WHERE eligible_still_in_icu IS TRUE
) ranked WHERE eligible_stay_number=1;

DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM landmark_mimic48.primary_landmark_cohort
  GROUP BY subject_id,landmark_hours HAVING count(*)>1)
 OR EXISTS(SELECT 1 FROM eicu_landmark.primary_landmark_cohort
  GROUP BY uniquepid,landmark_hours HAVING count(*)>1)
 THEN RAISE EXCEPTION 'Duplicate patient contribution'; END IF;
 IF EXISTS(SELECT 1 FROM landmark_mimic48.primary_landmark_cohort c
  JOIN landmark_mimic48.admissions a USING(subject_id,hadm_id)
  WHERE a.deathtime<a.admittime)
 THEN RAISE EXCEPTION 'Invalid death-before-admission MIMIC stay'; END IF;
END $$;

COMMIT;
ANALYZE eicu_landmark.patient;
ANALYZE eicu_landmark.hospital;
-- Result 1: post-amendment cohort sizes/outcomes; these supersede primary v2.
SELECT 'MIMIC' AS database_name,landmark_hours,count(*) AS patients,
 count(DISTINCT subject_id) AS distinct_patients,sum(hospital_mortality) AS hospital_deaths,
 round(100.0*sum(hospital_mortality)/NULLIF(count(*),0),2) AS mortality_percent
FROM landmark_mimic48.primary_landmark_cohort GROUP BY landmark_hours
UNION ALL
SELECT 'eICU',landmark_hours,count(*),count(DISTINCT uniquepid),sum(hospital_mortality),
 round(100.0*sum(hospital_mortality)/NULLIF(count(*),0),2)
FROM eicu_landmark.primary_landmark_cohort GROUP BY landmark_hours
ORDER BY database_name,landmark_hours;

-- Result 2: actual impact of changing MIMIC selection, not patient exclusions.
SELECT c.landmark_hours,count(*) AS patients,
 count(*) FILTER(WHERE c.stay_id<>o.stay_id) AS selected_stay_changed,
 count(*) FILTER(WHERE c.hadm_id<>o.hadm_id) AS selected_hospitalization_changed,
 sum(c.hospital_mortality) AS priority_rule_deaths,
 sum(o.hospital_mortality) AS chronological_rule_deaths,
 count(*) FILTER(WHERE c.hospital_mortality<>o.hospital_mortality) AS outcome_label_changed_with_selected_stay
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.sensitivity_primary_cohort_chronological o USING(subject_id,landmark_hours)
GROUP BY c.landmark_hours ORDER BY c.landmark_hours;

-- Result 3: identical hash implementation can be checked against local Python.
SELECT encode(sha256(convert_to('landmark_transportability_hospital_selection_v1|eicu|example_patient|123','UTF8')),'hex') AS selection_hash_test;

