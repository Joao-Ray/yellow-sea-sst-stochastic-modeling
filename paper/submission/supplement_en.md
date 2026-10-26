# Supplementary information

## Spatial aggregation and observation-source dependence of short-range SST forecast skill in the Yellow–Bohai Sea

### S1. Evidence chronology and frozen records

The original regional exploration uses 2010–2025 OISST and several chronological test folds. Its latest model uses 2010–2019 for fitting, 2020–2021 for selection, 2022 for symmetric interval calibration and 2023–2025 for historical testing. The temporal protocol was committed before acquiring January–August 2026 OISST targets. Its SHA-256 is 8a11e5b9b56845936cbd72495a2f066bd2d5ae2a2a9044bc18282169ce684aa4; protocol commit d0f6f17d84054df852c96640fe8ca5a9033c8fcf records the model choices.

The independent-instrument protocol was frozen after inspection of the OISST 2026 scores, but before reading the AMSR2 target values. Its SHA-256 is ecc8c46b5f2653dc2e4f3e636c9206a2460bbe2c5dd15123f82ad51cdaba2f03; protocol commit a3deb64aba90017d59b47ac1c9404f0efbe41ad7 records that design. The linked forecast, history and spatial-mask hashes are preserved in the protocol. The 2026 origin history was assembled from the already locked regional targets, requiring identical values where target records repeat; individual forecasts still access only their origin and earlier observations.

The spatial and diagnostic extension was designed on 9 October 2026 after all original outcomes had been viewed. Its local design record is not public preregistration and is not an untouched external test. Coefficients, EOFs and mode autoregressions are fitted only to the training period; candidate selection uses only the selection period. This is an important computational restriction, but the scientific decision to add these models and diagnostics remains retrospective. No frozen primary model, threshold, external bias or calibration radius was altered.

### S2. Source acquisition and decoding

Two hundred monthly NOAA OISST subsets cover the 6,087-date record and the 44×44 acquired grid. The fixed polygon mask comprises 651 cells. Each subset has its provider URL, acquisition metadata and SHA-256 checksum. The original regional means use single-precision xarray cosine weights and reductions, followed by CSV rounding; new spatial diagnostics use double-precision weights and losses. Their maximum regional-mean difference is approximately 1.23×10⁻⁵°C, within a documented 2×10⁻⁵°C precision check. Frozen forecasts and primary metrics retain their original arithmetic. New external RMSE replication must agree within 10⁻⁵°C and use exactly the original scoring-date counts.

RSS files follow the daily version 8.2 provider naming convention. Remote byte-range acquisition preserves strong entity tags and chunk hashes before writing the cropped subset. Arrays contain separate ascending and descending SST, UTC measurement times and the land, coast, sea-ice and no-observation masks. Per-subset checksums and all provider URLs are retained in the independent provenance record. Native cell centres match the OISST centres; no external spatial interpolation or gap filling is performed.

A complete 5 February 2026 source file was also downloaded and decoded with NetCDF automatic scale/mask handling, independently of the HDF5 byte-range subset path. SST, times and the four quality masks match exactly. The complete-file SHA-256 is 6eb061870361ee819ab39597debde4db61aa412381f6dc3c94c892378c0a858f. The audit tests extraction integrity; it is not an independent calibration or buoy comparison. Its date was selected after inspecting product differences, and no scoring rule changed as a result.

### S3. Spatial candidate calculation

The training seasonal field is an ordinary least-squares regression on an intercept and three sine/cosine pairs, with optional linear trend. Let a(d) be its residual field, W the diagonal normalized cosine-weight matrix and U the eigenvectors of the training covariance of W¹ᐟ²a. The weighted EOF scores are z(d)=UᵀW¹ᐟ²a(d). Retained score histories are fitted with autoregressions using an intercept. The reconstruction operator is B=W⁻¹ᐟ²U. Only retained modes are propagated; unresolved origin anomalies persist according to equation (2) in the main text.

EOF signs are fixed by choosing the sign of each column so that its largest absolute loading is positive. Sign conventions do not identify mechanisms or affect forecasts. The rank/order/trend combination is chosen by minimum seven-day mean daily complete-grid squared error during 2020–2021. Ties prefer lower rank, lower order and no trend. Unstable candidates are excluded before scoring. The selected rank is 10, order is 7, trend inclusion is true, and retained training variance is 84.5%. All selection scores appear below; there is no search over 2026 performance.

**Table S1. Training-only candidate selection.** RMSE is in °C. The table includes every eligible stationary candidate.

| Trend | Rank | Order | Selection days | Selection RMSE (°C) |
|---|---|---|---|---|
| False | 1 | 1 | 731 | 0.8513 |
| False | 3 | 1 | 731 | 0.8459 |
| False | 5 | 1 | 731 | 0.8422 |
| False | 10 | 1 | 731 | 0.8412 |
| False | 1 | 3 | 731 | 0.8594 |
| False | 3 | 3 | 731 | 0.8560 |
| False | 5 | 3 | 731 | 0.8533 |
| False | 10 | 3 | 731 | 0.8522 |
| False | 1 | 7 | 731 | 0.8567 |
| False | 3 | 7 | 731 | 0.8506 |
| False | 5 | 7 | 731 | 0.8459 |
| False | 10 | 7 | 731 | 0.8407 |
| True | 1 | 1 | 731 | 0.8441 |
| True | 3 | 1 | 731 | 0.8418 |
| True | 5 | 1 | 731 | 0.8420 |
| True | 10 | 1 | 731 | 0.8417 |
| True | 1 | 3 | 731 | 0.8475 |
| True | 3 | 3 | 731 | 0.8485 |
| True | 5 | 3 | 731 | 0.8491 |
| True | 10 | 3 | 731 | 0.8488 |
| True | 1 | 7 | 731 | 0.8467 |
| True | 3 | 7 | 731 | 0.8427 |
| True | 5 | 7 | 731 | 0.8398 |
| True | 10 | 7 | 731 | 0.8351 |

![Figure S1. Training-only weighted spatial modes.](spatial_modes.png)

**Figure S1.** The first available retained modes are shown, up to four panels. Loadings are normalized for display, with sign conventions described above. They describe covariance structure on the fitted field, not independently established circulation or heat-flux mechanisms.

### S4. Calendar-block inference

The original paired daily bootstrap uses 1,000 replicates and 30- and 60-day blocks. The new secondary analysis uses 1,999 circular-block replicates, random seed 20261009, and retains unscored calendar dates as gaps. Every replicate draws one set of dates for both model and baseline. The difference series is centred at its observed mean to generate a null distribution for equal expected squared losses. The two-sided p value includes a one-count correction. Percentile intervals are calculated from paired RMSE skill and squared-loss advantage draws. At least 100 valid draws are required.

Separate six-member families are formed for each block length: regional OISST at three horizons and nighttime AMSR2 at three horizons. Holm adjustment uses the ordered p values with monotonically increasing adjusted values. Its family-wise interpretation depends on the validity of the individual p values; approximate stationary-loss assumptions and the short, seasonally evolving record remain limitations. Afternoon results and retrospective spatial controls are not added to this family and are not assigned adjusted confirmatory claims.

**Table S2. Secondary inference for the original frozen comparisons.** Skills and their bounds are fractions. These intervals use the new replicate count; the original published intervals remain the primary record.

| Target | Lead (d) | Block (d) | p bootstrap two sided | p holm six comparisons | Skill lower | Skill upper |
|---|---|---|---|---|---|---|
| Regional OISST (2026) | 1 | 30 | 0.0005 | 0.0030 | 0.1429 | 0.2767 |
| Regional OISST (2026) | 7 | 30 | 0.7780 | 1.0000 | -0.1292 | 0.1650 |
| Regional OISST (2026) | 30 | 30 | 0.1730 | 0.6920 | -0.4142 | 0.0600 |
| Nighttime AMSR2 (2026) | 1 | 30 | 0.0470 | 0.2350 | 0.0002 | 0.0075 |
| Nighttime AMSR2 (2026) | 7 | 30 | 0.2620 | 0.7860 | -0.0107 | 0.0290 |
| Nighttime AMSR2 (2026) | 30 | 30 | 0.6545 | 1.0000 | -0.0218 | 0.0335 |
| Regional OISST (2026) | 1 | 60 | 0.0005 | 0.0030 | 0.1492 | 0.2742 |
| Regional OISST (2026) | 7 | 60 | 0.7900 | 1.0000 | -0.1220 | 0.1637 |
| Regional OISST (2026) | 30 | 60 | 0.1575 | 0.6300 | -0.2948 | 0.0473 |
| Nighttime AMSR2 (2026) | 1 | 60 | 0.0665 | 0.3325 | 0.0003 | 0.0074 |
| Nighttime AMSR2 (2026) | 7 | 60 | 0.1890 | 0.6300 | -0.0071 | 0.0243 |
| Nighttime AMSR2 (2026) | 30 | 60 | 0.6860 | 1.0000 | -0.0212 | 0.0327 |

![Figure S2. Sensitivity to paired calendar-block length.](secondary_inference.png)

**Figure S2.** Secondary 95% skill intervals using thirty- and sixty-day blocks. The two panels correspond to the separate verification targets within the six-comparison family. The figure does not establish validity of stationary-block inference for a seasonally varying eight-month sample.

### S5. Seasonal scores and calibrated interval quality

Seasons use calendar months: DJF (December–February), MAM (March–May), JJA (June–August) and SON (September–November). The historical evaluation has three full annual cycles; the 2026 evaluation has January–August only. No 2026 SON values are filled. The 2026 DJF subset lacks December and should not be directly interpreted as the same seasonal exposure as historical DJF. The number of scored dates accompanies each summary.

**Table S3. Seasonal regional errors for the frozen selected projection.** RMSE and bias are in °C. Double-precision spatial projection arithmetic can differ slightly from the original region-only calculation.

