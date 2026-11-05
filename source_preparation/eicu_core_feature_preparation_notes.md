# eICU core candidate feature preparation

MIMIC core candidate counts and coverage are confirmed in mimic_core_candidate_features_confirmed.json/.md. Equivalent eICU core processing is prepared but not yet executed. No models are fitted.

Run run_eicu_core_features.ps1. It streams vitalPeriodic, vitalAperiodic and lab compressed files, retains required columns/variables in the 0-to-48-hour windows of the union of selected eICU stays, and checkpoints completed source tables. General lab features exclude labtypeid 7 blood-gas rows except for mapped blood lactate, matching the chemistry/hematology source intent in MIMIC. Late revision offsets are retained raw but excluded from an earlier feature window.

The local hospital-priority selection is checked against the confirmed patient/death totals. A temporary cohort import then compares exact patient/stay/landmark/outcome rows with the current database view before measurement import. A mismatch stops the transaction. This avoids extracting under one selection rule while using another database cohort.

Three selected source tables are imported: core_vitalperiodic_source_v1, core_vitalaperiodic_source_v1 and core_lab_source_v1. The source rows remain in PostgreSQL for traceability and further feature audits. The original compressed files remain unchanged. The script creates core_features_candidate_v1 with the same 26 core concepts as the MIMIC candidate, preserving missing values and all primary-cohort rows.

Use the same finite-value and artifact bounds. Periodic temperature is already Celsius. Periodic sao2 represents monitor SpO2, not a blood-gas saturation. Pressure uses the latest valid arterial or noninvasive observation with arterial priority at equal times. Exact-time duplicates are averaged. Source offsets and last revision are restricted through each landmark, with no future imputation.

Vital-periodic and aperiodic observationoffset denotes the time data entered eCareManager. There is no separate event/entry history equivalent to MIMIC charttime/storetime. Treat the recorded offset as both observation and availability proxy and report this limitation. Periodic observations are archived five-minute medians and can be noisy; they are not the same measurement process as all clinician-entered MIMIC observations. MIMIC/eICU event-time-only timing sensitivity should be considered after the full pipeline is finalized.

Sources: https://raw.githubusercontent.com/MIT-LCP/eicu-code/main/website/content/eicutables/vitalPeriodic.md ; https://raw.githubusercontent.com/MIT-LCP/eicu-code/main/website/content/eicutables/vitalAperiodic.md ; https://raw.githubusercontent.com/MIT-LCP/eicu-code/main/website/content/eicutables/lab.md

Lab values require a recognized system unit and a compatible recognized interface unit or missing interface unit. Unit aliases are analyte-specific, including monovalent mEq/L/mmol/L equivalence and scaled count units. Unrecognized or contradictory interface labels are conservatively omitted from candidate features pending unit review, not treated as normal values or silently rescaled. Report their raw combinations in Result 3. The same labels should not be assumed to have identical numerical units when source fields disagree. This is a candidate compatibility rule; final lock depends on coverage/QC.

Only core vital/lab tables are included now. Periodic temperature may have lower coverage because it requires an interfaced probe. Nurse-charted temperature and GCS/treatment sources still require mapping and may be added before the final predictor dictionary is locked. Do not call this candidate model input the complete final predictor set or train the final model yet.

The build uses indexed per-stay queries rather than a massive long-format vital unpivot. It still scans large compressed files during preparation and may take substantial time. Preparation stops at 60 GB staging or less than 10 GB free; import/build checkpoints estimate remaining staging plus database size and WAL growth, stopping above 90 GB to reserve overhead within the overall 100 GB budget. These are checkpoint checks rather than a hard filesystem quota.

The source import and feature construction share a transaction. Row counts and exact cohort rows/outcomes are verified before commit. On failure the transaction rolls back and staged CSVs are preserved. A successful run deletes only the three verified staged measurement CSVs after completion; it preserves source compressed files, the expected cohort CSV and manifests. Existing candidate/source tables are never overwritten. The final outputs are cohort counts, feature coverage and raw lab unit combinations.

Files prepared locally; PostgreSQL execution remains pending. No external predictive performance has been used to select variables, rules or parameters.
