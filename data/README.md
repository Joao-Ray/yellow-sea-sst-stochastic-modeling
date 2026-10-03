# Data directory

This directory is intentionally data-free in version control.

- `raw/oisst/`: NOAA OISST v2.1 daily NetCDF files created by the downloader.
- `raw/psl-pilot/`: monthly official regional subsets, each with a provenance
  JSON and SHA-256 checksum; approximately 33 MiB for the frozen pilot.
- `processed/`: derived regional SST and anomaly time series, predictions, and
  metrics.
- `processed/pilot/`: frozen config, Chinese/English reports, figures, daily
  series, model parameters, forecasts, diagnostics, and acquisition provenance.
- `raw/research/`: expanded monthly SST subsets covering the complete polygon.
- `raw/boundaries/`: official Marine Regions polygon and checksum/source metadata;
  fetch from the provider rather than redistributing geometry.
- `processed/research/`: complete backtests, calibration, sensitivity, residual
  diagnostics, standalone HTML report, five figures, manuscript and checksums.

Both subdirectories are ignored by Git. Recreate them using the commands in the
repository-level README rather than committing data products.
