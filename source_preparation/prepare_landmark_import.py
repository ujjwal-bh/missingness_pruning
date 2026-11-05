"""Stream a study-specific MIMIC-IV subset; never connect to PostgreSQL."""
import argparse
import csv
import gzip
import json
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

CHARTEVENT_IDS = {
    220045, 220050, 220051, 220052, 220179, 220180, 220181,
    220210, 220277, 223761, 223762, 220739, 223900, 223901,
    223835, 223848, 223849, 224684, 224685, 224686, 224688,
    224689, 224690, 220339, 224700, 226732, 226260, 229314,
    225126, 227290, 224144, 224145, 224146, 224149, 224150,
    224151, 224152, 224153, 224154, 224155, 224156,
    226512, 224639, 226730,
}
LAB_LABELS = {
    'albumin', 'anion gap', 'base excess', 'bicarbonate', 'bilirubin, total',
    'calcium, total', 'calculated total co2', 'chloride', 'creatinine',
    'glucose', 'hematocrit', 'hemoglobin', 'inr(pt)', 'lactate', 'magnesium',
    'oxygen saturation', 'pco2', 'ph', 'phosphate', 'platelet count',
    'po2', 'potassium', 'pt', 'ptt', 'sodium', 'urea nitrogen',
    'white blood cells', 'free calcium', 'specimen type',
}
TREATMENT_LABEL = re.compile(r'^(?:norepinephrine|epinephrine|vasopressin|dopamine|dobutamine|phenylephrine)(?:\b|\.)', re.I)
PROCEDURE_IDS = {224385, 225468, 225477, 225792, 225794, 227194,
                 225441, 225802, 225803, 225805, 225809, 225955, 225436}

def rows(base, table, ids=None, entities=None, entity_key=None):
    if entities is not None:
        # The C CSV parser avoids constructing dictionaries for irrelevant rows.
        import pandas as pd
        allowed_ids = {str(value) for value in ids} if ids is not None else None
        allowed_entities = {str(value) for value in entities}
        path = base / (table + '.csv.gz')
        scanned = 0
        # Decode with Python first: this bundled pandas build changes degree
        # symbols when it opens the gzip path directly.
        with gzip.open(path, 'rt', encoding='utf-8', newline='') as handle:
            for chunk in pd.read_csv(handle, dtype=str, na_filter=False,
                                     chunksize=250000):
                scanned += len(chunk)
                if scanned % 5000000 == 0:
                    print(f'{table}: {scanned:,} source rows scanned',flush=True)
                mask = chunk[entity_key].isin(allowed_entities)
                if allowed_ids is not None:
                    mask &= chunk['itemid'].isin(allowed_ids)
                selected = chunk.loc[mask]
                yield from selected.to_dict('records')
        return
    with gzip.open(base / (table + '.csv.gz'), 'rt', encoding='utf-8', newline='') as handle:
        yield from csv.DictReader(handle)

def dt(value):
    return datetime.fromisoformat(value) if value else None

def number(value):
    return int(value) if value else None

def observation_in_window(row, start, stop):
    # Retain late-charted records; enforce availability during model construction.
    chart = row.get('charttime', '')
    if chart and not start <= chart <= stop:
        return False
    return True

def interval_in_window(row, start, stop):
    event_start, event_end = row.get('starttime', ''), row.get('endtime', '')
    if not event_start:
        return True
    if event_start > stop:
        return False
    if event_end and event_end < start:
        return False
    return True

