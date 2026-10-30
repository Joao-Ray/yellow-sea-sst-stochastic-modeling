# Buoy support robustness implementation plan

Scope: continue the authorized data-verification and manuscript improvement. Add a retrospective descriptive sensitivity, using existing locked forecasts and accepted point matches. Do not change models, matching, quality thresholds, primary tests, or previous phase artifacts. Run within the existing clean research branch and its recorded Python environment.

Approach: compute platform-day losses, reproduce every existing buoy daily score, then remove each type/ID combination and each platform type in turn. Recompute the original equal-platform-within-date/equal-date estimand on all surviving dates. Also show the full-sample scoring on exactly those same dates to distinguish changed date support. Compare an alternative equal-platform-over-period summary, labelled a different estimand. Report all models, horizons, passes, both observation targets and failed cases. No new p-values or confidence intervals.

## Tasks
1. Add tests with hand-calculated uneven record counts, multiple dates, platform IDs shared by types, vanished dates, empty deletion, and nonfinite losses. Verify RED.
2. Implement `src/buoy_robustness.py` aggregation, deletion and support functions; verify GREEN. Read original accepted collocations and frozen cubes; validate original daily-score agreement before generating sensitivity outputs.
3. Add complete CSVs, provenance hashes, protected-file before/after audit, two-panel descriptive figure and computed report. All payload checksums and reviewed copies must agree.
4. Integrate a short main-text boundary and supplementary methods/table/figure in existing publication assembly; update Chinese interpretation and reproduction instructions. Preserve previous frozen artifacts and historical release packages.
5. Run all tests, formatting and manifest checks; inspect the new figure and rendered document links; request independent code review; resolve findings. Publish concrete changes to the existing draft PR and create a new dated review package if possible.

## Review focus
- Repeated records cannot overweight a platform-day.
- A deletion can remove a date; full-sample comparisons must use the same remaining dates.
- Composite platform type/ID, not ID alone, defines the removal unit.
- Empty deletion returns explicit unscorable support, without infinity or a false zero.
- Concentration is a weighting diagnostic, not independent sample size; leave-one-platform ranges are not uncertainty intervals.
