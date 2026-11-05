\set ON_ERROR_STOP on
-- Remaining audits only; no clinical source imports or persistent changes.
BEGIN;
CREATE TEMP TABLE extension_selected_mimic_stays ON COMMIT DROP AS
SELECT DISTINCT s.subject_id,s.hadm_id,s.stay_id,s.intime
FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id);
CREATE INDEX ON extension_selected_mimic_stays(stay_id);
CREATE TEMP TABLE extension_mimic_chart ON COMMIT DROP AS
SELECT x.stay_id,x.itemid,x.charttime,x.storetime,x.value,x.valuenum
FROM landmark_mimic48.chartevents x JOIN extension_selected_mimic_stays s USING(stay_id)
WHERE x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'
AND x.itemid IN(224144,224153,224154);
CREATE INDEX ON extension_mimic_chart(stay_id,charttime);

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
