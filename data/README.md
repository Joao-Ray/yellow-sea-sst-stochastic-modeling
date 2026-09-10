# Data directory

This directory is intentionally data-free in version control.

- `raw/oisst/`: NOAA OISST v2.1 daily NetCDF files created by the downloader.
- `processed/`: derived regional SST and anomaly time series, predictions, and
  metrics.

Both subdirectories are ignored by Git. Recreate them using the commands in the
repository-level README rather than committing data products.
