"""Generate draft core feature SQL; source tables and cohort views stay intact."""
import json
import hashlib
from pathlib import Path

root=Path(__file__).parent.resolve()
cfg=json.loads((root/'predictor_cleaning_rules_v1.json').read_text(encoding='utf-8'))
spec=cfg['variables'];signature=hashlib.sha256((root/'predictor_cleaning_rules_v1.json').read_bytes()).hexdigest()
mapping=[]
for r in spec:
    for itemid in r['mimic_itemids']:
        allowed_units=r['units_accepted_mimic']
        if r['variable']=='temperature':
            suffix='f' if itemid==223761 else 'c'
            allowed_units=[u for u in allowed_units if u.endswith(suffix)]
        aliases="ARRAY["+','.join("'%s'"%u.replace("'","''") for u in allowed_units)+"]::text[]"
        lower='>=' if r['lower_inclusive'] else '>'
        upper='<=' if r['upper_inclusive'] else '<'
        mapping.append(f"('{r['variable']}',{itemid},'{r['domain']}',{r['lower_bound']},{r['upper_bound']},'{lower}','{upper}',{aliases})")
sql=['-- Candidate feature build: not final modeling data. Run entire file in pgAdmin.',
     '-- May take time and temporary disk space; source records are not changed.',
     '-- A preexisting candidate table causes an error rather than being overwritten.',
     '-- All patients are retained regardless of predictor missingness.',
     'BEGIN;',
     'CREATE TEMP TABLE core_mapping(variable text,itemid bigint,domain text,low double precision,high double precision,low_op text,high_op text,unit_aliases text[]) ON COMMIT DROP;',
     'INSERT INTO core_mapping VALUES\n'+',\n'.join(mapping)+';',
     '''CREATE TEMP TABLE selected_core_stays ON COMMIT DROP AS
SELECT DISTINCT s.subject_id,s.hadm_id,s.stay_id,s.intime
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id);
CREATE INDEX ON selected_core_stays(stay_id);
CREATE INDEX ON selected_core_stays(subject_id,intime);''',
     r'''CREATE TEMP TABLE core_observation_raw ON COMMIT DROP AS
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
JOIN core_mapping m ON m.itemid=x.itemid AND m.domain='laboratory';''',
     '''CREATE TABLE landmark_mimic48.core_observation_qc_candidate_v1 AS
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
 o.source_priority ASC,o.available_time DESC,o.itemid ASC;''']
pivot=',\n'.join(f" max(v.value) FILTER(WHERE v.variable='{r['variable']}') AS {r['variable']}" for r in spec)
sql.append(f'''CREATE TABLE landmark_mimic48.core_features_candidate_v1 AS
SELECT c.subject_id,c.hadm_id,c.stay_id,c.landmark_hours,c.landmark_time,c.hospital_mortality,
 LEAST(p.anchor_age+extract(year FROM s.intime)::integer-p.anchor_year,90) AS age_capped_90,
 CASE WHEN p.gender='F' THEN 1 WHEN p.gender='M' THEN 0 END AS female,
 {pivot}
FROM landmark_mimic48.primary_landmark_cohort c
JOIN landmark_mimic48.icustays s USING(subject_id,hadm_id,stay_id)
JOIN landmark_mimic48.patients p USING(subject_id)
LEFT JOIN latest_core_value v ON v.stay_id=c.stay_id AND v.landmark_hours=c.landmark_hours
GROUP BY c.subject_id,c.hadm_id,c.stay_id,c.landmark_hours,c.landmark_time,c.hospital_mortality,p.anchor_age,p.anchor_year,p.gender,s.intime;
ALTER TABLE landmark_mimic48.core_features_candidate_v1 ADD PRIMARY KEY(landmark_hours,subject_id);
COMMENT ON TABLE landmark_mimic48.core_features_candidate_v1 IS 'Candidate core features; rule SHA256 {signature}; not imputed/scaled; remaining domains and external harmonization pending';''')
sql.append('''DO $$ BEGIN
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
''')
coverage='\nUNION ALL\n'.join(f"SELECT landmark_hours,'{r['variable']}' AS variable,count(*) AS patients,count({r['variable']}) AS observed_patients,round(100.0*count({r['variable']})/count(*),2) AS observed_percent FROM landmark_mimic48.core_features_candidate_v1 GROUP BY landmark_hours" for r in spec)
sql.append(coverage+'\nORDER BY landmark_hours,variable;')
sql.append('''-- Result 4: exact UTF-8 bytes of stored temperature labels.
SELECT itemid,recorded_unit,encode(convert_to(recorded_unit,'UTF8'),'hex') AS utf8_hex
FROM (SELECT DISTINCT itemid,valueuom AS recorded_unit FROM landmark_mimic48.chartevents WHERE itemid IN(223761,223762)) u
ORDER BY itemid,recorded_unit;''')
(root/'07_build_mimic_core_candidate_features.sql').write_text('\n\n'.join(sql)+'\n',encoding='utf-8')
print('Candidate MIMIC core feature SQL generated with row/outcome and time-window assertions.')
