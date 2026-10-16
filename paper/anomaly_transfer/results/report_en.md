# Climatology-assisted anomaly transfer and simple controls

## Evidence status

Retrospective sensitivity designed after inspecting raw-transfer failures and hyperparameter-boundary selection. This is neither a blind test nor a new confirmatory experiment. The finite expanded grids and both representations are retained. Select each source family/group/representation on 2020–2021 seven-day RMSE only; fit coefficients and all climatologies/scales on 2010–2019 targets. Seasonal-anomaly transfer uses destination training climatology and residual scales, together with destination origin histories, but unchanged source increment coefficients and feature scaler. Destination-local fits use source-selected hyperparameters. Every group, lead, year and context is reported, including deterioration. New block intervals are pointwise descriptive sensitivities, with no new confirmatory p values. Original frozen protocols, forecasts and all prior process-transfer results remain unchanged.

## Methods

Following inspection of the raw-transfer failures and candidate-boundary choices, we added an explicitly retrospective sensitivity. Ridge penalties span 0.01–1,000,000 (nine logarithmic values) and minimum tree leaf sizes are 5, 20, 50, 100, 200, 400 and 800 (200 trees). Each representation, family and feature group is selected only by source seven-day RMSE over 2020–2021, retaining all choices for evaluation at 1, 7 and 30 days. All fits end in 2019. Raw-feature models retain the original feature definitions and random seed, permitting exact selection-score checks at the old candidates.

For the second representation, a regional three-harmonic seasonal cycle with linear trend C_r(t) and residual standard deviation sigma_r are estimated on 2010–2019 alone. SST state is a_r(t) = [T_r(t) − C_r(t)] / sigma_r. Models predict a_r(t+h)−a_r(t), using the same lag/calendar layout; weather drivers are likewise normalized by their own regional training cycle and residual scale before delayed trailing windows are formed. Transfer keeps the source increment predictor and source feature scaler, and decodes C_d(t+h)+sigma_d[a_d(t)+u_s(X_d)]. The destination seasonal/trend coefficients and scales require destination 2010–2019 history. This is climatology-assisted transfer, not a data-free or zero-shot forecast. Origin SST histories are also local.

Fixed descriptive references are training climatology alone and no-intercept AR(1) decay: C_d(t+h)+sigma_d phi^h a_d(t), with phi fitted by least squares on consecutive training anomalies only. Source and destination phi are 0.965144 and 0.952303; each uses 3,651 training pairs. We report both destination phi and unchanged source phi, and reject rather than clip unstable training coefficients. No decay value is chosen using validation or test scores. Pointwise paired 30/60-day block intervals (1,999 resamples) are descriptive; no new p values or confirmatory family is introduced. Neither this expansion nor its simple controls convert previously viewed outcomes into an untouched holdout.

## Results

Expanding the source-selection grids removes every upper-edge choice: 0 of twelve selected configurations remain at the expanded upper limit. The raw ridge penalty remains 10 in all groups, while raw trees select a minimum leaf size of 100 instead of the earlier maximum of 50. One anomaly-tree configuration (heat/wind) selects the lower edge of five, so finite-candidate sensitivity is not eliminated. Original narrow-grid selection RMSEs reproduce exactly. Neither expanded grid nor representation is selected by destination outcomes; both representations and all source-selected configurations are retained (Supplementary Table S16).

Removing each region's training seasonal cycle/trend and scaling its anomalies markedly reduces the large raw-transfer penalty. In 2023–2025 the thirty-day SST-only destination RMSE is 0.8419°C for ridge and 0.8415°C for regional trees, compared with 0.9711°C for local anomaly persistence. However, the transferred one-parameter source AR(1) gives 0.8390°C, slightly better than either complex model. This comparison supports a climatology-assisted anomaly-memory reference, without establishing a nonlinear or multifeature transfer advantage. The normalization change and model selection change are joint statistical interventions and do not identify a physical cause.

The partial-year check is less favourable to complexity. In January–August 2026, thirty-day destination RMSE is 0.9179°C for ridge and 0.8255°C for trees, versus 0.8028°C for local AR(1), 0.8448°C for source AR(1) transfer and 0.7356°C for training climatology alone. Thus a three-complete-year reduction relative to non-decaying persistence does not imply a uniform gain over simple decay or climatology across periods. Figure 7 and Supplementary Table S17 retain both periods, families and all horizons.

On the source region's same nighttime AMSR2 support, the thirty-day SST-only anomaly-tree projection has RMSE 2.0866°C in 2023–2025 and 2.3432°C in January–August 2026. Projected training climatology gives 2.0842°C and 2.3199°C, respectively. These new regional-increment models do not improve on that simple thirty-day reference in either period. They are distinct from the previously locked EOF-based spatial tree control, whose three-year RMSE remains 1.9387°C. New satellite scores are descriptive reuses of viewed observations, not a new independent test.

## All SST-only comparisons

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

## Complete source selection

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

![Transfer controls](anomaly_transfer_controls.png)

![Source selection](expanded_source_selection.png)