| Period | Lead (d) | season | Days | RMSE (°C) | Bias (°C) |
|---|---|---|---|---|---|
| 2023-2025 | 1 | DJF | 271 | 0.0832 | 0.0028 |
| 2023-2025 | 1 | JJA | 276 | 0.1591 | -0.0210 |
| 2023-2025 | 1 | MAM | 276 | 0.1342 | 0.0255 |
| 2023-2025 | 1 | SON | 273 | 0.1224 | -0.0071 |
| 2023-2025 | 7 | DJF | 271 | 0.3454 | 0.0261 |
| 2023-2025 | 7 | JJA | 276 | 0.7530 | -0.1499 |
| 2023-2025 | 7 | MAM | 276 | 0.5189 | 0.1471 |
| 2023-2025 | 7 | SON | 273 | 0.5215 | -0.0202 |
| 2023-2025 | 30 | DJF | 271 | 0.4128 | 0.1630 |
| 2023-2025 | 30 | JJA | 276 | 1.1370 | -0.4129 |
| 2023-2025 | 30 | MAM | 276 | 0.7312 | 0.4377 |
| 2023-2025 | 30 | SON | 273 | 0.6870 | -0.1396 |
| 2026-Jan-Aug | 1 | DJF | 59 | 0.0720 | 0.0237 |
| 2026-Jan-Aug | 1 | JJA | 92 | 0.1432 | -0.0103 |
| 2026-Jan-Aug | 1 | MAM | 92 | 0.1227 | 0.0118 |
| 2026-Jan-Aug | 7 | DJF | 59 | 0.2595 | 0.1239 |
| 2026-Jan-Aug | 7 | JJA | 92 | 0.7468 | -0.1240 |
| 2026-Jan-Aug | 7 | MAM | 92 | 0.5253 | 0.0908 |
| 2026-Jan-Aug | 30 | DJF | 59 | 0.4175 | 0.3507 |
| 2026-Jan-Aug | 30 | JJA | 92 | 1.0638 | -0.2154 |
| 2026-Jan-Aug | 30 | MAM | 92 | 0.4825 | 0.2913 |

For interval limits l and u, observed SST y and nominal miscoverage α=0.05, the interval score is (u−l)+(2/α)(l−y) when y<l, or (u−l)+(2/α)(y−u) when y>u, and equals the width otherwise. We report coverage, mean width and mean score for the already frozen radii, without recalibration. The score is proper for the target quantiles, but empirical performance under serial dependence and drift must still be assessed.

**Table S4. 2026 regional interval diagnostics by model, horizon and season.** Coverage is a fraction; width and interval score are in °C. This table includes baselines and is distinct from external gridded verification.

| Lead (d) | Method | season | Days | coverage | mean interval score celsius | mean width celsius |
|---|---|---|---|---|---|---|
| 7 | ar_harmonic_trend | DJF | 59 | 1.0000 | 2.0388 | 2.0388 |
| 7 | ar_harmonic_trend | JJA | 92 | 0.8696 | 4.4802 | 2.0388 |
| 7 | ar_harmonic_trend | MAM | 92 | 0.9674 | 2.2807 | 2.0388 |
| 30 | ar_harmonic_trend | DJF | 59 | 1.0000 | 3.3633 | 3.3633 |
| 30 | ar_harmonic_trend | JJA | 92 | 0.9348 | 4.1804 | 3.3633 |
| 30 | ar_harmonic_trend | MAM | 92 | 1.0000 | 3.3633 | 3.3633 |
| 1 | persistence | DJF | 59 | 1.0000 | 0.6515 | 0.6515 |
| 1 | persistence | JJA | 92 | 0.9457 | 0.7917 | 0.6515 |
| 1 | persistence | MAM | 92 | 0.9457 | 0.8696 | 0.6515 |
| 7 | persistence | DJF | 59 | 1.0000 | 2.0890 | 2.0890 |
| 7 | persistence | JJA | 92 | 0.8152 | 3.6009 | 2.0890 |
| 7 | persistence | MAM | 92 | 0.9022 | 2.7671 | 2.0890 |
| 30 | persistence | DJF | 59 | 1.0000 | 3.6463 | 3.6463 |
| 30 | persistence | JJA | 92 | 0.9891 | 3.6489 | 3.6463 |
| 30 | persistence | MAM | 92 | 1.0000 | 3.6463 | 3.6463 |
| 1 | ridge_harmonic_trend | DJF | 59 | 1.0000 | 0.5288 | 0.5288 |
| 1 | ridge_harmonic_trend | JJA | 92 | 0.9348 | 0.6034 | 0.5288 |
| 1 | ridge_harmonic_trend | MAM | 92 | 0.9565 | 0.6561 | 0.5288 |

### S6. Surface memory and sampling diagnostics

Training-only regional residuals subtract an estimated harmonic cycle and trend. For each lag, both endpoints must fall within the same named season. Pearson correlations use those pairs only. Lag-one linear coefficients and conditional AR(1) half-lives, where 0<φ<1, are included in the accompanying CSV. These are sample descriptors, not demonstrated physical relaxation times. Seasonal reemergence cannot be inferred without subsurface and heat-budget evidence.

**Table S5. Same-season lagged associations in the training regional series.** No 2026 observations enter these values.

| season | lag days | n pairs | correlation |
|---|---|---|---|
| DJF | 1 | 891 | 0.9744 |
| DJF | 7 | 825 | 0.7699 |
| DJF | 30 | 572 | 0.4562 |
| MAM | 1 | 910 | 0.9570 |
| MAM | 7 | 850 | 0.5986 |
| MAM | 30 | 620 | 0.4584 |
| JJA | 1 | 910 | 0.9687 |
| JJA | 7 | 850 | 0.6724 |
| JJA | 30 | 620 | 0.0955 |
| SON | 1 | 900 | 0.9576 |
| SON | 7 | 840 | 0.6158 |
| SON | 30 | 610 | 0.0468 |

Grid-to-land distance is the minimum spherical distance from an ocean cell centre to a cell missing OISST on 1 January 2010 within the 44×44 acquisition box. Bins are [0,50), [50,100) and [100,10000) km. The proxy is bounded by this box and does not represent the nearest high-resolution coastline. On each scored date, discrepancies are first weighted within each available bin and then averaged equally over its dates. Different bins and seasons can have different cell–date compositions, so their differences are descriptive rather than controlled estimates of distance effects.

**Table S6. Seasonal product differences by land-distance proxy.** RMS difference and bias (OISST minus AMSR2) are in °C. Date counts, cell–date counts and pass labels specify the available support.

| Pass | distance proxy bin | season | Days | n cell day pairs | rms difference | bias |
|---|---|---|---|---|---|---|
| Afternoon | 0-50 | JJA | 3 | 3 | 1.9763 | -1.8938 |
| Afternoon | 0-50 | MAM | 1 | 1 | 1.1960 | -1.1960 |
| Afternoon | 100-10000 | DJF | 52 | 10236 | 0.8103 | 0.1685 |
| Afternoon | 100-10000 | JJA | 84 | 13650 | 1.6504 | -1.1771 |
| Afternoon | 100-10000 | MAM | 79 | 14835 | 2.2136 | -1.0981 |
| Afternoon | 50-100 | DJF | 52 | 2786 | 1.1697 | -0.0011 |
| Afternoon | 50-100 | JJA | 84 | 3682 | 2.1632 | -1.5108 |
| Afternoon | 50-100 | MAM | 79 | 3886 | 2.4045 | -1.2904 |
| Nighttime | 0-50 | DJF | 1 | 1 | 1.9050 | 1.9050 |
| Nighttime | 100-10000 | DJF | 55 | 9830 | 2.2149 | -0.4685 |
| Nighttime | 100-10000 | JJA | 84 | 12454 | 1.7723 | -0.8282 |
| Nighttime | 100-10000 | MAM | 86 | 14272 | 2.3389 | -0.7849 |
| Nighttime | 50-100 | DJF | 55 | 2614 | 1.7917 | -0.3533 |
| Nighttime | 50-100 | JJA | 84 | 3381 | 1.8442 | -0.9025 |
| Nighttime | 50-100 | MAM | 85 | 3841 | 2.1850 | -0.8192 |

### S7. Complete spatial comparison results

**Table S7. All spatial evaluation metrics.** Both skill columns are fractions. Frozen anomaly projection and grid-specific anomaly persistence are different baselines. Each within-target comparison uses identical masks and dates; across-target differences may reflect spatial support as well as the source. Raw grid persistence is retained as a secondary reference.

