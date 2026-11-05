# Evaluation implementation clarification

Recorded after predictor-only preparation and during source-only fitting, before any new target score or label evaluation.

- The primary ridge targeted-minus-keep-all external AUROC difference uses5000paired two-stage hospital/patient bootstrap replicates. ANN replication, targeted-versus-drop-all and source-test AUROC diagnostics share the same5000draws for pairing.
- Calibration and Brier diagnostic intervals use the first2000successful paired draws. This is a computational allocation for secondary diagnostics, not a choice made after seeing their values.
- Random controls are20fixed source-fitted models per family. Report every point metric, mean/median/range and the number whose external AUROC exceeds targeted. The empirical spread across masks is not a confidence interval, and no formal superiority over the random-pruning algorithm is established by rank or point means. Do not average their predictions and call it the random-control metric. No best random mask is selected as a new primary comparator or model.
- Preparation hospital inventory:201of207target hospitals have at least one adaptation patient; all207have evaluation patients. The rule is pooled-target adaptation and does not claim hospital-specific adaptation or guarantee benefit at every center. Do not drop the six hospitals without adaptation observations from the evaluation.
- The1000replicate predictor-only mask-stability analysis resamples patients, not hospitals. It assesses sample-level rate-ranking stability conditional on the represented hospital mix. It does not quantify adaptation under a new hospital mixture or refit mortality models.
- A reference-pipeline numeric pass is not independent clinical certification of permissive artifact guards. A fresh full raw timestamp audit was not performed. These limitations stay in the report even if the primary result is positive.
- Internal source losses are reported with confidence intervals. There is no formal clinical non-inferiority margin or equivalence claim. A target gain alongside an internal loss must be described as a tradeoff.

Primary raw feature mapping, cohort, source splits, preprocessing, pruning budget and model settings remain unchanged from the protocol. Source-only fit code identity is already frozen; scoring/inference identities are recorded before target outcomes are evaluated. Historical data/outcome exposure remains disclosed.
