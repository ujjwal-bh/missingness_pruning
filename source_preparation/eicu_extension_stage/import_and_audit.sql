\set ON_ERROR_STOP on

BEGIN;

SET LOCAL client_encoding='UTF8';

CREATE TEMP TABLE extension_expected_cohorts(landmark_hours integer,uniquepid text,patientunitstayid bigint,hospital_mortality integer) ON COMMIT DROP;

\copy extension_expected_cohorts FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_core_stage/expected_cohorts.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF EXISTS(
(SELECT * FROM extension_expected_cohorts EXCEPT SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v3)
UNION ALL
(SELECT landmark_hours,uniquepid,patientunitstayid,hospital_mortality FROM eicu_landmark.core_features_candidate_v3 EXCEPT SELECT * FROM extension_expected_cohorts)
) THEN RAISE EXCEPTION 'Extension extraction cohort differs from candidate v3'; END IF; END $$;

DO $$ BEGIN IF pg_database_size(current_database())+994298601::bigint*6::bigint>90000000000::bigint THEN RAISE EXCEPTION 'Extension conservative storage estimate exceeds 90 GB'; END IF; END $$;

CREATE TABLE eicu_landmark.extension_infusiondrug_source_v1("infusiondrugid" bigint,"patientunitstayid" bigint,"infusionoffset" bigint,"drugname" text,"drugrate" text,"infusionrate" text,"drugamount" text,"volumeoffluid" text,"patientweight" text);

\copy eicu_landmark.extension_infusiondrug_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_extension_stage/infusionDrug.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.extension_infusiondrug_source_v1)<>1784574 THEN RAISE EXCEPTION 'Extension source import count mismatch: infusionDrug'; END IF; END $$;

CREATE INDEX ON eicu_landmark.extension_infusiondrug_source_v1(patientunitstayid,infusionoffset);

COMMENT ON TABLE eicu_landmark.extension_infusiondrug_source_v1 IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';

CREATE TABLE eicu_landmark.extension_treatment_source_v1("treatmentid" bigint,"patientunitstayid" bigint,"treatmentoffset" bigint,"treatmentstring" text);

\copy eicu_landmark.extension_treatment_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_extension_stage/treatment.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.extension_treatment_source_v1)<>1633398 THEN RAISE EXCEPTION 'Extension source import count mismatch: treatment'; END IF; END $$;

CREATE INDEX ON eicu_landmark.extension_treatment_source_v1(patientunitstayid,treatmentoffset);

COMMENT ON TABLE eicu_landmark.extension_treatment_source_v1 IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';

CREATE TABLE eicu_landmark.extension_respiratorycare_source_v1("respcareid" bigint,"patientunitstayid" bigint,"respcarestatusoffset" bigint,"currenthistoryseqnum" bigint,"airwaytype" text,"ventstartoffset" bigint,"ventendoffset" bigint,"priorventstartoffset" bigint,"priorventendoffset" bigint);

\copy eicu_landmark.extension_respiratorycare_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_extension_stage/respiratoryCare.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.extension_respiratorycare_source_v1)<>256541 THEN RAISE EXCEPTION 'Extension source import count mismatch: respiratoryCare'; END IF; END $$;

CREATE INDEX ON eicu_landmark.extension_respiratorycare_source_v1(patientunitstayid,respcarestatusoffset);

COMMENT ON TABLE eicu_landmark.extension_respiratorycare_source_v1 IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';

CREATE TABLE eicu_landmark.extension_respiratorycharting_source_v1("respchartid" bigint,"patientunitstayid" bigint,"respchartoffset" bigint,"respchartentryoffset" bigint,"respcharttypecat" text,"respchartvaluelabel" text,"respchartvalue" text);

\copy eicu_landmark.extension_respiratorycharting_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_extension_stage/respiratoryCharting.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.extension_respiratorycharting_source_v1)<>5927177 THEN RAISE EXCEPTION 'Extension source import count mismatch: respiratoryCharting'; END IF; END $$;

CREATE INDEX ON eicu_landmark.extension_respiratorycharting_source_v1(patientunitstayid,respchartoffset);

