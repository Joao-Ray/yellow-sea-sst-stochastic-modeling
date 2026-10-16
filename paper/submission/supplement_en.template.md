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

EOF signs are fixed by choosing the sign of each column so that its largest absolute loading is positive. Sign conventions do not identify mechanisms or affect forecasts. The rank/order/trend combination is chosen by minimum seven-day mean daily complete-grid squared error during 2020–2021. Ties prefer lower rank, lower order and no trend. Unstable candidates are excluded before scoring. The selected rank is {{spatial_rank}}, order is {{spatial_order}}, trend inclusion is {{spatial_trend}}, and retained training variance is {{spatial_variance_percent}}%. All selection scores appear below; there is no search over 2026 performance.

**Table S1. Training-only candidate selection.** RMSE is in °C. The table includes every eligible stationary candidate.

{{selection_table}}

![Figure S1. Training-only weighted spatial modes.](spatial_modes.png)

**Figure S1.** The first available retained modes are shown, up to four panels. Loadings are normalized for display, with sign conventions described above. They describe covariance structure on the fitted field, not independently established circulation or heat-flux mechanisms.

### S4. Calendar-block inference

The original paired daily bootstrap uses 1,000 replicates and 30- and 60-day blocks. The new secondary analysis uses 1,999 circular-block replicates, random seed 20261009, and retains unscored calendar dates as gaps. Every replicate draws one set of dates for both model and baseline. The difference series is centred at its observed mean to generate a null distribution for equal expected squared losses. The two-sided p value includes a one-count correction. Percentile intervals are calculated from paired RMSE skill and squared-loss advantage draws. At least 100 valid draws are required.

Separate six-member families are formed for each block length: regional OISST at three horizons and nighttime AMSR2 at three horizons. Holm adjustment uses the ordered p values with monotonically increasing adjusted values. Its family-wise interpretation depends on the validity of the individual p values; approximate stationary-loss assumptions and the short, seasonally evolving record remain limitations. Afternoon results and retrospective spatial controls are not added to this family and are not assigned adjusted confirmatory claims.

**Table S2. Secondary inference for the original frozen comparisons.** Skills and their bounds are fractions. These intervals use the new replicate count; the original published intervals remain the primary record.

{{inference_table}}

![Figure S2. Sensitivity to paired calendar-block length.](secondary_inference.png)

**Figure S2.** Secondary 95% skill intervals using thirty- and sixty-day blocks. The two panels correspond to the separate verification targets within the six-comparison family. The figure does not establish validity of stationary-block inference for a seasonally varying eight-month sample.

### S5. Seasonal scores and calibrated interval quality

Seasons use calendar months: DJF (December–February), MAM (March–May), JJA (June–August) and SON (September–November). The historical evaluation has three full annual cycles; the 2026 evaluation has January–August only. No 2026 SON values are filled. The 2026 DJF subset lacks December and should not be directly interpreted as the same seasonal exposure as historical DJF. The number of scored dates accompanies each summary.

**Table S3. Seasonal regional errors for the frozen selected projection.** RMSE and bias are in °C. Double-precision spatial projection arithmetic can differ slightly from the original region-only calculation.

{{seasonal_table}}

For interval limits l and u, observed SST y and nominal miscoverage α=0.05, the interval score is (u−l)+(2/α)(l−y) when y<l, or (u−l)+(2/α)(y−u) when y>u, and equals the width otherwise. We report coverage, mean width and mean score for the already frozen radii, without recalibration. The score is proper for the target quantiles, but empirical performance under serial dependence and drift must still be assessed.

**Table S4. 2026 regional interval diagnostics by model, horizon and season.** Coverage is a fraction; width and interval score are in °C. This table includes baselines and is distinct from external gridded verification.

{{interval_table}}

### S6. Surface memory and sampling diagnostics

Training-only regional residuals subtract an estimated harmonic cycle and trend. For each lag, both endpoints must fall within the same named season. Pearson correlations use those pairs only. Lag-one linear coefficients and conditional AR(1) half-lives, where 0<φ<1, are included in the accompanying CSV. These are sample descriptors, not demonstrated physical relaxation times. Seasonal reemergence cannot be inferred without subsurface and heat-budget evidence.

**Table S5. Same-season lagged associations in the training regional series.** No 2026 observations enter these values.

