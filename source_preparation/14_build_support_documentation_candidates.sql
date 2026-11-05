\set ON_ERROR_STOP on

BEGIN;

SET LOCAL client_encoding='UTF8';

DO $$ BEGIN IF pg_database_size(current_database())>90000000000::bigint THEN RAISE EXCEPTION 'Database already exceeds 90 GB working guard'; END IF; END $$;

CREATE TEMP TABLE support_mimic_stays ON COMMIT DROP AS
SELECT DISTINCT s.stay_id,s.intime FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays s USING(stay_id);
CREATE INDEX ON support_mimic_stays(stay_id);
CREATE TABLE landmark_mimic48.support_documentation_events_candidate_v1 AS
WITH events AS (
SELECT x.stay_id AS stay_key,GREATEST(x.starttime,s.intime) AS event_time,
GREATEST(x.starttime,x.storetime,s.intime) AS available_time,s.intime,
'vasopressor'::text AS domain,'inputevents'::text AS source,x.itemid::text AS source_label
FROM landmark_mimic48.inputevents x JOIN support_mimic_stays s USING(stay_id) JOIN landmark_mimic48.d_items d USING(itemid)
WHERE d.label ~* '^(norepinephrine|epinephrine|vasopressin|dopamine|phenylephrine)(\M|\.)'
AND x.rate>0 AND x.amount>0 AND x.storetime IS NOT NULL
AND x.rate::text NOT IN('NaN','Infinity','-Infinity') AND x.amount::text NOT IN('NaN','Infinity','-Infinity')
AND COALESCE(x.statusdescription,'') NOT IN('Rewritten','Bolus','Cancelled','Canceled')
AND x.endtime>x.starttime AND x.endtime>s.intime AND x.starttime<=s.intime+interval '48 hours'
UNION ALL
SELECT x.stay_id,GREATEST(x.starttime,s.intime),GREATEST(x.starttime,x.storetime,s.intime),s.intime,
CASE WHEN x.itemid=225792 THEN 'invasive_ventilation' ELSE 'rrt' END,'procedureevents',x.itemid::text
FROM landmark_mimic48.procedureevents x JOIN support_mimic_stays s USING(stay_id)
WHERE x.itemid IN(225792,225441,225802,225803,225805,225809,225955)
AND x.storetime IS NOT NULL AND COALESCE(x.statusdescription,'') NOT IN('Rewritten','Cancelled','Canceled')
AND x.endtime>x.starttime AND x.endtime>s.intime AND x.starttime<=s.intime+interval '48 hours'
AND CASE WHEN length(btrim(x.value))<=32 AND btrim(x.value) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' THEN x.value::double precision>0 ELSE false END
UNION ALL
SELECT x.stay_id,x.charttime,GREATEST(x.charttime,x.storetime),s.intime,
CASE WHEN x.itemid IN(224144,224153,224154) THEN 'rrt' ELSE 'invasive_ventilation' END,'chartevents',x.itemid::text
FROM landmark_mimic48.chartevents x JOIN support_mimic_stays s USING(stay_id)
WHERE x.charttime BETWEEN s.intime AND s.intime+interval '48 hours' AND x.storetime IS NOT NULL
AND ((x.itemid IN(224144,224153,224154) AND x.valuenum>0 AND x.valuenum::text NOT IN('NaN','Infinity','-Infinity'))
OR (x.itemid=223849 AND x.value IN('CMV','CMV/ASSIST','CMV/ASSIST/AutoFlow','CMV/AutoFlow','SIMV','SIMV/AutoFlow','SIMV/PRES','SIMV/PSV','SIMV/PSV/AutoFlow','SIMV/VOL','VOL/AC','PCV+','PCV+/PSV','PCV+Assist','PRES/AC','PRVC/AC','PRVC/SIMV','APRV'))
OR (x.itemid=229314 AND x.value IN('(S) CMV','APV (cmv)','P-CMV','SIMV','APV (simv)','P-SIMV','VS','ASV','APRV')))
)
SELECT stay_key,extract(epoch FROM(event_time-intime))/60.0 AS event_minutes,
extract(epoch FROM(available_time-intime))/60.0 AS available_minutes,domain,source,source_label FROM events;


