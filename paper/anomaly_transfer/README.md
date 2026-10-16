# Expanded source selection and climatology-assisted anomaly transfer

Retrospective sensitivity, 16 October 2026. The design follows inspection of earlier raw-transfer failures and candidate-edge selections; it is not a blind or prospectively registered test.

- `design_record.json`: finite expanded source grids, temporal cutoffs and input hashes.
- `benchmark_design.json`: fixed training-only climatology and AR(1) references.
- `results/`: all aggregate metrics, annual/seasonal outcomes, selection curves, parameters, pointwise intervals and audits; `report_en.md` explains the complete SST-only results.
- `results/anomaly_transfer_controls.*`: both periods, both families, all leads and simple controls.
- `results/expanded_source_selection.*`: every source-validation candidate, including remaining lower-edge sensitivity.

Destination training climatology, trend and residual scales are fitted locally on 2010–2019. Source increment coefficients and source feature scalers remain fixed. This is climatology-assisted transfer, not zero-shot transfer. All destination outcomes are same-product OISST comparisons on 230 adjacent northern Eastern China Sea cells.

The 2023–2025 thirty-day anomaly-transfer improvement over non-decaying persistence is matched by a simple source AR(1) reference. Partial 2026 destination outcomes favour training climatology alone at thirty days. Projected source-region AMSR2 scores also retain fixed climatology and AR(1) comparisons. No new p values or confirmatory discovery claims are added.

Full predictions, daily losses and fitted models are stored locally in `data/processed/anomaly_transfer/` and included in the reproducibility data package; large daily files are omitted from reviewed repository tables. Original frozen files and prior process-transfer outputs are protected by hash checks. See [Chinese assessment](../../docs/ANOMALY_TRANSFER_zh.md) and the integrated manuscript/supplement for reproduction and limitations.