{{memory_table}}

Grid-to-land distance is the minimum spherical distance from an ocean cell centre to a cell missing OISST on 1 January 2010 within the 44×44 acquisition box. Bins are [0,50), [50,100) and [100,10000) km. The proxy is bounded by this box and does not represent the nearest high-resolution coastline. On each scored date, discrepancies are first weighted within each available bin and then averaged equally over its dates. Different bins and seasons can have different cell–date compositions, so their differences are descriptive rather than controlled estimates of distance effects.

**Table S6. Seasonal product differences by land-distance proxy.** RMS difference and bias (OISST minus AMSR2) are in °C. Date counts, cell–date counts and pass labels specify the available support.

{{distance_table}}

### S7. Complete spatial comparison results

**Table S7. All spatial evaluation metrics.** Both skill columns are fractions. Frozen anomaly projection and grid-specific anomaly persistence are different baselines. Each within-target comparison uses identical masks and dates; across-target differences may reflect spatial support as well as the source. Raw grid persistence is retained as a secondary reference.

{{all_metrics_table}}

### S8. Reproduction and integrity checks

**Table S8. Descriptive paired block intervals for the retrospective EOF–AR control.** Each skill interval is relative to the named baseline and uses a common scoring support. These unadjusted intervals are exploratory; no p-value claim is added to the frozen six-comparison family.

{{spatial_intervals_table}}

Reproduction proceeds through the original historical research, the frozen OISST validation, the frozen AMSR2 validation, and then the publication extension. The extension entry point is `python -m src.publication`, with `configs/publication.json` defining the explicit candidate grid, temporal boundaries and scoring rules. Frozen protocol hashes are checked on input. NOAA subset and AMSR2 subset hashes are checked before scoring. The fixed field has consecutive daily dates, matching coordinates and finite ocean values. No candidate fitting routine reads selection or evaluation observations to estimate parameters.

Daily CSVs retain errors, masks/counts and all loss components; aggregate tables average those daily quantities. Both exact identities are checked on every matched scoring date with an absolute 10⁻¹⁰°C² threshold. The maximum observed residual in the loss decomposition is {{identity_tolerance}}°C². Altering future values in dedicated tests cannot change training parameters or an origin-restricted forecast. Further tests cover paired support, multiplicity adjustment, cancellation of discrepancy loss by a negative interaction, and interval-score penalties.

The generated manuscript and supplement draw tables directly from the analysis outputs. Figures are supplied in 300 dpi PNG and scalable SVG formats, with checksums. Protocol records include software hashes, provider acquisition hashes, exact model parameters, seeds and analysis scope. No reference to an open repository substitutes for an immutable archived release DOI; such a deposition should accompany final submission. Author identities, affiliations, funding, conflicts and contributor roles must be confirmed separately before submission.
### S9. Three-year acquisition lock and stronger controls

The three-year forecast lock (`paper/confirmation/frozen_protocol.json`, SHA-256 `cf6a462d4d55ecd80915925cea8bba313680f11402a708d9764bc8715a761502`) precedes the new AMSR2 acquisition. Public commit `6edc533f2cd5f7d0d6f61a0b441f6610cd54ebed` records the design and hashes at 03:34:52 UTC on 10 October 2026. The pre-existing spatial basis, regional forecasts and all seven new forecast arrays were fixed at this stage. All 1,096 external dates were obtained without source absences; insufficient valid cells still exclude individual dates from scoring. Original 2026 selected-forecast scores are reproduced to the documented 10⁻⁵°C tolerance.

New control selection is restricted to the previously specified training and selection boundaries. Ridge VAR uses standardized lagged modal features, an unpenalized intercept and an L2 penalty scaled by the number of training pairs. The companion spectral radius must remain below one. Its recursively propagated retained scores enter the same spatial increment reconstruction as EOF–AR. The tree control standardizes each retained modal increment by its training standard deviation before joint fitting, so high-variance modes do not automatically dominate its split loss. Each horizon has separate training targets, while leaf size and feature fraction are selected once at seven days. Elapsed time and calendar harmonics are deterministic target features; all SST features are origin restricted. Horizon overlap and rolling origin updates do not permit reading intermediate future observations.

**Table S9. Every stronger-control candidate.** Selection RMSE is in °C. Candidate settings and all fitted coefficients remain in the machine-readable results.