| Period | Target | Pass | Lead (d) | Method | Days | RMSE (°C) | Skill vs frozen persistence | Skill vs grid persistence |
|---|---|---|---|---|---|---|---|---|
| 2023-2025 | Full-grid OISST | all | 1 | EOF–AR spatial increments | 1096 | 0.2431 | 0.0710 | 0.0348 |
| 2023-2025 | Full-grid OISST | all | 1 | Frozen regional persistence | 1096 | 0.2617 | 0.0000 | -0.0390 |
| 2023-2025 | Full-grid OISST | all | 1 | Frozen regional forecast | 1096 | 0.2405 | 0.0811 | 0.0453 |
| 2023-2025 | Full-grid OISST | all | 1 | Grid anomaly persistence | 1096 | 0.2519 | 0.0375 | 0.0000 |
| 2023-2025 | Full-grid OISST | all | 1 | Raw grid persistence | 1096 | 0.2844 | -0.0868 | -0.1292 |
| 2023-2025 | Full-grid OISST | all | 7 | EOF–AR spatial increments | 1096 | 0.8228 | 0.0321 | -0.0078 |
| 2023-2025 | Full-grid OISST | all | 7 | Frozen regional persistence | 1096 | 0.8501 | 0.0000 | -0.0412 |
| 2023-2025 | Full-grid OISST | all | 7 | Frozen regional forecast | 1096 | 0.8098 | 0.0474 | 0.0081 |
| 2023-2025 | Full-grid OISST | all | 7 | Grid anomaly persistence | 1096 | 0.8165 | 0.0396 | 0.0000 |
| 2023-2025 | Full-grid OISST | all | 7 | Raw grid persistence | 1096 | 1.2346 | -0.4523 | -0.5121 |
| 2023-2025 | Full-grid OISST | all | 30 | EOF–AR spatial increments | 1096 | 1.2580 | 0.1589 | 0.0375 |
| 2023-2025 | Full-grid OISST | all | 30 | Frozen regional persistence | 1096 | 1.4956 | 0.0000 | -0.1443 |
| 2023-2025 | Full-grid OISST | all | 30 | Frozen regional forecast | 1096 | 1.4153 | 0.0537 | -0.0828 |
| 2023-2025 | Full-grid OISST | all | 30 | Grid anomaly persistence | 1096 | 1.3071 | 0.1261 | 0.0000 |
| 2023-2025 | Full-grid OISST | all | 30 | Raw grid persistence | 1096 | 4.1514 | -1.7757 | -2.1761 |
| 2023-2025 | Regional OISST | all | 1 | EOF–AR spatial increments | 1096 | 0.1277 | 0.2230 | 0.1519 |
| 2023-2025 | Regional OISST | all | 1 | Frozen regional persistence | 1096 | 0.1643 | 0.0000 | -0.0915 |
| 2023-2025 | Regional OISST | all | 1 | Frozen regional forecast | 1096 | 0.1279 | 0.2219 | 0.1507 |
| 2023-2025 | Regional OISST | all | 1 | Grid anomaly persistence | 1096 | 0.1506 | 0.0839 | 0.0000 |
| 2023-2025 | Regional OISST | all | 1 | Raw grid persistence | 1096 | 0.1985 | -0.2079 | -0.3185 |
| 2023-2025 | Regional OISST | all | 7 | EOF–AR spatial increments | 1096 | 0.5546 | 0.0940 | 0.0664 |
| 2023-2025 | Regional OISST | all | 7 | Frozen regional persistence | 1096 | 0.6121 | 0.0000 | -0.0305 |
| 2023-2025 | Regional OISST | all | 7 | Frozen regional forecast | 1096 | 0.5548 | 0.0936 | 0.0660 |
| 2023-2025 | Regional OISST | all | 7 | Grid anomaly persistence | 1096 | 0.5940 | 0.0296 | 0.0000 |
| 2023-2025 | Regional OISST | all | 7 | Raw grid persistence | 1096 | 1.0845 | -0.7717 | -0.8257 |
| 2023-2025 | Regional OISST | all | 30 | EOF–AR spatial increments | 1096 | 0.7977 | 0.1367 | 0.1763 |
| 2023-2025 | Regional OISST | all | 30 | Frozen regional persistence | 1096 | 0.9240 | 0.0000 | 0.0459 |
| 2023-2025 | Regional OISST | all | 30 | Frozen regional forecast | 1096 | 0.7873 | 0.1479 | 0.1870 |
| 2023-2025 | Regional OISST | all | 30 | Grid anomaly persistence | 1096 | 0.9685 | -0.0482 | 0.0000 |
| 2023-2025 | Regional OISST | all | 30 | Raw grid persistence | 1096 | 3.9813 | -3.3089 | -3.1109 |
| 2026-Jan-Aug | Full-grid OISST | all | 1 | EOF–AR spatial increments | 243 | 0.2410 | 0.0662 | 0.0410 |
| 2026-Jan-Aug | Full-grid OISST | all | 1 | Frozen regional persistence | 243 | 0.2581 | 0.0000 | -0.0270 |
| 2026-Jan-Aug | Full-grid OISST | all | 1 | Frozen regional forecast | 243 | 0.2402 | 0.0694 | 0.0443 |
| 2026-Jan-Aug | Full-grid OISST | all | 1 | Grid anomaly persistence | 243 | 0.2513 | 0.0263 | 0.0000 |
| 2026-Jan-Aug | Full-grid OISST | all | 1 | Raw grid persistence | 243 | 0.2789 | -0.0806 | -0.1097 |
| 2026-Jan-Aug | Full-grid OISST | all | 7 | EOF–AR spatial increments | 243 | 0.7998 | 0.0318 | 0.0297 |
| 2026-Jan-Aug | Full-grid OISST | all | 7 | Frozen regional persistence | 243 | 0.8261 | 0.0000 | -0.0023 |
| 2026-Jan-Aug | Full-grid OISST | all | 7 | Frozen regional forecast | 243 | 0.8161 | 0.0121 | 0.0099 |
| 2026-Jan-Aug | Full-grid OISST | all | 7 | Grid anomaly persistence | 243 | 0.8243 | 0.0022 | 0.0000 |
| 2026-Jan-Aug | Full-grid OISST | all | 7 | Raw grid persistence | 243 | 1.1774 | -0.4253 | -0.4285 |
| 2026-Jan-Aug | Full-grid OISST | all | 30 | EOF–AR spatial increments | 243 | 1.1102 | 0.1335 | 0.0879 |
| 2026-Jan-Aug | Full-grid OISST | all | 30 | Frozen regional persistence | 243 | 1.2812 | 0.0000 | -0.0525 |
| 2026-Jan-Aug | Full-grid OISST | all | 30 | Frozen regional forecast | 243 | 1.3366 | -0.0433 | -0.0981 |
| 2026-Jan-Aug | Full-grid OISST | all | 30 | Grid anomaly persistence | 243 | 1.2172 | 0.0499 | 0.0000 |
| 2026-Jan-Aug | Full-grid OISST | all | 30 | Raw grid persistence | 243 | 3.8702 | -2.0209 | -2.1796 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 1 | EOF–AR spatial increments | 215 | 1.8415 | 0.0069 | 0.0092 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 1 | Frozen regional persistence | 215 | 1.8543 | 0.0000 | 0.0023 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 1 | Frozen regional forecast | 215 | 1.8457 | 0.0047 | 0.0070 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 1 | Grid anomaly persistence | 215 | 1.8586 | -0.0023 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 1 | Raw grid persistence | 215 | 1.9237 | -0.0374 | -0.0350 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 7 | EOF–AR spatial increments | 215 | 1.9730 | 0.0314 | 0.0467 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 7 | Frozen regional persistence | 215 | 2.0368 | 0.0000 | 0.0158 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 7 | Frozen regional forecast | 215 | 2.0174 | 0.0095 | 0.0252 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 7 | Grid anomaly persistence | 215 | 2.0696 | -0.0161 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 7 | Raw grid persistence | 215 | 2.5711 | -0.2623 | -0.2423 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 30 | EOF–AR spatial increments | 215 | 1.9882 | 0.0832 | 0.1318 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 30 | Frozen regional persistence | 215 | 2.1686 | 0.0000 | 0.0531 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 30 | Frozen regional forecast | 215 | 2.1396 | 0.0134 | 0.0657 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 30 | Grid anomaly persistence | 215 | 2.2901 | -0.0560 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Afternoon | 30 | Raw grid persistence | 215 | 4.9499 | -1.2825 | -1.1614 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 1 | EOF–AR spatial increments | 225 | 2.1052 | 0.0064 | 0.0081 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 1 | Frozen regional persistence | 225 | 2.1189 | 0.0000 | 0.0017 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 1 | Frozen regional forecast | 225 | 2.1108 | 0.0038 | 0.0055 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 1 | Grid anomaly persistence | 225 | 2.1224 | -0.0017 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 1 | Raw grid persistence | 225 | 2.1635 | -0.0211 | -0.0194 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 7 | EOF–AR spatial increments | 225 | 2.1852 | 0.0297 | 0.0369 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 7 | Frozen regional persistence | 225 | 2.2521 | 0.0000 | 0.0074 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 7 | Frozen regional forecast | 225 | 2.2264 | 0.0114 | 0.0187 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 7 | Grid anomaly persistence | 225 | 2.2688 | -0.0074 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 7 | Raw grid persistence | 225 | 2.6272 | -0.1666 | -0.1580 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 30 | EOF–AR spatial increments | 225 | 2.1923 | 0.0746 | 0.0893 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 30 | Frozen regional persistence | 225 | 2.3691 | 0.0000 | 0.0158 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 30 | Frozen regional forecast | 225 | 2.3533 | 0.0067 | 0.0224 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 30 | Grid anomaly persistence | 225 | 2.4072 | -0.0161 | 0.0000 |
| 2026-Jan-Aug | Matched AMSR2 | Nighttime | 30 | Raw grid persistence | 225 | 4.7577 | -1.0082 | -0.9764 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 1 | EOF–AR spatial increments | 215 | 0.2201 | 0.0958 | 0.0492 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 1 | Frozen regional persistence | 215 | 0.2435 | 0.0000 | -0.0515 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 1 | Frozen regional forecast | 215 | 0.2222 | 0.0873 | 0.0403 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 1 | Grid anomaly persistence | 215 | 0.2315 | 0.0489 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 1 | Raw grid persistence | 215 | 0.2596 | -0.0664 | -0.1213 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 7 | EOF–AR spatial increments | 215 | 0.7798 | 0.0206 | 0.0489 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 7 | Frozen regional persistence | 215 | 0.7962 | 0.0000 | 0.0289 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 7 | Frozen regional forecast | 215 | 0.8114 | -0.0191 | 0.0103 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 7 | Grid anomaly persistence | 215 | 0.8199 | -0.0297 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 7 | Raw grid persistence | 215 | 1.1654 | -0.4638 | -0.4215 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 30 | EOF–AR spatial increments | 215 | 1.0410 | 0.1176 | 0.1700 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 30 | Frozen regional persistence | 215 | 1.1797 | 0.0000 | 0.0594 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 30 | Frozen regional forecast | 215 | 1.2971 | -0.0996 | -0.0342 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 30 | Grid anomaly persistence | 215 | 1.2542 | -0.0632 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Afternoon | 30 | Raw grid persistence | 215 | 3.7173 | -2.1511 | -1.9639 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 1 | EOF–AR spatial increments | 225 | 0.2426 | 0.0796 | 0.0624 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 1 | Frozen regional persistence | 225 | 0.2636 | 0.0000 | -0.0187 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 1 | Frozen regional forecast | 225 | 0.2436 | 0.0759 | 0.0587 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 1 | Grid anomaly persistence | 225 | 0.2587 | 0.0184 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 1 | Raw grid persistence | 225 | 0.2790 | -0.0585 | -0.0783 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 7 | EOF–AR spatial increments | 225 | 0.7898 | 0.0392 | 0.0548 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 7 | Frozen regional persistence | 225 | 0.8220 | 0.0000 | 0.0162 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 7 | Frozen regional forecast | 225 | 0.8164 | 0.0068 | 0.0229 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 7 | Grid anomaly persistence | 225 | 0.8355 | -0.0164 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 7 | Raw grid persistence | 225 | 1.1408 | -0.3878 | -0.3654 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 30 | EOF–AR spatial increments | 225 | 1.0298 | 0.1066 | 0.1379 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 30 | Frozen regional persistence | 225 | 1.1527 | 0.0000 | 0.0350 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 30 | Frozen regional forecast | 225 | 1.2610 | -0.0939 | -0.0556 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 30 | Grid anomaly persistence | 225 | 1.1946 | -0.0363 | 0.0000 |
| 2026-Jan-Aug | Matched OISST | Nighttime | 30 | Raw grid persistence | 225 | 3.6868 | -2.1983 | -2.0863 |
| 2026-Jan-Aug | Regional OISST | all | 1 | EOF–AR spatial increments | 243 | 0.1220 | 0.2065 | 0.1535 |
| 2026-Jan-Aug | Regional OISST | all | 1 | Frozen regional persistence | 243 | 0.1538 | 0.0000 | -0.0669 |
| 2026-Jan-Aug | Regional OISST | all | 1 | Frozen regional forecast | 243 | 0.1213 | 0.2109 | 0.1582 |
| 2026-Jan-Aug | Regional OISST | all | 1 | Grid anomaly persistence | 243 | 0.1441 | 0.0627 | 0.0000 |
| 2026-Jan-Aug | Regional OISST | all | 1 | Raw grid persistence | 243 | 0.1866 | -0.2134 | -0.2945 |
| 2026-Jan-Aug | Regional OISST | all | 7 | EOF–AR spatial increments | 243 | 0.5672 | 0.0391 | 0.0730 |
| 2026-Jan-Aug | Regional OISST | all | 7 | Frozen regional persistence | 243 | 0.5903 | 0.0000 | 0.0353 |
| 2026-Jan-Aug | Regional OISST | all | 7 | Frozen regional forecast | 243 | 0.5762 | 0.0239 | 0.0584 |
| 2026-Jan-Aug | Regional OISST | all | 7 | Grid anomaly persistence | 243 | 0.6119 | -0.0366 | 0.0000 |
| 2026-Jan-Aug | Regional OISST | all | 7 | Raw grid persistence | 243 | 1.0258 | -0.7378 | -0.6765 |
| 2026-Jan-Aug | Regional OISST | all | 30 | EOF–AR spatial increments | 243 | 0.7441 | -0.1568 | 0.1639 |
| 2026-Jan-Aug | Regional OISST | all | 30 | Frozen regional persistence | 243 | 0.6432 | 0.0000 | 0.2772 |
| 2026-Jan-Aug | Regional OISST | all | 30 | Frozen regional forecast | 243 | 0.7476 | -0.1623 | 0.1600 |
| 2026-Jan-Aug | Regional OISST | all | 30 | Grid anomaly persistence | 243 | 0.8900 | -0.3836 | 0.0000 |
| 2026-Jan-Aug | Regional OISST | all | 30 | Raw grid persistence | 243 | 3.7083 | -4.7649 | -3.1666 |

