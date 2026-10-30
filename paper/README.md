# Paper materials

A revised Chinese manuscript with exploratory backtests and frozen temporal validation is available at [manuscript_zh.md](manuscript_zh.md).
The six figures in `figures/` are generated from the fixed research outputs.
Their data and code provenance is documented in the manuscript and
[completion notes](../docs/COMPLETION_zh.md).
Aggregate scores and diagnostics for all cases are in results/.

Reproduce the report and manuscript using:

```bash
python -m src.research
python -m src.validation evaluate
```

The IHO Yellow Sea polygon used here includes Bohai. This is an explicit
operational region, not a claim about a unique geographical definition.
The extension was designed after initial pilot test scores were viewed;
results are exploratory retrospective evidence, not pristine confirmation.

The draft is ready for scientific review. Journal submission, authorship,
independent observational confirmation, and causal claims are outside this software/study deliverable.

A previously unexamined 2026 January-August temporal window is now reported
in the abstract, methods, results, discussion and conclusions. Its 1-day skill
is positive; 7-day evidence is inconclusive and 30-day point skill is negative.
See [frozen design and aggregate validation](validation/README.md). This is
the same OISST product, not an independent observational source.
