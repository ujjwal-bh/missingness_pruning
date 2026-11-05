"""Generate auditable pre-landmark documentation flags; not active-treatment truth labels."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
audit=json.loads((ROOT/'extension_source_audits_complete_2026_10_15.json').read_text())['completed_audits']
vent=[];renal=[];ambiguous=[]
strong={'assist controlled','volume controlled','pressure controlled','synchronized intermittent','volume assured'}
modalities={'hemodialysis','peritoneal dialysis','c v v h','c v v h d','c a v h d','sled','ultrafiltration (fluid removal only)'}
for row in audit['E4']['rows']:
    label=row['treatmentstring'];parts=label.lower().split('|')
    if 'mechanical ventilation' in parts and not any('non-invasive' in p for p in parts):
        (vent if any(p in strong for p in parts) else ambiguous).append(label)
    if len(parts)>=3 and parts[0]=='renal' and parts[1]=='dialysis' and parts[2] in modalities:
        renal.append(label)
def values(labels):return ','.join("'"+s.replace("'","''")+"'" for s in sorted(labels))
rules={'status':'Candidate documentation flags only; no final primary predictor decision',
 'positive_means':'Qualifying positive documentation available by landmark, not proof of currently active treatment',
 'zero_means':'No qualifying documentation found in selected sources; never confirmed absence of treatment',
 'eicu_strict_ventilation_treatment_labels':vent,'eicu_ambiguous_mechanical_ventilation_labels':ambiguous,
 'eicu_renal_treatment_labels':renal,'vasopressor_agents':['norepinephrine','epinephrine','phenylephrine','dopamine','vasopressin'],
 'excluded_inotrope':'dobutamine','rate_policy':'Positive numeric rate; conflicting zero/positive drug and volume rates rejected; no dose equivalence calculated'}
(ROOT/'support_documentation_mapping_candidate_v1.json').write_text(json.dumps(rules,indent=2),encoding='utf-8')
lines=[r'\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL client_encoding='UTF8';",
       "DO $$ BEGIN IF pg_database_size(current_database())>90000000000::bigint THEN RAISE EXCEPTION 'Database already exceeds 90 GB working guard'; END IF; END $$;"]
# Normalize existing MIMIC records to minute offsets with separate event and availability.
lines.append("""CREATE TEMP TABLE support_mimic_stays ON COMMIT DROP AS
SELECT DISTINCT s.stay_id,s.intime FROM landmark_mimic48.primary_landmark_cohort c JOIN landmark_mimic48.icustays s USING(stay_id);
CREATE INDEX ON support_mimic_stays(stay_id);
CREATE TABLE landmark_mimic48.support_documentation_events_candidate_v1 AS
WITH events AS (
SELECT x.stay_id AS stay_key,GREATEST(x.starttime,s.intime) AS event_time,
GREATEST(x.starttime,x.storetime,s.intime) AS available_time,s.intime,
'vasopressor'::text AS domain,'inputevents'::text AS source,x.itemid::text AS source_label
FROM landmark_mimic48.inputevents x JOIN support_mimic_stays s USING(stay_id) JOIN landmark_mimic48.d_items d USING(itemid)
WHERE d.label ~* '^(norepinephrine|epinephrine|vasopressin|dopamine|phenylephrine)(\\M|\\.)'
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
""")
lines.append(f"""CREATE TABLE eicu_landmark.support_documentation_events_candidate_v1 AS
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
CASE WHEN treatmentstring IN({values(vent)}) THEN 'invasive_ventilation'
WHEN treatmentstring IN({values(renal)}) THEN 'rrt' ELSE 'ambiguous_ventilation' END,'treatment',treatmentstring
FROM eicu_landmark.extension_treatment_source_v1
WHERE treatmentstring IN({values(vent+renal+ambiguous)})
UNION ALL
SELECT patientunitstayid,respchartoffset,GREATEST(respchartoffset,respchartentryoffset),'invasive_ventilation','respiratoryCharting',respchartvaluelabel||'='||respchartvalue
FROM eicu_landmark.extension_respiratorycharting_source_v1
WHERE respchartentryoffset IS NOT NULL
AND ((respchartvaluelabel='Mechanical Ventilator Mode' AND respchartvalue IN('AC/CMV','SIMV','SIMV+'))
OR (respchartvaluelabel='Ventilator Support Mode' AND respchartvalue IN('CMV','SIMV','APV')));
""")
reports=[];sources=[]
for dataset,schema,person,stay in [('MIMIC','landmark_mimic48','subject_id','stay_id'),('eICU','eicu_landmark','uniquepid','patientunitstayid')]:
    event_table=f'{schema}.support_documentation_events_candidate_v1'
    target=f'{schema}.support_documentation_features_candidate_v1'
    lines += [f'CREATE INDEX ON {event_table}(stay_key,available_minutes,event_minutes);']
    fields=[]
    for domain in ['vasopressor','invasive_ventilation','rrt','ambiguous_ventilation']:
        fields.append(f"EXISTS(SELECT 1 FROM {event_table} x WHERE x.stay_key=c.{stay} AND x.domain='{domain}' AND x.event_minutes BETWEEN 0 AND c.landmark_hours*60 AND x.available_minutes<=c.landmark_hours*60)::integer AS {domain}_documented")
    lines += [f"CREATE TABLE {target} AS SELECT c.*,{','.join(fields)} FROM {schema}.primary_landmark_cohort c;",
        f'ALTER TABLE {target} ADD PRIMARY KEY(landmark_hours,{person});',
        f"""DO $$ BEGIN IF EXISTS(SELECT 1 FROM {schema}.primary_landmark_cohort c FULL JOIN {target} f USING(landmark_hours,{person})
WHERE c.{person} IS NULL OR f.{person} IS NULL OR c.{stay} IS DISTINCT FROM f.{stay} OR c.hospital_mortality IS DISTINCT FROM f.hospital_mortality)
THEN RAISE EXCEPTION 'Support candidate cohort/outcome mismatch'; END IF; END $$;""",
        f"COMMENT ON TABLE {target} IS 'Candidate pre-landmark positive documentation flags; 0 means no qualifying documentation, never confirmed absence of treatment; not active-at-landmark state or frozen model input';"]
    reports.append(f"SELECT '{dataset}' AS dataset,landmark_hours,count(*) AS patients,sum(hospital_mortality) AS hospital_deaths,sum(vasopressor_documented) AS vasopressor_documented,sum(invasive_ventilation_documented) AS strict_ventilation_documented,sum(rrt_documented) AS rrt_documented,sum(ambiguous_ventilation_documented) AS ambiguous_ventilation_documented FROM {target} GROUP BY landmark_hours")
    sources.append(f"SELECT '{dataset}' AS dataset,domain,source,count(*) AS positive_documentation_rows FROM {event_table} GROUP BY domain,source")
lines+=['COMMIT;']
for schema in ['landmark_mimic48','eicu_landmark']:
    lines += [f'ANALYZE {schema}.support_documentation_events_candidate_v1;',f'ANALYZE {schema}.support_documentation_features_candidate_v1;']
lines+=['\nUNION ALL\n'.join(reports)+' ORDER BY dataset,landmark_hours;','\nUNION ALL\n'.join(sources)+' ORDER BY dataset,domain,source;']
(ROOT/'14_build_support_documentation_candidates.sql').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
print(f'Prepared support documentation candidates; exact eICU labels: {len(vent)} strict ventilation, {len(renal)} RRT, {len(ambiguous)} ambiguous ventilation.')
