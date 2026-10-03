# Yellow Sea SST Stochastic Modeling

A reproducible research project for studying Yellow Sea sea-surface-temperature
(SST) anomalies with stochastic-process and statistical-learning methods.

## Research question

How predictable are daily Yellow Sea SST anomalies from their own temporal
history, and which stochastic or statistical models describe their persistence,
variability, and forecast uncertainty without overstating the available
evidence?

The project includes a leakage-safe experiment with climatology, persistence,
AR(1), validation-selected AR(p), an exact OU interpretation, and an offline
synthetic demo. A reproducible observational pilot adds official regional
acquisition, paired calendar-block skill intervals, and residual diagnostics.
It does **not** claim robust observational model superiority. See the
[Chinese quick start](docs/QUICKSTART_zh.md) and
[validation protocol](docs/VALIDATION.md).

## Data source

The project uses the NOAA/NCEI 1/4-degree Daily Optimum Interpolation Sea
Surface Temperature (OISST), Version 2.1, AVHRR-only product. NOAA describes it
as a global Level-4 analysis combining satellite and in-situ observations on a
0.25-degree grid. The record begins in September 1981. Final files replace
near-real-time preliminary files after NOAA's production delay.

- Dataset DOI: [10.25921/RE9P-PT57](https://doi.org/10.25921/RE9P-PT57)
- [NOAA/NCEI OISST v2.1 product page](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)
- [NOAA/NCEI THREDDS catalog](https://www.ncei.noaa.gov/thredds/catalog/OisstBase/NetCDF/V2.1/AVHRR/catalog.html)
- Reynolds et al. (2007), [Daily High-Resolution-Blended Analyses for Sea Surface Temperature](https://doi.org/10.1175/2007JCLI1824.1)
- Banzon et al. (2016), [A long-term record of blended satellite and in situ sea-surface temperature for climate monitoring, modeling and environmental studies](https://doi.org/10.5194/essd-8-165-2016)
- Huang et al. (2021), [Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version 2.1](https://doi.org/10.1175/JCLI-D-20-0166.1)

Downloaded NOAA files and all derived data are excluded from version control.
Users must comply with NOAA's terms and cite the dataset in resulting work.

## Project structure

```text
data/                    Local-only raw and processed data
src/data/                Downloading and preprocessing modules
src/models/              Persistence, AR(1)/AR(p), exact OU interpretation
src/evaluation/          Time splits, common-support scores, reports
src/demo.py              Offline synthetic NetCDF-to-report workflow
src/pilot.py             Frozen observational pilot and provenance
configs/pilot.json       Dates, region, candidate orders, bootstrap design
docs/                    Quick start and validation protocol
notebooks/               Reproducible exploration notebooks
tests/                   Unit tests for core transformations
paper/                   Manuscript scope and remaining research requirements
```

## Reproduction

Python 3.11 is recommended. Commands below are run from the repository root.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Run the complete workflow without downloading data

```bash
python -m src.demo
```

This creates a ten-year **synthetic** SST grid with land cells and short/long
gaps, preprocesses it, and evaluates 1-, 7-, and 30-day forecasts. Read
`data/processed/demo/summary.md` and `overview.png`. All outputs clearly identify
the synthetic source and are excluded from Git. They are software validation,
not Yellow Sea observations or paper results.

### Acquire multi-year regional NOAA data

For multi-year records, prefer the official NOAA PSL regional service:

```bash
python -m src.data.download_psl \
  --start-date 2010-01-01 --end-date 2025-12-31 \
  --output-dir data/raw/psl-pilot
```

This downloads monthly SST subsets instead of global daily files. Every file
has a request URL, product/version note, dates, coordinates and SHA-256 sidecar;
cached files are verified before reuse. The downloader crops service padding
and checks every requested date. Up to three HTTP requests overlap, while
NetCDF access is serialized because the backend is not thread-safe.
Recent data less than 16 days old are rejected to avoid the provisional period.

The [NOAA PSL catalog](https://psl.noaa.gov/thredds/catalog/Datasets/noaa.oisst.v2.highres/catalog.html)
provides the [official subset service](https://psl.noaa.gov/thredds/ncss/grid/Datasets/noaa.oisst.v2.highres/sst.day.mean.2022.nc/dataset.html).
Historical files before 2016 retain OISST v2 metadata; NOAA NCEI states their
SST values are unchanged in v2.1. The distinction is preserved in provenance.
Files from 2016 onward must identify v2.1. Acknowledge NOAA PSL in uses of its
served data, alongside the dataset citation above.

### Run the frozen observational pilot

```bash
python -m src.pilot
```

The design in `configs/pilot.json` is saved before acquisition/evaluation:
2010–2019 training, 2020–2022 validation, 2023–2025 test; candidate AR orders
1/3/7/14 selected on validation 7-day RMSE; 1/7/30-day test forecasts; 500 paired
circular calendar-block bootstrap replicates with blocks of at least 30 days.
Parameters stay fitted to training observations. The selected-model validation
score is selection-biased and is reported separately from test results.

Read `data/processed/pilot/报告_zh.md` or `summary.md`. Outputs include raw regional
CSV, input/acquisition checksums, runtime versions, parameter files, error/skill
tables, residual correlations, Q–Q and coverage plots. Skill intervals rely on
approximate stationarity and block length; no final marine-boundary or
cross-period superiority claim is made. This is an exploratory bounding-box
pilot, not a pre-registered final study.

### Small check using NCEI global daily files

Download a week of final files first. Full decades of global daily files require
many gigabytes, so choose and budget a longer study period deliberately:

```bash
python -m src.data.download_oisst \
  --start-date 2022-01-01 \
  --end-date 2022-01-07 \
  --output-dir data/raw/oisst
```

Preprocess this small check using the default bounding box (31-39 degrees
north, 117-127 degrees east) and a month climatology within the downloaded week:

```bash
python -m src.data.preprocess \
  --input-dir data/raw/oisst \
  --output-file data/processed/yellow_sea_sst_daily.csv \
  --lat-min 31 --lat-max 39 --lon-min 117 --lon-max 127 \
  --climatology month \
  --climatology-start 2022-01-01 --climatology-end 2022-01-07
```

The week-long check validates downloading and preprocessing only. Its seasonal
cycle is not suitable for forecasting. Coverage is measured against cells with
any valid SST in the input record, excluding permanent land. This empirical
mask is not an exact geographical Yellow Sea boundary; the default rectangle
also contains adjacent seas. Short internal gaps are filled only when the
**whole** gap is within the configured limit. Raw values remain in
`sst_observed_celsius`; a metadata JSON accompanies the CSV.

For exploratory analysis, launch `jupyter lab` and run
`notebooks/01_explore_yellow_sea_sst.ipynb`. The notebook expects the processed
CSV above and deliberately contains no stored outputs.

### Run a chronological forecasting experiment

After acquiring a deliberately chosen multi-year record and preprocessing it,
use explicit training/validation cutoffs. For an example **1991–2025 input
record** (not included), run:

```bash
python -m src.evaluation.experiment \
  --input-file data/processed/yellow_sea_sst_daily.csv \
  --output-dir data/processed/experiment \
  --train-end 2010-12-31 --validation-end 2015-12-31 \
  --horizons 1 7 30
```

This recomputes climatology from training observations, ignores input anomaly
columns, and excludes interpolated values from fitting, origins, and targets.
Training parameters stay frozen; each forecast uses the observed value at its
origin, without observing intermediate future days. Validation and test scores
are separate, and all compared models use the same eligible dates per horizon.
No model selection or significance claim is made. Reports include conditional
AR(1) Gaussian intervals and empirical coverage, plus limitations.

The stationary OU process is the exact interpretation of the AR(1) transition
when `0 < phi < 1`; its parameters and half-life appear in `parameters.json`.
It has the same forecasts as AR(1) and is not counted as an independent model.

The original Phase 1 persistence command remains available for an exploratory
diagnostic. Its supplied anomaly series may have used a reference period
overlapping the test segment; use the Phase 2 experiment for comparisons:

```bash
python -m src.models.persistence \
  --input-file data/processed/yellow_sea_sst_daily.csv \
  --predictions-file data/processed/persistence_predictions.csv \
  --metrics-file data/processed/persistence_metrics.json
```

Run the test suite without downloading NOAA data:

```bash
python -m pytest
```

## Current status

**Observational pilot completed locally.** The frozen 2010–2025 design produced
5,844 valid daily regional means, no missing days, and a 2023–2025 independent
test segment. AR(1) was selected on validation; its test RMSE did not beat
persistence at 1/7/30 days, and 7/30-day conditional interval coverage was below
the nominal 95%. These are exploratory results for a rectangle containing
adjacent seas; see [project status](docs/PROJECT_STATUS.md).

Training-only preprocessing,
chronological validation/test splits, common-support multihorizon evaluation,
AR(1)/OU parameters, conditional uncertainty, labeled synthetic demo, regression
tests, validation-selected AR(p), audited regional acquisition, block-bootstrap
skill intervals, residual diagnostics, and GitHub Actions are included. Downloaded observations and generated
outputs stay local and are not committed.

Next research steps: decide a defensible geographical ocean mask, inspect trend
and seasonal smoothing choices, repeat independent time splits and block-length
sensitivity, and compare richer models under a predeclared protocol. XGBoost models and
manuscript conclusions are not yet implemented.
