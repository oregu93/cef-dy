# HOLDOUT_CLEAN_ENERGY_ADMISSION_V1 — emergency checkpoint

Status: `EMERGENCY_STOPPED__SAFE_CHECKPOINT`

Date: 2026-10-19

Base commit: `dc339abbc70b0e355c7e27beada8474d1af0ba5a`

The predefined numerical grid completed before the stop:

- 18 joint shared-centroid models;
- 9 joint block-specific-centroid models;
- 18 single-block models;
- 45 discovery scans / 30 profiles;
- holdout detector access count: 0.

All 18 joint shared-centroid models passed the script's numerical validity
checks. Their centroid range is 17.92222252972972–18.13090493378874 meV and
their covariance statistical-sigma range is 0.08344563151350837–
0.1088397538202497 meV. The nine common-vs-separate-centroid likelihood-ratio
p-values range from 0.06067724926946348 to 0.9942762829345833.

These are checkpoint diagnostics, not a completed scientific admission
decision. No conservative estimate, model systematic, recommended likelihood,
comparison to historical/literature values, or observables-table update has
yet been adjudicated.

Next exact action: read `model_grid.json` and `model_grid.csv`; evaluate the
predefined model ensemble and block diagnostics; then decide PASS versus
`MODEL_DEPENDENT_ENERGY`. Do not rerun the grid unless integrity verification
fails.
