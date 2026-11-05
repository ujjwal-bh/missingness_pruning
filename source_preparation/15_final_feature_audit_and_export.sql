\set ON_ERROR_STOP on

BEGIN;

SET LOCAL client_encoding='UTF8';

CREATE TEMP TABLE model_candidate_export ON COMMIT DROP AS
SELECT 'MIMIC'::text AS dataset,c.subject_id::text AS patient_id,c.stay_id::bigint AS stay_id,'MIMIC'::text AS hospital_id,
c.landmark_hours,c.hospital_mortality,CASE WHEN get_byte(patient_hash,0)::bigint*16777216+get_byte(patient_hash,1)::bigint*65536+get_byte(patient_hash,2)::bigint*256+get_byte(patient_hash,3)<3006477107::bigint THEN 'train'
WHEN get_byte(patient_hash,0)::bigint*16777216+get_byte(patient_hash,1)::bigint*65536+get_byte(patient_hash,2)::bigint*256+get_byte(patient_hash,3)<3650722201::bigint THEN 'validation' ELSE 'test' END AS split,
c.age_capped_90,c.female,c.creatinine,c.bun,c.sodium,c.potassium,c.chloride,c.bicarbonate,c.glucose,c.hemoglobin,c.hematocrit,c.wbc,c.platelets,c.calcium_total,c.magnesium,c.phosphate,c.albumin,c.bilirubin_total,c.lactate,c.heart_rate,c.respiratory_rate,c.spo2,c.temperature,c.systolic_bp,c.diastolic_bp,c.mean_bp,g.gcs_total_components,g.gcs_total_reported,g.gcs_component_age_hours,g.gcs_latest_assessment_unassessable,d.vasopressor_documented,d.invasive_ventilation_documented,d.rrt_documented,d.ambiguous_ventilation_documented
FROM (SELECT *,sha256(convert_to('landmark_model_split_v1|mimic|'||subject_id::text,'UTF8')) AS patient_hash FROM landmark_mimic48.core_features_candidate_v1) c
JOIN landmark_mimic48.gcs_features_candidate_v1 g ON c.subject_id=g.subject_id AND c.landmark_hours=g.landmark_hours
JOIN landmark_mimic48.support_documentation_features_candidate_v1 d ON c.subject_id=d.subject_id AND c.landmark_hours=d.landmark_hours
WHERE c.stay_id=g.stay_id AND c.stay_id=d.stay_id AND c.hospital_mortality=g.hospital_mortality AND c.hospital_mortality=d.hospital_mortality
UNION ALL
SELECT 'eICU'::text AS dataset,c.uniquepid::text AS patient_id,c.patientunitstayid::bigint AS stay_id,c.hospitalid::text AS hospital_id,
c.landmark_hours,c.hospital_mortality,'external'::text AS split,
c.age_capped_90,c.female,c.creatinine,c.bun,c.sodium,c.potassium,c.chloride,c.bicarbonate,c.glucose,c.hemoglobin,c.hematocrit,c.wbc,c.platelets,c.calcium_total,c.magnesium,c.phosphate,c.albumin,c.bilirubin_total,c.lactate,c.heart_rate,c.respiratory_rate,c.spo2,c.temperature,c.systolic_bp,c.diastolic_bp,c.mean_bp,g.gcs_total_components,g.gcs_total_reported,g.gcs_component_age_hours,g.gcs_latest_assessment_unassessable,d.vasopressor_documented,d.invasive_ventilation_documented,d.rrt_documented,d.ambiguous_ventilation_documented
FROM eicu_landmark.core_features_candidate_v3 c
JOIN eicu_landmark.gcs_features_candidate_v1 g ON c.uniquepid=g.uniquepid AND c.landmark_hours=g.landmark_hours
JOIN eicu_landmark.support_documentation_features_candidate_v1 d ON c.uniquepid=d.uniquepid AND c.landmark_hours=d.landmark_hours
WHERE c.patientunitstayid=g.patientunitstayid AND c.patientunitstayid=d.patientunitstayid AND c.hospital_mortality=g.hospital_mortality AND c.hospital_mortality=d.hospital_mortality;

ALTER TABLE model_candidate_export ADD PRIMARY KEY(dataset,landmark_hours,patient_id);

