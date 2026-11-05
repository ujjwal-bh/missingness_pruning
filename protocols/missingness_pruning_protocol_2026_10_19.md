# Missingness indicator pruning study protocol

Date 19 October 2026. Status: preparation and audit protocol locked before fitting the proposed targeted-pruning models. The researcher authorized starting the proposed study after its limitations were discussed. The MIMIC/eICU datasets and many earlier outcome-linked results have already been examined. This is an exploratory, target-informed adaptation benchmark, not a preregistered discovery, a pristine external validation, or a new deployment-ready method. Existing files and models remain unchanged.

## Primary question and target

At a24h ICU landmark, does deleting a fixed budget of explicit missingness indicators with the largest absolute source-target missingness-rate differences improve target-evaluation AUROC relative to retaining all indicators? Quantify source performance cost and target calibration separately. Do not infer a causal missingness mechanism, a clinical benefit, universal improvement or novelty from a positive contrast.

Primary family: unweighted ridge logistic regression, selected for transparent, inexpensive assessment of the indicator intervention. Secondary replication: the existing compact ANN architecture. No model-family winner is selected using target outcomes. The primary comparison is targeted pruning versus keep-all for ridge; other comparisons and ANN are secondary exploratory diagnostics. A new independent replication would be required for stronger confirmation.

## Fixed reference data rather than simultaneous data redesign

Use the hash-verified existing26-concept feature exports at24h, preserving approved adult eligibility, one selected hospitalization/ICU episode per patient, hospital mortality outcome, source patient splits and available-by-landmark feature rules. There is no cross-landmark episode-switching contrast in this study. Missing means absent in the final harmonized analysis table, including source absence, timing restrictions and rejected/unsupported measurements; it is not necessarily a test that was never ordered.

The reference uses latest valid available measurement from ICU entry through24h, age capped90 and existing recorded-sex encoding. Original screened clinical measurement values are preserved in the exports, followed by source-fitted0.5/99.5percentile clipping, median imputation and standardization during fitting. The same transformations are applied to the target; no target medians, caps or scaling are learned. Do not add trajectories, new predictors, labels or exclusions while comparing indicators. The26clinical input values remain in every strategy.

This resolves the earlier design review for this bounded benchmark by holding its reference pipeline constant; it does not declare every earlier choice optimal. The lab artifact guards include permissive upper bounds, and there is no independent clinical certification of all retained extreme values. Prepared exports do not contain all per-feature timestamps, so a new raw availability/staleness audit cannot be claimed. Mapping, units, cohort reconstruction and prior timestamp-audit provenance must be checked before any fitting. If hash/alignment/finite/rule checks fail, stop for a versioned repair before performance evaluation. Broader clinical redesign, all-episode selection, fixed-horizon mortality, alternate imputation or post-discharge outcome reconstruction are outside this initial benchmark.

## Label-free target partition and selection

Use SHA256 of UTF8 `missingness_pruning_adaptation_v1|eicu|patient_id`; interpret the first32bits as unsigned. Values below858993459 enter adaptation (approximately20%); all others enter target evaluation. All records from the same patient share partition. This is a reproducible adaptation/evaluation split of previously examined data, not a way to erase historical outcome exposure. The target cohort and eligibility labels originated in prior data preparation; label-free here refers to the new partition, pruning, adaptation and model-selection procedure, not the historical cohort construction.

The preparation/selector loader must not parse any target outcome column. It may read patient/stay/hospital keys, landmark/split and26predictor columns. The selector receives source-fitting and target-adaptation predictors only, with no outcome or identifier columns. Target-evaluation rates or labels do not choose the deletion set, its budget, its seed or any hyperparameter. Source validation/test predictors do not determine the deletion set. Target-evaluation keys may be counted and hashed for integrity only. Keep target evaluation out of model-fitting/stopping code.

Define source missingness as the proportion missing among source fitting patients; target missingness among target adaptation patients. Primary discrepancy for each measurement is the absolute difference of those proportions. Rank descending; break exact ties by variable name. Candidates are the24vital/laboratory indicators. Age/sex flags are excluded from targeted/random pruning because they are demographic recording fields rather than clinical measurement availability. The primary budget is six (one quarter of24), an explicit engineering design choice, not a clinically optimal or outcome-selected number. Always apply this fixed rule; do not search budgets/thresholds against target AUROC. Recompute the source side of the ranking within each source training fold; use all source training patients for the final model mask.

## Comparison strategies

1. Keep-all:26clinical values plus26explicit flags (52inputs).
2. Targeted:26clinical values plus20flags (46inputs); remove the six ranked measurement flags.
3. Drop-all:26clinical values, no flags (26inputs).
4. Random-budget controls:20fixed unique uniformly drawn subsets of six of the24measurement flags, seed2026101906, preserving demographic flags (46inputs). The random draw is independent of outcomes and missingness rates; it is not restricted to remove informative flags. Report this limitation and all20results, never only the best random mask. Summarize mean/median/range of model metrics across masks, not mean prediction unless a separate ensemble were explicitly defined (none is planned).

