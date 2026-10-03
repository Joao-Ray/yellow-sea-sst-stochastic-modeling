# Project status — 2026-10-03

## Completed locally

The project now has a reproducible exploratory observational pilot, in addition
to the offline synthetic workflow. Software includes training-only seasonal
preprocessing, calendar-aware persistence/climatology/AR(1)/AR(p) forecasts,
validation-only order selection, exact OU interpretation, common-support
chronological scoring, conditional intervals, paired calendar-block skill
intervals, residual diagnostics, and Chinese/English reports.

The frozen design in configs/pilot.json was saved before test-score inspection:

- Domain: 31–39 N, 117–127 E; cosine-latitude-weighted ocean cells. This rectangle
  includes neighboring seas and is not a final geographical Yellow Sea boundary.
- Official NOAA PSL acquisition: 192 monthly files, approximately 33 MiB,
  2010-01-01 through 2025-12-31. Every file has a verified checksum and source URL.
- Regional daily series: 5,844 finite values; no missing or interpolated days.
- Training: 2010–2019; validation: 2020–2022; test: 2023–2025.
- Candidate orders: 1/3/7/14; validation 7-day RMSE selected AR(1). Training
  coefficients remain frozen. Each test horizon has 1,096 common scoring dates.
- Skill intervals: 500 paired circular calendar-block replicates, 30-day blocks,
  seed 42. Dependence, nonstationarity, and block sensitivity remain limitations.

## Initial observational findings

| Horizon | Persistence RMSE (°C) | Selected AR(1) RMSE (°C) | Skill | 95% skill interval | AR interval coverage |
|---:|---:|---:|---:|---|---:|
| 1 day | 0.1503 | 0.1537 | -2.2% | [-4.7%, -0.2%] | 97.0% |
| 7 days | 0.5665 | 0.5767 | -1.8% | [-8.8%, 3.7%] | 86.4% |
| 30 days | 0.9086 | 1.0242 | -12.7% | [-29.0%, 3.8%] | 84.9% |

There is no observed improvement over persistence in this test segment. The
7/30-day skill intervals include zero. Conditional Gaussian intervals under-cover
at those horizons. Training AR(1) residuals retain lag-one correlation of 0.390,
and the Q–Q plot shows tail departures. These outputs motivate additional
model and calibration work; they do not establish robust regional conclusions.

## Verification

- All 43 unit/regression tests passed locally on Python 3.11.
- The synthetic NetCDF-to-report demo and complete observed pilot ran locally.
- Generated overview and residual/coverage figures were visually checked.
- A 2010-01-01 PSL regional grid matched the NCEI v2.1 grid to 1e-5 °C,
  including the missing-cell pattern; a 2022 seven-day sample was also checked.
- A netCDF4 import emits one NumPy binary-size RuntimeWarning during tests in
  this macOS environment. It persists with netCDF4 1.7.4; IO, numerical checks,
  and the complete pilot passed. The warning is retained and not suppressed.

## Remaining research work

1. Specify a justified marine boundary and compare region definitions.
2. Fit and validate trend-aware or smoothed-seasonal alternatives; preserve
   this initial pilot and label changes informed by its test scores exploratory.
3. Repeat independent periods and block lengths; inspect year-level errors and
   interval calibration before making model-superiority claims.
4. Consider richer statistical/learning models under a predeclared protocol.
5. Draft a manuscript only after these assumptions and robustness checks are
   resolved. OU duplicates AR(1)'s transition and is not another competitor.

Raw/derived data, fitted parameters, and generated reports remain in ignored
local data directories. Source, tests, and documentation are prepared for a
draft pull request; the main branch is updated only after review and merge.
