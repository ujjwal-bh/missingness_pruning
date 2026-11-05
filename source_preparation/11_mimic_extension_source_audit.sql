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
