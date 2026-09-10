# Yellow Sea SST Stochastic Modeling

A reproducible research project for studying Yellow Sea sea-surface-temperature
(SST) anomalies with stochastic-process and statistical-learning methods.

## Research question

How predictable are daily Yellow Sea SST anomalies from their own temporal
history, and which stochastic or statistical models describe their persistence,
variability, and forecast uncertainty without overstating the available
evidence?

Phase 1 establishes the auditable data pipeline, exploratory workflow, and a
minimal persistence baseline. It does **not** report experimental results or
claim that any model outperforms the baseline.

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
src/models/              Forecast baselines (Phase 1: persistence only)
src/evaluation/          Forecast metrics
notebooks/               Reproducible exploration notebooks
tests/                   Unit tests for core transformations
paper/                   Manuscript materials (intentionally empty in Phase 1)
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

Download a date range of final OISST v2.1 daily files (example dates only;
choose the study period deliberately):

```bash
python -m src.data.download_oisst \
  --start-date 1982-01-01 \
  --end-date 2025-12-31 \
  --output-dir data/raw/oisst
```

Preprocess the files using the default Yellow Sea bounding box (31-39 degrees
north, 117-127 degrees east) and a day-of-year climatology:

```bash
python -m src.data.preprocess \
  --input-dir data/raw/oisst \
  --output-file data/processed/yellow_sea_sst_daily.csv \
  --lat-min 31 --lat-max 39 --lon-min 117 --lon-max 127 \
  --climatology dayofyear
```

Then launch `jupyter lab` and run
`notebooks/01_explore_yellow_sea_sst.ipynb`. The notebook expects the processed
CSV above and deliberately contains no stored outputs.

Create persistence-baseline predictions and metrics only after preprocessing:

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

**Phase 1 only.** Repository scaffolding, NOAA download tooling, preprocessing,
exploratory analysis, a persistence baseline, and unit tests are included.
No observational data, generated results, fitted AR/OU/XGBoost models, or paper
conclusions are committed. Later phases must define a leakage-safe validation
protocol before comparing models.
