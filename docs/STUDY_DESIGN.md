# Study design

The intervention is a source-model refit after deleting six explicit measurement-missingness indicators selected using unlabeled target predictors. It does not delete clinical values or change the mortality threshold.

## Population and outcome

Adult patients must satisfy the existing 24-hour ICU and hospitalization landmark rules. Among eligible hospitalizations, a deterministic outcome-independent hash selects one hospitalization per patient; the earliest eligible ICU stay within that hospitalization contributes. This retrospective contribution rule is not chronological first-ever admission selection.

The outcome is recorded in-hospital death after the landmark during the selected hospitalization. MIMIC uses hospital mortality status and recorded death timing. eICU lacks exact death timestamps; discharge statuses and offsets are administrative proxies for eligibility. Post-discharge mortality is not inferred.

## Predictors and strategies

All strategies retain 26 values: age capped at 90, recorded female-sex encoding, seven vital signs and 17 laboratory measurements. Values are the latest valid available observations between ICU entry and 24 hours, under the archived mapping, unit and availability rules.

Preprocessing is learned within source fitting samples: percentile clipping for measurement values, median imputation and standardization. Missingness flags are defined before imputation. The selector ranks the 24 measurement flags by absolute missingness-rate difference between source fitting patients and the target adaptation partition, with alphabetical ties.

| Strategy | Explicit flags | Total input columns |
| --- | ---: | ---: |
| Keep all | 26 | 52 |
| Targeted | 20 | 46 |
| Drop all | 0 | 26 |
| Random budget controls | 20 | 46 |

Age and sex flags are not candidates for targeted/random deletion. Twenty fixed random masks per family supply descriptive controls. The deletion budget of six is fixed and is not established as an optimum.

## Development and evaluation

The source-training partition contains 37,872 patients; source validation contains 8,245 and is unused for fresh tuning; source test contains 8,149. Target adaptation contains 20,589 patients and target evaluation contains 82,748. Target outcomes do not select flags, preprocessing parameters or hyperparameters. Adaptation and evaluation patients are disjoint, but their hospitals overlap.

The primary model family is unweighted ridge logistic regression, with five-fold source-only tuning by log loss. The secondary neural network uses two hidden layers, batch normalization, dropout, unweighted binary cross-entropy, AdamW and source-only early stopping. Final ANN probabilities average three seeds. See the executable code and dated protocols for every parameter.

The primary endpoint is targeted-minus-keep-all external ridge AUROC. Other discrimination, probability error and calibration comparisons are secondary. Initial intervals condition on fitted models and masks. The subsequent 200-draw paired full-pipeline bootstrap repeats training, tuning, preprocessing and selection. Its percentile tails have limited Monte Carlo precision.

## Focused amendment

The post-review amendment derives drop-all-minus-keep-all contrasts from saved draws, summarizes bootstrap shape, compares targeted scores with the fixed random-mask mean, and isolates selector sensitivity using 2,000 outcome-free draws for each of three source-fixed target resampling schemes. It does not add mortality-model refits.

The imported-laboratory audit checks presence for six variables in source training and target adaptation. It cannot inspect pre-import omissions, establish a clinical cause for missingness shifts, or certify each numerical value and latest-observation choice.

## Interpretation

The targeted rule did not demonstrate external benefit under broader pipeline uncertainty. Historical use of both databases limits confirmatory claims. This study does not establish equivalence, a general optimal missing-data strategy, unseen-hospital transportability or clinical deployment readiness. Code organization and comment cleanup on 5 November 2026 did not rerun or change the reported experiments.