The same source fitting data, clinical value preprocessing, CV folds and model-development budget apply to all strategies. Deleting a flag requires a source refit. Do not just set target flags to zero inside a model trained with those flags.

## Future fitting specification and evaluation gate

No fitting is part of the preparation command. After successful preparation/audit, fitting must use this written specification and a frozen executable identity before any new target scores are examined.

Ridge C candidates:0.0001,0.001,0.01,0.1,1,10,100,1000,10000;5fold source-training CV stratified by mortality, seed20261015, choose mean held-out log loss, smaller C for an exact tie. All preprocessing and source-rate ranking fitted within fitting folds, using the unchanged unlabeled adaptation set. Class weight1. No target-loss selection, balancing, external recalibration or threshold search. Source folds never span a patient across fit/held-out.

ANN replication: hidden64/32, ReLU, batch normalization, dropout0.1, BCE, AdamW, lr0.001, weight decay0.00001, batch1024 and gradient norm clip5. These previously source-chosen optimizer/architecture values remain fixed across strategies. Five source-training folds; each fitting fold has its own15% stratified stopping subset, seed20261015+fold; source preprocessing and ranking use the inner fitting subset only. Early stopping AP, patience10, minimum improvement0.0001, maximum100epochs; median best epoch across folds for final fits on all source training patients. Final seeds20261016/17/18, equal mean probability; report seed dispersion. Each strategy gets its own source-selected epoch count, so this is a comparison of complete fitted pipelines, not a pure fixed-coefficient indicator intervention. No architecture search or external choice of a lucky seed/mask.

The primary endpoint is AUROC(targeted ridge)-AUROC(keep-all ridge) on the same target-evaluation patients. Calibration intercept/slope and Brier/log loss are specified secondary metrics, with no external prediction updates. Compare targeted against drop-all and random masks to evaluate whether the shift rule adds value beyond generic indicator deletion. Report source test AUROC/calibration differences with paired intervals. No formal non-inferiority claim or invented margin: a clinically or operationally justified margin has not been supplied. A positive AUROC difference alone does not establish better calibration or preserved source performance.

Use5000paired conditional bootstrap replicates for the primary contrast. At this single landmark, each target patient contributes at one hospital: resample hospitals and then patients within each sampled hospital; preserve pairing across strategies. Source intervals resample patients. Report hospital counts and heterogeneity, not a guarantee that pooled benefit occurs at every hospital. Fit/selection/adaptation-sample uncertainty is not included in these intervals. A separate1000replicate label-free source/adaptation patient-bootstrap diagnostic assesses mask stability and ranking uncertainty; it does not change the locked mask or substitute for full algorithm uncertainty. Target-hospital-specific adaptation and an entirely independent test dataset are later extensions, not completed validation.

## Reproducibility and interpretation

Output root `model_preparation/missingness_pruning_2026_10_19_v1` for protocol/config snapshots, partition manifest, label-free missingness/ranking tables, random masks, audit results and selector stability. Restricted identifiers stay only in clearly labelled local files. Models and results, if subsequently fitted, use a separate versioned result directory. No database mutations or deletion are necessary. Code, plan and source file hashes, package versions, commands and failures are recorded. A label-poisoning test must establish selector output invariance and unexpected-column rejection; masks may not depend on target labels, variable order or input row order.

Continue to disclose historical exposure and the unresolved historical data-flow/ethics review. There is no guarantee of higher precision/recall, improved calibration, publication, novelty or clinical usefulness. Preserve negative, inconclusive and source-harm findings. An externally positive but source-damaging result must be reported as a tradeoff. Similar performance to drop-all is not proof that rate-based selection adds value.

## Closest precedent and novelty boundary

Domain Adaptation under Missingness Shift (Zhou et al2023) studies labeled source/unlabeled target adaptation and includes eICU examples: https://proceedings.mlr.press/v206/zhou23b.html . Robust prediction under missingness shifts (Rockenschaub et al2024 preprint) studies when informative missingness does not transport: https://arxiv.org/abs/2406.16484 . Missing-indicator development/deployment assumptions are addressed in Sisk et al2023: https://pmc.ncbi.nlm.nih.gov/articles/PMC10515473/ .

A focused search did not establish whether this exact six-indicator rate-ranking rule has already been evaluated. That absence is not evidence of novelty or a first-in-literature claim. The proposed contribution is an interpretable empirical rule comparison under a stated target-informed protocol, pending a deeper related-work review and independent validation.
