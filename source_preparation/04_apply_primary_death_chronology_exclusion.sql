-- Run once in pgAdmin Query Tool connected to landmark_research.
-- Updates the primary VIEW only; no source or imported data rows are deleted.
-- Preserves the original first-eligible definition for sensitivity analysis.
-- Confirmed researcher decision on 13 October 2026:
-- death before hospital admission excluded in primary, retained for sensitivity.
BEGIN;

-- Guard against applying the change to an unexpected schema/view definition.
DO $$ BEGIN
 IF to_regclass('landmark_mimic48.primary_landmark_cohort') IS NULL THEN
  RAISE EXCEPTION 'Original primary cohort view is missing';
 END IF;
END $$;

-- Derive the original definition independently; rerunning this script does
-- not overwrite sensitivity cohorts with the newly excluded primary cohort.
CREATE OR REPLACE VIEW landmark_mimic48.sensitivity_primary_cohort_original_timing AS
SELECT * FROM (
 SELECT e.*,row_number() OVER (
  PARTITION BY subject_id,landmark_hours ORDER BY landmark_time,stay_id
 ) AS eligible_stay_number
 FROM landmark_mimic48.landmark_eligibility e
 WHERE eligible_still_in_icu IS TRUE
) ranked WHERE eligible_stay_number=1;

-- Require no recorded death before hospital admission, BEFORE ranking.
-- Use a semijoin so existing output columns and types are preserved.
CREATE OR REPLACE VIEW landmark_mimic48.primary_landmark_cohort AS
SELECT * FROM (
 SELECT e.*,row_number() OVER (
  PARTITION BY subject_id,landmark_hours ORDER BY landmark_time,stay_id
 ) AS eligible_stay_number
 FROM landmark_mimic48.landmark_eligibility e
 WHERE eligible_still_in_icu IS TRUE
  AND EXISTS (
   SELECT 1 FROM landmark_mimic48.admissions a
   WHERE a.subject_id=e.subject_id AND a.hadm_id=e.hadm_id
    AND (a.deathtime<a.admittime) IS NOT TRUE
  )
) ranked WHERE eligible_stay_number=1;

-- Validate the rule in the replacement primary view before committing.
DO $$ BEGIN
 IF EXISTS (
  SELECT 1 FROM landmark_mimic48.primary_landmark_cohort c
  JOIN landmark_mimic48.admissions a USING(subject_id,hadm_id)
  WHERE a.deathtime<a.admittime
 ) THEN RAISE EXCEPTION 'Death-before-admission stay remains in primary cohort'; END IF;
 IF EXISTS (
  SELECT 1 FROM landmark_mimic48.primary_landmark_cohort
  GROUP BY landmark_hours,subject_id HAVING count(*)>1
 ) THEN RAISE EXCEPTION 'Duplicate patient in primary cohort'; END IF;
END $$;

COMMIT;

-- Result 1: original sensitivity and revised primary counts side by side.
WITH original AS (
 SELECT landmark_hours,count(*) AS original_patients,sum(hospital_mortality) AS original_deaths
 FROM landmark_mimic48.sensitivity_primary_cohort_original_timing
 GROUP BY landmark_hours
), revised AS (
 SELECT landmark_hours,count(*) AS revised_patients,sum(hospital_mortality) AS revised_deaths
 FROM landmark_mimic48.primary_landmark_cohort GROUP BY landmark_hours
)
SELECT o.landmark_hours,o.original_patients,r.revised_patients,
 o.original_patients-r.revised_patients AS patients_no_longer_represented,
 o.original_deaths,r.revised_deaths,
 round(100.0*r.revised_deaths/NULLIF(r.revised_patients,0),2) AS revised_mortality_percent
FROM original o JOIN revised r USING(landmark_hours) ORDER BY o.landmark_hours;

-- Result 2: quantify replacement stays instead of assuming simple subtraction.
SELECT o.landmark_hours,
 count(*) FILTER(WHERE r.subject_id IS NULL) AS patients_removed,
 count(*) FILTER(WHERE r.stay_id<>o.stay_id) AS patients_with_replacement_stay,
 count(*) FILTER(WHERE r.stay_id=o.stay_id) AS patients_with_same_stay
FROM landmark_mimic48.sensitivity_primary_cohort_original_timing o
LEFT JOIN landmark_mimic48.primary_landmark_cohort r
 USING(landmark_hours,subject_id)
GROUP BY o.landmark_hours ORDER BY o.landmark_hours;

-- Result 3: final rule checks; flagged-primary counts must be zero.
SELECT c.landmark_hours,count(*) AS primary_patients,
 count(DISTINCT c.subject_id) AS distinct_patients,
 count(*) FILTER(WHERE a.deathtime<a.admittime) AS death_before_admission_in_primary,
 count(*) FILTER(WHERE c.eligible_still_in_icu IS NOT TRUE) AS not_eligible,
 count(*) FILTER(WHERE c.hospital_mortality=1 AND
                 (a.deathtime IS NULL OR a.deathtime<=c.landmark_time)) AS death_not_confirmed_after_landmark
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.admissions a USING(subject_id,hadm_id)
GROUP BY c.landmark_hours ORDER BY c.landmark_hours;