### S8. Reproduction and integrity checks

**Table S8. Descriptive paired block intervals for the retrospective EOF–AR control.** Each skill interval is relative to the named baseline and uses a common scoring support. These unadjusted intervals are exploratory; no p-value claim is added to the frozen six-comparison family.

| Period | Target | Lead (d) | Baseline | Block (d) | Skill lower | Skill upper |
|---|---|---|---|---|---|---|
| 2023-2025 | Full-grid OISST | 1 | Frozen regional persistence | 30 | 0.0528 | 0.0877 |
| 2023-2025 | Full-grid OISST | 1 | Frozen regional persistence | 60 | 0.0520 | 0.0871 |
| 2023-2025 | Full-grid OISST | 1 | Grid anomaly persistence | 30 | 0.0131 | 0.0544 |
| 2023-2025 | Full-grid OISST | 1 | Grid anomaly persistence | 60 | 0.0107 | 0.0564 |
| 2023-2025 | Full-grid OISST | 7 | Frozen regional persistence | 30 | -0.0119 | 0.0695 |
| 2023-2025 | Full-grid OISST | 7 | Frozen regional persistence | 60 | -0.0085 | 0.0709 |
| 2023-2025 | Full-grid OISST | 7 | Grid anomaly persistence | 30 | -0.0611 | 0.0371 |
| 2023-2025 | Full-grid OISST | 7 | Grid anomaly persistence | 60 | -0.0648 | 0.0393 |
| 2023-2025 | Full-grid OISST | 30 | Frozen regional persistence | 30 | 0.0906 | 0.2222 |
| 2023-2025 | Full-grid OISST | 30 | Frozen regional persistence | 60 | 0.0873 | 0.2307 |
| 2023-2025 | Full-grid OISST | 30 | Grid anomaly persistence | 30 | -0.0772 | 0.1251 |
| 2023-2025 | Full-grid OISST | 30 | Grid anomaly persistence | 60 | -0.0828 | 0.1305 |
| 2026-Jan-Aug | Full-grid OISST | 1 | Frozen regional persistence | 30 | 0.0437 | 0.0849 |
| 2026-Jan-Aug | Full-grid OISST | 1 | Frozen regional persistence | 60 | 0.0502 | 0.0818 |
| 2026-Jan-Aug | Full-grid OISST | 1 | Grid anomaly persistence | 30 | 0.0147 | 0.0650 |
| 2026-Jan-Aug | Full-grid OISST | 1 | Grid anomaly persistence | 60 | 0.0227 | 0.0537 |
| 2026-Jan-Aug | Full-grid OISST | 7 | Frozen regional persistence | 30 | -0.0517 | 0.1143 |
| 2026-Jan-Aug | Full-grid OISST | 7 | Frozen regional persistence | 60 | -0.0431 | 0.1050 |
| 2026-Jan-Aug | Full-grid OISST | 7 | Grid anomaly persistence | 30 | -0.0413 | 0.0757 |
| 2026-Jan-Aug | Full-grid OISST | 7 | Grid anomaly persistence | 60 | -0.0230 | 0.0579 |
| 2026-Jan-Aug | Full-grid OISST | 30 | Frozen regional persistence | 30 | 0.0221 | 0.2540 |
| 2026-Jan-Aug | Full-grid OISST | 30 | Frozen regional persistence | 60 | 0.0274 | 0.2806 |
| 2026-Jan-Aug | Full-grid OISST | 30 | Grid anomaly persistence | 30 | -0.1062 | 0.2069 |
| 2026-Jan-Aug | Full-grid OISST | 30 | Grid anomaly persistence | 60 | -0.1208 | 0.1878 |
| 2026-Jan-Aug | Matched AMSR2 | 1 | Frozen regional persistence | 30 | 0.0016 | 0.0115 |
| 2026-Jan-Aug | Matched AMSR2 | 1 | Frozen regional persistence | 60 | 0.0010 | 0.0122 |
| 2026-Jan-Aug | Matched AMSR2 | 1 | Grid anomaly persistence | 30 | 0.0034 | 0.0136 |
| 2026-Jan-Aug | Matched AMSR2 | 1 | Grid anomaly persistence | 60 | 0.0025 | 0.0139 |
| 2026-Jan-Aug | Matched AMSR2 | 7 | Frozen regional persistence | 30 | 0.0122 | 0.0492 |
| 2026-Jan-Aug | Matched AMSR2 | 7 | Frozen regional persistence | 60 | 0.0109 | 0.0475 |
| 2026-Jan-Aug | Matched AMSR2 | 7 | Grid anomaly persistence | 30 | 0.0122 | 0.0623 |
| 2026-Jan-Aug | Matched AMSR2 | 7 | Grid anomaly persistence | 60 | 0.0095 | 0.0625 |
| 2026-Jan-Aug | Matched AMSR2 | 30 | Frozen regional persistence | 30 | 0.0366 | 0.1191 |
| 2026-Jan-Aug | Matched AMSR2 | 30 | Frozen regional persistence | 60 | 0.0378 | 0.1156 |
| 2026-Jan-Aug | Matched AMSR2 | 30 | Grid anomaly persistence | 30 | 0.0220 | 0.1571 |
| 2026-Jan-Aug | Matched AMSR2 | 30 | Grid anomaly persistence | 60 | 0.0105 | 0.1640 |

Reproduction proceeds through the original historical research, the frozen OISST validation, the frozen AMSR2 validation, and then the publication extension. The extension entry point is `python -m src.publication`, with `configs/publication.json` defining the explicit candidate grid, temporal boundaries and scoring rules. Frozen protocol hashes are checked on input. NOAA subset and AMSR2 subset hashes are checked before scoring. The fixed field has consecutive daily dates, matching coordinates and finite ocean values. No candidate fitting routine reads selection or evaluation observations to estimate parameters.

Daily CSVs retain errors, masks/counts and all loss components; aggregate tables average those daily quantities. Both exact identities are checked on every matched scoring date with an absolute 10⁻¹⁰°C² threshold. The maximum observed residual in the loss decomposition is 2.13e-14°C². Altering future values in dedicated tests cannot change training parameters or an origin-restricted forecast. Further tests cover paired support, multiplicity adjustment, cancellation of discrepancy loss by a negative interaction, and interval-score penalties.

The generated manuscript and supplement draw tables directly from the analysis outputs. Figures are supplied in 300 dpi PNG and scalable SVG formats, with checksums. Protocol records include software hashes, provider acquisition hashes, exact model parameters, seeds and analysis scope. No reference to an open repository substitutes for an immutable archived release DOI; such a deposition should accompany final submission. Author identities, affiliations, funding, conflicts and contributor roles must be confirmed separately before submission.
### S9. Three-year acquisition lock and stronger controls

The three-year forecast lock (`paper/confirmation/frozen_protocol.json`, SHA-256 `cf6a462d4d55ecd80915925cea8bba313680f11402a708d9764bc8715a761502`) precedes the new AMSR2 acquisition. Public commit `6edc533f2cd5f7d0d6f61a0b441f6610cd54ebed` records the design and hashes at 03:34:52 UTC on 10 October 2026. The pre-existing spatial basis, regional forecasts and all seven new forecast arrays were fixed at this stage. All 1,096 external dates were obtained without source absences; insufficient valid cells still exclude individual dates from scoring. Original 2026 selected-forecast scores are reproduced to the documented 10⁻⁵°C tolerance.

New control selection is restricted to the previously specified training and selection boundaries. Ridge VAR uses standardized lagged modal features, an unpenalized intercept and an L2 penalty scaled by the number of training pairs. The companion spectral radius must remain below one. Its recursively propagated retained scores enter the same spatial increment reconstruction as EOF–AR. The tree control standardizes each retained modal increment by its training standard deviation before joint fitting, so high-variance modes do not automatically dominate its split loss. Each horizon has separate training targets, while leaf size and feature fraction are selected once at seven days. Elapsed time and calendar harmonics are deterministic target features; all SST features are origin restricted. Horizon overlap and rolling origin updates do not permit reading intermediate future observations.

**Table S9. Every stronger-control candidate.** Selection RMSE is in °C. Candidate settings and all fitted coefficients remain in the machine-readable results.

| Family | Order | Penalty | Min leaf | Feature fraction | 7-day selection RMSE (°C) |
| --- | --- | --- | --- | --- | --- |
| EOF–VAR ridge | 1.0 | 0.0001 | — | — | 0.8553 |
| EOF–VAR ridge | 1.0 | 0.001 | — | — | 0.8557 |
| EOF–VAR ridge | 1.0 | 0.01 | — | — | 0.8605 |
| EOF–VAR ridge | 1.0 | 0.1 | — | — | 0.9478 |
| EOF–VAR ridge | 3.0 | 0.0001 | — | — | 0.8675 |
| EOF–VAR ridge | 3.0 | 0.001 | — | — | 0.8679 |
| EOF–VAR ridge | 3.0 | 0.01 | — | — | 0.8709 |
| EOF–VAR ridge | 3.0 | 0.1 | — | — | 0.8840 |
| EOF–VAR ridge | 7.0 | 0.0001 | — | — | 0.8601 |
| EOF–VAR ridge | 7.0 | 0.001 | — | — | 0.8603 |
| EOF–VAR ridge | 7.0 | 0.01 | — | — | 0.8619 |
| EOF–VAR ridge | 7.0 | 0.1 | — | — | 0.8709 |
| EOF–ExtraTrees | — | — | 5.0 | 0.5 | 0.8331 |
| EOF–ExtraTrees | — | — | 5.0 | 1.0 | 0.8345 |
| EOF–ExtraTrees | — | — | 20.0 | 0.5 | 0.8363 |
| EOF–ExtraTrees | — | — | 20.0 | 1.0 | 0.8365 |
| EOF–ExtraTrees | — | — | 50.0 | 0.5 | 0.8415 |
| EOF–ExtraTrees | — | — | 50.0 | 1.0 | 0.8421 |