COMMENT ON TABLE eicu_landmark.extension_respiratorycharting_source_v1 IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';

CREATE TABLE eicu_landmark.extension_nursecharting_source_v1("nursingchartid" bigint,"patientunitstayid" bigint,"nursingchartoffset" bigint,"nursingchartentryoffset" bigint,"nursingchartcelltypecat" text,"nursingchartcelltypevallabel" text,"nursingchartcelltypevalname" text,"nursingchartvalue" text);

\copy eicu_landmark.extension_nursecharting_source_v1 FROM 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/eicu_extension_stage/nurseCharting.csv' WITH(FORMAT csv,HEADER true,NULL '')

DO $$ BEGIN IF (SELECT count(*) FROM eicu_landmark.extension_nursecharting_source_v1)<>5716525 THEN RAISE EXCEPTION 'Extension source import count mismatch: nurseCharting'; END IF; END $$;

CREATE INDEX ON eicu_landmark.extension_nursecharting_source_v1(patientunitstayid,nursingchartoffset);

COMMENT ON TABLE eicu_landmark.extension_nursecharting_source_v1 IS 'Selected 0-48h source audit; not a finalized treatment-state feature; source rows preserved';

COMMIT;

ANALYZE eicu_landmark.extension_nursecharting_source_v1;

ANALYZE eicu_landmark.extension_infusiondrug_source_v1;

ANALYZE eicu_landmark.extension_treatment_source_v1;

ANALYZE eicu_landmark.extension_respiratorycare_source_v1;

ANALYZE eicu_landmark.extension_respiratorycharting_source_v1;

-- Aggregate mapping audits only. No patient identifiers or model inputs are output.
\echo 'E1 eICU neurological labels and most frequent values (up to 12 per label/name)'
WITH x AS (
SELECT nursingchartcelltypevallabel AS label,nursingchartcelltypevalname AS name,
nursingchartvalue AS value,count(*) AS source_rows,
count(*) FILTER(WHERE nursingchartentryoffset IS NULL) AS missing_entry_time,
count(*) FILTER(WHERE nursingchartentryoffset<nursingchartoffset) AS entry_before_event
FROM eicu_landmark.extension_nursecharting_source_v1 GROUP BY 1,2,3
), ranked AS (SELECT *,row_number() OVER(PARTITION BY label,name ORDER BY source_rows DESC,value) AS rank FROM x)
SELECT label,name,value,source_rows,missing_entry_time,entry_before_event FROM ranked WHERE rank<=12 ORDER BY label,name,rank;

\echo 'E2 eICU GCS total candidate coverage and source coverage (not final features)'
SELECT c.landmark_hours,count(*) AS patients,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_nursecharting_source_v1 n
 WHERE n.patientunitstayid=c.patientunitstayid AND n.nursingchartoffset BETWEEN 0 AND c.landmark_offset_minutes
 AND n.nursingchartentryoffset IS NOT NULL AND GREATEST(n.nursingchartoffset,n.nursingchartentryoffset)<=c.landmark_offset_minutes
 AND lower(n.nursingchartcelltypevallabel)='glasgow coma score' AND lower(n.nursingchartcelltypevalname)='gcs total'
 AND btrim(n.nursingchartvalue) IN('3','4','5','6','7','8','9','10','11','12','13','14','15'))) AS numeric_gcs_total_available,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_infusiondrug_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.infusionoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_infusion_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_treatment_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.treatmentoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_treatment_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_respiratorycare_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.respcarestatusoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_respiratory_care_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_respiratorycharting_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.respchartoffset BETWEEN 0 AND c.landmark_offset_minutes AND x.respchartentryoffset IS NOT NULL AND GREATEST(x.respchartoffset,x.respchartentryoffset)<=c.landmark_offset_minutes)) AS any_available_respiratory_chart
FROM eicu_landmark.core_features_candidate_v3 c GROUP BY c.landmark_hours ORDER BY c.landmark_hours;

