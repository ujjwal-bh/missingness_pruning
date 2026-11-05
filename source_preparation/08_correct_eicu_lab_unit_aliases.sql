\set ON_ERROR_STOP on
BEGIN;
SET LOCAL client_encoding='UTF8';
-- Preserve v1 and all raw source tables. Fail if v2 already exists.
CREATE TABLE eicu_landmark.core_features_candidate_v2 AS
SELECT c.uniquepid,c.patienthealthsystemstayid,c.patientunitstayid,c.hospitalid,
c.landmark_hours,c.landmark_offset_minutes,c.hospital_mortality,c.age_capped_90,c.female,
v0.value AS creatinine,
v1.value AS bun,
v2.value AS sodium,
v3.value AS potassium,
v4.value AS chloride,
v5.value AS bicarbonate,
v6.value AS glucose,
v7.value AS hemoglobin,
v8.value AS hematocrit,
v9.value AS wbc,
v10.value AS platelets,
v11.value AS calcium_total,
v12.value AS magnesium,
v13.value AS phosphate,
v14.value AS albumin,
v15.value AS bilirubin_total,
v16.value AS lactate,
c.heart_rate,
c.respiratory_rate,
c.spo2,
c.temperature,
c.systolic_bp,
c.diastolic_bp,
c.mean_bp
FROM eicu_landmark.core_features_candidate_v1 c
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='creatinine'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=150
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v0 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='BUN'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=300
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v1 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='sodium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=200
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v2 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='potassium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=30
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v3 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='chloride'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v4 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='bicarbonate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('meq/l','mmol/l','mmole/l'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v5 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='glucose'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v6 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='Hgb'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('g/dl','gm/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('g/dl','gm/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v7 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='Hct'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('%','%pcv')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('%','%pcv'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=100
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v8 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='WBC x 1000'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('*10^3/ul','/nl','10(3)/mcl','10(3)mcl','10*3/ul','10*9/l','1000/cmm','103/ul','10^3/ul','10^9/l','10e3/mcl','10e3/ul','10x3/ul','bil/l','k/cmm','k/cumm','k/mcl','k/mm3','k/mmcu','k/ul','th/cmm','th/cumm','th/mm3','th/ul','thd/ul','thou/cmm','thou/cumm','thou/mm3','thou/ul','thous/ul','ths/ul','x(10)3/ul','x10(3)/mcl','x103/ul','x10^3/ul','x10^9/l','x10e3/ul')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('*10^3/ul','/nl','10(3)/mcl','10(3)mcl','10*3/ul','10*9/l','1000/cmm','103/ul','10^3/ul','10^9/l','10e3/mcl','10e3/ul','10x3/ul','bil/l','k/cmm','k/cumm','k/mcl','k/mm3','k/mmcu','k/ul','th/cmm','th/cumm','th/mm3','th/ul','thd/ul','thou/cmm','thou/cumm','thou/mm3','thou/ul','thous/ul','ths/ul','x(10)3/ul','x10(3)/mcl','x103/ul','x10^3/ul','x10^9/l','x10e3/ul'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>=0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v9 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='platelets x 1000'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('*10^3/ul','/nl','10(3)/mcl','10(3)mcl','10*3/ul','10*9/l','1000/cmm','103/ul','10^3/ul','10^9/l','10e3/mcl','10e3/ul','10x3/ul','bil/l','k/cmm','k/cumm','k/mcl','k/mm3','k/mmcu','k/ul','th/cmm','th/cumm','th/mm3','th/ul','thd/ul','thou/cmm','thou/cumm','thou/mm3','thou/ul','thous/ul','ths/ul','x(10)3/ul','x10(3)/mcl','x103/ul','x10^3/ul','x10^9/l','x10e3/ul')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('*10^3/ul','/nl','10(3)/mcl','10(3)mcl','10*3/ul','10*9/l','1000/cmm','103/ul','10^3/ul','10^9/l','10e3/mcl','10e3/ul','10x3/ul','bil/l','k/cmm','k/cumm','k/mcl','k/mm3','k/mmcu','k/ul','th/cmm','th/cumm','th/mm3','th/ul','thd/ul','thou/cmm','thou/cumm','thou/mm3','thou/ul','thous/ul','ths/ul','x(10)3/ul','x10(3)/mcl','x103/ul','x10^3/ul','x10^9/l','x10e3/ul'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v10 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='calcium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v11 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='magnesium'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v12 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='phosphate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v13 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='albumin'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('g/dl','gm/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('g/dl','gm/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>0 AND labresult<=10
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v14 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='total bilirubin'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mg/dl'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>=0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v15 ON true
LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='lactate'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND lower(regexp_replace(replace(COALESCE(labmeasurenamesystem,''),'µ','u'),'[[:space:]]','','g')) IN ('mmol/l','mmole/l')
AND (COALESCE(labmeasurenameinterface,'')='' OR lower(regexp_replace(replace(COALESCE(labmeasurenameinterface,''),'µ','u'),'[[:space:]]','','g')) IN ('mmol/l','mmole/l'))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult>=0 AND labresult<=10000
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) v16 ON true;
ALTER TABLE eicu_landmark.core_features_candidate_v2 ADD PRIMARY KEY(landmark_hours,uniquepid);
DO $$ BEGIN
IF EXISTS(SELECT 1 FROM eicu_landmark.core_features_candidate_v1 a FULL JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid)
WHERE a.uniquepid IS NULL OR b.uniquepid IS NULL OR a.patientunitstayid IS DISTINCT FROM b.patientunitstayid OR a.hospital_mortality IS DISTINCT FROM b.hospital_mortality)
THEN RAISE EXCEPTION 'Cohort/outcome mismatch'; END IF;
IF EXISTS(SELECT 1 FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) WHERE (a.creatinine IS NOT NULL AND b.creatinine IS NULL) OR (a.bun IS NOT NULL AND b.bun IS NULL) OR (a.sodium IS NOT NULL AND b.sodium IS NULL) OR (a.potassium IS NOT NULL AND b.potassium IS NULL) OR (a.chloride IS NOT NULL AND b.chloride IS NULL) OR (a.bicarbonate IS NOT NULL AND b.bicarbonate IS NULL) OR (a.glucose IS NOT NULL AND b.glucose IS NULL) OR (a.hemoglobin IS NOT NULL AND b.hemoglobin IS NULL) OR (a.hematocrit IS NOT NULL AND b.hematocrit IS NULL) OR (a.wbc IS NOT NULL AND b.wbc IS NULL) OR (a.platelets IS NOT NULL AND b.platelets IS NULL) OR (a.calcium_total IS NOT NULL AND b.calcium_total IS NULL) OR (a.magnesium IS NOT NULL AND b.magnesium IS NULL) OR (a.phosphate IS NOT NULL AND b.phosphate IS NULL) OR (a.albumin IS NOT NULL AND b.albumin IS NULL) OR (a.bilirubin_total IS NOT NULL AND b.bilirubin_total IS NULL) OR (a.lactate IS NOT NULL AND b.lactate IS NULL)) THEN RAISE EXCEPTION 'Previously observed lab value lost'; END IF; END $$;
COMMENT ON TABLE eicu_landmark.core_features_candidate_v2 IS 'Lab unit spelling correction 2026-10-15; v1 preserved; temperature and other domains still pending; no imputation or model fit';
COMMIT;
ANALYZE eicu_landmark.core_features_candidate_v2;
SELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM eicu_landmark.core_features_candidate_v2 GROUP BY landmark_hours ORDER BY landmark_hours;
SELECT b.landmark_hours,'creatinine' AS variable,count(*) AS patients,count(a.creatinine) AS observed_v1,count(b.creatinine) AS observed_v2,round(100.0*count(b.creatinine)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.creatinine IS DISTINCT FROM b.creatinine) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'bun' AS variable,count(*) AS patients,count(a.bun) AS observed_v1,count(b.bun) AS observed_v2,round(100.0*count(b.bun)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.bun IS DISTINCT FROM b.bun) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'sodium' AS variable,count(*) AS patients,count(a.sodium) AS observed_v1,count(b.sodium) AS observed_v2,round(100.0*count(b.sodium)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.sodium IS DISTINCT FROM b.sodium) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'potassium' AS variable,count(*) AS patients,count(a.potassium) AS observed_v1,count(b.potassium) AS observed_v2,round(100.0*count(b.potassium)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.potassium IS DISTINCT FROM b.potassium) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'chloride' AS variable,count(*) AS patients,count(a.chloride) AS observed_v1,count(b.chloride) AS observed_v2,round(100.0*count(b.chloride)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.chloride IS DISTINCT FROM b.chloride) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'bicarbonate' AS variable,count(*) AS patients,count(a.bicarbonate) AS observed_v1,count(b.bicarbonate) AS observed_v2,round(100.0*count(b.bicarbonate)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.bicarbonate IS DISTINCT FROM b.bicarbonate) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'glucose' AS variable,count(*) AS patients,count(a.glucose) AS observed_v1,count(b.glucose) AS observed_v2,round(100.0*count(b.glucose)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.glucose IS DISTINCT FROM b.glucose) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'hemoglobin' AS variable,count(*) AS patients,count(a.hemoglobin) AS observed_v1,count(b.hemoglobin) AS observed_v2,round(100.0*count(b.hemoglobin)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.hemoglobin IS DISTINCT FROM b.hemoglobin) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'hematocrit' AS variable,count(*) AS patients,count(a.hematocrit) AS observed_v1,count(b.hematocrit) AS observed_v2,round(100.0*count(b.hematocrit)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.hematocrit IS DISTINCT FROM b.hematocrit) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'wbc' AS variable,count(*) AS patients,count(a.wbc) AS observed_v1,count(b.wbc) AS observed_v2,round(100.0*count(b.wbc)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.wbc IS DISTINCT FROM b.wbc) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'platelets' AS variable,count(*) AS patients,count(a.platelets) AS observed_v1,count(b.platelets) AS observed_v2,round(100.0*count(b.platelets)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.platelets IS DISTINCT FROM b.platelets) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'calcium_total' AS variable,count(*) AS patients,count(a.calcium_total) AS observed_v1,count(b.calcium_total) AS observed_v2,round(100.0*count(b.calcium_total)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.calcium_total IS DISTINCT FROM b.calcium_total) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'magnesium' AS variable,count(*) AS patients,count(a.magnesium) AS observed_v1,count(b.magnesium) AS observed_v2,round(100.0*count(b.magnesium)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.magnesium IS DISTINCT FROM b.magnesium) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'phosphate' AS variable,count(*) AS patients,count(a.phosphate) AS observed_v1,count(b.phosphate) AS observed_v2,round(100.0*count(b.phosphate)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.phosphate IS DISTINCT FROM b.phosphate) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'albumin' AS variable,count(*) AS patients,count(a.albumin) AS observed_v1,count(b.albumin) AS observed_v2,round(100.0*count(b.albumin)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.albumin IS DISTINCT FROM b.albumin) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'bilirubin_total' AS variable,count(*) AS patients,count(a.bilirubin_total) AS observed_v1,count(b.bilirubin_total) AS observed_v2,round(100.0*count(b.bilirubin_total)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.bilirubin_total IS DISTINCT FROM b.bilirubin_total) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
UNION ALL
SELECT b.landmark_hours,'lactate' AS variable,count(*) AS patients,count(a.lactate) AS observed_v1,count(b.lactate) AS observed_v2,round(100.0*count(b.lactate)/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.lactate IS DISTINCT FROM b.lactate) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours
ORDER BY landmark_hours,variable;