**Table S10. New nighttime nine-comparison family, both block choices.** Pointwise skill bounds are percentages and are not family-wise confidence bounds. Holm-adjusted p values are listed independently. The seed, number of replicates, primary pass and baseline were fixed before acquisition; this family is separate from Table S2.

| Model | Lead (d) | Block (d) | 95% skill interval (%) | Raw p | Holm p (9 tests) |
| --- | --- | --- | --- | --- | --- |
| EOF–AR | 1 | 30 | [0.40, 1.29] | 0.0015 | 0.0105 |
| EOF–VAR ridge | 1 | 30 | [0.23, 0.98] | 0.0030 | 0.0150 |
| EOF–ExtraTrees | 1 | 30 | [0.25, 0.64] | 0.0010 | 0.0090 |
| EOF–AR | 7 | 30 | [0.19, 5.37] | 0.0470 | 0.1410 |
| EOF–VAR ridge | 7 | 30 | [-0.73, 4.50] | 0.1580 | 0.1580 |
| EOF–ExtraTrees | 7 | 30 | [0.79, 3.13] | 0.0020 | 0.0120 |
| EOF–AR | 30 | 30 | [1.09, 13.08] | 0.0300 | 0.1200 |
| EOF–VAR ridge | 30 | 30 | [-0.14, 12.13] | 0.0625 | 0.1410 |
| EOF–ExtraTrees | 30 | 30 | [4.33, 10.79] | 0.0010 | 0.0090 |
| EOF–AR | 1 | 60 | [0.29, 1.38] | 0.0055 | 0.0385 |
| EOF–VAR ridge | 1 | 60 | [0.13, 1.06] | 0.0195 | 0.0975 |
| EOF–ExtraTrees | 1 | 60 | [0.21, 0.69] | 0.0025 | 0.0200 |
| EOF–AR | 7 | 60 | [-0.42, 5.81] | 0.1025 | 0.3075 |
| EOF–VAR ridge | 7 | 60 | [-1.48, 4.94] | 0.2540 | 0.3075 |
| EOF–ExtraTrees | 7 | 60 | [0.58, 3.34] | 0.0145 | 0.0870 |
| EOF–AR | 30 | 60 | [0.40, 13.99] | 0.0550 | 0.2200 |
| EOF–VAR ridge | 30 | 60 | [-1.32, 13.13] | 0.1145 | 0.3075 |
| EOF–ExtraTrees | 30 | 60 | [3.96, 11.10] | 0.0020 | 0.0180 |

![Figure S3. Annual nighttime external skill.](annual_external_skill.png)

**Figure S3.** Annual skill is descriptive and compares identical dates/cells against grid-specific anomaly persistence. A pooled improvement can coexist with a negative year. No annual significance claim or retrospective exclusion of an unfavourable year is made.

![Figure S4. Pointwise uncertainty for the three-year external comparison.](primary_external_intervals.png)

**Figure S4.** Paired pointwise 95% intervals from 30- and 60-day calendar blocks. Multiplicity-adjusted tests appear in Table S10; a positive interval need not imply adjusted significance.

![Figure S5. External coverage by UTC month.](external_coverage_calendar.png)

**Figure S5.** All acquired dates enter the denominator for the fraction of dates meeting the minimum-20-cell gate. Domain weight fractions use the fixed cosine-latitude mask. The new three full years and the separate January–August 2026 window are shown without imputing missing observations.

**Table S11. Change in thirty-day squared-loss advantage between matched OISST and AMSR2, 2023–2025.** The baseline is grid-specific anomaly persistence. All entries are °C² and use identical date/cell support. The difference between external and analysis advantage equals the signed discrepancy perturbation; positive product discrepancy alone does not determine ranking.

| Pass | Model | Analysis advantage (°C²) | External advantage (°C²) | Discrepancy perturbation (°C²) |
| --- | --- | --- | --- | --- |
| ascending | EOF–AR | 0.2902 | 0.7938 | 0.5035 |
| ascending | EOF–ExtraTrees | 0.5091 | 0.6940 | 0.1849 |
| ascending | EOF–VAR ridge | 0.2757 | 0.7096 | 0.4340 |
| ascending | Regional projection | -0.1300 | 0.2025 | 0.3324 |
| descending | EOF–AR | 0.2495 | 0.6256 | 0.3761 |
| descending | EOF–ExtraTrees | 0.5038 | 0.6453 | 0.1415 |
| descending | EOF–VAR ridge | 0.2214 | 0.5428 | 0.3214 |
| descending | Regional projection | -0.1294 | 0.0544 | 0.1838 |

### S10. In situ matching, weighting and dependence

The iQuam protocol (`paper/insitu/frozen_protocol.json`, SHA-256 `4eac347075875db867689e80369b43b04d289efcf0dc7d6cff85966dceb4ddcf`) was publicly committed at 03:55:21 UTC on 10 October 2026 in `16fa9b784692c9bf2eacdf5513433865a3e602db`, before reading iQuam SST values. Only a variable/attribute inventory and official source filenames had been inspected. For each month, the highest file-version suffix visible at that time was fixed in the protocol; subsequent retrieval does not select a replacement version after seeing temperatures.

The point match retains quality level 5, finite SST from −2 to 35°C, buoy platform types 2/3/4/6/8, valid nonempty identifiers and thermometric observations (provider `sst_flags` bit 0 equals zero). Bit 1 distinguishes nighttime from daytime. The time origin is exactly seconds since 1 January 1981 00:00:00 UTC, and values must belong to the recorded source month and evaluation window. The nearest spherical fixed-cell centre must lie within 20 km. This is a point-to-grid-support rule; it does not assert that a point lies inside an exact coastline or that measurement time and depth match the daily analysis. No interpolation, depth correction, diurnal adjustment or SST bias correction is fitted.

Let eₚₖd be a collocated error for record k from platform identity p on date d, with platform type included in the identity. Daily loss is L(d)=P(d)⁻¹Σₚ[nₚd⁻¹Σₖeₚₖd²], where P(d) counts sampled platforms and nₚd counts a platform's records that date. RMSE is the square root of the equally weighted date mean of L(d). Absolute and signed errors follow the same nested weighting. This retains within-platform squared variation, rather than replacing it with a squared platform-mean error. Repeated hourly records cannot dominate other platforms or count as independent replicates. Platform support and every annual result are retained in CSV files.

The 36 source months yield 1,036 nighttime dates, 124,481 records and 25 platform-type/identifier combinations. Annual nighttime date counts are 362, 365, 309; the sample meets the frozen 60-date-per-year coverage gate. The thirty-day tree RMSE is 1.2917°C, compared with 1.4696°C for grid anomaly persistence (skill 12.11%). October 2025 has no accepted nighttime buoy records; complete source acquisition does not imply complete monthly sampling. All models, annual results and matched OISST losses are retained in the supplement. This comparison concerns the sampled buoy locations and dates. Quality-control reference dependence, possible assimilation overlap, repeated platforms and support mismatch preclude a statistically independent truth claim; no additional significance claim is made.

![Figure S6. Quality-screened buoy point support.](buoy_support.png)

**Figure S6.** Displayed points are the unique coordinates of accepted nighttime/daytime observations, with fixed ocean-cell centres for context. Identical coordinates are plotted once; all temporal records are retained for scoring. Map density does not measure effective independent sample size. The scoring scheme balances platforms within dates and dates within the sample, not geographical area.

**Table S12. Annual nighttime buoy scores for the nonlinear spatial control and persistence.** Values are descriptive; shared quality-control references and possible OISST assimilation overlap preclude an independent-truth interpretation.

| Year | Model | Lead (d) | Dates | RMSE (°C) | Bias (°C) | Skill (%) |
| --- | --- | --- | --- | --- | --- | --- |
| 2023 | EOF–ExtraTrees | 1 | 362 | 0.7174 | -0.0218 | 0.76 |
| 2023 | Grid anomaly persistence | 1 | 362 | 0.7229 | -0.0127 | 0.00 |
| 2023 | EOF–ExtraTrees | 7 | 362 | 0.9818 | -0.1083 | 3.16 |
| 2023 | Grid anomaly persistence | 7 | 362 | 1.0138 | -0.0272 | 0.00 |
| 2023 | EOF–ExtraTrees | 30 | 362 | 1.0678 | -0.1707 | 15.11 |
| 2023 | Grid anomaly persistence | 30 | 362 | 1.2579 | -0.0653 | 0.00 |
| 2024 | EOF–ExtraTrees | 1 | 365 | 0.7461 | -0.0304 | 0.80 |
| 2024 | Grid anomaly persistence | 1 | 365 | 0.7521 | 0.0144 | 0.00 |
| 2024 | EOF–ExtraTrees | 7 | 365 | 0.9741 | -0.2162 | 3.57 |
| 2024 | Grid anomaly persistence | 7 | 365 | 1.0102 | 0.0055 | 0.00 |
| 2024 | EOF–ExtraTrees | 30 | 365 | 1.4380 | -0.4340 | 11.51 |
| 2024 | Grid anomaly persistence | 30 | 365 | 1.6250 | -0.0094 | 0.00 |
| 2025 | EOF–ExtraTrees | 1 | 309 | 0.8569 | -0.3609 | 0.81 |
| 2025 | Grid anomaly persistence | 1 | 309 | 0.8640 | -0.3563 | 0.00 |
| 2025 | EOF–ExtraTrees | 7 | 309 | 1.0991 | -0.3940 | 4.67 |
| 2025 | Grid anomaly persistence | 7 | 309 | 1.1530 | -0.3686 | 0.00 |
| 2025 | EOF–ExtraTrees | 30 | 309 | 1.3474 | -0.4401 | 10.54 |
| 2025 | Grid anomaly persistence | 30 | 309 | 1.5061 | -0.4407 | 0.00 |

### S11. Additional reproduction and integrity

