# Full-pipeline robustness amendment — 19 October 2026

Status: exploratory robustness analysis, specified after the first pruning experiment.
This does not constitute an independent confirmatory study or preregistration.

## Question and fixed scope
Repeat uncertainty assessment for the existing 24-hour MIMIC-to-eICU benchmark,
allowing the fitting sample, unlabeled adaptation sample, indicator mask,
preprocessing, model selection, ANN optimization and evaluation sample to vary.
The primary contrast remains external ridge AUROC: targeted minus keep-all.
ANN replication, targeted minus drop-all, internal discrimination, Brier score,
average precision and calibration diagnostics are secondary. No new budget,
threshold, cohort, feature, architecture or outcome definition is selected.
No random-mask models are refitted: those remain descriptive controls in the
original experiment. This amendment evaluates the three anchor strategies.

## Resampling and refitting
200 predetermined paired bootstrap replicates per family. Source training
patients are sampled with replacement; source test patients independently.
Target hospitals are sampled with replacement, then adaptation and evaluation
patients independently within each hospital draw, preserving their original
disjoint partitions. The same hospital draws are used for adaptation and
evaluation, capturing their shared hospital mix. Hospitals without adaptation
patients contribute none to adaptation and retain evaluation patients.
No adaptation outcome is read. All masks depend only on predictor missingness.
The same replicate samples are used for all strategies and both families.

Repeated copies of a source patient remain in the same CV fold and ANN stopping
partition. Use five-fold stratified group CV (patient groups); the original
unresampled fit used ordinary stratified CV. This grouping is necessary to avoid
bootstrap duplicate leakage. Preprocessing and targeted selection are refitted
inside every fitting fold (inside the ANN inner fit for stopping), and again on
the full bootstrap training sample. Final source fits precede scoring within
each family/replicate. Later replicates follow fixed rules regardless of results.

Ridge retains its original nine-C grid and mean CV log-loss selection. ANN
retains its original architecture, optimizer, unweighted BCE, five inner-stopping
fits, median selected epoch and three-member final ensemble. Fold and optimizer
seeds vary deterministically by replicate, shared across strategies. Fit failures
stop the job; they are not silently discarded or replaced by favorable draws.

## Reporting and limitations
Report the original estimates alongside paired percentile bootstrap intervals,
mask frequencies, selected hyperparameters/epochs and replicate completion.
200 replicates is a computational robustness assessment: each 2.5% tail has
approximately five observations, so interval endpoints have Monte Carlo noise.
Do not use these intervals as a precise confirmatory significance threshold.
Report disagreement with the earlier fixed-fit intervals without selecting the
more favorable interval. No source noninferiority claim has an approved margin.
No inference over novel databases, unmeasured data-generation processes, clinical
coding/QC redesigns or alternative architectures is implied. Source is one
database; target hospital inference is within the observed hospital population.
Prior dataset exposure and selection of this question remain disclosed.

## Reproducibility and completion
Separate new output directory; preserve all original evidence. Hash inputs,
implementation and this amendment before fitting. Save aggregate replicate
checkpoints, masks, tuning choices and timings; retain patient data locally.
Write completed.json only after both families have all 200 valid replicates and
summary reconciliation succeeds. Running logs do not establish completion.
The manuscript remains an author-review draft until results and Word output are
updated and verified. Independent confirmation requires genuinely untouched data.
