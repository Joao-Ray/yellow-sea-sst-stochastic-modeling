# Northern ECS observation-source verification

This phase fixes predictions and scoring before evaluating the previously unscored destination subset of existing AMSR2 and iQuam caches. It is a conditional geographical extension after earlier OISST and source-instrument outcomes were known. The rectangular source files already included the destination, so this is not a pre-acquisition freeze or blind holdout.

The locked package covers 230 northern Eastern China Sea cells, 1,339 dates from 2023 through August 2026, and thirteen methods at 1/7/30 days. Four transferred ridge/tree forecasts and five fixed regional references use their existing prediction files. Four additional grid references use only 2010–2019 seasonal/trend fits and the previously estimated regional AR(1) coefficients. No outcome-based tuning is permitted.

Primary comparison is 2023–2025 nighttime AMSR2: two anomaly models × three leads × three simple baselines (projected source AR(1), grid source AR(1), grid climatology), an eighteen-comparison Holm family separately per 30/60-day block choice. Each primary year needs 120 scored dates and every scored satellite day needs twenty valid cells. Thresholds are fixed; insufficient coverage suppresses primary inference. Other models, afternoon, matched OISST, partial 2026 and buoy outcomes are descriptive.

Buoys use the previously locked monthly iQuam versions and quality/matching rules, plus a strict exclusion of observations within 20 km of any original source-region cell. This prevents reusing the earlier source matching support. Each buoy year needs sixty nighttime dates; failure is reported. Quality-control reference and possible OISST assimilation overlap prevent a latent-truth independence claim. NOAA's known human-monitoring interruption remains relevant.

- `frozen_protocol.json`: exact rules, forecast fingerprints, input/software hashes and prior-output protection.
- `source_manifest.json`: previously acquired instrument file identities and acquisition times, without examining new scores.
- `grid_parameters.json`: fixed training-only grid coefficients and copied regional decay values.
- `public_lock.json`: added after the remote protocol bytes are verified, before evaluation.
- `results/`: added after scoring, including complete coverage and failures.

Reproduce with `python -m src.destination_validation prepare`, then verify the public lock, run `python -m src.destination_validation evaluate` and `python -m src.destination_validation deliver`. Forecast arrays and daily losses accompany the local reproducibility package.

Chronology correction: a previous process-transfer audit described destination satellite observations as not acquired. The full rectangular cache already contained their cells; destination scores had not been produced. The original audit is retained, and this correction is explicitly recorded in the new protocol.


## Completed evaluation and audit

The 2023–2025 nighttime AMSR2 support has 896 dates (297/296/303 per year) and
113,190 cell-date pairs. Nighttime buoys have 1,051 dates, 43,889 records and
29 platform-type/ID combinations after excluding previous source matching support.
At thirty days, anomaly ridge/trees have satellite RMSE 1.8252/1.8213°C against
1.6006°C for fixed grid source AR(1); buoy values are 1.4678/1.4827°C against
1.2113°C. Complex regional transfer is not supported over the spatial decay reference.
All eighteen primary contrasts, methods, annual/seasonal and partial-year results
are retained in `results/`. `independent_audit.json` independently checks extraction,
matching and weighted daily scoring. Near-bisector candidate ranking preserves the
locked float32 cell-angle conversion; exact record/cell assignments are required.
The integrated manuscript/SI and Chinese assessment explain the inference boundaries.