The original frozen protocols and primary tables are preserved. With historical NOAA inputs and the original frozen records in place, `python -m src.confirmation prepare` verifies and retains existing locked forecast bytes; it refuses to overwrite an existing lock. `python -m src.confirmation acquire --workers 4` obtains or verifies every 2023–2025 AMSR2 date. `python -m src.confirmation_evaluation` requires all dates to be acquired or explicitly recorded absent and scores the frozen arrays. `python -m src.insitu acquire --workers 3` verifies or acquires every fixed iQuam source month; `python -m src.insitu evaluate` uses the same frozen arrays. `python -m src.publication_delivery` assembles the integrated manuscript and reviewed aggregates without fitting or selecting models again.

For reconstruction from upstream caches, `python -m src.confirmation_rebuild --output-dir data/processed/confirmation_rebuild --install-exact` repeats the original fixed fitting/selection calculation in a new directory and installs missing archived outputs only when every frozen SHA-256 matches. It cannot overwrite a conflicting archive. On 15 October 2026, in the recorded software/platform environment, the independent rerun reproduced all four output files byte for byte: candidate selection, benchmark parameters, serialized tree models and the complete 1,339-date forecast cube. This is a post-outcome computational replication, not a new prospective freeze; the original forecasts and outcomes remain unchanged. The reconstruction audit accompanies the reviewed results.

HTTP range responses require exact byte counts, explicit range bounds and a stable strong ETag. Interrupted bodies are retried and are never cached as valid bytes. An extraction optimization decodes only requested variable-length platform identifiers; comparison with the original method on the same May 2024 source gives identical values for all ten stored arrays and the same subset SHA-256. The audit records both software hashes. Newer official files omit old root version/date attributes; compatibility checks instead require the already frozen versioned filename, provider title/institution, identical units and actual point UTC-month filtering. These transport/format changes do not alter the frozen geographic subset, source selection or matching rules. Source URL/ETag, verified byte-range hashes, acquisition timestamps, subset hashes and source metadata accompany every local input. Freeze chronology, score replication and exact loss identities are checked separately from the geophysical dependencies of the observing products.


### S12. Retrospective physical-information and geographical-transfer controls

The local design in `paper/process_transfer/design_record.json` records the configuration, acquisition-based scope amendments and software hashes. It is not a prospective public freeze: earlier OISST and external forecast scores were known. The complete source/destination evaluation uses fixed non-overlapping ocean centres, not an error-selected subregion. The destination is only the northern Eastern China Sea intersection with the original acquired box. Figure S7 shows the unsampled extent of the destination polygon as well as the evaluated cells. Original frozen forecasts and protocols retain their checksums.

All eight NCEP/NCAR R1 fields use the official daily-averages surface-Gaussian archive. Original response hashes and cropped-file hashes are retained for 128 variable/year files. The regional Gaussian weights are sums of the original SST ocean weights assigned by spherical nearest centre. Coarse cells may contain land and do not resolve the coastline. Net heat input is constructed from four separately directed radiation fields to avoid ambiguity in net-radiation sign conventions. Upward turbulent fluxes are subtracted. Provider values are retained without clipping small negative directed radiation artifacts. The feature is a reanalysis diagnostic, not an observed ocean heat budget. Magnitude is computed after daily regional u/v averaging and must not be interpreted as the average scalar speed, stress or resolved mixing energy.

For a target d and lead h, SST features stop at d−h and the 1/7/30-day forcing windows stop at d−h−1. Target calendar harmonics and the elapsed-time feature are known at origin. Source and destination features share the same ordered definitions. Source training means and standard deviations are retained unchanged for transfer. Labels used to estimate a direct h-day increment end by 2019; no increment ending in selection or evaluation enters fitting. Separate source 2020–2021 seven-day selection is applied to each family and feature group, after which all three horizons use the source-selected hyperparameter. In this run every group selects the largest enumerated ridge penalty (10) and minimum tree leaf (50); the inference is conditional on this finite grid and does not exclude different behaviour under stronger regularization or another representation. Destination-local models are not independently tuned. The 2022 interval-calibration year from the original study is not reused to calibrate these new point predictions.

The two new groups add either three heat features or twelve heat/wind features to the 17-feature SST design. Ridge uses a fitted intercept; ExtraTrees uses 200 estimators, all features, fixed seed 20261016 and minimum leaf sizes selected from 5/20/50. Missing values are rejected rather than interpolated. The original regional forecasts and locked spatial ExtraTrees model are distinct from these new direct regional models and are not replaced by them.

**Table S13. All twelve source-region forcing contrasts.** Gains are percentages relative to the same family fitted with SST/calendar only. Sixty-day block intervals are pointwise; Holm p values adjust over all 36 source/local/transfer contrasts. Both block lengths, all 36 comparisons and every annual and seasonal score are archived in CSV files. Positive intervals alone do not establish multiplicity-adjusted support or remove hindsight.

| family | group | horizon_days | Gain (%) | 60-d pointwise CI (%) | Holm p (36) |
| --- | --- | --- | --- | --- | --- |
| ridge | sst_heat | 1 | -1.05 | [-2.29, -0.18] | 0.7560 |
| ridge | sst_heat | 7 | -1.24 | [-4.13, 1.11] | 1.0000 |
| ridge | sst_heat | 30 | -1.10 | [-3.51, 0.47] | 1.0000 |
| ridge | sst_heat_wind | 1 | -0.19 | [-2.48, 1.62] | 1.0000 |
| ridge | sst_heat_wind | 7 | -0.52 | [-5.86, 3.95] | 1.0000 |
| ridge | sst_heat_wind | 30 | -2.43 | [-6.75, 0.52] | 1.0000 |
| trees | sst_heat | 1 | 0.10 | [-0.27, 0.42] | 1.0000 |
| trees | sst_heat | 7 | 0.19 | [-0.49, 0.79] | 1.0000 |
| trees | sst_heat | 30 | -0.50 | [-1.43, 0.72] | 1.0000 |
| trees | sst_heat_wind | 1 | 1.34 | [0.53, 2.09] | 0.1760 |
| trees | sst_heat_wind | 7 | 0.04 | [-0.79, 0.93] | 1.0000 |
| trees | sst_heat_wind | 30 | -0.46 | [-2.35, 1.87] | 1.0000 |

![Figure S7. Evaluated domains and training seasonal diagnostics.](process_domains_and_seasonality.png)

**Figure S7.** Panel (a) shows only the evaluated fixed SST ocean-cell centres in colour; grey outlines are the official IHO sea-area polygons, including the unscored Eastern China Sea extent. The other panels show monthly averages of reanalysis net heat input (brown) and daily SST tendency (blue), estimated from 2010–2019 alone. Separate axes have different units and the curves do not constitute a heat-budget closure, regression estimate or causal test. No mixed-layer depth or advection is observed.

**Table S14. Every SST-only geographical-transfer score.** January–August 2026 and the three complete years remain separate. Direct transfer uses the identical source fit/scaler; destination-local references use destination training observations with source-selected hyperparameters. RMSE is °C. Negative skill values are retained.