DO $$ BEGIN IF EXISTS(
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
THEN RAISE EXCEPTION 'Invalid outcome'; END IF; END $$;

\echo 'F1 Cohort and patient split counts; external outcomes are not used for tuning'

SELECT dataset,landmark_hours,split,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM model_candidate_export GROUP BY dataset,landmark_hours,split ORDER BY dataset,landmark_hours,split;

\echo 'F2 Candidate distributions and missingness; descriptive source audit only'

SELECT dataset,landmark_hours,'age_capped_90'::text AS variable,count(*) AS patients,count(age_capped_90) AS observed_patients,min(age_capped_90) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY age_capped_90) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY age_capped_90) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY age_capped_90) AS p99,max(age_capped_90) AS maximum,count(*) FILTER(WHERE age_capped_90::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'female'::text AS variable,count(*) AS patients,count(female) AS observed_patients,min(female) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY female) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY female) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY female) AS p99,max(female) AS maximum,count(*) FILTER(WHERE female::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'creatinine'::text AS variable,count(*) AS patients,count(creatinine) AS observed_patients,min(creatinine) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY creatinine) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY creatinine) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY creatinine) AS p99,max(creatinine) AS maximum,count(*) FILTER(WHERE creatinine::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'bun'::text AS variable,count(*) AS patients,count(bun) AS observed_patients,min(bun) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY bun) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY bun) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY bun) AS p99,max(bun) AS maximum,count(*) FILTER(WHERE bun::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'sodium'::text AS variable,count(*) AS patients,count(sodium) AS observed_patients,min(sodium) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY sodium) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY sodium) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY sodium) AS p99,max(sodium) AS maximum,count(*) FILTER(WHERE sodium::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'potassium'::text AS variable,count(*) AS patients,count(potassium) AS observed_patients,min(potassium) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY potassium) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY potassium) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY potassium) AS p99,max(potassium) AS maximum,count(*) FILTER(WHERE potassium::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'chloride'::text AS variable,count(*) AS patients,count(chloride) AS observed_patients,min(chloride) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY chloride) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY chloride) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY chloride) AS p99,max(chloride) AS maximum,count(*) FILTER(WHERE chloride::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'bicarbonate'::text AS variable,count(*) AS patients,count(bicarbonate) AS observed_patients,min(bicarbonate) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY bicarbonate) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY bicarbonate) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY bicarbonate) AS p99,max(bicarbonate) AS maximum,count(*) FILTER(WHERE bicarbonate::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'glucose'::text AS variable,count(*) AS patients,count(glucose) AS observed_patients,min(glucose) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY glucose) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY glucose) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY glucose) AS p99,max(glucose) AS maximum,count(*) FILTER(WHERE glucose::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'hemoglobin'::text AS variable,count(*) AS patients,count(hemoglobin) AS observed_patients,min(hemoglobin) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY hemoglobin) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY hemoglobin) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY hemoglobin) AS p99,max(hemoglobin) AS maximum,count(*) FILTER(WHERE hemoglobin::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'hematocrit'::text AS variable,count(*) AS patients,count(hematocrit) AS observed_patients,min(hematocrit) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY hematocrit) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY hematocrit) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY hematocrit) AS p99,max(hematocrit) AS maximum,count(*) FILTER(WHERE hematocrit::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'wbc'::text AS variable,count(*) AS patients,count(wbc) AS observed_patients,min(wbc) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY wbc) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY wbc) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY wbc) AS p99,max(wbc) AS maximum,count(*) FILTER(WHERE wbc::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'platelets'::text AS variable,count(*) AS patients,count(platelets) AS observed_patients,min(platelets) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY platelets) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY platelets) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY platelets) AS p99,max(platelets) AS maximum,count(*) FILTER(WHERE platelets::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'calcium_total'::text AS variable,count(*) AS patients,count(calcium_total) AS observed_patients,min(calcium_total) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY calcium_total) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY calcium_total) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY calcium_total) AS p99,max(calcium_total) AS maximum,count(*) FILTER(WHERE calcium_total::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'magnesium'::text AS variable,count(*) AS patients,count(magnesium) AS observed_patients,min(magnesium) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY magnesium) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY magnesium) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY magnesium) AS p99,max(magnesium) AS maximum,count(*) FILTER(WHERE magnesium::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'phosphate'::text AS variable,count(*) AS patients,count(phosphate) AS observed_patients,min(phosphate) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY phosphate) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY phosphate) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY phosphate) AS p99,max(phosphate) AS maximum,count(*) FILTER(WHERE phosphate::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'albumin'::text AS variable,count(*) AS patients,count(albumin) AS observed_patients,min(albumin) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY albumin) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY albumin) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY albumin) AS p99,max(albumin) AS maximum,count(*) FILTER(WHERE albumin::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'bilirubin_total'::text AS variable,count(*) AS patients,count(bilirubin_total) AS observed_patients,min(bilirubin_total) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY bilirubin_total) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY bilirubin_total) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY bilirubin_total) AS p99,max(bilirubin_total) AS maximum,count(*) FILTER(WHERE bilirubin_total::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'lactate'::text AS variable,count(*) AS patients,count(lactate) AS observed_patients,min(lactate) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY lactate) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY lactate) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY lactate) AS p99,max(lactate) AS maximum,count(*) FILTER(WHERE lactate::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'heart_rate'::text AS variable,count(*) AS patients,count(heart_rate) AS observed_patients,min(heart_rate) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY heart_rate) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY heart_rate) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY heart_rate) AS p99,max(heart_rate) AS maximum,count(*) FILTER(WHERE heart_rate::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'respiratory_rate'::text AS variable,count(*) AS patients,count(respiratory_rate) AS observed_patients,min(respiratory_rate) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY respiratory_rate) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY respiratory_rate) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY respiratory_rate) AS p99,max(respiratory_rate) AS maximum,count(*) FILTER(WHERE respiratory_rate::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'spo2'::text AS variable,count(*) AS patients,count(spo2) AS observed_patients,min(spo2) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY spo2) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY spo2) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY spo2) AS p99,max(spo2) AS maximum,count(*) FILTER(WHERE spo2::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'temperature'::text AS variable,count(*) AS patients,count(temperature) AS observed_patients,min(temperature) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY temperature) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY temperature) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY temperature) AS p99,max(temperature) AS maximum,count(*) FILTER(WHERE temperature::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'systolic_bp'::text AS variable,count(*) AS patients,count(systolic_bp) AS observed_patients,min(systolic_bp) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY systolic_bp) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY systolic_bp) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY systolic_bp) AS p99,max(systolic_bp) AS maximum,count(*) FILTER(WHERE systolic_bp::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'diastolic_bp'::text AS variable,count(*) AS patients,count(diastolic_bp) AS observed_patients,min(diastolic_bp) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY diastolic_bp) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY diastolic_bp) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY diastolic_bp) AS p99,max(diastolic_bp) AS maximum,count(*) FILTER(WHERE diastolic_bp::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'mean_bp'::text AS variable,count(*) AS patients,count(mean_bp) AS observed_patients,min(mean_bp) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY mean_bp) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY mean_bp) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY mean_bp) AS p99,max(mean_bp) AS maximum,count(*) FILTER(WHERE mean_bp::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours
UNION ALL
SELECT dataset,landmark_hours,'gcs_total_components'::text AS variable,count(*) AS patients,count(gcs_total_components) AS observed_patients,min(gcs_total_components) AS minimum,percentile_cont(0.01) WITHIN GROUP(ORDER BY gcs_total_components) AS p01,percentile_cont(0.5) WITHIN GROUP(ORDER BY gcs_total_components) AS median,percentile_cont(0.99) WITHIN GROUP(ORDER BY gcs_total_components) AS p99,max(gcs_total_components) AS maximum,count(*) FILTER(WHERE gcs_total_components::text IN('NaN','Infinity','-Infinity')) AS nonfinite FROM model_candidate_export GROUP BY dataset,landmark_hours ORDER BY dataset,landmark_hours,variable;

\copy (SELECT * FROM model_candidate_export WHERE dataset='MIMIC' ORDER BY landmark_hours,patient_id) TO 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/model_preparation/mimic_candidate_features.csv' WITH(FORMAT csv,HEADER true,NULL '')

\copy (SELECT * FROM model_candidate_export WHERE dataset='eICU' ORDER BY landmark_hours,patient_id) TO 'C:/Users/Lenovo/Documents/Ujjwal/Masters application/research/model_preparation/eicu_candidate_features.csv' WITH(FORMAT csv,HEADER true,NULL '')

COMMIT;
