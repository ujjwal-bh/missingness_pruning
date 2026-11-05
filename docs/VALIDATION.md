# Repository validation on 5 November 2026

The organization task preserved the original research workspace and created a separate Git repository for the missingness-pruning study. No mortality models were trained and no database queries were executed.

Checks completed:

- All 13 historical method tests passed using synthetic arrays and invented metric fixtures in a temporary private workspace.
- All 38 copied Python files retained the syntax trees of their source versions. Two redundant comments were removed; methodological and data-handling notes were retained.
- All nine hash-bound source-reference artifacts matched their original audit hashes.
- Original aggregate evidence verification passed, including 400 checkpoint hashes and the original interval summaries.
- Focused aggregate evidence verification passed for 60 full-pipeline and 60 fixed-model summaries, 6,000 selector draws and 12 laboratory-presence checks.
- The repository checker found no dataset, weight, prediction or exported-result files in the release, and its credential-pattern checks passed.
- Git exclusions cover data, weights, caches and credential files. The intended source-preparation SQL templates remain includable. Line-ending conversion is disabled to protect hash-bound artifacts.
- A dry run of Git staging listed the intended code/documentation files only. No commit, remote setup or push was performed.

The separate local evidence companion contains aggregate results only. Existing raw data, patient exports and fitted models remain in their original local locations. The dependency environment was reused for validation; a clean installation and a new raw-source PostgreSQL reconstruction were not performed. Automated credential-pattern checks are limited and do not replace inspecting future files before staging.
