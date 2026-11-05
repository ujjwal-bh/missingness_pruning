-- Candidate feature build: not final modeling data. Run entire file in pgAdmin.

-- May take time and temporary disk space; source records are not changed.

-- A preexisting candidate table causes an error rather than being overwritten.

-- All patients are retained regardless of predictor missingness.

BEGIN;

CREATE TEMP TABLE core_mapping(variable text,itemid bigint,domain text,low double precision,high double precision,low_op text,high_op text,unit_aliases text[]) ON COMMIT DROP;

INSERT INTO core_mapping VALUES
('creatinine',50912,'laboratory',0,150,'>','<=',ARRAY['mg/dl']::text[]),
('creatinine',52546,'laboratory',0,150,'>','<=',ARRAY['mg/dl']::text[]),
('bun',51006,'laboratory',0,300,'>','<=',ARRAY['mg/dl']::text[]),
('bun',52647,'laboratory',0,300,'>','<=',ARRAY['mg/dl']::text[]),
('sodium',50983,'laboratory',0,200,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('sodium',52623,'laboratory',0,200,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('potassium',50971,'laboratory',0,30,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('potassium',52610,'laboratory',0,30,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('chloride',50902,'laboratory',0,10000,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('chloride',52535,'laboratory',0,10000,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('bicarbonate',50882,'laboratory',0,10000,'>','<=',ARRAY['meq/l','mmol/l']::text[]),
('glucose',50931,'laboratory',0,10000,'>','<=',ARRAY['mg/dl']::text[]),
('glucose',52569,'laboratory',0,10000,'>','<=',ARRAY['mg/dl']::text[]),
('hemoglobin',51222,'laboratory',0,10000,'>','<=',ARRAY['g/dl']::text[]),
('hemoglobin',51640,'laboratory',0,10000,'>','<=',ARRAY['g/dl']::text[]),
('hematocrit',51221,'laboratory',0,100,'>','<=',ARRAY['%']::text[]),
('hematocrit',51638,'laboratory',0,100,'>','<=',ARRAY['%']::text[]),
('hematocrit',51639,'laboratory',0,100,'>','<=',ARRAY['%']::text[]),
('wbc',51301,'laboratory',0,10000,'>=','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('wbc',51755,'laboratory',0,10000,'>=','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('wbc',51756,'laboratory',0,10000,'>=','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('wbc',51300,'laboratory',0,10000,'>=','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('platelets',51265,'laboratory',0,10000,'>','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('platelets',53189,'laboratory',0,10000,'>','<=',ARRAY['k/ul','10^3/ul','10^9/l']::text[]),
('calcium_total',50893,'laboratory',0,10000,'>','<=',ARRAY['mg/dl']::text[]),
('magnesium',50960,'laboratory',0,10000,'>','<=',ARRAY['mg/dl']::text[]),
('phosphate',50970,'laboratory',0,10000,'>','<=',ARRAY['mg/dl']::text[]),
('albumin',50862,'laboratory',0,10,'>','<=',ARRAY['g/dl']::text[]),
('albumin',53085,'laboratory',0,10,'>','<=',ARRAY['g/dl']::text[]),
('bilirubin_total',50885,'laboratory',0,10000,'>=','<=',ARRAY['mg/dl']::text[]),
('bilirubin_total',53089,'laboratory',0,10000,'>=','<=',ARRAY['mg/dl']::text[]),
('lactate',50813,'laboratory',0,10000,'>=','<=',ARRAY['mmol/l']::text[]),
('lactate',52442,'laboratory',0,10000,'>=','<=',ARRAY['mmol/l']::text[]),
('lactate',53154,'laboratory',0,10000,'>=','<=',ARRAY['mmol/l']::text[]),
('heart_rate',220045,'vital',0,300,'>','<',ARRAY['bpm']::text[]),
('respiratory_rate',220210,'vital',0,70,'>','<',ARRAY['insp/min','breaths/min']::text[]),
('spo2',220277,'vital',0,100,'>','<=',ARRAY['%']::text[]),
('temperature',223761,'vital',10,50,'>','<',ARRAY['°f','â°f']::text[]),
('temperature',223762,'vital',10,50,'>','<',ARRAY['°c','â°c']::text[]),
('systolic_bp',220050,'vital',0,400,'>','<',ARRAY['mmhg']::text[]),
('systolic_bp',220179,'vital',0,400,'>','<',ARRAY['mmhg']::text[]),
('diastolic_bp',220051,'vital',0,300,'>','<',ARRAY['mmhg']::text[]),
('diastolic_bp',220180,'vital',0,300,'>','<',ARRAY['mmhg']::text[]),
('mean_bp',220052,'vital',0,300,'>','<',ARRAY['mmhg']::text[]),
('mean_bp',220181,'vital',0,300,'>','<',ARRAY['mmhg']::text[]);

CREATE TEMP TABLE selected_core_stays ON COMMIT DROP AS
SELECT DISTINCT s.subject_id,s.hadm_id,s.stay_id,s.intime
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id);
CREATE INDEX ON selected_core_stays(stay_id);
CREATE INDEX ON selected_core_stays(subject_id,intime);

CREATE TEMP TABLE core_observation_raw ON COMMIT DROP AS
SELECT s.stay_id,m.variable,x.itemid,x.charttime AS event_time,
 x.storetime,GREATEST(x.charttime,x.storetime) AS available_time,
 lower(regexp_replace(COALESCE(x.valueuom,''),'\s','','g'))=ANY(m.unit_aliases) AS unit_ok,
 CASE WHEN x.itemid=223761 THEN (x.valuenum-32)/1.8 ELSE x.valuenum END AS value,
 CASE WHEN x.itemid IN(220050,220051,220052) THEN 0 ELSE 1 END AS source_priority,
 m.low,m.high,m.low_op,m.high_op
FROM landmark_mimic48.chartevents x
JOIN selected_core_stays s USING(stay_id)
JOIN core_mapping m ON m.itemid=x.itemid AND m.domain='vital'
WHERE x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'
UNION ALL
SELECT s.stay_id,m.variable,x.itemid,x.charttime,x.storetime,
 GREATEST(x.charttime,x.storetime),
 lower(regexp_replace(COALESCE(x.valueuom,''),'\s','','g'))=ANY(m.unit_aliases),
 x.valuenum,1,m.low,m.high,m.low_op,m.high_op
FROM landmark_mimic48.labevents x
JOIN selected_core_stays s ON x.subject_id=s.subject_id
 AND (x.hadm_id IS NULL OR x.hadm_id=s.hadm_id)
 AND x.charttime BETWEEN s.intime AND s.intime+interval '48 hours'
JOIN core_mapping m ON m.itemid=x.itemid AND m.domain='laboratory';

CREATE TABLE landmark_mimic48.core_observation_qc_candidate_v1 AS
SELECT variable,count(*) AS observations,
 count(*) FILTER(WHERE NOT unit_ok) AS unknown_unit,
 count(*) FILTER(WHERE storetime IS NULL) AS unknown_availability,
 count(*) FILTER(WHERE storetime<event_time) AS entry_before_event,
 count(*) FILTER(WHERE value IS NULL OR value::text IN('NaN','Infinity','-Infinity')) AS nonnumeric_or_nonfinite,
 count(*) FILTER(WHERE value::text NOT IN('NaN','Infinity','-Infinity') AND
  ((low_op='>' AND value<=low) OR (low_op='>=' AND value<low)
   OR (high_op='<' AND value>=high) OR (high_op='<=' AND value>high))) AS outside_screening_bounds
FROM core_observation_raw GROUP BY variable;

CREATE TEMP TABLE core_observation_valid ON COMMIT DROP AS
SELECT stay_id,variable,event_time,available_time,source_priority,itemid,avg(value) AS value
FROM core_observation_raw
WHERE unit_ok AND storetime IS NOT NULL AND event_time IS NOT NULL
 AND value IS NOT NULL AND value::text NOT IN('NaN','Infinity','-Infinity')
 AND CASE WHEN low_op='>' THEN value>low ELSE value>=low END
 AND CASE WHEN high_op='<' THEN value<high ELSE value<=high END
GROUP BY stay_id,variable,event_time,available_time,source_priority,itemid;
CREATE INDEX ON core_observation_valid(stay_id,variable,event_time,available_time);

CREATE TEMP TABLE latest_core_value ON COMMIT DROP AS
SELECT DISTINCT ON(c.landmark_hours,c.stay_id,o.variable)
 c.landmark_hours,c.stay_id,o.variable,o.value,o.event_time,o.available_time
FROM landmark_mimic48.primary_landmark_cohort c
JOIN core_observation_valid o ON o.stay_id=c.stay_id
 AND o.event_time<=c.landmark_time AND o.available_time<=c.landmark_time
ORDER BY c.landmark_hours,c.stay_id,o.variable,o.event_time DESC,
 o.source_priority ASC,o.available_time DESC,o.itemid ASC;

CREATE TABLE landmark_mimic48.core_features_candidate_v1 AS
SELECT c.subject_id,c.hadm_id,c.stay_id,c.landmark_hours,c.landmark_time,c.hospital_mortality,
 LEAST(p.anchor_age+extract(year FROM s.intime)::integer-p.anchor_year,90) AS age_capped_90,
 CASE WHEN p.gender='F' THEN 1 WHEN p.gender='M' THEN 0 END AS female,
  max(v.value) FILTER(WHERE v.variable='creatinine') AS creatinine,
 max(v.value) FILTER(WHERE v.variable='bun') AS bun,
 max(v.value) FILTER(WHERE v.variable='sodium') AS sodium,
 max(v.value) FILTER(WHERE v.variable='potassium') AS potassium,
 max(v.value) FILTER(WHERE v.variable='chloride') AS chloride,
 max(v.value) FILTER(WHERE v.variable='bicarbonate') AS bicarbonate,
 max(v.value) FILTER(WHERE v.variable='glucose') AS glucose,
 max(v.value) FILTER(WHERE v.variable='hemoglobin') AS hemoglobin,
 max(v.value) FILTER(WHERE v.variable='hematocrit') AS hematocrit,
 max(v.value) FILTER(WHERE v.variable='wbc') AS wbc,
 max(v.value) FILTER(WHERE v.variable='platelets') AS platelets,
 max(v.value) FILTER(WHERE v.variable='calcium_total') AS calcium_total,
 max(v.value) FILTER(WHERE v.variable='magnesium') AS magnesium,
 max(v.value) FILTER(WHERE v.variable='phosphate') AS phosphate,
 max(v.value) FILTER(WHERE v.variable='albumin') AS albumin,
 max(v.value) FILTER(WHERE v.variable='bilirubin_total') AS bilirubin_total,
 max(v.value) FILTER(WHERE v.variable='lactate') AS lactate,
 max(v.value) FILTER(WHERE v.variable='heart_rate') AS heart_rate,
 max(v.value) FILTER(WHERE v.variable='respiratory_rate') AS respiratory_rate,
 max(v.value) FILTER(WHERE v.variable='spo2') AS spo2,
 max(v.value) FILTER(WHERE v.variable='temperature') AS temperature,
 max(v.value) FILTER(WHERE v.variable='systolic_bp') AS systolic_bp,
 max(v.value) FILTER(WHERE v.variable='diastolic_bp') AS diastolic_bp,
 max(v.value) FILTER(WHERE v.variable='mean_bp') AS mean_bp
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id)
JOIN landmark_mimic48.patients p USING(subject_id)
LEFT JOIN latest_core_value v ON v.stay_id=c.stay_id AND v.landmark_hours=c.landmark_hours
GROUP BY c.subject_id,c.hadm_id,c.stay_id,c.landmark_hours,c.landmark_time,c.hospital_mortality,p.anchor_age,p.anchor_year,p.gender,s.intime;
ALTER TABLE landmark_mimic48.core_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,subject_id);
COMMENT ON TABLE landmark_mimic48.core_features_candidate_v1 IS 'Candidate core features; rule SHA256 e67a133cd2b6e69fa5d33cf1352a17c1882e819082d8f466d7f4ad30fe7be40a; not imputed/scaled; remaining domains and external harmonization pending';

DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM landmark_mimic48.primary_landmark_cohort c
 FULL JOIN landmark_mimic48.core_features_candidate_v1 f USING(subject_id,landmark_hours)
 WHERE c.subject_id IS NULL OR f.subject_id IS NULL OR c.stay_id<>f.stay_id OR c.hospital_mortality<>f.hospital_mortality)
 THEN RAISE EXCEPTION 'Candidate feature rows do not match primary cohort'; END IF;
 IF EXISTS(SELECT 1 FROM latest_core_value v JOIN landmark_mimic48.primary_landmark_cohort c USING(stay_id,landmark_hours)
 WHERE v.event_time>c.landmark_time OR v.available_time>c.landmark_time)
 THEN RAISE EXCEPTION 'Post-landmark information in features'; END IF;
END $$;
COMMIT;
ANALYZE landmark_mimic48.core_features_candidate_v1;

-- Result 1: counts/outcomes must match amended primary cohorts.
SELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths
FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours ORDER BY landmark_hours;
-- Result 2: artifact-screening audit. Categories can overlap.
SELECT * FROM landmark_mimic48.core_observation_qc_candidate_v1 ORDER BY variable;
-- Result 3: coverage of each mapped measurement at each landmark.


SELECT landmark_hours,'creatinine' AS variable,count(*) AS patients,count(creatinine) AS observed_patients,round(100.0*count(creatinine)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bun' AS variable,count(*) AS patients,count(bun) AS observed_patients,round(100.0*count(bun)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'sodium' AS variable,count(*) AS patients,count(sodium) AS observed_patients,round(100.0*count(sodium)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'potassium' AS variable,count(*) AS patients,count(potassium) AS observed_patients,round(100.0*count(potassium)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'chloride' AS variable,count(*) AS patients,count(chloride) AS observed_patients,round(100.0*count(chloride)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bicarbonate' AS variable,count(*) AS patients,count(bicarbonate) AS observed_patients,round(100.0*count(bicarbonate)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'glucose' AS variable,count(*) AS patients,count(glucose) AS observed_patients,round(100.0*count(glucose)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'hemoglobin' AS variable,count(*) AS patients,count(hemoglobin) AS observed_patients,round(100.0*count(hemoglobin)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'hematocrit' AS variable,count(*) AS patients,count(hematocrit) AS observed_patients,round(100.0*count(hematocrit)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'wbc' AS variable,count(*) AS patients,count(wbc) AS observed_patients,round(100.0*count(wbc)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'platelets' AS variable,count(*) AS patients,count(platelets) AS observed_patients,round(100.0*count(platelets)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'calcium_total' AS variable,count(*) AS patients,count(calcium_total) AS observed_patients,round(100.0*count(calcium_total)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'magnesium' AS variable,count(*) AS patients,count(magnesium) AS observed_patients,round(100.0*count(magnesium)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'phosphate' AS variable,count(*) AS patients,count(phosphate) AS observed_patients,round(100.0*count(phosphate)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'albumin' AS variable,count(*) AS patients,count(albumin) AS observed_patients,round(100.0*count(albumin)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'bilirubin_total' AS variable,count(*) AS patients,count(bilirubin_total) AS observed_patients,round(100.0*count(bilirubin_total)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'lactate' AS variable,count(*) AS patients,count(lactate) AS observed_patients,round(100.0*count(lactate)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'heart_rate' AS variable,count(*) AS patients,count(heart_rate) AS observed_patients,round(100.0*count(heart_rate)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'respiratory_rate' AS variable,count(*) AS patients,count(respiratory_rate) AS observed_patients,round(100.0*count(respiratory_rate)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'spo2' AS variable,count(*) AS patients,count(spo2) AS observed_patients,round(100.0*count(spo2)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'temperature' AS variable,count(*) AS patients,count(temperature) AS observed_patients,round(100.0*count(temperature)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'systolic_bp' AS variable,count(*) AS patients,count(systolic_bp) AS observed_patients,round(100.0*count(systolic_bp)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'diastolic_bp' AS variable,count(*) AS patients,count(diastolic_bp) AS observed_patients,round(100.0*count(diastolic_bp)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
UNION ALL
SELECT landmark_hours,'mean_bp' AS variable,count(*) AS patients,count(mean_bp) AS observed_patients,round(100.0*count(mean_bp)/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours
ORDER BY landmark_hours,variable;

-- Result 4: exact UTF-8 bytes of stored temperature labels.
SELECT itemid,recorded_unit,encode(convert_to(recorded_unit,'UTF8'),'hex') AS utf8_hex
FROM (SELECT DISTINCT itemid,valueuom AS recorded_unit FROM landmark_mimic48.chartevents WHERE itemid IN(223761,223762)) u
ORDER BY itemid,recorded_unit;
