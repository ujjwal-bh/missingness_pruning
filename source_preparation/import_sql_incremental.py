"""Generate resumable table transactions with cleanup only after verification."""
import hashlib
import json
from pathlib import Path

def generate(folder, stats, legacy_builder):
    from prepare_landmark_import import sql_type
    folder = folder.resolve()
    legacy_builder(folder, stats)
    legacy = (folder/'import.sql').read_text(encoding='utf-8')
    view_start = legacy.index('CREATE VIEW ')
    view_end = legacy.index('DO $$ DECLARE', view_start)
    views = legacy[view_start:view_end].replace('CREATE VIEW ', 'CREATE OR REPLACE VIEW ')
    # Preserve the researcher's confirmed primary/sensitivity timing decision
    # on future SQL regeneration, without changing extraction or source rows.
    decision_file = Path(__file__).parent/'04_apply_primary_death_chronology_exclusion.sql'
    if decision_file.exists():
        decision_sql = decision_file.read_text(encoding='utf-8')
        start = decision_sql.index('CREATE OR REPLACE VIEW landmark_mimic48.sensitivity_primary_cohort_original_timing')
        end = decision_sql.index('-- Validate the rule',start)
        views += '\n'+decision_sql[start:end]
    amendment_file = Path(__file__).parent/'05_harmonize_patient_contribution.sql'
    if amendment_file.exists():
        amendment_sql = amendment_file.read_text(encoding='utf-8')
        start=amendment_sql.index('-- Begin MIMIC definitions')
        end=amendment_sql.index('-- End MIMIC definitions',start)
        views += '\n'+amendment_sql[start:end]
    report = legacy[legacy.index('COMMIT;',view_end)+len('COMMIT;'):]
    signature = hashlib.sha256(json.dumps(stats,sort_keys=True).encode()).hexdigest()
    schema = 'landmark_mimic48'
    cleanup = (Path(__file__).parent/'delete_verified_stage.ps1').resolve()
    remaining = sum((folder/(n+'.csv')).stat().st_size for n in stats if (folder/(n+'.csv')).exists())
    lines = ['\\set ON_ERROR_STOP on', "SET client_encoding='UTF8';", "SET timezone='UTC';",
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='{schema}') AND to_regclass('{schema}._import_completed') IS NULL THEN RAISE EXCEPTION 'Existing schema has no incremental import ledger; refusing to modify it'; END IF; END $$;",
        f'CREATE SCHEMA IF NOT EXISTS {schema};',
        f'CREATE TABLE IF NOT EXISTS {schema}._import_completed (table_name text PRIMARY KEY, signature text NOT NULL, row_count bigint NOT NULL, staged_bytes bigint NOT NULL, completed_at timestamptz DEFAULT now());',
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {schema}._import_completed WHERE signature <> '{signature}') THEN RAISE EXCEPTION 'Import manifest differs from saved database progress'; END IF; END $$;",
        'CREATE TEMP TABLE import_budget_baseline AS SELECT COALESCE(sum(size),0) AS wal_bytes FROM pg_ls_waldir();']
    def budget(staged):
        return f"""DO $$ DECLARE used_bytes numeric; BEGIN
SELECT {staged} + COALESCE((SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='{schema}' AND c.relkind='r'),0)
+ GREATEST(COALESCE((SELECT sum(size) FROM pg_ls_waldir()),0)-(SELECT wal_bytes FROM import_budget_baseline),0) INTO used_bytes;
IF used_bytes > 90000000000 THEN RAISE EXCEPTION 'Storage estimate exceeds 90 GB; stopped within the 100 GB overall budget'; END IF; END $$;"""
    # Largest files first to recover disk space early.
    for name, entry in sorted(stats.items(),key=lambda pair:pair[1]['bytes'],reverse=True):
        path = folder/(name+'.csv')
        current_bytes = path.stat().st_size if path.exists() else 0
        if current_bytes and current_bytes != entry['bytes']:
            raise RuntimeError(f'{name}: staged file size changed.')
        lines.extend([f"SELECT EXISTS (SELECT 1 FROM {schema}._import_completed WHERE table_name='{name}') AS already_loaded \\gset",
                      '\\if :already_loaded', f'\\echo Reusing committed table {name}', '\\else', 'BEGIN;'])
        definitions = ', '.join(f'"{col}" {sql_type(col)}' for col in entry['columns'])
        lines.append(f'CREATE TABLE {schema}.{name} ({definitions});')
        escaped = path.as_posix().replace("'","''")
        lines.append(f"\\copy {schema}.{name} FROM '{escaped}' WITH (FORMAT csv, HEADER true, NULL '')")
        check = f"DO $$ BEGIN IF (SELECT count(*) FROM {schema}.{name}) <> {entry['rows']} THEN RAISE EXCEPTION 'Row count mismatch: {name}'; END IF; END $$;"
        lines.extend([check, budget(remaining),
                      f"INSERT INTO {schema}._import_completed (table_name,signature,row_count,staged_bytes) VALUES ('{name}','{signature}',{entry['rows']},{entry['bytes']});",
                      'COMMIT;', '\\endif', check])
        # Cleanup executes only after COMMIT was acknowledged and a fresh
        # database row-count check succeeded. Any earlier error stops psql.
        lines.extend([f'\\! powershell -NoProfile -ExecutionPolicy Bypass -File "{cleanup}" -Table {name} -ExpectedBytes {entry["bytes"]}',
                      '\\if :SHELL_ERROR', "DO $$ BEGIN RAISE EXCEPTION 'Staged CSV cleanup failed; database table is committed, rerun safely after fixing cleanup'; END $$;", '\\endif'])
        remaining -= current_bytes
    lines.append('BEGIN;')
    for table,key in [('patients','subject_id'),('admissions','hadm_id'),('icustays','stay_id'),('d_items','itemid'),('d_labitems','itemid')]:
        lines.append(f'CREATE UNIQUE INDEX IF NOT EXISTS {table}_key_idx ON {schema}.{table} ({key});')
        lines.append(budget(remaining))
    for table,key,timecol in [('chartevents','stay_id','charttime'),('inputevents','stay_id','starttime'),('procedureevents','stay_id','starttime'),('outputevents','stay_id','charttime'),('datetimeevents','stay_id','charttime'),('ingredientevents','stay_id','starttime'),('labevents','subject_id','charttime'),('icustays','subject_id','intime'),('transfers','hadm_id','intime')]:
        lines.append(f'CREATE INDEX IF NOT EXISTS {table}_time_idx ON {schema}.{table} ({key},{timecol});')
        lines.append(budget(remaining))
    lines.extend([views,'COMMIT;',report])
    # Replace the entrypoint atomically; preserve the manifest/checkpoints.
    temporary = folder/'import.sql.tmp'
    temporary.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    temporary.replace(folder/'import.sql')

if __name__ == '__main__':
    from prepare_landmark_import import make_sql_legacy
    folder=Path(__file__).parent/'landmark_import_stage'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['extraction_profile']!='broad_100gb_v1':
        raise SystemExit('Unexpected extraction profile; refusing import.')
    generate(folder,manifest['tables'],make_sql_legacy)
    print('Resumable import SQL ready: staged CSVs deleted only after verified table commits.')