\echo 'E3 eICU infusion names and rate quality for candidate vasopressors'
WITH parsed AS (
SELECT *,CASE WHEN length(btrim(drugrate))<=32 AND btrim(drugrate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' THEN drugrate::double precision END AS dose,
CASE WHEN length(btrim(infusionrate))<=32 AND btrim(infusionrate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' THEN infusionrate::double precision END AS volume_rate
FROM eicu_landmark.extension_infusiondrug_source_v1
WHERE drugname ~* '(norepinephrine|levophed|epinephrine|adrenalin|phenylephrine|neosynephrine|vasopressin|dopamine|dobutamine)'
)
SELECT drugname,count(*) AS source_rows,count(*) FILTER(WHERE dose>0) AS positive_drug_rate,
count(*) FILTER(WHERE volume_rate>0) AS positive_volume_rate,
count(*) FILTER(WHERE dose=0 OR volume_rate=0) AS at_least_one_zero_rate,
count(*) FILTER(WHERE (dose>0 AND volume_rate=0) OR (dose=0 AND volume_rate>0)) AS positive_zero_disagreement,
count(*) FILTER(WHERE dose IS NULL AND volume_rate IS NULL) AS neither_rate_numeric
FROM parsed GROUP BY drugname ORDER BY source_rows DESC,drugname;

\echo 'E4 eICU treatment labels for ventilation and renal replacement mapping'
SELECT treatmentstring,count(*) AS source_rows
FROM eicu_landmark.extension_treatment_source_v1
WHERE treatmentstring ~* '(ventila|dialys|\mC[ ]?V[ ]?V[ ]?H|\mCRRT\M|\mSLED\M|ultrafiltrat|hemofiltrat)'
GROUP BY treatmentstring ORDER BY source_rows DESC,treatmentstring;

\echo 'E5 eICU respiratory care timing and airway evidence'
SELECT airwaytype,count(*) AS source_rows,
count(*) FILTER(WHERE ventstartoffset IS NOT NULL) AS known_vent_start,
count(*) FILTER(WHERE ventendoffset IS NOT NULL) AS known_vent_end,
count(*) FILTER(WHERE ventstartoffset<0) AS vent_start_before_unit,
count(*) FILTER(WHERE ventstartoffset>respcarestatusoffset) AS start_after_entry,
count(*) FILTER(WHERE ventendoffset<ventstartoffset) AS end_before_start,
count(*) FILTER(WHERE ventendoffset>respcarestatusoffset) AS end_after_entry
FROM eicu_landmark.extension_respiratorycare_source_v1 GROUP BY airwaytype ORDER BY source_rows DESC;

\echo 'E6 eICU respiratory chart label inventory'
SELECT respchartvaluelabel,count(*) AS source_rows,
count(*) FILTER(WHERE respchartentryoffset IS NULL) AS missing_entry_time,
count(*) FILTER(WHERE respchartentryoffset<respchartoffset) AS entry_before_event
FROM eicu_landmark.extension_respiratorycharting_source_v1 GROUP BY respchartvaluelabel ORDER BY source_rows DESC,respchartvaluelabel;

\echo 'E7 eICU respiratory mode/device values (up to 15 per label)'
WITH x AS (
SELECT respchartvaluelabel,respchartvalue,count(*) AS source_rows
FROM eicu_landmark.extension_respiratorycharting_source_v1
WHERE respchartvaluelabel ~* '(mode|airway|device|ventilator type|oxygen.*delivery)'
GROUP BY 1,2
), ranked AS(SELECT *,row_number() OVER(PARTITION BY respchartvaluelabel ORDER BY source_rows DESC,respchartvalue) AS rank FROM x)
SELECT respchartvaluelabel,respchartvalue,source_rows FROM ranked WHERE rank<=15 ORDER BY respchartvaluelabel,rank;

\echo 'E8 eICU source documentation by hospital at the primary 24-hour landmark'
SELECT c.hospitalid,count(*) AS patients,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_infusiondrug_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.infusionoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_infusion_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_treatment_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.treatmentoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_treatment_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_respiratorycare_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.respcarestatusoffset BETWEEN 0 AND c.landmark_offset_minutes)) AS any_respiratory_care_source,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM eicu_landmark.extension_respiratorycharting_source_v1 x WHERE x.patientunitstayid=c.patientunitstayid AND x.respchartoffset BETWEEN 0 AND c.landmark_offset_minutes AND x.respchartentryoffset IS NOT NULL AND GREATEST(x.respchartoffset,x.respchartentryoffset)<=c.landmark_offset_minutes)) AS any_available_respiratory_chart
FROM eicu_landmark.core_features_candidate_v3 c WHERE c.landmark_hours=24 GROUP BY c.hospitalid ORDER BY c.hospitalid;