| Period | Family | Lead (d) | Source RMSE | Transfer RMSE | Local-fit RMSE | Local persistence RMSE | Transfer skill (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2023-2025 | ridge | 1 | 0.1429 | 0.2084 | 0.1531 | 0.1584 | -31.59 |
| 2023-2025 | ridge | 7 | 0.5506 | 1.0692 | 0.5696 | 0.5924 | -80.47 |
| 2023-2025 | ridge | 30 | 0.8101 | 2.1815 | 0.8481 | 0.9711 | -124.65 |
| 2023-2025 | trees | 1 | 0.1509 | 0.1641 | 0.1609 | 0.1584 | -3.61 |
| 2023-2025 | trees | 7 | 0.5911 | 0.6570 | 0.6075 | 0.5924 | -10.90 |
| 2023-2025 | trees | 30 | 0.9519 | 1.4497 | 1.0829 | 0.9711 | -49.29 |
| 2026-Jan-Aug | ridge | 1 | 0.1361 | 0.2139 | 0.1720 | 0.1820 | -17.49 |
| 2026-Jan-Aug | ridge | 7 | 0.5748 | 1.0200 | 0.6304 | 0.6873 | -48.41 |
| 2026-Jan-Aug | ridge | 30 | 0.7441 | 1.9562 | 0.7541 | 1.1599 | -68.65 |
| 2026-Jan-Aug | trees | 1 | 0.1404 | 0.1822 | 0.1807 | 0.1820 | -0.10 |
| 2026-Jan-Aug | trees | 7 | 0.5744 | 0.6987 | 0.6470 | 0.6873 | -1.66 |
| 2026-Jan-Aug | trees | 30 | 0.7313 | 1.3844 | 0.7899 | 1.1599 | -19.35 |

![Figure S8. Direct transfer and destination-local fitting across forcing groups.](regional_transfer.png)

**Figure S8.** All groups and both families are retained at all three leads, including the additional training-calibrated reference added after inspecting the raw transfer failures. Lower RMSE is better. The horizontal benchmark uses destination-local training climatology, while direct transfer uses no destination-fitted coefficients. These are descriptive OISST comparisons on an adjacent shelf subregion, not independent-instrument or full-basin geographical validation.

#### Additional matched-satellite diagnostic

The source-region cell forecast is the origin OISST field plus the new regional predicted increment. All eighteen new family/group/horizon forecasts are evaluated with the unchanged nighttime AMSR2 flags, cosine-latitude weights and minimum-20-cell gate on the same dates. No newly estimated spatial pattern, SST bias correction, model selection or p value is introduced. The additional projection check was added after the local design record and is explicitly descriptive. Its matched OISST and AMSR2 aggregate and annual scores are archived alongside the full daily series.

A further descriptive diagnostic projects every source-region forecast onto the origin OISST spatial offsets and evaluates the same 1,002 nighttime AMSR2 dates. Across all twelve forcing-versus-SST-only contrasts, point-estimated gains range from -0.07% to 1.06%; 8 of the twelve estimates are positive. No additional fitting, selection or significance claim is made. These regional-increment projections are distinct from the previously locked nonlinear spatial model.

#### Reproduction and computational safeguards

With the original OISST cache in place, run `python -m src.process_transfer prepare`, `python -m src.process_transfer acquire --workers 3`, `python -m src.process_transfer evaluate`, `python -m src.process_external`, `python -m src.process_alignment` and `python -m src.process_transfer deliver`. Boundary geometry is acquired directly from Marine Regions, validated by identifier/name/bounds/axis order and retained locally. Provider geometry is not redistributed. The forcing downloader verifies the R1 product identifier, field units, exact daily calendar and finite cropped values. Raw response and subset hashes are kept separately. No 2026 forcing window is silently shortened: that entire new forcing comparison is excluded because the chosen product ceased production in March. No replacement reanalysis was selected after examining scores.

Future-perturbation tests confirm that changing SST after the origin or weather on/after the origin cannot change an individual feature row; changing post-training labels cannot change training scaling or coefficients; changing post-selection outcomes cannot change the source hyperparameter; prediction on destination features cannot mutate the source scaler or coefficients. Original locked-file hashes are checked before and after the new experiment. These checks establish the stated computational information restrictions, not observational independence or measured operational latency.


#### Post-outcome calibration reference: explicit destination-training information

After the unchanged-source failures had been inspected, an additional descriptive location/scale reference was added (`python -m src.process_alignment`). Source regression/tree coefficients and source-selected hyperparameters are retained. For destination features Xd, z = (Xd−mean_d)/sd_d uses only destination 2010–2019 feature statistics. If the source predictor produces an increment u(z), the calibrated destination increment is mean_delta_d + sd_delta_d [u(z)−mean_delta_s]/sd_delta_s. Source and destination increment moments use only targets ending by 2019 and the complete training feature rows. No local regression or tree coefficients are used. The destination scaler is retrieved from the training statistics already stored with the local-reference model, independently of its fitted predictor.

This reference uses destination training histories to estimate calibration parameters. It is neither unchanged-scaler transfer nor a destination-data-free forecast. All feature groups, families, leads and annual scores are retained; no extra tuning, p value or selection is attached. The joint feature/increment calibration cannot separate individual causes of geographical shift, and its addition after seeing raw failures is recorded rather than treated as preregistered evidence. Tests verify that future labels cannot alter its increment moments, that changing local regression coefficients cannot alter its forecasts, and that an affine copy of a source series yields the corresponding affine-calibrated forecast.

**Table S15. SST-only transfer with destination-training calibration.** All numbers are °C. Raw transfer and local-fit references reproduce Table S14; the extra calibrated column uses destination training location/scale. Both periods, families and all leads are retained.

| Period | Family | Lead (d) | Raw transfer RMSE | Training-calibrated RMSE | Local-fit RMSE | Local persistence RMSE |
| --- | --- | --- | --- | --- | --- | --- |
| 2023-2025 | ridge | 1 | 0.2084 | 0.1738 | 0.1531 | 0.1584 |
| 2023-2025 | ridge | 7 | 1.0692 | 0.6676 | 0.5696 | 0.5924 |
| 2023-2025 | ridge | 30 | 2.1815 | 1.0360 | 0.8481 | 0.9711 |
| 2023-2025 | trees | 1 | 0.1641 | 0.1683 | 0.1609 | 0.1584 |
| 2023-2025 | trees | 7 | 0.6570 | 0.6171 | 0.6075 | 0.5924 |
| 2023-2025 | trees | 30 | 1.4497 | 1.0504 | 1.0829 | 0.9711 |
| 2026-Jan-Aug | ridge | 1 | 0.2139 | 0.1796 | 0.1720 | 0.1820 |
| 2026-Jan-Aug | ridge | 7 | 1.0200 | 0.6735 | 0.6304 | 0.6873 |
| 2026-Jan-Aug | ridge | 30 | 1.9562 | 0.8704 | 0.7541 | 1.1599 |
| 2026-Jan-Aug | trees | 1 | 0.1822 | 0.1849 | 0.1807 | 0.1820 |
| 2026-Jan-Aug | trees | 7 | 0.6987 | 0.6718 | 0.6470 | 0.6873 |
| 2026-Jan-Aug | trees | 30 | 1.3844 | 0.9772 | 0.7899 | 1.1599 |


### S13. Expanded grids, climatology-assisted transfer and simple memory controls

The local design and separate benchmark record in `paper/anomaly_transfer/` were made after the raw-transfer failures and upper-edge selections were known. They are not public prospective locks. This phase does not alter any original forecast, protocol, prior process-transfer result or statistical family. Both representations, all three feature groups and all source-selected families/leads are retained. There is no destination hyperparameter search. The full-period forcing groups stop at 2025; January–August 2026 is SST-only.

Following inspection of the raw-transfer failures and candidate-boundary choices, we added an explicitly retrospective sensitivity. Ridge penalties span 0.01–1,000,000 (nine logarithmic values) and minimum tree leaf sizes are 5, 20, 50, 100, 200, 400 and 800 (200 trees). Each representation, family and feature group is selected only by source seven-day RMSE over 2020–2021, retaining all choices for evaluation at 1, 7 and 30 days. All fits end in 2019. Raw-feature models retain the original feature definitions and random seed, permitting exact selection-score checks at the old candidates.

For the second representation, a regional three-harmonic seasonal cycle with linear trend C_r(t) and residual standard deviation sigma_r are estimated on 2010–2019 alone. SST state is a_r(t) = [T_r(t) − C_r(t)] / sigma_r. Models predict a_r(t+h)−a_r(t), using the same lag/calendar layout; weather drivers are likewise normalized by their own regional training cycle and residual scale before delayed trailing windows are formed. Transfer keeps the source increment predictor and source feature scaler, and decodes C_d(t+h)+sigma_d[a_d(t)+u_s(X_d)]. The destination seasonal/trend coefficients and scales require destination 2010–2019 history. This is climatology-assisted transfer, not a data-free or zero-shot forecast. Origin SST histories are also local.

Fixed descriptive references are training climatology alone and no-intercept AR(1) decay: C_d(t+h)+sigma_d phi^h a_d(t), with phi fitted by least squares on consecutive training anomalies only. Source and destination phi are 0.965144 and 0.952303; each uses 3,651 training pairs. We report both destination phi and unchanged source phi, and reject rather than clip unstable training coefficients. No decay value is chosen using validation or test scores. Pointwise paired 30/60-day block intervals (1,999 resamples) are descriptive; no new p values or confirmatory family is introduced. Neither this expansion nor its simple controls convert previously viewed outcomes into an untouched holdout.

Training cycles are evaluated at future calendar dates using fixed coefficients, not refitted to evaluation outcomes. Origin and lagged SST values are locally observed inputs. Weather windows end at least one calendar day before the origin. Feature construction is verified against perturbations beyond these cutoffs. Local-reference fits share source-selected hyperparameters, rather than destination-optimized choices. All twelve source choices and every validation candidate score are archived, including ridge effective degrees of freedom and median tree leaf counts.

**Table S16. All source-selected configurations.** Selection RMSE is °C for seven-day source forecasts in 2020–2021. A lower-edge heat/wind anomaly-tree choice remains, preventing a claim that every candidate-boundary issue is resolved. Raw ridge choices become interior without changing value.

| representation | family | group | Value | 2020 RMSE | 2021 RMSE | Pooled RMSE | Lower edge | Upper edge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw | ridge | sst | 10 | 0.5263 | 0.5239 | 0.5251 | False | False |
| raw | trees | sst | 100 | 0.5423 | 0.5763 | 0.5596 | False | False |
| raw | ridge | sst_heat | 10 | 0.5196 | 0.5224 | 0.5210 | False | False |
| raw | trees | sst_heat | 100 | 0.5476 | 0.5758 | 0.5619 | False | False |
| raw | ridge | sst_heat_wind | 10 | 0.5123 | 0.5099 | 0.5111 | False | False |
| raw | trees | sst_heat_wind | 100 | 0.5382 | 0.5712 | 0.5549 | False | False |
| seasonal_anomaly | ridge | sst | 10000 | 0.5159 | 0.5362 | 0.5261 | False | False |
| seasonal_anomaly | trees | sst | 200 | 0.5134 | 0.5265 | 0.5200 | False | False |
| seasonal_anomaly | ridge | sst_heat | 1000 | 0.5267 | 0.5220 | 0.5243 | False | False |
| seasonal_anomaly | trees | sst_heat | 200 | 0.5152 | 0.5256 | 0.5204 | False | False |
| seasonal_anomaly | ridge | sst_heat_wind | 1000 | 0.5165 | 0.5107 | 0.5136 | False | False |
| seasonal_anomaly | trees | sst_heat_wind | 5 | 0.5161 | 0.5145 | 0.5153 | True | False |

![Figure S9. Source-only expanded candidate curves.](expanded_source_selection.png)

**Figure S9.** Stars mark each representation/family/group choice based only on pooled 2020–2021 RMSE. Dotted lines show the former upper grid value. Both axes use their plotted units; hyperparameter axes are logarithmic. Curves do not show destination or test outcomes. No uncertainty or repeated-validation stability is inferred from a single pooled selection.

**Table S17. All SST-only destination transfer comparisons.** RMSE is °C. Gain and pointwise 95% paired 60-day block intervals compare the anomaly model with destination-local AR(1), not source AR(1), raw transfer or climatology. They are unadjusted descriptive intervals, not simultaneous coverage or a new confirmatory test. Both 30/60-day choices are archived in `decay_reference_intervals.csv`. Three full years have 1,096 dates; January–August 2026 has 243.

| Period | Family | Lead (d) | Raw transfer | Anomaly transfer | Local AR(1) | Source AR(1) transfer | Gain vs local AR(1) (%) | 60-d pointwise CI (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023-2025 | ridge | 1 | 0.2084 | 0.1564 | 0.1609 | 0.1590 | 2.83 | [1.58, 4.24] |
| 2023-2025 | ridge | 7 | 1.0692 | 0.5588 | 0.5685 | 0.5623 | 1.70 | [-1.04, 4.70] |
| 2023-2025 | ridge | 30 | 2.1815 | 0.8419 | 0.8605 | 0.8390 | 2.17 | [-9.71, 10.93] |
| 2023-2025 | trees | 1 | 0.1614 | 0.1561 | 0.1609 | 0.1590 | 3.00 | [1.98, 3.90] |
| 2023-2025 | trees | 7 | 0.6311 | 0.5595 | 0.5685 | 0.5623 | 1.58 | [0.13, 2.91] |
| 2023-2025 | trees | 30 | 1.3667 | 0.8415 | 0.8605 | 0.8390 | 2.22 | [-7.02, 8.15] |
| 2026-Jan-Aug | ridge | 1 | 0.2139 | 0.1773 | 0.1809 | 0.1805 | 1.96 | [0.59, 2.95] |
| 2026-Jan-Aug | ridge | 7 | 1.0200 | 0.6259 | 0.6161 | 0.6273 | -1.59 | [-2.67, -0.50] |
| 2026-Jan-Aug | ridge | 30 | 1.9562 | 0.9179 | 0.8028 | 0.8448 | -14.34 | [-18.70, -2.50] |
| 2026-Jan-Aug | trees | 1 | 0.1812 | 0.1752 | 0.1809 | 0.1805 | 3.11 | [1.56, 4.61] |
| 2026-Jan-Aug | trees | 7 | 0.6899 | 0.6058 | 0.6161 | 0.6273 | 1.67 | [-1.27, 3.98] |
| 2026-Jan-Aug | trees | 30 | 1.4178 | 0.8255 | 0.8028 | 0.8448 | -2.83 | [-8.10, 0.90] |

Climatology-only destination RMSE is 0.9410°C in 2023–2025 and 0.7356°C in January–August 2026 at every lead, since it ignores the forecast origin. Full annual and seasonal outcomes, destination-local fits, all forcing groups, baseline metrics and satellite projections accompany the aggregate CSVs. At thirty days the source AR(1) transfer is slightly better than either SST-only complex anomaly model over the three full years; this point-estimate comparison is distinct from the local-AR(1) intervals tabulated above. No interval against source AR(1) or climatology is inferred from an interval against another reference.

#### Satellite common-support reference reconstruction

Every regional model is projected as the observed origin OISST spatial field plus a uniform predicted regional increment. For a given date/lead/target on the same normalized visible-cell weights, squared loss of an increment delta has the exact form A + 2 B delta + delta² and bias B + delta. Recovering A and B from an already audited regional projection allows identical-support scoring of fixed climatology and AR(1) projections. Before scoring them, this quadratic is checked against every directly computed new-model daily loss (maximum discrepancy below 1e-10°C²). This is algebraic reuse of identical observations, not a new measurement or independently estimated truth. `external_reference_audit.json` records the actual discrepancy and input hashes. `external_benchmark_metrics.csv` retains both matched OISST and AMSR2, both periods and all leads; `external_decay_intervals.csv` compares new source models to projected source-local AR(1) with descriptive 30/60-day pointwise intervals.

#### Reconstruction and completeness

With prior caches intact, run `python -m src.anomaly_transfer prepare`, `python -m src.anomaly_transfer evaluate`, `python -m src.anomaly_transfer external`, `python -m src.anomaly_benchmarks`, `python -m src.anomaly_reference_external`, `python -m src.anomaly_transfer deliver` and `python -m src.publication_delivery`. No new external values are required. The design verifies aggregated input hashes; evaluation reproduces every original narrow-grid validation score and preserves the prior frozen files and complete process-transfer outputs. Numerical reconstruction checks every scientific CSV to 1e-10 tolerance; tree parallelism can change floating-point sums and serialized model bytes. The record does not claim cross-platform byte identity. Local data packages include full predictions, daily losses and the model archive; reviewed repository tables omit large daily files. New pointwise intervals are explicitly separate from the old six-, nine- and thirty-six-comparison families.


### S14. Destination satellite and buoy verification

The publicly accessible [pre-scoring commit](https://github.com/Joao-Ray/yellow-sea-sst-stochastic-modeling/commit/0d9d318fece43baa067ae853e598e7681ce10767) contains the protocol, software, input hashes, every forecast-array fingerprint and exact source versions. The lock was remotely verified on 21 October 2026 before destination scoring began. Source files had already been acquired and earlier source-region/destination-OISST results were known. This chronology supports a fixed conditional geographical comparison, with no claim that all design or raw data were previously unviewed. In particular, the earlier process-transfer audit's acquisition wording is corrected: the rectangular satellite cache already contained destination cells, whose destination scores had not been produced. The historical audit is retained.

All thirteen methods and three leads use the same source-selected regional predictions or fixed references. Projected source AR(1), local AR(1), regional climatology and anomaly persistence retain origin spatial offsets. Separate grid references fit three harmonic orders plus a linear trend on each destination cell's 2010–2019 values. Grid source/local AR(1) uses the previously estimated source/destination **regional** coefficient; this does not fit 230 separate decay parameters. Grid climatology ignores origin anomalies; grid anomaly persistence does not damp them. Grid climatology is distinct from projecting the regional climatology while preserving origin spatial offsets.

**Table S18. Complete locked primary family.** Two anomaly models × three leads × three references. Positive gain favours the anomaly model. Intervals are unadjusted pointwise 95% paired intervals; both p columns are two-sided and Holm adjusted within all eighteen contrasts at their named block length. A small adjusted p with negative gain supports deterioration. Nothing is added to or removed from the older six-, nine- or thirty-six-comparison families. The use of stationary circular blocks and prior outcome-dependent design limits interpretation.

| Model | Reference | Lead (d) | Gain (%) | 60-d pointwise CI (%) | Holm p, 30 d | Holm p, 60 d |
| --- | --- | --- | --- | --- | --- | --- |
| Anomaly ridge | Grid climatology | 1 | 28.05 | [17.10, 38.77] | 0.0090 | 0.0090 |
| Anomaly ridge | Grid climatology | 7 | 16.01 | [6.23, 25.60] | 0.0385 | 0.0880 |
| Anomaly ridge | Grid climatology | 30 | -8.24 | [-17.81, 1.10] | 0.3400 | 0.5400 |
| Anomaly ridge | Grid source AR(1) | 1 | -0.17 | [-0.36, 0.00] | 0.3570 | 0.5400 |
| Anomaly ridge | Grid source AR(1) | 7 | -2.20 | [-3.32, -1.33] | 0.0090 | 0.0090 |
| Anomaly ridge | Grid source AR(1) | 30 | -14.03 | [-20.02, -8.51] | 0.0090 | 0.0090 |
| Anomaly ridge | Projected source AR(1) | 1 | 0.02 | [-0.05, 0.12] | 1.0000 | 1.0000 |
| Anomaly ridge | Projected source AR(1) | 7 | 0.02 | [-0.17, 0.24] | 1.0000 | 1.0000 |
| Anomaly ridge | Projected source AR(1) | 30 | 0.27 | [-1.74, 2.35] | 1.0000 | 1.0000 |
| Anomaly trees | Grid climatology | 1 | 28.14 | [17.28, 38.80] | 0.0090 | 0.0090 |
| Anomaly trees | Grid climatology | 7 | 16.14 | [6.77, 25.19] | 0.0240 | 0.0720 |
| Anomaly trees | Grid climatology | 30 | -8.01 | [-16.33, 0.08] | 0.2025 | 0.4005 |
| Anomaly trees | Grid source AR(1) | 1 | -0.05 | [-0.25, 0.12] | 1.0000 | 1.0000 |
| Anomaly trees | Grid source AR(1) | 7 | -2.05 | [-3.17, -1.13] | 0.0090 | 0.0090 |
| Anomaly trees | Grid source AR(1) | 30 | -13.79 | [-19.52, -8.89] | 0.0090 | 0.0090 |
| Anomaly trees | Projected source AR(1) | 1 | 0.14 | [0.04, 0.25] | 0.0800 | 0.1500 |
| Anomaly trees | Projected source AR(1) | 7 | 0.18 | [-0.41, 0.62] | 1.0000 | 1.0000 |
| Anomaly trees | Projected source AR(1) | 30 | 0.49 | [-0.70, 1.69] | 1.0000 | 1.0000 |

**Table S19. Every nighttime buoy method, 2023–2025.** RMSE is °C on 1,051 equally weighted dates after balancing platform type/ID within each date. These values are descriptive, with no new buoy significance test. Record counts, platform support, annual/seasonal outcomes and daytime/matched-OISST metrics accompany the CSVs.

| Method | 1 d RMSE | 7 d RMSE | 30 d RMSE |
| --- | --- | --- | --- |
| raw ridge | 0.5677 | 1.2248 | 2.5494 |
| raw trees | 0.5740 | 0.9340 | 1.8470 |
| Anomaly ridge | 0.5725 | 0.8884 | 1.4678 |
| Anomaly trees | 0.5717 | 0.8918 | 1.4827 |
| projected climatology | 1.0820 | 1.2043 | 1.5878 |
| projected local ar1 | 0.5737 | 0.8997 | 1.5217 |
| Projected source AR(1) | 0.5734 | 0.8915 | 1.4983 |
| projected anomaly persistence | 0.5737 | 0.8971 | 1.4951 |
| raw persistence | 0.5998 | 1.1745 | 3.2026 |
| Grid climatology | 1.3750 | 1.3750 | 1.3750 |
| Grid source AR(1) | 0.5695 | 0.8493 | 1.2113 |
| Grid local AR(1) | 0.5702 | 0.8634 | 1.2518 |
| Grid anomaly persistence | 0.5700 | 0.8652 | 1.2922 |

![Figure S10. Monthly destination instrument support.](destination_observation_coverage.png)

**Figure S10.** Satellite bars show the number of dates meeting the fixed twenty-cell gate; the line shows median visible destination weight across all nights in each month, including unscored nights. Buoy bars count dates after quality and source-proximity exclusions. Satellite coverage includes January–August 2026; the version-fixed buoy collection ends in 2025. All three primary satellite years exceed the 120-date gate, and all buoy years exceed the sixty-date gate. Passing a date-count gate does not establish full spatial coverage or missing-at-random sampling.

#### Point matching and prior-support exclusion

Best-quality thermometric iQuam buoy records use the same version, temperature bounds, platform types, day/night flags and UTC calendar as the earlier source-region description. A record must be within 20 km of a destination centre and **more than** 20 km from every source centre. This explicitly removes any location eligible for the previous source matching, including boundary cases. No temperature outcome enters these distances or exclusions. Repeated observations from a platform remain in its daily squared/absolute/signed loss, then platforms and dates receive equal weights. The same platform may operate in different regions or years; geographical exclusion does not create statistical independence of platforms or QC references.

#### Independent implementation audit

`python -m src.destination_audit` reconstructs masks directly from original satellite caches, verifies every model's daily weighted loss, and independently matches all buoy records using double-precision unit-sphere KD-tree candidates with spherical reranking at the frozen coordinate precision, instead of the production all-pairs search. It compares complete record multisets and nearest-cell assignments. The original stored float32 cell-angle conversion and stable tie order are preserved: at near bisectors, a fully double-precision alternative can select an adjacent cell, so changing precision would change the locked matching rule. Regression tests cover these cases. Inverse platform-day and daily-platform weights with independent accumulation reproduce hierarchical buoy scoring. Every satellite/buoy daily loss is required to agree within 1e-10, and all frozen arrays and earlier outputs retain their hashes. This verifies scientific arithmetic and extraction; it does not make the underlying observation sources or acquisitions independent.

Reproduce with `python -m src.destination_validation prepare`, public-lock verification, `python -m src.destination_validation evaluate`, `python -m src.destination_audit`, `python -m src.destination_validation deliver`, and `python -m src.publication_delivery`. The original public protocol remains fixed. Archive hashes identify the fitted grid coefficients, source manifests, complete locked projections, daily losses and point matches; large arrays and daily point records are distributed in the local data package. The official iQuam notice about discontinued human monitoring remains applicable, and quality-control reference and potential OISST input overlap are retained as evidence boundaries.