{{confirmation_selection_table}}

**Table S10. New nighttime nine-comparison family, both block choices.** Pointwise skill bounds are percentages and are not family-wise confidence bounds. Holm-adjusted p values are listed independently. The seed, number of replicates, primary pass and baseline were fixed before acquisition; this family is separate from Table S2.

{{confirmation_inference_table}}

![Figure S3. Annual nighttime external skill.](annual_external_skill.png)

**Figure S3.** Annual skill is descriptive and compares identical dates/cells against grid-specific anomaly persistence. A pooled improvement can coexist with a negative year. No annual significance claim or retrospective exclusion of an unfavourable year is made.

![Figure S4. Pointwise uncertainty for the three-year external comparison.](primary_external_intervals.png)

**Figure S4.** Paired pointwise 95% intervals from 30- and 60-day calendar blocks. Multiplicity-adjusted tests appear in Table S10; a positive interval need not imply adjusted significance.

![Figure S5. External coverage by UTC month.](external_coverage_calendar.png)

**Figure S5.** All acquired dates enter the denominator for the fraction of dates meeting the minimum-20-cell gate. Domain weight fractions use the fixed cosine-latitude mask. The new three full years and the separate January–August 2026 window are shown without imputing missing observations.

**Table S11. Change in thirty-day squared-loss advantage between matched OISST and AMSR2, 2023–2025.** The baseline is grid-specific anomaly persistence. All entries are °C² and use identical date/cell support. The difference between external and analysis advantage equals the signed discrepancy perturbation; positive product discrepancy alone does not determine ranking.

{{confirmation_transfer_table}}

### S10. In situ matching, weighting and dependence

The iQuam protocol (`paper/insitu/frozen_protocol.json`, SHA-256 `4eac347075875db867689e80369b43b04d289efcf0dc7d6cff85966dceb4ddcf`) was publicly committed at 03:55:21 UTC on 10 October 2026 in `16fa9b784692c9bf2eacdf5513433865a3e602db`, before reading iQuam SST values. Only a variable/attribute inventory and official source filenames had been inspected. For each month, the highest file-version suffix visible at that time was fixed in the protocol; subsequent retrieval does not select a replacement version after seeing temperatures.

The point match retains quality level 5, finite SST from −2 to 35°C, buoy platform types 2/3/4/6/8, valid nonempty identifiers and thermometric observations (provider `sst_flags` bit 0 equals zero). Bit 1 distinguishes nighttime from daytime. The time origin is exactly seconds since 1 January 1981 00:00:00 UTC, and values must belong to the recorded source month and evaluation window. The nearest spherical fixed-cell centre must lie within 20 km. This is a point-to-grid-support rule; it does not assert that a point lies inside an exact coastline or that measurement time and depth match the daily analysis. No interpolation, depth correction, diurnal adjustment or SST bias correction is fitted.

Let eₚₖd be a collocated error for record k from platform identity p on date d, with platform type included in the identity. Daily loss is L(d)=P(d)⁻¹Σₚ[nₚd⁻¹Σₖeₚₖd²], where P(d) counts sampled platforms and nₚd counts a platform's records that date. RMSE is the square root of the equally weighted date mean of L(d). Absolute and signed errors follow the same nested weighting. This retains within-platform squared variation, rather than replacing it with a squared platform-mean error. Repeated hourly records cannot dominate other platforms or count as independent replicates. Platform support and every annual result are retained in CSV files.

{{insitu_results_text}}

![Figure S6. Quality-screened buoy point support.](buoy_support.png)

**Figure S6.** Displayed points are the unique coordinates of accepted nighttime/daytime observations, with fixed ocean-cell centres for context. Identical coordinates are plotted once; all temporal records are retained for scoring. Map density does not measure effective independent sample size. The scoring scheme balances platforms within dates and dates within the sample, not geographical area.

**Table S12. Annual nighttime buoy scores for the nonlinear spatial control and persistence.** Values are descriptive; shared quality-control references and possible OISST assimilation overlap preclude an independent-truth interpretation.

{{insitu_annual_table}}

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

{{process_forcing_table}}

![Figure S7. Evaluated domains and training seasonal diagnostics.](process_domains_and_seasonality.png)