class Writer:
    def __init__(self, folder, limit):
        self.folder, self.limit = folder, limit
        self.stats, self.total = {}, 0
        self.checkpoint = folder / 'completed_tables.json'
        self.completed = json.loads(self.checkpoint.read_text(encoding='utf-8')) if self.checkpoint.exists() else {}

    def write(self, name, source, columns):
        path = self.folder / (name + '.csv')
        saved = self.completed.get(name)
        if saved and path.exists():
            stat = path.stat()
            if saved['bytes'] != stat.st_size or saved['mtime_ns'] != stat.st_mtime_ns or saved['columns'] != columns:
                raise RuntimeError(f'{name}: completed file changed; refusing to reuse it.')
            self.stats[name] = {key: saved[key] for key in ['rows','bytes','columns']}
            self.total += saved['bytes']
            if self.total > self.limit:
                raise RuntimeError('Completed staged files exceed the staging cap; import SQL was not produced.')
            print(f'{name}: reusing {saved["rows"]:,} completed rows; no source rescan',flush=True)
            return
        count, last = 0, time.monotonic()
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore', quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for row in source:
                writer.writerow({col: row.get(col, '') for col in columns})
                count += 1
                if count % 100000 == 0:
                    handle.flush()
                    size = path.stat().st_size
                    if self.total + size > self.limit:
                        raise RuntimeError('Staging cap exceeded; import SQL was not produced.')
                    if shutil.disk_usage(self.folder).free < 10_000_000_000:
                        raise RuntimeError('Less than 10 GB free; stopping preparation.')
                    if time.monotonic() - last > 30:
                        print(f'{name}: {count:,} retained rows', flush=True)
                        last = time.monotonic()
            handle.flush()
        size = path.stat().st_size
        self.total += size
        if self.total > self.limit:
            raise RuntimeError('Staging cap exceeded; import SQL was not produced.')
        self.stats[name] = {'rows': count, 'bytes': size, 'columns': columns}
        self.completed[name] = dict(self.stats[name], mtime_ns=path.stat().st_mtime_ns)
        temporary = self.checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.completed,indent=2),encoding='utf-8')
        temporary.replace(self.checkpoint)
        print(f'{name}: {count:,} rows; {size / 1024**2:.1f} MiB', flush=True)

def sql_type(col):
    if col in {'subject_id', 'hadm_id', 'stay_id', 'transfer_id', 'itemid', 'labevent_id', 'specimen_id',
               'anchor_age', 'anchor_year', 'hospital_expire_flag', 'warning', 'orderid', 'linkorderid', 'caregiver_id'}:
        return 'bigint'
    if col in {'intime', 'outtime', 'admittime', 'dischtime', 'deathtime', 'charttime',
               'storetime', 'starttime', 'endtime', 'edregtime', 'edouttime'}:
        return 'timestamp'
    if col == 'dod':
        return 'date'
    if col in {'valuenum', 'los', 'amount', 'rate', 'patientweight', 'totalamount',
               'originalamount', 'originalrate', 'ref_range_lower', 'ref_range_upper'}:
        return 'double precision'
    return 'text'