-- Temporary audit tables only; original sources and candidate features are unchanged.
BEGIN;
CREATE TEMP TABLE extension_selected_mimic_stays ON COMMIT DROP AS
SELECT DISTINCT s.subject_id,s.hadm_id,s.stay_id,s.intime
FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id);
CREATE INDEX ON extension_selected_mimic_stays(stay_id);
CREATE TEMP TABLE extension_mimic_chart ON COMMIT DROP AS
SELECT x.stay_id,x.itemid,x.charttime,x.storetime,x.value,x.valuenum
FROM landmark_mimic48.chartevents x JOIN extension_selected_mimic_stays s USING(stay_id)
WHERE x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'
AND x.itemid IN(220739,223900,223901,223848,223849,229314,226732,227290,224144,224153,224154);
CREATE INDEX ON extension_mimic_chart(stay_id,charttime);

\echo 'M1 MIMIC GCS component values and availability'
SELECT x.itemid,d.label,x.value,x.valuenum,count(*) AS source_rows,
count(*) FILTER(WHERE x.storetime IS NULL) AS missing_storetime,
count(*) FILTER(WHERE x.storetime<x.charttime) AS entry_before_event
FROM extension_mimic_chart x JOIN landmark_mimic48.d_items d USING(itemid)
WHERE x.itemid IN(220739,223900,223901)
GROUP BY x.itemid,d.label,x.value,x.valuenum ORDER BY x.itemid,source_rows DESC;

\echo 'M2 MIMIC same-time complete GCS candidate coverage; no defaults or component carry forward'
WITH grouped AS(
SELECT stay_id,charttime,max(storetime) AS latest_entry,
count(*) FILTER(WHERE storetime IS NULL) AS missing_entry,
min(valuenum) FILTER(WHERE itemid=220739) AS eye_min,max(valuenum) FILTER(WHERE itemid=220739) AS eye_max,
min(valuenum) FILTER(WHERE itemid=223900) AS verbal_min,max(valuenum) FILTER(WHERE itemid=223900) AS verbal_max,
min(valuenum) FILTER(WHERE itemid=223901) AS motor_min,max(valuenum) FILTER(WHERE itemid=223901) AS motor_max,
bool_or(itemid=223900 AND (value ILIKE '%ETT%' OR value ILIKE '%trach%')) AS verbal_unassessable
FROM extension_mimic_chart WHERE itemid IN(220739,223900,223901) GROUP BY stay_id,charttime
)
SELECT c.landmark_hours,count(*) AS patients,
count(*) FILTER(WHERE EXISTS(SELECT 1 FROM grouped g WHERE g.stay_id=c.stay_id AND g.charttime<=c.landmark_time
AND g.missing_entry=0 AND GREATEST(g.charttime,g.latest_entry)<=c.landmark_time
AND g.eye_min=g.eye_max AND g.eye_min BETWEEN 1 AND 4 AND g.eye_min=trunc(g.eye_min::numeric)
AND g.verbal_min=g.verbal_max AND g.verbal_min BETWEEN 1 AND 5 AND g.verbal_min=trunc(g.verbal_min::numeric)
AND g.motor_min=g.motor_max AND g.motor_min BETWEEN 1 AND 6 AND g.motor_min=trunc(g.motor_min::numeric)
AND NOT g.verbal_unassessable)) AS complete_assessable_gcs_available
FROM landmark_mimic48.primary_landmark_cohort c GROUP BY c.landmark_hours ORDER BY c.landmark_hours;

