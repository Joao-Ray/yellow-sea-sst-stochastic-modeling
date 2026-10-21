# Frozen temporal validation: January-August 2026

- [Chinese validation report](时间验证报告_zh.md)
- [Complete frozen parameters and protocol](frozen_protocol.json)
- [Selection scores](selection_scores.csv), [holdout scores](metrics.csv),
  [paired block sensitivity](block_sensitivity.csv), [acquisition provenance](evaluation_protocol.json)
- [Integrated revised manuscript](../manuscript_zh.md)
- [Protocol and reproduction notes](../../docs/TEMPORAL_VALIDATION_zh.md)

Config and fitted parameters were committed in d0f6f17 before acquiring 2026 SST.
Training ends in 2019, method selection in 2021, interval calibration in 2022.
Selected 1/7/30-day methods have 21.1%/2.4%/-16.2% skill. The 7/30-day skill
intervals include zero. All 243 target days are valid. No re-selection, refitting
or calibration used the new scores.

This is a new temporal window of the same NOAA OISST product, not independent
instrumental observations or live prospective forecasts. The IHO domain includes
Bohai. The window is not a complete annual cycle. Multiple comparison correction
is not applied and paired block intervals assume approximate stationarity.
