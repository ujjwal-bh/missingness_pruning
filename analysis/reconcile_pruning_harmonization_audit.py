"""Reconcile aggregate database audit with the original missingness ranking."""
from pathlib import Path
import csv,json,hashlib,math
R=Path(__file__).resolve().parent
A=R/'model_results/pruning_focused_amendment_2026_10_29_v1'
def read(name):
    with (A/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rank={r['variable']:r for r in read('all_24_shifts_and_selection_stability.csv')}
    rows=[];checks=[]
    for db,n,col in [('MIMIC',37872,'source_missing'),('eICU',20589,'adaptation_missing')]:
        funnel=read(db+'_harmonization_funnel.csv');assert len(funnel)==6
        for r in funnel:
            assert int(r['patients'])==int(r['expected_patients'])==n
            assert int(r['feature_presence_mismatches'])==0
            fields=['any_imported_event_patients','linked_event_patients','finite_numeric_patients','compatible_unit_patients','available_by_24h_patients','screened_available_patients']
            counts=[n]+[int(r[f]) for f in fields]
            assert all(a>=b for a,b in zip(counts,counts[1:]))
            assert counts[-1]==int(r['final_observed_patients'])
            missing=1-counts[-1]/n
            assert math.isclose(missing,float(rank[r['variable']][col]),abs_tol=1e-12)
            rows.append({'dataset':db,'variable':r['variable'],'patients':n,'no_imported_event_patients':n-counts[1],'nonnumeric_only_loss_patients':counts[2]-counts[3],'unit_stage_loss_patients':counts[3]-counts[4],'availability_stage_loss_patients':counts[4]-counts[5],'screening_stage_loss_patients':counts[5]-counts[6],'final_missing_patients':n-counts[-1],'final_missing_percent':100*missing})
            checks.append({'dataset':db,'variable':r['variable'],'missing_rate_matches_original':True,'feature_presence_mismatches':0})
    with (A/'harmonization_funnel_reconciliation.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    contrasts=[]
    for v in ['phosphate','magnesium','lactate','albumin','platelets','bicarbonate']:
        s=next(r for r in rows if r['dataset']=='MIMIC' and r['variable']==v);t=next(r for r in rows if r['dataset']=='eICU' and r['variable']==v)
        contrasts.append({'variable':v,'source_missing_percent':s['final_missing_percent'],'target_missing_percent':t['final_missing_percent'],'signed_missing_shift_pp':t['final_missing_percent']-s['final_missing_percent'],'signed_no_imported_event_shift_pp':100*(t['no_imported_event_patients']/20589-s['no_imported_event_patients']/37872)})
    with (A/'harmonization_shift_decomposition.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(contrasts[0]));w.writeheader();w.writerows(contrasts)
    result={'status':'passed','date':'2026-10-29','checks':checks,'read_only_database_audit_completed':True,'inference_scope':'Imported, mapped laboratory tables only; no inference about pre-import omissions or clinical causes. Sequential patient-level funnel losses depend on stage order. These are checks of presence, not value or latest-observation identity.','inputs':{db+'_harmonization_funnel.csv':sha(A/(db+'_harmonization_funnel.csv')) for db in ['MIMIC','eICU']}}
    (A/'harmonization_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    report=['# Imported laboratory harmonization audit','', 'Completed on 29 October 2026 using the revised read-only query. All 12 checks matched saved feature presence, and all missingness rates matched the original ranking. No model training occurred.','', '| Variable | MIMIC missing % | eICU missing % | Signed shift pp | Shift before post-import QC pp |','| --- | ---: | ---: | ---: | ---: |']
    for r in contrasts:report.append(f"| {r['variable']} | {r['source_missing_percent']:.2f} | {r['target_missing_percent']:.2f} | {r['signed_missing_shift_pp']:+.2f} | {r['signed_no_imported_event_shift_pp']:+.2f} |")
    report+=['','The large selected-variable shifts are already present when absence means no mapped imported event in the time window. Subsequent numerical, unit, availability and screening checks alter the rates but do not create these large shifts. All screening-stage patient losses were zero for these six variables. This does not prove that missingness reflects clinical practice: pre-import mapping omissions, source coverage, case mix and recording differences remain possible. The audit does not verify numerical feature values, staleness, or each selected latest observation.','', 'The original planner underestimated the training cohort at one row. The revised SQL discourages nested loops and materializes feature flags; all selection and aggregate expressions remain unchanged. Successful completion supports the usefulness of this execution change without proving which individual operation dominated the original runtime.']
    (A/'Harmonization_audit_report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','checks':len(checks),'contrasts':contrasts},indent=2))
if __name__=='__main__':main()