def make_sql_legacy(folder, stats):
    schema = 'landmark_mimic48'
    staged_bytes = sum(entry.get('bytes', 0) for entry in stats.values())
    # Track staged files + schema tables/indexes + growth in allocated WAL.
    # Leave 10 GB for transient index builds and other unmeasured overhead.
    budget_check = f'''DO $$ DECLARE used_bytes numeric; BEGIN
SELECT {staged_bytes} + COALESCE((SELECT sum(pg_total_relation_size(c.oid))
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='{schema}' AND c.relkind='r'),0)
 + GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)
 - (SELECT wal_bytes FROM import_budget_baseline),0) INTO used_bytes;
IF used_bytes > 90000000000 THEN
 RAISE EXCEPTION 'Import storage estimate exceeds 90 GB; stopping to reserve overhead within the 100 GB budget';
END IF; END $$;'''
    lines = ['\\set ON_ERROR_STOP on', 'BEGIN;',
             '-- Fails safely if this schema already exists; never overwrite previous data.',
             f'CREATE SCHEMA {schema};', "SET LOCAL timezone = 'UTC';",
             "SET LOCAL client_encoding = 'UTF8';"]
    lines.append('CREATE TEMP TABLE import_budget_baseline ON COMMIT DROP AS SELECT COALESCE(sum(size),0) AS wal_bytes FROM pg_ls_waldir();')
    for name, entry in stats.items():
        columns = entry['columns']
        definitions = ', '.join(f'"{col}" {sql_type(col)}' for col in columns)
        lines.append(f'CREATE TABLE {schema}.{name} ({definitions});')
        csv_path = (folder / (name + '.csv')).as_posix().replace("'", "''")
        lines.append(f"\\copy {schema}.{name} FROM '{csv_path}' WITH (FORMAT csv, HEADER true, NULL '')")
        # Assert that the database received exactly the staged rows.
        lines.append(f"DO $$ BEGIN IF (SELECT count(*) FROM {schema}.{name}) <> {entry['rows']} THEN RAISE EXCEPTION 'Row count mismatch: {name}'; END IF; END $$;")
        lines.append(budget_check)
    for table, key in [('patients','subject_id'), ('admissions','hadm_id'), ('icustays','stay_id'),
                       ('d_items','itemid'), ('d_labitems','itemid')]:
        lines.append(f'ALTER TABLE {schema}.{table} ADD PRIMARY KEY ({key});')
        lines.append(budget_check)
    for table in ['chartevents','inputevents','procedureevents','outputevents','datetimeevents','ingredientevents']:
        timecol = 'starttime' if table in ['inputevents','procedureevents','ingredientevents'] else 'charttime'
        lines.append(f'CREATE INDEX ON {schema}.{table} (stay_id, {timecol});')
        lines.append(budget_check)
    lines.extend([f'CREATE INDEX ON {schema}.labevents (subject_id, charttime);',
                  f'CREATE INDEX ON {schema}.icustays (subject_id, intime);',
                  f'CREATE INDEX ON {schema}.transfers (hadm_id, intime);'])
    lines.append(f'''CREATE VIEW {schema}.landmark_eligibility AS
SELECT s.subject_id, s.hadm_id, s.stay_id, l.hours AS landmark_hours,
       s.intime + l.hours * interval '1 hour' AS landmark_time,
       p.anchor_age + extract(year FROM s.intime)::integer - p.anchor_year AS age_at_icu,
       s.outtime > s.intime + l.hours * interval '1 hour'
       AND a.dischtime > s.intime + l.hours * interval '1 hour'
       AND (a.deathtime IS NULL OR a.deathtime > s.intime + l.hours * interval '1 hour')
       AND NOT (a.hospital_expire_flag = 1 AND a.deathtime IS NULL)
       AS eligible_still_in_icu,
       a.hospital_expire_flag = 1 AND a.deathtime IS NULL AS death_time_uncertain,
       a.hospital_expire_flag AS hospital_mortality,
       row_number() OVER (PARTITION BY s.subject_id, l.hours ORDER BY s.intime, s.stay_id)
       AS chronological_stay_number
FROM {schema}.icustays s
JOIN {schema}.patients p USING (subject_id)
JOIN {schema}.admissions a USING (subject_id, hadm_id)
CROSS JOIN (VALUES (12), (24), (36), (48)) l(hours);''')
    lines.append(f'''CREATE VIEW {schema}.primary_landmark_cohort AS
SELECT * FROM (
    SELECT e.*, row_number() OVER (
        PARTITION BY subject_id, landmark_hours ORDER BY landmark_time, stay_id
    ) AS eligible_stay_number
    FROM {schema}.landmark_eligibility e
    WHERE eligible_still_in_icu
) ranked WHERE eligible_stay_number = 1;''')
    lines.append(budget_check)
    lines.append('COMMIT;')
    for name in stats:
        lines.append(f'ANALYZE {schema}.{name};')
    lines.append(f"SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS study_tables_size FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='{schema}' AND c.relkind='r';")
    lines.append(f'SELECT landmark_hours, count(*) AS adult_stays, count(*) FILTER (WHERE eligible_still_in_icu) AS eligible_stays, count(*) FILTER (WHERE death_time_uncertain) AS uncertain_death_time_stays FROM {schema}.landmark_eligibility GROUP BY landmark_hours ORDER BY landmark_hours;')
    lines.append(f'SELECT landmark_hours, count(*) AS first_eligible_patient_stays, sum(hospital_mortality) AS hospital_deaths FROM {schema}.primary_landmark_cohort GROUP BY landmark_hours ORDER BY landmark_hours;')
    (folder / 'import.sql').write_text('\n'.join(lines) + '\n', encoding='utf-8')