\echo 'M3 MIMIC ventilation and dialysis chart labels (up to 20 frequent values per item)'
WITH x AS(
SELECT itemid,value,count(*) AS source_rows FROM extension_mimic_chart
WHERE itemid IN(223848,223849,229314,226732,227290) GROUP BY itemid,value
), ranked AS(SELECT *,row_number() OVER(PARTITION BY itemid ORDER BY source_rows DESC,value) AS rank FROM x)
SELECT x.itemid,d.label,x.value,x.source_rows FROM ranked x JOIN landmark_mimic48.d_items d USING(itemid)
WHERE rank<=20 ORDER BY itemid,rank;

\echo 'M4 MIMIC vasopressor and inotrope infusion rates and statuses'
SELECT x.itemid,d.label,x.rateuom,x.statusdescription,count(*) AS source_rows,
count(*) FILTER(WHERE x.rate>0) AS positive_rate,
count(*) FILTER(WHERE x.amount>0) AS positive_amount,
count(*) FILTER(WHERE x.storetime IS NULL) AS missing_storetime,
count(*) FILTER(WHERE x.storetime<x.starttime) AS entry_before_start,
count(*) FILTER(WHERE x.endtime<x.starttime) AS end_before_start,
count(*) FILTER(WHERE x.storetime>x.endtime) AS entry_after_end
FROM landmark_mimic48.inputevents x JOIN extension_selected_mimic_stays s USING(stay_id)
JOIN landmark_mimic48.d_items d USING(itemid)
WHERE d.label ~* '^(norepinephrine|epinephrine|vasopressin|dopamine|dobutamine|phenylephrine)(\M|\.)'
AND x.starttime<=s.intime+interval '48 hours' AND (x.endtime IS NULL OR x.endtime>=s.intime)
GROUP BY x.itemid,d.label,x.rateuom,x.statusdescription ORDER BY x.itemid,source_rows DESC;

\echo 'M5 MIMIC ventilation and dialysis procedures and status'
SELECT x.itemid,d.label,x.statusdescription,x.valueuom,count(*) AS source_rows,
count(*) FILTER(WHERE CASE
WHEN length(btrim(x.value))<=32 AND btrim(x.value) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
THEN btrim(x.value)::double precision>0 ELSE false END) AS positive_value,
count(*) FILTER(WHERE x.storetime IS NULL) AS missing_storetime,
count(*) FILTER(WHERE x.storetime<x.starttime) AS entry_before_start,
count(*) FILTER(WHERE x.endtime<x.starttime) AS end_before_start,
count(*) FILTER(WHERE x.storetime>x.endtime) AS entry_after_end
FROM landmark_mimic48.procedureevents x JOIN extension_selected_mimic_stays s USING(stay_id)
JOIN landmark_mimic48.d_items d USING(itemid)
WHERE x.itemid IN(224385,225468,225477,225792,225794,227194,225441,225802,225803,225805,225809,225955,225436)
AND x.starttime<=s.intime+interval '48 hours' AND (x.endtime IS NULL OR x.endtime>=s.intime)
GROUP BY x.itemid,d.label,x.statusdescription,x.valueuom ORDER BY x.itemid,source_rows DESC;

\echo 'M6 MIMIC dialysis flow chart evidence'
SELECT x.itemid,d.label,count(*) AS source_rows,
count(*) FILTER(WHERE x.valuenum>0) AS positive_values,
count(*) FILTER(WHERE x.valuenum=0) AS zero_values,
count(*) FILTER(WHERE x.valuenum IS NULL) AS missing_numeric_value,
count(*) FILTER(WHERE x.storetime IS NULL) AS missing_storetime,
count(*) FILTER(WHERE x.storetime<x.charttime) AS entry_before_event
FROM extension_mimic_chart x JOIN landmark_mimic48.d_items d USING(itemid)
WHERE x.itemid IN(224144,224153,224154) GROUP BY x.itemid,d.label ORDER BY x.itemid;
COMMIT;

