# Missingness indicator pruning for ICU mortality prediction

Analysis code for **Pruning missingness indicators by marginal rate shifts for ICU mortality prediction**, an exploratory MIMIC-IV to eICU-CRD study by Ujjwal Bhattarai and Kriti Sharma.

The study asks whether removing the six measurement-missingness indicators with the largest absolute source–target missingness-rate differences improves external mortality prediction. Models are developed in MIMIC-IV. Unlabeled eICU adaptation predictors select indicators; a separate eICU patient partition is used for evaluation. The fixed landmark is 24 hours after ICU entry.

The primary comparison did not demonstrate an external AUROC benefit from targeted pruning over keeping all indicators after accounting for broader training and selection uncertainty. These analyses are exploratory because both databases and earlier outcomes had already been examined. The dated internal specification is not an independent preregistration.

## Repository layout

```text
analysis/             Model fitting, selection, scoring, inference and shared utilities
tests/                Synthetic tests of selection, resampling and evaluation methods
config/               Predictor scope, mappings and validated-export receipts
protocols/            Initial specification and subsequent amendments
source_preparation/   Historical extraction, cohort and feature-building scripts and SQL
tools/                Portable workspace, test, execution and verification commands
docs/                 Study design, data reconstruction and reproduction guidance
provenance/           Source hashes, working-layout mapping and code-cleaning record
```

**No datasets, patient rows, model weights, predictions or result tables are stored in this repository.** Code and configuration contain variable names, hash seeds, expected cohort counts and file-integrity receipts. Those are required to describe the study. Actual records and generated results belong in a separate private folder. `.gitignore` excludes common research-data formats as a second layer of protection.

## Environment

Python 3.12 was used. Install the observed dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` records versions from the historical analysis environment; installation on a new machine has not been tested. PyTorch availability depends on the Python/OS combination. CPU execution is sufficient. Numerical libraries and hardware can affect optimization and early stopping, so fixed seeds do not guarantee bitwise-identical refits on every platform.

## Run the method tests without data

```powershell
python tools/run_tests.py
python tools/check_repository.py
```

The first command creates a temporary external workspace and runs the 13 historical tests with synthetic arrays and invented metric fixtures. It does not read patient data or train mortality models. The second checks the tracked release contents, Python syntax, source-code equivalence and data exclusions. It does not scan or upload your raw datasets.

## Reproduce from validated feature exports

MIMIC-IV 3.1 and eICU-CRD 2.0 require separate authorized PhysioNet access. See [source reconstruction](docs/SOURCE_DATA.md) for the historical extraction order. The following example assumes the two validated CSV exports already exist in a **separate** research folder:

```text
D:/private/research/model_preparation/mimic_candidate_features.csv
D:/private/research/model_preparation/eicu_candidate_features.csv
```

Create a new private run outside the repository:

```powershell
python tools/prepare_workspace.py --research-root "D:/private/research" --work-dir "D:/private/pruning-run-01"
python tools/run_study.py --work-dir "D:/private/pruning-run-01" --stage prepare
python tools/run_study.py --work-dir "D:/private/pruning-run-01" --stage train
python tools/run_study.py --work-dir "D:/private/pruning-run-01" --stage evaluate
python tools/run_study.py --work-dir "D:/private/pruning-run-01" --stage robustness
```

Run the stages in order. `prepare_workspace.py` checks the original export SHA256 values and refuses to overwrite an existing run. Preparation reads no outcome labels for indicator selection. Training fits both families and all 23 strategies per family. Evaluation records an implementation identity before scoring. Robustness repeats the three anchor pipelines in 200 paired bootstrap replicates per family and can take many hours. No stage runs automatically merely by cloning this repository.

The historical full-export hashes include multiple landmarks and unused extension fields, even though this study reads only 24-hour core features. An equivalent newly serialized table may have different bytes. Do not disable the hash checks: a changed export requires a new documented identity and audit.

The private run recreates the original flat working layout expected by the analysis modules. This keeps their statistical behavior intact while placing all new patient-level files and model outputs outside Git. Code cleanup removed redundant comments without changing Python syntax trees; the exact transformation record is in `provenance/code_cleaning.json`. Hash-bound source-preparation files are preserved verbatim so their reference checks remain valid. `.gitattributes` prevents automatic line-ending conversion from breaking those hashes on another OS. Historical output records cannot be reused as if generated by these newly hashed code files.

## Verify the existing study results without patient data

Aggregate evidence is distributed separately. Supply an external evidence folder containing `aggregate_results/`:

```powershell
python tools/verify_results.py --evidence-root "D:/private/pruning-evidence"
```

This reconstructs the original and focused contrast summaries, checks 400 aggregate refitting checkpoints, checks 6,000 selector-only draws and reconciles the 12 imported-laboratory presence checks. It does not train models. The archive structure is described in [reproducibility](docs/REPRODUCIBILITY.md). Result files are deliberately excluded from this repository, including aggregate CSV tables.

## Methods and limitations

- Same 26 clinical values for all strategies: demographics, seven vital signs and 17 laboratories.
- Keep-all: 52 inputs; targeted deletion: 46; drop-all: 26.
- Primary family: unweighted L2-regularized logistic regression. Secondary family: a compact neural network trained with unweighted binary cross-entropy.
- Twenty random six-indicator deletion masks per family are descriptive controls.
- Source-only preprocessing and tuning; target outcome labels do not choose masks or model settings.
- Target adaptation and evaluation have disjoint patients but overlapping hospitals. This is not unseen-hospital validation.
- A subsequent refitting amendment and focused evidence checks are distinguished from the initial specification. No equivalence or non-inferiority claim is supported by an interval spanning zero.

See [study design](docs/STUDY_DESIGN.md) and the dated [protocols](protocols/). The pruning experiment does not include the earlier landmark-comparison experiments or later model-performance exploration.

## Authors

Ujjwal Bhattarai and Kriti Sharma, independent researchers, Kathmandu, Nepal. Correspondence: bhattaraiujjwal26@gmail.com. sharma0100kriti@gmail.com