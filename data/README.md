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
- `raw/validation/`: eight monthly OISST subsets for the frozen 2026 test.
- `raw/independent/`: 243 daily AMSR2 subsets, acquisition manifests and the
  independently decoded full-file audit; source measurements remain local.
- `processed/publication/`: retrospective spatial controls, daily paired losses,
  exact loss identities, descriptive spatial intervals, secondary inference,
  seasonal/interval diagnostics, generated English manuscript and supplement.
- `raw/confirmation/`: all 1,096 daily AMSR2 geographic subsets for 2023–2025,
  with source URLs, ETags, verified byte ranges and subset SHA-256 manifests.
- `processed/confirmation/`: locked seven-model forecast cube, serialized tree
  estimators, new nine-comparison inference, daily losses and annual/seasonal tables.
- `processed/confirmation_rebuild/`: separate post-outcome reconstruction and
  byte-exact audit; original frozen archives are never overwritten.
- `raw/insitu/`: 36 version-locked iQuam monthly point subsets in original units,
  including all geographic records before quality/point-matching filters.
- `processed/insitu/`: point collocations, platform-balanced daily losses, actual
  coverage, source/extraction audits and descriptive buoy verification.
- `processed/submission/`: integrated English manuscript/supplement, self-contained
  HTML, eleven scientific figures and integrity manifest.

Only reviewed aggregates, protocol hashes and source provenance are mirrored to
`paper/confirmation/results/` and `paper/insitu/results/`. Large forecast/model
archives and daily/raw records remain local and can be rebuilt from upstream
caches using the exact-hash reconstruction command. An immutable public data/code
deposition remains a submission requirement. iQuam quality checks use analysis
references and its observations may overlap OISST inputs; buoy scores are not an
independent-truth estimate.

Both subdirectories are ignored by Git. Recreate them using the commands in the
repository-level README rather than committing data products.
