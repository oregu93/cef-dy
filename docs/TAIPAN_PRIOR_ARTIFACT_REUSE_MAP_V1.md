# TAIPAN prior-artifact reuse map v1 (historical pre-integration review)

> The temperature status in this review was superseded on 2026-10-21 by the
> accepted `taipan_temperature_mapping_v1` reconstruction. The executable current
> contract is `configs/taipan_prior_artifact_reuse_v1.yaml`.

This map freezes the pre-run boundary for the user-executed exploratory CEF
pipeline. The scientific authority is the public `oregu93/cef-dy` repository.
The private repository records `EXP-TAIPAN-001` as known but not located and
unverified, so it is not used as a TAIPAN scientific-state source.

## Reused layers

| Layer | Classification | Current role |
|---|---|---|
| A002 scan points, scan inventory, lattice/UB states, semantics and provenance | `REUSE_DIRECTLY` | Canonical acquisition geometry, energies, counts metadata and provenance; no new raw parser. |
| A003 scan classification, acquisition states, instrument configuration and normalization groups | `REUSE_DIRECTLY` | Count-control and justified nuisance-scale grouping. |
| B001 blind split and discovery point representation | `REUSE_DIRECTLY` | Discovery-only detector values. The sealed holdout is not decoded or used. |
| B001 blind feature catalogue and reproducibility table | `REUSE_AS_EXPLORATORY_ANCHOR` | Overlapping discovery windows; not one-to-one CEF levels. |
| B001 scientific review | `REUSE_FOR_VALIDATION_ONLY` | Interpretation boundary and independent review context. |
| C001 v1.1 resolution evidence and background sensitivity | `REUSE_AS_EXPLORATORY_ANCHOR` | Empirical resolution/background semantics only. |
| C001 final fits, parameter uncertainty, resolution status and context assessment | `REUSE_FOR_VALIDATION_ONLY` | Diagnostics; never silently promoted into current CEF targets. |
| Legacy scan 104062 fit | `REUSE_AS_EXPLORATORY_ANCHOR` | Gaussian `FWHM = 0.894 ± 0.025 meV` near `Q ≈ 2.26 Å⁻¹`; not a production TAS resolution function. |
| Legacy 44.4-meV Q diagnostic | `REUSE_FOR_VALIDATION_ONLY` | `DIAGNOSTIC_OR_POSSIBLY_MIXED`; never a mandatory CEF level. |
| Legacy scalar 6.45/18.2/27.9-meV hypotheses | `SUPERSEDED` | Not current fit targets. The W02 energy status is `MODEL_DEPENDENT_ENERGY`. |
| Historical R3/R5/R7 and formal/PCM/M0 models | `REUSE_AS_EXPLORATORY_ANCHOR` | Deterministic initialization or frozen-seed diagnostics only. |
| Literature M(H), commit `2c17955c…` | `REUSE_FOR_VALIDATION_ONLY` | Downstream frozen single-ion validation; joint fitting remains disabled. |
| Private-repository TAIPAN asset entry | `NOT_APPLICABLE_TO_CURRENT_OBJECTIVE` | `KNOWN_BUT_NOT_LOCATED`, `UNVERIFIED`, no repository paths. |

The machine-readable identities, SHA-256 values and classifications are in
[`configs/taipan_prior_artifact_reuse_v1.yaml`](../configs/taipan_prior_artifact_reuse_v1.yaml).

## Temperature audit

A002 preserves several temperature-like raw channels but selects none as a
physical sample temperature: every scan has `temperature_summary_K = null`
and `selection_status = no_unique_sensor_or_unit_selected`. The legacy state
records approximate 3.4–3.5 K and 10 K blocks, but no reviewed artifact maps
their exact membership to `scan_record_id` or `raw_scan_id` with verified
channel semantics. Chronology and recollection are deliberately not used.

Therefore:

```text
TEN_K_BLOCK_STATUS = NOT_YET_ESTABLISHED
TEN_K_SCAN_COUNT = 0
TEN_K_SCAN_IDS_SOURCE = NONE__NO_REVIEWED_DETERMINISTIC_SCAN_TO_TEMPERATURE_MAPPING
```

The materializer may produce a deterministic discovery-only, temperature-
unresolved bridge table for inspection, but the data audit remains `NOT_READY`
for the 10-K CEF sanity run until a reviewed mapping is supplied.

The dedicated blocker report and the metadata-only preflight for priority raw
scans 104095, 104098, 104099, 104215 and 104225 are in
[`docs/TAIPAN_TEMPERATURE_MAPPING_BLOCKER_V1.md`](TAIPAN_TEMPERATURE_MAPPING_BLOCKER_V1.md)
and
[`configs/taipan_cx02_priority_scan_preflight_v1.yaml`](../configs/taipan_cx02_priority_scan_preflight_v1.yaml).

## Blind features and the 44.4-meV region

B001 contributes eight overlapping windows: BF-001–BF-003 span the broad
2.5–7 meV region, BF-004–BF-005 span 17.5–20.5 meV, and BF-006–BF-008 span
40.5–46.5 meV. Overlaps are preserved explicitly by allowing multiple
`feature_id` values per measured point. No B001 feature becomes a mandatory
CEF assignment. BF-006–BF-008 are retained as masked diagnostic points because
the earlier Q test does not strongly support a simple one-component localized
Dy form-factor/polarization interpretation.

## Intensity, geometry, background and resolution

The bridge uses the original long-form discovery points without gridding. For
monitor-controlled data it records both original detector/monitor values and
the linear working quantity `detector_counts / monitor`, in
`counts_per_monitor`. A nuisance scale is permitted only per A003
normalization/instrument block, never per scan.

For each point, Q is recalculated from its own A002 `lattice_state_id` using
orthorhombic Pbnm reciprocal coordinates and reordered into the internal
`(b,c,a)` frame. Undefined directions fail closed; powder averaging is not a
fallback.

The single-crystal intensity calculation transports the reference-site
transition tensor over all four Pbnm Dy(4c) sites using the accepted
`STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001` matrices and sums the four
localized independent-site responses. The regression invariant is
`sum_s R_s M R_s^T = 4 diag(M_XX,M_YY,M_ZZ)`. This does not introduce four
independent CEF parameter sets and does not represent coherent inter-site
dynamical correlations.

The point layer is not background-subtracted. The configured semantics are
`LOCAL_LINEAR_BACKGROUND`, informed by B001/C001 but not claimed as a unique
physical background. The 0.894-meV elastic Gaussian is an approximate frozen
forward baseline only; intrinsic linewidth inference and production TAS
resolution claims remain forbidden.