CREATE TABLE eicu_landmark.support_documentation_events_candidate_v1 AS
WITH rates AS(
SELECT *,CASE WHEN length(btrim(drugrate))<=32 AND btrim(drugrate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' THEN drugrate::double precision END AS dose,
CASE WHEN length(btrim(infusionrate))<=32 AND btrim(infusionrate) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' THEN infusionrate::double precision END AS volume_rate
FROM eicu_landmark.extension_infusiondrug_source_v1
)
SELECT patientunitstayid AS stay_key,infusionoffset AS event_minutes,infusionoffset AS available_minutes,
'vasopressor'::text AS domain,'infusionDrug'::text AS source,drugname AS source_label FROM rates
WHERE drugname ~* '(norepinephrine|levophed|epinephrine|adrenalin|phenylephrine|neosynephrine|vasopressin|dopamine)'
AND drugname !~* 'dobutamine'
AND ((dose>0 AND drugname ~* '(ml/hr|mcg/min|mcg/kg/min|mg/kg/min|units/min|units/hr)') OR volume_rate>0)
AND NOT (COALESCE(dose>0,false) AND COALESCE(volume_rate=0,false))
AND NOT (COALESCE(volume_rate>0,false) AND COALESCE(dose=0,false))
UNION ALL
SELECT patientunitstayid,treatmentoffset,treatmentoffset,
CASE WHEN treatmentstring IN('pulmonary|ventilation and oxygenation|mechanical ventilation|assist controlled','pulmonary|ventilation and oxygenation|mechanical ventilation|pressure controlled','pulmonary|ventilation and oxygenation|mechanical ventilation|synchronized intermittent','pulmonary|ventilation and oxygenation|mechanical ventilation|volume assured','pulmonary|ventilation and oxygenation|mechanical ventilation|volume controlled','surgery|pulmonary therapies|mechanical ventilation|assist controlled','surgery|pulmonary therapies|mechanical ventilation|pressure controlled','surgery|pulmonary therapies|mechanical ventilation|synchronized intermittent','surgery|pulmonary therapies|mechanical ventilation|volume controlled','toxicology|drug overdose|mechanical ventilation|assist controlled','toxicology|drug overdose|mechanical ventilation|pressure controlled','toxicology|drug overdose|mechanical ventilation|synchronized intermittent','toxicology|drug overdose|mechanical ventilation|volume controlled') THEN 'invasive_ventilation'
WHEN treatmentstring IN('renal|dialysis|C A V H D','renal|dialysis|C V V H','renal|dialysis|C V V H D','renal|dialysis|SLED','renal|dialysis|hemodialysis','renal|dialysis|hemodialysis|emergent','renal|dialysis|hemodialysis|for acute renal failure','renal|dialysis|hemodialysis|for chronic renal failure','renal|dialysis|peritoneal dialysis','renal|dialysis|peritoneal dialysis|emergent','renal|dialysis|peritoneal dialysis|for acute renal failure','renal|dialysis|peritoneal dialysis|for chronic renal failure','renal|dialysis|peritoneal dialysis|with cannula placement','renal|dialysis|ultrafiltration (fluid removal only)','renal|dialysis|ultrafiltration (fluid removal only)|emergent','renal|dialysis|ultrafiltration (fluid removal only)|for acute renal failure','renal|dialysis|ultrafiltration (fluid removal only)|for chronic renal failure') THEN 'rrt' ELSE 'ambiguous_ventilation' END,'treatment',treatmentstring
FROM eicu_landmark.extension_treatment_source_v1
WHERE treatmentstring IN('pulmonary|ventilation and oxygenation|mechanical ventilation','pulmonary|ventilation and oxygenation|mechanical ventilation|assist controlled','pulmonary|ventilation and oxygenation|mechanical ventilation|permissive hypercapnea','pulmonary|ventilation and oxygenation|mechanical ventilation|pressure controlled','pulmonary|ventilation and oxygenation|mechanical ventilation|pressure support','pulmonary|ventilation and oxygenation|mechanical ventilation|synchronized intermittent','pulmonary|ventilation and oxygenation|mechanical ventilation|tidal volume 6-10 ml/kg','pulmonary|ventilation and oxygenation|mechanical ventilation|tidal volume < 6 ml/kg','pulmonary|ventilation and oxygenation|mechanical ventilation|tidal volume > 10 ml/kg','pulmonary|ventilation and oxygenation|mechanical ventilation|volume assured','pulmonary|ventilation and oxygenation|mechanical ventilation|volume controlled','renal|dialysis|C A V H D','renal|dialysis|C V V H','renal|dialysis|C V V H D','renal|dialysis|SLED','renal|dialysis|hemodialysis','renal|dialysis|hemodialysis|emergent','renal|dialysis|hemodialysis|for acute renal failure','renal|dialysis|hemodialysis|for chronic renal failure','renal|dialysis|peritoneal dialysis','renal|dialysis|peritoneal dialysis|emergent','renal|dialysis|peritoneal dialysis|for acute renal failure','renal|dialysis|peritoneal dialysis|for chronic renal failure','renal|dialysis|peritoneal dialysis|with cannula placement','renal|dialysis|ultrafiltration (fluid removal only)','renal|dialysis|ultrafiltration (fluid removal only)|emergent','renal|dialysis|ultrafiltration (fluid removal only)|for acute renal failure','renal|dialysis|ultrafiltration (fluid removal only)|for chronic renal failure','surgery|pulmonary therapies|mechanical ventilation','surgery|pulmonary therapies|mechanical ventilation|assist controlled','surgery|pulmonary therapies|mechanical ventilation|permissive hypercapnea','surgery|pulmonary therapies|mechanical ventilation|pressure controlled','surgery|pulmonary therapies|mechanical ventilation|pressure support','surgery|pulmonary therapies|mechanical ventilation|synchronized intermittent','surgery|pulmonary therapies|mechanical ventilation|tidal volume 6-10 ml/kg','surgery|pulmonary therapies|mechanical ventilation|tidal volume < 6 ml/kg','surgery|pulmonary therapies|mechanical ventilation|tidal volume > 10 ml/kg','surgery|pulmonary therapies|mechanical ventilation|volume controlled','toxicology|drug overdose|mechanical ventilation','toxicology|drug overdose|mechanical ventilation|assist controlled','toxicology|drug overdose|mechanical ventilation|permissive hypercapnea','toxicology|drug overdose|mechanical ventilation|pressure controlled','toxicology|drug overdose|mechanical ventilation|pressure support','toxicology|drug overdose|mechanical ventilation|synchronized intermittent','toxicology|drug overdose|mechanical ventilation|tidal volume 6-10 ml/kg','toxicology|drug overdose|mechanical ventilation|volume controlled')
UNION ALL
SELECT patientunitstayid,respchartoffset,GREATEST(respchartoffset,respchartentryoffset),'invasive_ventilation','respiratoryCharting',respchartvaluelabel||'='||respchartvalue
FROM eicu_landmark.extension_respiratorycharting_source_v1
WHERE respchartentryoffset IS NOT NULL
AND ((respchartvaluelabel='Mechanical Ventilator Mode' AND respchartvalue IN('AC/CMV','SIMV','SIMV+'))
OR (respchartvaluelabel='Ventilator Support Mode' AND respchartvalue IN('CMV','SIMV','APV')));


CREATE INDEX ON landmark_mimic48.support_documentation_events_candidate_v1(stay_key,available_minutes,event_minutes);

CREATE TABLE landmark_mimic48.support_documentation_features_candidate_v1 AS SELECT c.*,EXISTS(SELECT 1 FROM landmark_mimic48.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.stay_id AND x.domain='vasopressor' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS vasopressor_documented,EXISTS(SELECT 1 FROM landmark_mimic48.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.stay_id AND x.domain='invasive_ventilation' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS invasive_ventilation_documented,EXISTS(SELECT 1 FROM landmark_mimic48.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.stay_id AND x.domain='rrt' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS rrt_documented,EXISTS(SELECT 1 FROM landmark_mimic48.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.stay_id AND x.domain='ambiguous_ventilation' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS ambiguous_ventilation_documented FROM landmark_mimic48.primary_landmark_cohort c;

ALTER TABLE landmark_mimic48.support_documentation_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,subject_id);

DO $$ BEGIN IF EXISTS(SELECT 1 FROM landmark_mimic48.primary_landmark_cohort c FULL JOIN landmark_mimic48.support_documentation_features_candidate_v1 f USING(landmark_hours,subject_id)
WHERE c.subject_id IS NULL OR f.subject_id IS NULL OR c.stay_id IS DISTINCT FROM f.stay_id OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality)
THEN RAISE EXCEPTION 'Support candidate cohort/outcome mismatch'; END IF; END $$;

COMMENT ON TABLE landmark_mimic48.support_documentation_features_candidate_v1 IS 'Candidate pre-landmark positive documentation flags; 0 means no qualifying documentation, never confirmed absence of treatment; not active-at-landmark state or frozen model input';

CREATE INDEX ON eicu_landmark.support_documentation_events_candidate_v1(stay_key,available_minutes,event_minutes);

CREATE TABLE eicu_landmark.support_documentation_features_candidate_v1 AS SELECT c.*,EXISTS(SELECT 1 FROM eicu_landmark.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.patientunitstayid AND x.domain='vasopressor' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS vasopressor_documented,EXISTS(SELECT 1 FROM eicu_landmark.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.patientunitstayid AND x.domain='invasive_ventilation' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS invasive_ventilation_documented,EXISTS(SELECT 1 FROM eicu_landmark.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.patientunitstayid AND x.domain='rrt' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS rrt_documented,EXISTS(SELECT 1 FROM eicu_landmark.support_documentation_events_candidate_v1 x WHERE x.stay_key=c.patientunitstayid AND x.domain='ambiguous_ventilation' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS ambiguous_ventilation_documented FROM eicu_landmark.primary_landmark_cohort c;

ALTER TABLE eicu_landmark.support_documentation_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,uniquepid);

DO $$ BEGIN IF EXISTS(SELECT 1 FROM eicu_landmark.primary_landmark_cohort c FULL JOIN eicu_landmark.support_documentation_features_candidate_v1 f USING(landmark_hours,uniquepid)
WHERE c.uniquepid IS NULL OR f.uniquepid IS NULL OR c.patientunitstayid IS DISTINCT FROM f.patientunitstayid OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality)
THEN RAISE EXCEPTION 'Support candidate cohort/outcome mismatch'; END IF; END $$;

COMMENT ON TABLE eicu_landmark.support_documentation_features_candidate_v1 IS 'Candidate pre-landmark positive documentation flags; 0 means no qualifying documentation, never confirmed absence of treatment; not active-at-landmark state or frozen model input';

COMMIT;

ANALYZE landmark_mimic48.support_documentation_events_candidate_v1;

ANALYZE landmark_mimic48.support_documentation_features_candidate_v1;

ANALYZE eicu_landmark.support_documentation_events_candidate_v1;

ANALYZE eicu_landmark.support_documentation_features_candidate_v1;

SELECT 'MIMIC' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,sum(vasopressor_documented) AS vasopressor_documented,sum(invasive_ventilation_documented) AS strict_ventilation_documented,sum(rrt_documented) AS rrt_documented,sum(ambiguous_ventilation_documented) AS ambiguous_ventilation_documented FROM landmark_mimic48.support_documentation_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT 'eICU' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,sum(vasopressor_documented) AS vasopressor_documented,sum(invasive_ventilation_documented) AS strict_ventilation_documented,sum(rrt_documented) AS rrt_documented,sum(ambiguous_ventilation_documented) AS ambiguous_ventilation_documented FROM eicu_landmark.support_documentation_features_candidate_v1 GROUP BY landmark_hours ORDER BY dataset,landmark_hours;

SELECT 'MIMIC' AS dataset,domain,source,count(*) AS positive_documentation_rows FROM landmark_mimic48.support_documentation_events_candidate_v1 GROUP BY domain,source
UNION ALL
SELECT 'eICU' AS dataset,domain,source,count(*) AS positive_documentation_rows FROM eicu_landmark.support_documentation_events_candidate_v1 GROUP BY domain,source ORDER BY dataset,domain,source;
