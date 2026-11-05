"""Generate an additive unit-alias correction using existing PostgreSQL lab rows."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
cfg = json.loads((ROOT/'predictor_cleaning_rules_v1.json').read_text())
norm = lambda s: re.sub(r'\s+', '', s.replace('µ', 'u')).lower()
rules = {}
joins = []
features = []
checks = []
coverage = []
for i, r in enumerate(cfg['variables']):
    name = r['variable']
    if r['domain'] != 'laboratory':
        features.append('c.'+name)
        continue
    units = set(r['units_accepted_mimic'])
    if name in ('wbc', 'platelets'):
        units.update(['k/mcl','k/mm3','10*3/ul','x10^3/ul','x10^9/l',
            'k/cmm','k/cumm','k/mmcu','th/mm3','th/cmm','th/cumm','th/ul',
            'thou/cmm','thou/cumm','thou/ul','thou/mm3','thous/ul','ths/ul',
            'thd/ul','10e3/mcl','10e3/ul','10(3)/mcl','10(3)mcl',
            'x10e3/ul','x103/ul','x(10)3/ul','*10^3/ul','1000/cmm',
            '10x3/ul','10*9/l','x10(3)/mcl','103/ul','bil/l','/nl'])
    if name in ('albumin','hemoglobin'):
        units.add('gm/dl')
    if name == 'hematocrit':
        units.add('%pcv')
    if name in ('sodium','potassium','chloride','bicarbonate','lactate'):
        units.add('mmole/l')
    units = sorted({norm(u) for u in units})
    rules[name] = {'target_unit':r['target_unit'], 'accepted_normalized_units':units,
                   'rule':'Both source unit fields must be compatible; blank interface permitted as in v1. No numeric unit conversion.'}
    literal = ','.join("'"+u.replace("'","''")+"'" for u in units)
    sqlnorm = lambda c: f"lower(regexp_replace(replace(COALESCE({c},''),'µ','u'),'[[:space:]]','','g'))"
    lo = '>=' if r['lower_inclusive'] else '>'
    hi = '<=' if r['upper_inclusive'] else '<'
    alias = f'v{i}'
    joins.append(f"""LEFT JOIN LATERAL (
SELECT avg(labresult) AS value FROM eicu_landmark.core_lab_source_v1 l
WHERE l.patientunitstayid=c.patientunitstayid AND labname='{r['eicu_labname']}'
AND labresultoffset BETWEEN 0 AND c.landmark_offset_minutes
AND labresultrevisedoffset IS NOT NULL
AND GREATEST(labresultoffset,labresultrevisedoffset)<=c.landmark_offset_minutes
AND {sqlnorm('labmeasurenamesystem')} IN ({literal})
AND (COALESCE(labmeasurenameinterface,'')='' OR {sqlnorm('labmeasurenameinterface')} IN ({literal}))
AND labresult::text NOT IN ('NaN','Infinity','-Infinity')
AND labresult{lo}{r['lower_bound']} AND labresult{hi}{r['upper_bound']}
GROUP BY labresultoffset,GREATEST(labresultoffset,labresultrevisedoffset)
ORDER BY labresultoffset DESC,GREATEST(labresultoffset,labresultrevisedoffset) DESC LIMIT 1
) {alias} ON true""")
    features.append(f'{alias}.value AS {name}')
    checks.append(f'(a.{name} IS NOT NULL AND b.{name} IS NULL)')
    coverage.append(f"SELECT b.landmark_hours,'{name}' AS variable,count(*) AS patients,count(a.{name}) AS observed_v1,count(b.{name}) AS observed_v2,round(100.0*count(b.{name})/count(*),2) AS observed_percent_v2,count(*) FILTER(WHERE a.{name} IS DISTINCT FROM b.{name}) AS changed_values FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) GROUP BY b.landmark_hours")

sql = r"""\set ON_ERROR_STOP on
BEGIN;
SET LOCAL client_encoding='UTF8';
-- Preserve v1 and all raw source tables. Fail if v2 already exists.
CREATE TABLE eicu_landmark.core_features_candidate_v2 AS
SELECT c.uniquepid,c.patienthealthsystemstayid,c.patientunitstayid,c.hospitalid,
c.landmark_hours,c.landmark_offset_minutes,c.hospital_mortality,c.age_capped_90,c.female,
""" + ',\n'.join(features) + '\nFROM eicu_landmark.core_features_candidate_v1 c\n' + '\n'.join(joins) + ';\n'
sql += """ALTER TABLE eicu_landmark.core_features_candidate_v2 ADD PRIMARY KEY(landmark_hours,uniquepid);
DO $$ BEGIN
IF EXISTS(SELECT 1 FROM eicu_landmark.core_features_candidate_v1 a FULL JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid)
WHERE a.uniquepid IS NULL OR b.uniquepid IS NULL OR a.patientunitstayid IS DISTINCT FROM b.patientunitstayid OR a.hospital_mortality IS DISTINCT FROM b.hospital_mortality)
THEN RAISE EXCEPTION 'Cohort/outcome mismatch'; END IF;
"""
sql += 'IF EXISTS(SELECT 1 FROM eicu_landmark.core_features_candidate_v1 a JOIN eicu_landmark.core_features_candidate_v2 b USING(landmark_hours,uniquepid) WHERE '+ ' OR '.join(checks)+") THEN RAISE EXCEPTION 'Previously observed lab value lost'; END IF; END $$;\n"
sql += "COMMENT ON TABLE eicu_landmark.core_features_candidate_v2 IS 'Lab unit spelling correction 2026-10-15; v1 preserved; temperature and other domains still pending; no imputation or model fit';\nCOMMIT;\nANALYZE eicu_landmark.core_features_candidate_v2;\n"
sql += 'SELECT landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths FROM eicu_landmark.core_features_candidate_v2 GROUP BY landmark_hours ORDER BY landmark_hours;\n'
sql += '\nUNION ALL\n'.join(coverage)+'\nORDER BY landmark_hours,variable;\n'
(ROOT/'08_correct_eicu_lab_unit_aliases.sql').write_text(sql,encoding='utf-8')
(ROOT/'eicu_lab_unit_alias_rules_v2.json').write_text(json.dumps({'date':'2026-10-15','status':'Prepared; live verification pending','variables':rules},indent=2),encoding='utf-8')
print('Prepared correction SQL for 17 labs; original source and candidate v1 preserved.')