**Figure S7.** Panel (a) shows only the evaluated fixed SST ocean-cell centres in colour; grey outlines are the official IHO sea-area polygons, including the unscored Eastern China Sea extent. The other panels show monthly averages of reanalysis net heat input (brown) and daily SST tendency (blue), estimated from 2010–2019 alone. Separate axes have different units and the curves do not constitute a heat-budget closure, regression estimate or causal test. No mixed-layer depth or advection is observed.

**Table S14. Every SST-only geographical-transfer score.** January–August 2026 and the three complete years remain separate. Direct transfer uses the identical source fit/scaler; destination-local references use destination training observations with source-selected hyperparameters. RMSE is °C. Negative skill values are retained.

{{process_transfer_full_table}}

![Figure S8. Direct transfer and destination-local fitting across forcing groups.](regional_transfer.png)

**Figure S8.** All groups and both families are retained at all three leads, including the additional training-calibrated reference added after inspecting the raw transfer failures. Lower RMSE is better. The horizontal benchmark uses destination-local training climatology, while direct transfer uses no destination-fitted coefficients. These are descriptive OISST comparisons on an adjacent shelf subregion, not independent-instrument or full-basin geographical validation.

#### Additional matched-satellite diagnostic

The source-region cell forecast is the origin OISST field plus the new regional predicted increment. All eighteen new family/group/horizon forecasts are evaluated with the unchanged nighttime AMSR2 flags, cosine-latitude weights and minimum-20-cell gate on the same dates. No newly estimated spatial pattern, SST bias correction, model selection or p value is introduced. The additional projection check was added after the local design record and is explicitly descriptive. Its matched OISST and AMSR2 aggregate and annual scores are archived alongside the full daily series.

{{process_external_text}}

#### Reproduction and computational safeguards

With the original OISST cache in place, run `python -m src.process_transfer prepare`, `python -m src.process_transfer acquire --workers 3`, `python -m src.process_transfer evaluate`, `python -m src.process_external`, `python -m src.process_alignment` and `python -m src.process_transfer deliver`. Boundary geometry is acquired directly from Marine Regions, validated by identifier/name/bounds/axis order and retained locally. Provider geometry is not redistributed. The forcing downloader verifies the R1 product identifier, field units, exact daily calendar and finite cropped values. Raw response and subset hashes are kept separately. No 2026 forcing window is silently shortened: that entire new forcing comparison is excluded because the chosen product ceased production in March. No replacement reanalysis was selected after examining scores.

Future-perturbation tests confirm that changing SST after the origin or weather on/after the origin cannot change an individual feature row; changing post-training labels cannot change training scaling or coefficients; changing post-selection outcomes cannot change the source hyperparameter; prediction on destination features cannot mutate the source scaler or coefficients. Original locked-file hashes are checked before and after the new experiment. These checks establish the stated computational information restrictions, not observational independence or measured operational latency.


#### Post-outcome calibration reference: explicit destination-training information

After the unchanged-source failures had been inspected, an additional descriptive location/scale reference was added (`python -m src.process_alignment`). Source regression/tree coefficients and source-selected hyperparameters are retained. For destination features Xd, z = (Xd−mean_d)/sd_d uses only destination 2010–2019 feature statistics. If the source predictor produces an increment u(z), the calibrated destination increment is mean_delta_d + sd_delta_d [u(z)−mean_delta_s]/sd_delta_s. Source and destination increment moments use only targets ending by 2019 and the complete training feature rows. No local regression or tree coefficients are used. The destination scaler is retrieved from the training statistics already stored with the local-reference model, independently of its fitted predictor.

This reference uses destination training histories to estimate calibration parameters. It is neither unchanged-scaler transfer nor a destination-data-free forecast. All feature groups, families, leads and annual scores are retained; no extra tuning, p value or selection is attached. The joint feature/increment calibration cannot separate individual causes of geographical shift, and its addition after seeing raw failures is recorded rather than treated as preregistered evidence. Tests verify that future labels cannot alter its increment moments, that changing local regression coefficients cannot alter its forecasts, and that an affine copy of a source series yields the corresponding affine-calibrated forecast.

**Table S15. SST-only transfer with destination-training calibration.** All numbers are °C. Raw transfer and local-fit references reproduce Table S14; the extra calibrated column uses destination training location/scale. Both periods, families and all leads are retained.

{{process_alignment_table}}
