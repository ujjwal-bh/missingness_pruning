# Reproducibility

## What can run without the datasets

`python tools/run_tests.py` runs the 13 historical method tests in a temporary workspace with synthetic data. The summary test receives invented constant metric rows, not the published study results. No training is performed.

`python tools/check_repository.py` checks source syntax, unchanged Python syntax trees after comment cleanup, reference source hashes and the absence of research-data file formats in this release.

The statistical verification tools require the separate aggregate evidence companion. Its layout is:

```text
EXTERNAL_EVIDENCE_ROOT/
  SHA256SUMS.json
  aggregate_results/
    original/
    preparation/
    full_pipeline/
    focused_amendment/
    ...
```

Run `python tools/verify_results.py --evidence-root EXTERNAL_EVIDENCE_ROOT`. The original checker reconstructs 40 full-pipeline intervals, 60 fixed-model metric intervals and eight AUROC contrasts, and checks 400 checkpoint hashes. The focused checker reconstructs 60 full-pipeline and 60 fixed-model contrast summaries, checks 6,000 selector draws and reconciles 12 imported-laboratory checks. These are separate scripts within the same computational workflow, not independent external statistical review.

No aggregate evidence is automatically downloaded, generated from private records, or committed to Git. A release of those files would require a separate deliberate decision.

## Refitting from restricted exports

1. Install compatible dependencies and run the synthetic tests.
2. Obtain authorized feature exports separately. The file receipts in `config/` define the expected bytes.
3. Run `tools/prepare_workspace.py` with a new work directory outside this repository. It verifies input hashes before copying records.
4. Run the explicit `prepare`, `train`, `evaluate` and `robustness` stages in that order through `tools/run_study.py`.
5. Review verification records within the private run. Never copy its prediction rows, model weights, patient partitions or logs into this repository.

The code layout is mapped to the original flat workspace by `provenance/workspace_layout.json`. Historical statistical Python syntax trees were preserved, including source hash checks, sample sizes, thresholds, seeds and model settings. A comment cleanup changes file hashes and therefore creates new run identities. It does not authorize rewriting the identities of previous fitted artifacts or resuming an old run with altered code.

The ordinary source-training folds differ from the grouped folds used in bootstrap refits, where duplicate patient copies must stay together. Retain this distinction when interpreting the refitting distribution. Seeds alone do not guarantee bitwise replication across machines or numerical library versions.

## Focused amendment and database audit

The private workspace also contains `pruning_focused_amendment.py`, `verify_pruning_focused_amendment.py` and `reconcile_pruning_harmonization_audit.py`. Run the focused amendment only after the original inference outputs and full-pipeline verification exist. It requires local prediction-draw arrays and adaptation predictors; it creates no mortality-model fits.

The database audit generator and executed revised read-only SQL are in `source_preparation/audits/`. They contain historical PostgreSQL and output paths. Review them in a private workspace before use. Enter any database password locally through PostgreSQL's prompt or your own local connection setup. No password should be added to code.

Reconcile the audit only after the six-row output from each database is present in the focused result directory. The historical amendment script initially records the audit as pending; do not imply a fresh run completed its audit until its actual output has been checked. The aggregate-only verifier can check the already supplied audit evidence without a database connection.

## Scope of validation for this repository

The organization task ran syntax/source checks, synthetic method tests and reconstruction of the existing aggregate evidence. It did not repeat mortality-model training, reinstall the pinned dependencies from the internet, or reconstruct a fresh PostgreSQL database from raw MIMIC/eICU files. The raw-data reconstruction remains historical provenance, not a certified clean-machine installer.

The publication Word files and reference-verification package remain in the separate manuscript distribution. Document authoring tools, rendering caches, backups, superseded experiments and workstation runtime folders are intentionally excluded from this focused analysis repository.
