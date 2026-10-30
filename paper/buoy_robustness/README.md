# Retrospective buoy support robustness

This phase uses existing locked predictions and accepted source/destination iQuam
matches after all prior scores were known. It is descriptive, with no additional
significance tests, confidence intervals, matching changes or refits.

- `results/full_metrics.csv`: original equal-date/platform scores and the alternative
  equal-period-platform estimand; all models/leads/passes/targets and fixed references.
- `results/deletion_metrics.csv.gz`: every composite type/ID and whole-type removal,
  including full-platform reference losses on exactly the same retained dates.
- `results/deletion_summary.csv`: complete removal ranges, signs and support counts.
- `results/annual_metrics.csv`: all annual outcomes under both weighting estimands.
- `results/platform_weights.csv`: contribution to the original period score,
  raw record fractions and sole-platform dates.
- `results/evaluation_audit.json`: original daily-loss reproduction, input/software
  hashes, runtime versions and preservation of 268 earlier-stage files.
- `results/buoy_platform_sensitivity.png` / `.svg`: observed removal ranges;
  these segments are not inferential uncertainty intervals.

Removing type 4 leaves only 231 source / 288 destination nighttime dates. Such
subsets do not represent the original complete-period support. Platform identifiers,
QC references and possible OISST assimilation overlap do not create independent truth.

With existing caches, run `python -m src.buoy_robustness`, then
`python -m src.publication_delivery`. Previous protocols and result files are preserved.
See [Chinese interpretation](../../docs/BUOY_ROBUSTNESS_zh.md) and Supplementary S15.
