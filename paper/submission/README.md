# English scientific manuscript

Research draft, reviewed 10 October 2026. The intended research standard is
CAS Zone 1; this label is an objective, not an achieved publication rating.

- `manuscript_en.md`: full English scientific manuscript, four main figures
  and four main tables, followed by verified primary references.
- `supplement_en.md`: detailed chronology, acquisition/decoding audit, spatial
  selection, dependence/interval diagnostics and complete comparisons.
- `*.png` / `*.svg`: six new scientific figures, 300 dpi and vector formats.
- `results/`: reviewed aggregate tables and exact spatial parameters.
- `extension_design.json`: local retrospective design record; not a public
  preregistration or an untouched holdout.
- `references_verified.md`: checked bibliography and primary-source links.
- `*.template.md`: reproducible manuscript templates. Results are filled
  directly from `python -m src.publication` output tables.

## Evidence hierarchy

1. Original 2010–2025 exploration and historical sensitivity results.
2. Frozen January–August 2026 OISST temporal test, committed before acquisition.
3. Frozen AMSR2 instrument test, committed before external acquisition, but
   after the OISST outcomes were inspected.
4. Retrospective publication extension after all these outcomes were viewed.

The frozen model files and original primary metrics remain unchanged. The
extension has training-only parameters and selection-only tuning, which avoids
computational leakage but does not remove scientific hindsight. Its confidence
intervals are descriptive, and new spatial p-value claims are not added to the
original six-comparison family.

## Submission status

The manuscript and supporting experiments are reviewable. The available data
do not yet establish an instrument-independent full-basin forecast improvement,
a causal ocean mechanism, or superiority to forcing-informed forecast systems.
For the CAS Zone 1 objective, the Chinese assessment identifies these substantive
gaps and a concrete confirmation design. Authorship, affiliations, contributor
roles, funding, conflicts, target journal and an immutable data/code deposition
must be finalized by the responsible researchers before submission. No author
or funding declaration has been invented.
