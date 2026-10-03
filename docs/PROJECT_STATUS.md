# Project status — 2026-10-03

**Complete exploratory research version.** Source, configuration, tests,
reproducible acquisition, actual backtest outputs, figures, a readable Chinese
report, and a Chinese manuscript draft are implemented and verified.
See [completion notes](COMPLETION_zh.md) for deliverables and limitations.

## Complete study

- 2010–2025 NOAA OISST: 192 audited monthly subsets, approximately 47.7 MiB.
- Three domains have 5,844 valid daily means, no gaps or interpolation.
- Main domain: Marine Regions IHO Yellow Sea MRGID 4303 (includes Bohai),
  651 ocean grid centers; original rectangle 795; polygon interior 493.
- Fixed first-day ocean mask, explicit polygon membership, 80% coverage gate.
- Three disjoint test periods: 2017–2019, 2020–2022, 2023–2025. Training,
  parameter selection, interval calibration, and testing are time-separated.
- Eight models, three horizons, three domains and three periods: 216 score rows.
- Calendar seasonal cycle, harmonic seasonality, linear-trend alternatives,
  AR order selection, standardized ridge regression, paired block intervals,
  held-out empirical interval radii, yearly scores and residual diagnostics.
- 15/30/60-day block sensitivity, with effective length at least the horizon.
- Self-contained HTML report, Markdown report, five figures and manuscript.

## Selected descriptive findings

IHO domain / 2023–2025:

| Horizon | Anomaly persistence RMSE (°C) | Trend ridge RMSE (°C) | Trend ridge skill |
|---:|---:|---:|---:|
| 1 day | 0.1643 | 0.1279 | 22.2% |
| 7 days | 0.6121 | 0.5546 | 9.4% |
| 30 days | 0.9240 | 0.7905 | 14.4% |

The trend AR 30-day RMSE is 0.7873 °C, empirical coverage 96.3%, versus
90.8% for its original Gaussian interval. Earlier main-domain 30-day tests
include negative trend-model skill. Improvement is period-dependent.

These are exploratory results after the original pilot test was examined.
Regions and training periods overlap, block intervals assume approximate
stationarity, multiple comparisons are not corrected, and empirical intervals
do not guarantee future coverage. The source does not claim universal model
superiority, a unique marine definition, or publication acceptance.

## Verification

- 53 local unit/regression tests passed; style/static and diff checks passed.
- Full observed research workflow ran, including all nine region/period cases.
- Synthetic NetCDF-to-report demo and the original observed pilot remain usable.
- All scientific figures were visually reviewed.
- Original PSL/NCEI gridded spot checks matched to 1e-5 °C, including missingness.
- A netCDF4/NumPy binary-size RuntimeWarning remains in this macOS environment;
  IO and numeric checks passed and the warning is not suppressed.

Raw SST and boundary geometry remain local and ignored by Git. Generated
aggregate score tables, figures and a manuscript are included for review. Reproduction
records every acquisition URL/checksum, geometry checksum, runtime version,
config, model parameters, and output checksums.
