# Nursing temperature integration — prepared 2026-10-15

Status: preparation code and SQL generation locally checked; full extraction and PostgreSQL execution pending researcher run. No temperature coverage improvement has yet been demonstrated.

## Decisions

1. Preserve candidate v1 and lab-corrected v2. Build candidate v3 by changing only temperature; keep raw nursing fields for audit.
2. Scan the full compressed nurseCharting source, retaining all explicitly labelled Temperature (C) and Temperature (F) rows for selected ICU stays and event offsets 0–2880 minutes. No patient or observation sampling is used for the extraction. Other labels remain outside this focused extraction and require later coverage review.
3. Parse only strictly numeric text (bounded string length), use explicit unit labels, and convert F to C with (F−32)/1.8. Use the existing >10 and <50 Celsius screening bounds. Free-text qualifiers are not guessed or stripped into numbers.
4. Require a known nursing entry offset. Availability is max(event offset, entry offset); both event and availability must be within the landmark. Early entry timestamps are flagged but not assumed to make a future event available. Retain late-entered raw rows for auditing rather than using them before they were entered.
5. Celsius and Fahrenheit entries may represent duplicate forms of the same observation. Group by stay, event offset and availability offset. Average valid exact-group values separately by labelled unit. Prefer Celsius, falling back to converted Fahrenheit. When both group means exist and differ by more than 0.2 C, exclude the group from candidate temperature and report it. The 0.2 C threshold is a prespecified candidate consistency check allowing ordinary paired-form rounding, not a physiological screening boundary. Unit forms entered at different availability times are treated as separately available records; this rule does not claim verified identity of every observation.
6. Combine valid nursing groups with the existing monitor temperature source. Select latest event time available by landmark; prefer monitor only on an exact event-time tie, then latest availability within source. Retain monitor-only temperature if no nursing observation qualifies. A more recent valid nursing event may replace an existing monitor-derived value; report changed values.
7. Before committing, assert identical patient/stay/outcome/non-temperature features versus v2 and no loss of a previously observed temperature. Report cohort/death counts, before/after temperature coverage, source text/time quality counts and paired-unit disagreements. These are candidate validation outputs; large disagreement or unexpected coverage still needs review.

## Files and command

`prepare_eicu_nursing_temperature.py` prepares a small focused CSV and manifest, then generates transactional SQL. It checks the retained selection CSV against candidate v2 in PostgreSQL. A completed extraction can be reused only if source metadata, cohort SHA256 and staged-file metadata still match. Incomplete extraction restarts safely; no import is attempted after preparation failure.

Staging stops above 10 GB or below 10 GB free space. SQL checks a conservative database-plus-six-times-CSV storage estimate against 90 GB before import. This is an estimate, not a hard total filesystem/WAL limit. No full nurseCharting table is imported. The focused CSV is retained until results are reviewed, then can be deleted after successful import verification.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Lenovo\Documents\Ujjwal\Masters application\research\run_eicu_temperature_features.ps1"
```

The Python phase scans the source and writes staging files. The PostgreSQL password prompt starts the import/build phase. Return all four result tables. Do not rerun the earlier core import or lab correction.

## Sources and evidence

The local first-500,000-row discovery found explicit unit names and paired forms; saved in `eicu_temperature_discovery_sample_2026_10_15.json`. Discovery is not a coverage estimate. Official eICU nurseCharting documentation distinguishes chart/event offset from entry offset and describes the value as free text: https://raw.githubusercontent.com/MIT-LCP/eicu-code/main/website/content/eicutables/nurseCharting.md

No model fitted. GCS, treatment domains and final predictor lock remain pending.