def make_sql(folder, stats):
    from import_sql_incremental import generate
    generate(folder, stats, make_sql_legacy)

def prepare(base, folder, limit, restart=False):
    if folder.exists() and any(folder.iterdir()) and not restart:
        raise RuntimeError('Staging folder already contains files; use a new output folder.')
    if restart and ((folder/'import.sql').exists() or (folder/'manifest.json').exists()):
        raise RuntimeError('Completed preparation cannot be overwritten. Use a new output folder.')
    folder.mkdir(parents=True, exist_ok=True)
    patients = {number(r['subject_id']): r for r in rows(base, 'hosp/patients')}
    admissions = {number(r['hadm_id']): r for r in rows(base, 'hosp/admissions')}
    stays, windows, subject_windows, timing_anomalies = [], {}, {}, []
    for row in rows(base, 'icu/icustays'):
        subject = number(row['subject_id'])
        patient = patients.get(subject)
        start = dt(row['intime'])
        if not patient or not start or number(row['hadm_id']) not in admissions:
            continue
        age = int(patient['anchor_age']) + start.year - int(patient['anchor_year'])
        if age < 18:
            continue
        stays.append(row)
        # Retain short stays for attrition; retain post-ICU data
        # for the alive-and-hospitalized sensitivity analysis.
        stop = start + timedelta(hours=48)
        discharge = dt(admissions[number(row['hadm_id'])]['dischtime'])
        if discharge and discharge < start:
            timing_anomalies.append({'stay_id':row['stay_id'],
                                     'reason':'Hospital discharge precedes ICU admission'})
        window = (start.isoformat(' '), stop.isoformat(' '), number(row['hadm_id']))
        windows[number(row['stay_id'])] = window
        subject_windows.setdefault(subject, []).append(window)
    for subject in subject_windows:
        subject_windows[subject].sort()
    subjects = {number(r['subject_id']) for r in stays}
    hadms = {number(r['hadm_id']) for r in stays}
    writer = Writer(folder, limit)
    (folder/'timing_anomalies.json').write_text(json.dumps(timing_anomalies,indent=2),encoding='utf-8')
    print(f'Adult stays: {len(stays):,}; inconsistent hospital/ICU timing: {len(timing_anomalies):,}',flush=True)
    writer.write('patients', (patients[s] for s in sorted(subjects)),
                 ['subject_id','gender','anchor_age','anchor_year','anchor_year_group','dod'])
    writer.write('admissions', (admissions[h] for h in sorted(hadms)),
                 ['subject_id','hadm_id','admittime','dischtime','deathtime','admission_type',
                  'admission_location','discharge_location','race','hospital_expire_flag'])
    writer.write('icustays', stays, ['subject_id','hadm_id','stay_id','first_careunit','last_careunit','intime','outtime','los'])
    writer.write('transfers', (r for r in rows(base,'hosp/transfers') if number(r['hadm_id']) in hadms),
                 ['subject_id','hadm_id','transfer_id','eventtype','careunit','intime','outtime'])
    items = list(rows(base, 'icu/d_items'))
    labs = list(rows(base, 'hosp/d_labitems'))
    chart_ids = {int(r['itemid']) for r in items if r['linksto']=='chartevents'}
    input_ids = {int(r['itemid']) for r in items if r['linksto']=='inputevents'}
    procedure_ids = {int(r['itemid']) for r in items if r['linksto']=='procedureevents'}
    output_ids = {int(r['itemid']) for r in items if r['linksto']=='outputevents'}
    lab_ids = {int(r['itemid']) for r in labs}
    selected_items = chart_ids | input_ids | procedure_ids | output_ids
    writer.write('d_items', items, list(items[0]))
    writer.write('d_labitems', (r for r in labs if int(r['itemid']) in lab_ids), ['itemid','label','fluid','category'])
    (folder/'candidate_item_mapping.json').write_text(json.dumps({
        'status':'Candidate MODEL dictionary only; extraction retains all ICU/lab item types',
        'icu':[r for r in items if int(r['itemid']) in CHARTEVENT_IDS or TREATMENT_LABEL.search(r['label']) or int(r['itemid']) in PROCEDURE_IDS],
        'labs':[r for r in labs if r['fluid']=='Blood' and r['label'].lower() in LAB_LABELS]},indent=2),encoding='utf-8')
    def source_columns(table):
        with gzip.open(base/(table+'.csv.gz'),'rt',encoding='utf-8',newline='') as handle:
            return next(csv.reader(handle))
    def filtered_icu(table, ids, interval=False):
        for row in rows(base, 'icu/' + table, entities=windows, entity_key='stay_id'):
            window = windows.get(number(row['stay_id']))
            if not window:
                continue
            # A stay ID alone is insufficient if a malformed record disagrees.
            if number(row['hadm_id']) != window[2]:
                raise ValueError(f'{table}: admission/stay mismatch')
            if (interval_in_window if interval else observation_in_window)(row, window[0], window[1]):
                yield row
    writer.write('chartevents', filtered_icu('chartevents',chart_ids), source_columns('icu/chartevents'))
    def filtered_labs():
        for row in rows(base, 'hosp/labevents', entities=subjects, entity_key='subject_id'):
            if number(row['subject_id']) not in subjects:
                continue
            for start, stop, hadm in subject_windows.get(number(row['subject_id']), []):
                # Missing hadm_id is intentionally permitted; preserve original NULL.
                if row['hadm_id'] and number(row['hadm_id']) != hadm:
                    continue
                if observation_in_window(row,start,stop):
                    yield row
                    break  # never duplicate a lab shared by overlapping ICU windows
    writer.write('labevents', filtered_labs(), source_columns('hosp/labevents'))
    common = ['subject_id','hadm_id','stay_id','starttime','endtime','storetime','itemid']
    writer.write('inputevents', filtered_icu('inputevents',input_ids,True), source_columns('icu/inputevents'))
    writer.write('procedureevents', filtered_icu('procedureevents',procedure_ids,True),
                 source_columns('icu/procedureevents'))
    writer.write('outputevents', filtered_icu('outputevents',output_ids),
                 source_columns('icu/outputevents'))
    writer.write('datetimeevents', filtered_icu('datetimeevents',set()), source_columns('icu/datetimeevents'))
    writer.write('ingredientevents', filtered_icu('ingredientevents',set(),True), source_columns('icu/ingredientevents'))
    (folder/'manifest.json').write_text(json.dumps({
        'source':str(base.resolve()),'extraction_profile':'broad_100gb_v1',
        'additional_storage_budget_bytes':100_000_000_000,
        'maximum_window_hours':48,'adult_stays':len(stays),
        'staged_bytes':writer.total,'tables':writer.stats,
        'notes':['No first-stay or 12-hour eligibility exclusions during extraction.',
                 'All item types and late/unknown timestamps retained; availability enforced during modeling.',
                 'Interval endpoints retained as raw source fields; never use future duration as a predictor.',
                 'Lab joins require subject/time and admission checks, including missing hadm_id.',
                 'Predictor dictionary is provisional; eICU harmonization remains required.']},indent=2),encoding='utf-8')
    make_sql(folder,writer.stats)
    print(f'Ready: {folder / "import.sql"}. Staged total: {writer.total/1024**3:.2f} GiB.',flush=True)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path(__file__).parent/'MIMIC-IV-DATA')
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'landmark_import_stage')
    parser.add_argument('--staging-cap-gib',type=float,default=60_000_000_000/1024**3)
    parser.add_argument('--restart-preparation',action='store_true')
    args=parser.parse_args()
    prepare(args.source,args.output,int(args.staging_cap_gib*1024**3),args.restart_preparation)
