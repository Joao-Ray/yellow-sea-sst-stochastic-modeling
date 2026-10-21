# Past-forcing information and adjacent-shelf transfer

Retrospective extension, 16 October 2026. The original frozen temporal,
independent-instrument, three-year and in situ protocols remain unchanged.

## Design and limits

- `design_record.json`: local design/configuration and availability amendments,
  recorded before the new model scores. This is not a public preregistration.
- `results/report_en.md`: data-driven results and figures.
- `results/metrics.csv`, `annual_metrics.csv`, `seasonal_metrics.csv`: every
  family, feature group, horizon and fitting context, including failures.
- `results/forcing_inference.csv`: all 36 exploratory contrasts with both block
  lengths, pointwise intervals and Holm adjustment over the complete family.
- `results/external_metrics.csv` and `external_annual_metrics.csv`: descriptive
  matched-nighttime AMSR2/OISST projection checks; no additional selection or test.
- `results/provenance.json`, `sst_provenance.json`, `evaluation_audit.json`,
  `external_audit.json`: original response/subset hashes, exact provider URLs,
  software identities, fixed geometry and original-input integrity.
- `results/parameters.json`, `selection.csv`: source-only hyperparameter choices,
  training scaling and linear coefficients; serialized trees and full daily
  predictions are retained in the local data/results package.

The source is the original 651-cell Yellow–Bohai mask. The destination is only
230 ocean cells of northern Eastern China Sea MRGID 4302 inside the original
cached box, not the complete Eastern China Sea. There is no cell overlap and no
independent-instrument geographical test at the destination. Direct transfer
requires destination origin SST and past weather, but estimates no destination
parameters. Local-fit references use destination training labels with the same
source-selected hyperparameters.

The eight NCEP/NCAR R1 daily fields cover 2010–2025. Production ended on
17 March 2026, so there is no artificially extended 2026 forcing evaluation.
SST-only January–August 2026 results are reported separately. A calendar cutoff
at origin minus one day is not a reconstruction of real operational latency.
Reanalysis fluxes depend on model physics and prescribed/analysed SST; coarse
coastal grid boxes may contain land. Adding these features does not identify a
causal heat budget, mixed-layer depth, advection or wind mixing mechanism.

## Reproduce

After the original OISST acquisition:

```bash
python -m src.process_transfer prepare
python -m src.process_transfer acquire --workers 3
python -m src.process_transfer evaluate
python -m src.process_external
python -m src.process_transfer deliver
python -m src.publication_delivery
```

The extra satellite diagnostic requires the already acquired 2023–2025 AMSR2
subsets and original locked forecast archive. It reproduces the old baseline
scoring support/loss before accepting any new comparison. Raw crops, complete
regional/forcing series, daily predictions and model archive remain local or in
the separate data/results package. Provider sea-area geometry is downloaded and
validated directly and is not redistributed here.


## Additional post-outcome reference

After raw transfer failures were inspected, `python -m src.process_alignment`
adds a descriptive destination-training location/scale calibration. It retains
source model coefficients but requires destination 2010–2019 feature and increment
moments. This is not unchanged-scaler or destination-data-free transfer. No new
hyperparameter selection or p value is added; all groups/horizons/years remain
visible in `alignment_metrics.csv`, `alignment_annual_metrics.csv` and the audit.
Run it before `deliver` to include this explicitly post-outcome reference.
