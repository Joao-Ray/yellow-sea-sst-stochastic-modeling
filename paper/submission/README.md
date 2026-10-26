# English scientific manuscript

Research draft, reviewed 26 October 2026. The intended research standard is
CAS Zone 1; this label is an objective, not an achieved publication rating.

- `manuscript_en.md`: integrated English scientific manuscript, eight main figures
  and nine main tables, followed by verified primary references.
- `supplement_en.md`: detailed chronology, acquisition/decoding audit, spatial
  selection, dependence/interval diagnostics and complete comparisons.
- `*.png` / `*.svg`: eighteen scientific figures, 300 dpi and vector formats.
- `results/`: reviewed aggregate tables and exact spatial parameters.
- `extension_design.json`: local retrospective design record; not a public
  preregistration or an untouched holdout.
- `../confirmation/`: publicly locked three-year external experiment, coupled VAR
  and nonlinear controls, complete comparisons and byte-exact reconstruction audit.
- `../insitu/`: frozen source versions and descriptive buoy point-support checks.
- `../process_transfer/`: retrospective past-heat/wind ablations, unchanged-parameter
  transfer to 230 northern Eastern China Sea cells, complete failures and source provenance.
- `../anomaly_transfer/`: expanded source grids, climatology-assisted anomaly transfer,
  fixed climatology/AR(1) controls and complete partial-year failures; descriptive only.
- `../destination_validation/`: pre-scoring-locked destination satellite/buoy checks,
  fixed spatial decay references, all primary contrasts and independent arithmetic audit.
- `references_verified.md`: checked bibliography and primary-source links.
- `*.template.md`: reproducible manuscript templates. Results are filled
  directly from reviewed output tables. After the new analysis stages,
  `python -m src.publication_delivery` assembles all manuscripts without refitting.

## Evidence hierarchy

1. Original 2010–2025 exploration and historical sensitivity results.
2. Frozen January–August 2026 OISST temporal test, committed before acquisition.
3. Frozen AMSR2 instrument test, committed before external acquisition, but
   after the OISST outcomes were inspected.
4. Retrospective publication extension after all these outcomes were viewed.
5. Publicly forecast-locked 2023–2025 AMSR2 extension conditional on prior
   exploration, with three stronger spatial models × three horizons in a new
   nine-comparison family, Holm adjusted separately per block choice.
6. Source/matching-locked 2023–2025 iQuam buoy description; shared QC references
   and possible analysis input overlap prevent an independent-truth claim.
7. Retrospective forcing and adjacent-shelf extension, with a distinct 36-contrast
   exploratory family; further matched-satellite projection scores are descriptive.
   Full Eastern China Sea coverage and 2026 forcing beyond March were not acquired.
   An additional locally calibrated transfer reference was added after inspecting
   raw transfer failures and remains descriptive.

8. Retrospective expanded-grid and climatology-assisted anomaly sensitivity; local
   destination history is required, and simple anomaly decay/climatology controls
   prevent a general complexity or zero-shot-transfer claim. No new p values.

9. Pre-scoring-locked destination instrument comparison on existing previously acquired
   files: eighteen primary satellite contrasts, descriptive buoys, fixed spatial controls
   and explicit lack of complex-model advantage. This is not a new blind holdout.

The frozen model files and original primary metrics remain unchanged. The
initial extension has training-only parameters and selection-only tuning, which
avoids computational leakage but does not remove scientific hindsight. Its
intervals remain descriptive. Later primary spatial comparisons use the separately
frozen nine-comparison family and are not added to the original six-comparison
family. Pointwise intervals are not simultaneous family-wise intervals.

## Submission status

The manuscript and supporting experiments are reviewable. The available data
do not yet establish an instrument-independent full-basin forecast improvement,
a causal ocean mechanism, or superiority to forcing-informed forecast systems.
For the CAS Zone 1 objective, the Chinese assessment identifies these substantive
gaps and a concrete confirmation design. Authorship, affiliations, contributor
roles, funding, conflicts, target journal and an immutable data/code deposition
must be finalized by the responsible researchers before submission. No author
or funding declaration has been invented.
