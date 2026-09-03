---
title: "DyFeO3 — Stage 02R W02-02R-B-001 blind feature discovery specification"
type: work_job_specification
project_id: CEF-Dy
stage_id: M02R
task_id: T-02R-04
job_id: W02-02R-B-001
status: frozen
version: "1.0"
updated: 2026-09-04
language_content: ru
language_metadata: en
---

# W02-02R-B-001

## STATUS

```yaml
stage_id: M02R
task_id: T-02R-04
job_id: W02-02R-B-001
dataset_id: EXP-TAIPAN-001
design_status: approved
specification_status: frozen
execution_status: not_started
execution_authorized: false
parent_checkpoint: W02-02R-A-003
canonical_design_input_commit: 4b470c6ec70d75ac360b330f599bc74a7b97e037
governance_mode: lean_delta
required_tests: 16
```

No B-001 execution is authorized by this specification.

This job-specific DELTA consolidates `T02R04_B001_freeze_ready_design.md`,
including its authoritative freeze-ready revision / Project Control override.
Source SHA-256: `885e6a2277a28db2aa485982f69ceb03ef2f8cc3c47865073ae8dabe2aab7757`.
Superseded design alternatives are not execution rules. Shared Stage 02R
contracts remain authoritative outside this job-specific DELTA.

## GOAL

Build a CEF-blind, TAS-aware, exposure-aware representation of verified
energy-transfer scans and a frozen catalogue of reproducible spectral
structures without line-shape models, historical energy windows, arbitrary
normalization scales or physical assignments.

The primary discovery unit is the individual scan. No spectrum may be
pre-averaged merely because scans share an A-003 compatibility group.
The required architecture is:

```text
canonical A-002/A-003 metadata
→ detector-structure-blind exposure semantic preflight
→ energy-scan geometry eligibility
→ metadata-only algorithmic holdout seal
→ discovery-only detector access
→ high-rate / acquisition QC
→ per-scan exposure-aware Poisson representation
→ per-scan blind local multiscale discovery
→ within-count-control reproducibility
→ cross-mode energy-position annotation only
→ frozen neutral blind catalogue
```

## CANONICAL_INPUTS

Design baseline: `4b470c6ec70d75ac360b330f599bc74a7b97e037`.
Scientifically reviewed inputs are W02-02R-A-001, W02-02R-A-002 and W02-02R-A-003
for `EXP-TAIPAN-001`. Preserve all 201 canonical scan identities.

Canonical checkpoints and shared protocols:

```text
02_Work_Checkpoints/W02-02R-A-001.md
02_Work_Checkpoints/W02-02R-A-002.md
02_Work_Checkpoints/W02-02R-A-003.md
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
03_Protocols/STAGE02R_T02R03_A003_CLASSIFICATION_SPEC.md
```

Required machine-readable inputs and provenance for identity verification:

```text
04_Results/Stage02R/W02-02R-A-002/scan_inventory.csv
04_Results/Stage02R/W02-02R-A-002/scan_points.csv
04_Results/Stage02R/W02-02R-A-002/quality_diagnostics.csv
04_Results/Stage02R/W02-02R-A-002/semantic_verification_report.yaml
04_Results/Stage02R/W02-02R-A-002/provenance_manifest.yaml
04_Results/Stage02R/W02-02R-A-003/scan_classification.csv
04_Results/Stage02R/W02-02R-A-003/acquisition_states.yaml
04_Results/Stage02R/W02-02R-A-003/acquisition_boundaries.csv
04_Results/Stage02R/W02-02R-A-003/normalization_compatibility_groups.yaml
04_Results/Stage02R/W02-02R-A-003/provenance_manifest.yaml
```

`scan_point_auxiliary.csv` is not part of the default primary discovery path;
targeted QC may require only a concrete already-identified auxiliary field.
Raw TAIPAN data need not be reopened: `raw_data_access: none_by_default`,
`raw_reparse: false`. Canonical input integrity checks do not permit detector
fields to enter preflight, split assignment or holdout discovery logic.

A-003 groups are conditionally supported recorded-metadata compatibility
classes, not numerical normalization parameters or proof of complete physical
instrument identity. No numerical normalization has been established by A-003.

## BLINDNESS_CONTRACT

The following tokens are listed ONLY to define what static source/configuration
and output audits must reject as historical or model-driven discovery inputs:

```text
6.45 meV
~18.2 meV
27.90 meV
~44.4 meV
F002
F004
historical fitted centroids
historical candidate energies
historical discovery/fit windows
CEF level schemes and assignments
PCM / CFE / PCF / PyCrystalField predictions
exchange/CEF assignments
```

They MUST NOT occur as analysis constants, search/window boundaries, labels,
plot markers, expected features/energies, validation or synthetic-test targets,
or candidate-prior weights. No forbidden value/token may influence execution.
Synthetic locations remain unrelated to project energies.
Machine-readable catalogues and any diagnostic figures MUST contain no
historical target markers. Blind catalogue freeze precedes any historical comparison.
Neutral IDs are `BF-001`, `BF-002`, ...; no historical feature labels.

## EXPOSURE_SEMANTIC_PREFLIGHT

Run before detector values are read for spectral discovery. Allowed fields:

```text
scan identity
scan_variable_raw
count_control_mode
preset_channel_raw
header start/end timestamps
point_index
e_raw
time_raw
monitor_raw
```

`detector_raw` and `det_err_raw` are forbidden during this phase.

### Time-controlled gate

For each verified `en` scan with `count_control_mode=time_controlled`, require
`preset_channel_raw = time`, all `time_raw` finite and all `time_raw > 0`.
Let `t_med = median(t_i)`. For `N >= 5`, require at least `ceil(0.95*N)` points
with `abs(t_i/t_med - 1) <= 0.10`, and no point with
`abs(t_i/t_med - 1) > 0.25`.
Where verified header timestamps exist, additionally require:

```text
sum_i(t_i) <= (t_end - t_start) + 2.0 s
```

Passing establishes `time_raw_semantics = per_point_acquisition_exposure_seconds`
for that usable scan population.

### Monitor-controlled gate

For each verified `en` scan with `count_control_mode=monitor_controlled`, require
`preset_channel_raw = monitor`, all `monitor_raw` finite and all `monitor_raw > 0`.
Let `M_med = median(M_i)`. For `N >= 5`, require at least `ceil(0.95*N)` points
with `abs(M_i/M_med - 1) <= 0.10`, and `abs(M_i/M_med - 1) <= 0.25` for all points.
Passing establishes `monitor_raw_semantics = accumulated_monitor_count_exposure`
for that usable scan population.

### Short scans

For `N < 5`, require the correct preset channel, finite positive controlling
exposure and maximum relative deviation <= 0.25; record
`control_constancy_evidence = limited_by_short_scan`.
The applicable time/header-duration check remains as defined above.
Such scans may subsequently fail discovery geometry.

### Global versus scan-local failure

The following are GLOBAL semantic-contract stop conditions:

- A time-controlled scan has `preset_channel_raw` inconsistent with `time`.
- A monitor-controlled scan has `preset_channel_raw` inconsistent with `monitor`.
- Canonical field/schema identity is inconsistent across required inputs.
- The required controlling-exposure field is structurally absent.
- Evidence shows the proposed controlling field cannot represent documented exposure semantics.
- Required canonical A-002/A-003 input identity fails.

Any global condition gives `EXPOSURE_SEMANTIC_PREFLIGHT = FAIL` and STOP B-001
before detector discovery.

Scan-local failure reasons are:

```text
non_finite_controlling_exposure
non_positive_controlling_exposure
control_constancy_test_failed
time_header_duration_test_failed
```

These give `pre_detector_status = diagnostic_only_exposure_preflight_failed`,
not a global STOP. The scan does not enter the geometry-eligible population or
holdout assignment; detector values remain inaccessible to discovery.
Retain every failed scan with its exact failure reasons.

```yaml
exposure_mode_status:
  monitor_controlled:
    semantic_status: verified | globally_failed | no_usable_scans
  time_controlled:
    semantic_status: verified | globally_failed | no_usable_scans
```

`globally_failed` causes global STOP. `no_usable_scans` is not itself a semantic
contradiction; the other mode may proceed if a usable discovery population remains.
The non-controlling channel MUST NOT create cross-mode normalization,
monitor/time conversion, shared amplitude likelihood or a cross-mode scale.

## DATA_REPRESENTATION

Primary population: `scan_variable_raw == en` with verified `en/e` mapping
and usable native-grid energy/exposure data. The reviewed mapping covers 85 scans;
eligibility still requires the gates below. Other scan variables, including
Q, angular, rocking and aperture scans, cannot generate primary energy features.

For discovery points retain at least the following traceable representation:

```text
scan_record_id
point_index
energy_transfer_meV
detector_counts
monitor_counts
time_exposure
exposure_value
exposure_type
count_control_mode
acquisition_state_id
lattice_state_id
UB_state_id
display_rate
statistical_weight/likelihood inputs
QC flags
```

Monitor/time fields preserve the canonical `monitor_raw`/`time_raw` inputs.
Primary likelihood inputs are `(D_i, E_i)`; display-only rate is `r_i = D_i / E_i`.
Keep original point provenance when reversing descending trajectories.
No interpolation or rebinning is a prerequisite for discovery; no interpolation
is used for statistical testing. Different densities retain their native grids.
Interpolation may be used only for visualization.

## NORMALIZATION_POLICY

```yaml
monitor_controlled:
  discovery_exposure: monitor_raw
  display_rate: detector / monitor
time_controlled:
  discovery_exposure: time_raw
  display_rate: detector / time
within_monitor_class_pooling: allowed_only_hierarchically
within_time_class_pooling: allowed_only_hierarchically
direct_monitor_vs_time_amplitude_pooling: forbidden
common_scale_between_modes: forbidden
shared_amplitude_likelihood_between_modes: forbidden
A003_group_scale_parameter: forbidden
cross_mode_bridge_status: deferred
```

These are exposure representations, not fitted normalization constants.
Monitor- and time-controlled discovery remain separate. Cross-mode recurrence
provides energy-position annotation only, never rate/amplitude equality,
shared likelihood or a multiplicative calibration scale.
The mere presence of both exposure channels does not justify a bridge.
No ki/kf correction is applied; quantitative intensity treatment requires later review.

## STATISTICAL_MODEL

```text
D_i | E_i ~ Poisson(E_i * lambda_i)
monitor_controlled: E_i = monitor_raw
time_controlled:    E_i = time_raw
```

Exposure is conditioned upon. Achieved monitor counts are stopping exposure;
verified point duration is time-controlled exposure. No arbitrary exposure-scale
nuisance parameter is fitted. No independent denominator variance is added to
monitor exposure, and the non-controlling channel does not enter the primary likelihood.

Poisson likelihood supplies primary uncertainty. The display-only large-count
diagnostic is `sigma_rate = sqrt(D_i) / E_i`; low counts, including zero, do not
use symmetric Gaussian errors for inference. `det_err` is diagnostic-only until
separate semantic verification. Low but positive exposure is not automatically removed.
No invalid point silently enters the likelihood; failure handling follows the
exposure, detector-blind geometry and discovery-runtime gates below.

## SCAN_SELECTION_AND_QC

Use three separate status fields, never a mixed QC/holdout/discovery enum:

```yaml
pre_detector_status:
  - eligible_for_split
  - diagnostic_only_exposure_preflight_failed
  - diagnostic_only_insufficient_geometry
  - diagnostic_only_nonmonotonic_energy
  - diagnostic_only_duplicate_energy
  - diagnostic_only_insufficient_contiguous_geometry
  - not_primary_energy_discovery
split_role:
  - discovery
  - holdout
  - not_applicable
discovery_runtime_status:
  - not_evaluated
  - discovery_usable
  - excluded_nonfinite_detector
  - excluded_other_detector_QC
  - stop_high_rate_warning_region
```

Mandatory ordering:

```text
verified en scans
→ exposure-semantic preflight
→ detector-blind geometry/QC
→ pre_detector_status
→ eligible_for_split only
→ deterministic holdout assignment
→ blind_split.csv frozen
→ split_role discovery/holdout
→ detector access only for discovery
→ discovery-only detector QC
→ multiscale discovery
```

Scans outside the verified primary energy population receive
`not_primary_energy_discovery`. Non-finite energy is explicitly flagged and
excluded from usable geometry. A-002 parser/quality flags, exposure anomalies,
point count, source ordering, duplicate energies, gaps and endpoints remain explicit.
For discovery scans, non-finite detector gives `excluded_nonfinite_detector`;
other predefined detector QC failures give `excluded_other_detector_QC`.
Non-discovery scans retain `discovery_runtime_status = not_evaluated`.

Repeated/overlapping scans remain independent records, not pre-averaged spectra.
Lattice/UB/acquisition state is retained, not automatically pooled or rescaled.
Temperature remains descriptive only: no normalization, split or candidate
grouping may depend on it before unique physical-channel verification.

## DISCOVERY_GEOMETRY

Geometry is detector-blind. The source energy trajectory must be strictly
increasing or decreasing; reverse descending trajectories for analysis without
losing original provenance. Duplicate energy values give
`diagnostic_only_duplicate_energy`; reversals give `diagnostic_only_nonmonotonic_energy`.
Fewer than 9 usable points gives `diagnostic_only_insufficient_geometry`.

Frozen central widths are `[1, 3, 5, 7]`, with exactly three points in each flank.
For odd width `c` centered at index `j`:

```text
central: j-(c-1)/2 ... j+(c-1)/2
left flank: three immediately preceding points
right flank: three immediately following points
N_local = c + 6
```

Both full flanks are mandatory: local windows contain 7, 9, 11 or 13 points.
No primary statistic is calculated with an incomplete flank. Endpoint-only
structure may be `endpoint_diagnostic` but cannot satisfy catalogue reproducibility.
Nine points support the smallest persistent adjacent-scale geometry.

```text
delta_e_i = abs(e_{i+1} - e_i)
delta_e_med = median(delta_e_i)
invalid local window if any delta_e_i > 3 * delta_e_med
```

A scan remains eligible if sufficient valid windows survive; otherwise assign
`diagnostic_only_insufficient_contiguous_geometry`.
No instrument-resolution width is assumed.

## EXACT_MULTISCALE_STATISTIC

This is a project-specific local Poisson multiscale scan, not SMUCE.
For an admissible window `W = L ∪ C ∪ R`:

```text
x_i = e_i - median_{j in W}(e_j)
null: log(mu_i) = log(E_i) + beta0 + beta1*x_i
z_i = 1 for i in C, else 0
alternative: log(mu_i) = log(E_i) + beta0 + beta1*x_i + delta*z_i
delta >= 0
T_{j,c} = 2 * [ell(alternative_hat) - ell(null_hat)]
```

Clip tiny numerical negative values to zero; all-zero local detector counts give `T=0`.
`beta0`, `beta1` are predefined statistical nuisance parameters, not a physical
background model; they are neither subtracted nor physically interpreted.

Use `scipy.optimize.minimize`, `L-BFGS-B`, `maxiter=500`, `ftol=1.0e-12`, `gtol=1.0e-8`.
Null bounds: beta0/beta1 unbounded. Alternative: beta0/beta1 unbounded, delta in `[0,+inf)`.
Initialize:

```text
beta1 = 0
beta0 = log(max(sum(D), 0.5) / sum(E))
delta = 0
```

The alternative starts from fitted null parameters. Fit failure invalidates
that window and emits a numeric diagnostic. An optional unrestricted-delta
two-sided statistic is diagnostic-only; deficits cannot enter the blind catalogue.

### Bootstrap nuisance field

For every usable point choose a contiguous 9-point neighborhood containing it,
centered where possible and shifted at endpoints. Fit the same null Poisson
log-linear model and predict `mu0_i`.
This field is predefined, local, nuisance-only, not subtracted, not physically
interpreted and not candidate-adaptive. If it cannot be computed for all usable
points, the scan cannot enter discovery. Use native energy grids and exposures.

### Seed and authoritative FWER

Per-scan seed payload, exact order:

```text
stage02r_b001_bootstrap_seed_v1
master=CEF-Dy:T-02R-04:W02-02R-B-001:bootstrap-v1
scan_record_id=<SCAN_RECORD_ID>
```

Serialize UTF-8, LF after every line including final LF; SHA-256; interpret the
first 16 hex characters as an unsigned 64-bit seed for PCG64.
For each of exactly 2048 replicates, simulate `D_i^(b) ~ Poisson(mu0_i)` and
recompute all admissible local statistics.

```text
B = 2048
M_b = max over ALL admissible windows/scales of T_{j,c}^{(b)}
p_FWER(j,c) = [1 + #{b : M_b >= T_obs(j,c)}] / (B + 1)
             = [1 + #{b : M_b >= T_obs(j,c)}] / 2049
```

Compare against the bootstrap SCAN MAXIMUM `M_b`, not the bootstrap statistic
of only the same window. A primitive excess is significant iff `p_FWER <= 0.05`.
This is the authoritative per-scan multiplicity criterion.

## HOLDOUT_RULE

This is an `algorithmic holdout for anti-circularity`, not a fully independent
or unseen-to-humans experimental validation set.
Read metadata, pass exposure preflight, establish detector-blind geometry,
assign holdout, and write/freeze `blind_split.csv` BEFORE accessing any
discovery detector values.

Stratify `eligible_for_split` scans by exactly `count_control_mode` and
`acquisition_state_id`. With stratum size `n`:

```text
n >= 4: n_holdout = max(1, floor(0.25*n))
n < 4: holdout_count = 0; all scans = discovery
       holdout_status = unavailable_small_stratum
```

Canonical assignment payload, exact order:

```text
stage02r_b001_holdout_v1
salt=CEF-Dy:T-02R-04:W02-02R-B-001:algorithmic-holdout-v1
count_control_mode=<VALUE>
acquisition_state_id=<VALUE>
scan_record_id=<VALUE>
```

Serialize UTF-8, LF after every line including final LF; compute SHA-256.
Within each stratum sort by full hash ascending and take the first `n_holdout`.
Input order cannot affect assignment.

The split is immutable after `blind_split.csv` freezes. `holdout_backfill=false`:
if a discovery-assigned scan later fails detector QC, it retains its discovery
role and no holdout scan may be promoted. Holdout runtime status remains `not_evaluated`.

Before B-001 STOP_CONDITION, holdout scans may expose ONLY:

```text
scan_record_id
count_control_mode
acquisition_state_id
energy trajectory
geometry metadata
exposure-semantic fields
detector-blind QC metadata used before split
```

For holdout scans B-001 MUST NOT read/use:

```text
detector
det_err
detector / monitor
detector / time
detector-derived rate
candidate statistic
detector high-rate diagnostic
```

```yaml
holdout_high_rate_status:
  B001: not_evaluated_due_to_holdout_seal
```

The poison-value test must prove that holdout detector fields cannot change
discovery content/bytes or cause discovery to fail.
Holdout high-rate QC is deferred to T-02R-05 after blind-catalogue freeze;
B-001 itself never opens the holdout detector seal.

## HIGH_RATE_QC

Apply high-rate detector QC ONLY to `split_role=discovery`, before any feature
discovery. The documented saturation warning is a QC warning level, not a
detector-response or dead-time correction model.

For time-controlled discovery scans, successful exposure preflight establishes
elapsed seconds. For monitor-controlled discovery scans, `time_raw` may be used
for high-rate QC only if detector-blind checks establish all time values
finite/positive and:

```text
sum_i(t_i) <= (t_end - t_start) + 2 s
```

Otherwise the monitor-controlled scan is diagnostic-only and cannot enter
blind discovery. Record `diagnostic_only_high_rate_unassessable` as the exact
QC reason, with `discovery_runtime_status = excluded_other_detector_QC`;
do not add this reason to any frozen status enum or change its split role.
Time does not become the monitor-controlled likelihood exposure.

Where duration semantics pass, `R_i = D_i / t_i`:

```text
R < 28000            -> normal_rate_diagnostic
28000 <= R < 35000   -> approaching_documented_warning
R >= 35000          -> documented_warning_region
```

For otherwise usable discovery scans, `28000 <= R < 35000` remains
`discovery_usable` with `approaching_documented_warning` flag.
Any discovery point `R >= 35000` gives
`discovery_runtime_status = stop_high_rate_warning_region` and GLOBAL STOP
B-001 before feature discovery. Do not continue other discovery scans past this gate.
No dead-time correction; no holdout replacement; no holdout high-rate inspection.

## FEATURE_DISCOVERY_METHOD

Use per-scan exposure-aware local Poisson multiscale discovery, not a generic
local-maxima finder, summed spectrum or acquisition/group average.
Independent scan-level discovery precedes hierarchical same-mode reproducibility.

### Multiscale persistence

Ordered central widths are `1, 3, 5, 7`. A primary scan candidate requires
significant support at least at two adjacent scales: `1 ↔ 3`, `3 ↔ 5` or `5 ↔ 7`.
Centers may differ by at most one native point and central support intervals
must overlap. One significant scale alone is insufficient.
For central block indices `a...b`, define sampling-cell support:

```text
L = (e_{a-1} + e_a)/2
U = (e_b + e_{b+1})/2
```

Full flanks guarantee neighbors exist and give nonzero support even at width 1.

### Seed-based, non-transitive merging

Within each scan:

1. Identify persistent significant scale combinations.
2. Sort seeds by smallest `p_FWER`, then largest `T`, then lower energy.
3. Take the strongest remaining seed.
4. Absorb persistent windows whose support intersects seed support and whose center is within one point of the seed center.
5. Do NOT transitively expand beyond the seed support.
6. Repeat on remaining windows.

Seed support becomes `discovery_energy_interval`; store the union of absorbed
scale supports separately as `multiscale_support_union`.
No Gaussian/Lorentzian centroid is fitted; optional deficit diagnostics are not catalogue candidates.

## REPRODUCIBILITY_CRITERIA

For scan candidates A/B with intervals `IA=[LA,UA]`, `IB=[LB,UB]`:

```text
cA = (LA+UA)/2
cB = (LB+UB)/2
position-compatible iff intervals overlap AND cA in IB AND cB in IA
```

No amplitude comparison. Catalogue eligibility requires independently significant,
persistent, position-compatible excess candidates from at least two distinct
discovery scan IDs within the same `count_control_mode`.
A scan contributes at most one candidate to one feature cluster.

Within each control mode use complete-link clustering:

1. Sort by lowest representative energy, then lowest `p_FWER`, then scan ID.
2. Seed from the first candidate.
3. A candidate may join only if compatible with EVERY existing member.
4. Continue until no more candidates join.
5. Repeat with unassigned candidates.

```yaml
tier_0:
  meaning: single_scan_only
  blind_catalogue_eligible: false
tier_1:
  meaning: reproduced_within_count_control_class
  requirement: at_least_2_distinct_discovery_scans
  blind_catalogue_eligible: true
tier_2:
  meaning: reproduced_across_acquisition_contexts
  additional_requirement: at_least_2_distinct_acquisition_state_id_values
```

Tier 2 requires Tier 1 plus multiple acquisition states. A boundary alone or
cross-mode recurrence cannot replace that requirement.
Cross-mode recurrence is position annotation only: it MUST NOT rescue tier_0,
compare amplitudes, fit a shared scale or fit a shared likelihood.

Each blind feature record contains at least:

```text
blind_feature_id
count_control_mode
discovery_energy_interval
supporting_scan_record_ids
supporting_acquisition_state_ids
reproducibility_tier
scan_level_support_intervals
cross_mode_position_recurrence
```

Representative discovery location may be the midpoint of the intersection
envelope, labelled `discovery_location_not_confirmatory_centroid`.
Retain scan-local support, not fitted centroids.

### Empty catalogue versus empty discovery population

`blind_feature_catalogue.zero_features_allowed: true`.
PASS does not require a `BF-*` feature. With usable discovery scans, correct
execution finding no Tier-1 feature may PASS with a deterministic empty catalogue.
Do NOT weaken thresholds or reproducibility rules because the catalogue is empty.
`usable discovery scans == 0` instead causes STOP `no_usable_discovery_population`;
it is not a null scientific result.

## TAS_PHYSICS_BOUNDARY

Allowed: verified `e = Ei - Ef`, verified `en/e` mapping, count-control mode,
verified monitor/time exposure semantics, scan trajectory and energy ordering,
lattice/UB/acquisition-state metadata, recorded instrument metadata, detector
counting statistics and TAS-aware acquisition QC.

Forbidden/deferred in B-001: ki/kf correction, detector-efficiency correction,
monitor-efficiency calibration, dead-time correction, absolute intensity,
relative fitted intensity scales, resolution convolution/calculation,
magnetic form factors, polarization factors and model-based physical assignments.
Resolution-limited linewidths and quantitative cross-section treatment are deferred.
Frozen scope flags are recorded in §EXECUTION_CONTRACT.

## BACKGROUND_TERMINOLOGY

Physical background subtraction, candidate-driven background fits,
historical-background templates and candidate-driven background model selection
are forbidden. The predefined local nuisance `beta0 + beta1*e` trend (with the
centered coordinate in the exact statistic) is allowed solely inside the blind
statistic/bootstrap null. It is not subtracted or physically interpreted.
No line-shape model or physical background inference is implied by a local excess.

## OUTPUTS

Future execution directory: `04_Results/Stage02R/W02-02R-B-001/`.
Required future outputs:

```text
exposure_semantic_preflight.yaml
scan_selection.csv
blind_split.csv
discovery_point_representation.csv
discovery_qc.csv
scan_feature_candidates.csv
feature_reproducibility.csv
blind_feature_catalogue.yaml
discovery_diagnostics.yaml
provenance_manifest.yaml
test_report.yaml
```

Future source: `scripts/stage02r/b001_blind_feature_discovery.py`.
Future frozen config: `scripts/stage02r/b001_discovery_config.yaml`.
These are FUTURE EXECUTION artifacts; do NOT create them or the result directory
during specification materialization.

The preflight report retains mode statuses and exact scan-local failure reasons.
Scan selection records all three distinct status axes and QC decisions;
`blind_split.csv` records the immutable metadata-only split.
Point representations contain raw-count/exposure likelihood inputs, display-only
rates and QC, not a common normalization scale. Catalogue records follow
§REPRODUCIBILITY_CRITERIA and contain neutral IDs and discovery evidence only.
Produce the catalogue checksum so T-02R-05 can prove use of the pre-existing
frozen catalogue. Ordering and membership must be deterministic.
Any plots are secondary diagnostics subject to §BLINDNESS_CONTRACT.

## TESTS

Exactly B001-T01 through B001-T16 are mandatory. The following are the complete
authoritative reviewed definitions, with the amendments incorporated.

### B001-T01 — Canonical input integrity

Verify canonical HEAD, reviewed A-001/A-002/A-003 checkpoint identities, required artifact hashes, and 201 canonical scan identities. No raw reparse.

### B001-T02 — Blindness audit

Static source/config/output audit detects forbidden historical energies, F002/F004, CEF/PCM/CFE/PCF-driven targets, and historical fit windows. No forbidden value/token may influence execution. Synthetic fixtures must use non-project energies.

### B001-T03 — Exposure semantic gate

Verify exact time/monitor exposure rules. Distinguish global semantic contradiction => pre-discovery STOP from scan-local failure => scan-local diagnostic exclusion. No detector value may be read during this test.

### B001-T04 — Holdout anti-circularity

Verify exact stratification, 25% rule, minimum stratum size 4, hash payload, input-order invariance, and `holdout_backfill=false`. Poison holdout detector fields; discovery remains byte/content invariant and does not fail from poison values.

### B001-T05 — Discovery geometry

Verify `N<9 => diagnostic_only`, `N=9` supports smallest persistent geometry, central widths `[1,3,5,7]`, flanks `3+3`, full-flank endpoint exclusion, and 3x median-step gap rule. Detector cannot alter geometry eligibility.

### B001-T06 — Count-control separation

Verify monitor likelihood exposure=monitor only; time likelihood exposure=time only; no common cross-mode scale; no A-003 group scale; no cross-mode amplitude likelihood.

### B001-T07 — Exact local statistic

Verify null/alternative formulas, `delta>=0`, LRT definition, optimizer settings, all-zero-window `T=0`, and monotonic statistic response to increasing synthetic central excess.

### B001-T08 — Bootstrap determinism and multiplicity

Verify 2048 replicates, exact SHA-derived per-scan seed, PCG64, `M_b=max` over all valid windows/scales, authoritative `p_FWER=[1+#{b:M_b>=T_obs}]/2049`, alpha=0.05, and input-order invariance.

### B001-T09 — Synthetic null calibration

Run exact frozen 100-scan null fixture; PASS iff false-positive scans <=10/100.

### B001-T10 — Synthetic injection recovery

Run exact frozen 100-scan injection fixture; PASS iff recovered scans >=85/100 at the synthetic center.

### B001-T11 — High-rate QC

Verify 28000 cps => approaching warning; 35000 cps => documented warning region. Apply high-rate detector QC only to discovery-role scans. A discovery point >=35000 cps causes global STOP before feature detection. Holdout high-rate status remains `not_evaluated_due_to_holdout_seal`. No dead-time correction.

### B001-T12 — Point/acquisition QC and separated status axes

Verify non-finite energy, non-finite detector, zero/negative exposure, non-monotonic energy, duplicate energy, large local gap, endpoint-only excess, unassessable high-rate state, and semantic correctness of separate `pre_detector_status`, `split_role`, `discovery_runtime_status`. No invalid point silently enters likelihood.

### B001-T13 — Multiscale persistence and merging

Verify one significant scale alone => no primary candidate; adjacent significant scales => eligible; center shift <=1; seed-based non-transitive merging.

### B001-T14 — Reproducibility and cross-mode boundary

Verify single scan => tier_0; two compatible scans same control mode => tier_1; multiple acquisition states => tier_2; cross-mode recurrence => position annotation only. Cross-mode evidence cannot rescue non-reproduced within-mode feature.

### B001-T15 — TAS/scope boundary

Static/runtime audit verifies no ki/kf correction, dead-time correction, background subtraction, resolution calculation, shared normalization fitting, peak line-shape fitting, CEF analysis, or historical comparison. Local nuisance beta0/beta1 terms are explicitly allowed.

### B001-T16 — Catalogue freeze / output determinism

Verify neutral BF-* labels only; no holdout detector access; stable deterministic ordering and membership; catalogue checksum produced; STOP after blind catalogue. Deterministic empty catalogue is allowed. Zero usable discovery scans => STOP `no_usable_discovery_population`. Catalogue checksum must allow T-02R-05 to prove it uses the pre-existing frozen catalogue.

### Frozen synthetic calibration fixtures

Use the exact `synthetic_null_test` and `synthetic_injection_test` parameters in
§DETERMINISTIC_CONFIGURATION, with fixed deterministic synthetic-test RNG seeds.
The null fixture has 100 scans, 31 points, center mean counts 25 and log-rate
slope 0.015 per grid unit. PASS iff at most 10/100 scans produce any primary candidate.
The injection fixture has 100 scans, 31 points, central width 3 and rate
multiplier 2.5. Injection is at the middle grid point, unrelated to project energies.
PASS iff at least 85/100 scans recover primary support containing that center.

## PASS_CRITERIA

B-001 passes only if all of the following hold:

1. Canonical A-001/A-002/A-003 input integrity passes.
2. Global exposure semantic preflight passes before detector discovery access.
3. Time exposure is verified for usable time-controlled energy scans.
4. Monitor exposure is verified for usable monitor-controlled energy scans.
5. Scan-local exposure failures are excluded locally rather than misclassified as global semantic failure.
6. Non-controlling channel is not used as cross-mode normalization bridge.
7. Geometry eligibility is detector-blind.
8. Scans with fewer than 9 usable points cannot enter primary discovery.
9. Full left/right flanks are mandatory.
10. Large energy gaps cannot be crossed by a local test.
11. Holdout assignment occurs before detector access.
12. Holdout assignment is deterministic and metadata-only.
13. Holdout detector values are inaccessible to discovery logic.
14. `holdout_backfill=false`.
15. Discovery/holdout assignment is immutable after split freeze.
16. Monitor/time classes remain statistically independent for amplitude inference.
17. A-003 compatibility groups do not become fitted scales.
18. Primary uncertainty is handled through Poisson exposure-offset likelihood.
19. `det_err` does not drive significance.
20. Discovery-only high-rate QC completes before multiscale discovery.
21. Any discovery-role point >= documented warning level causes STOP.
22. Holdout high-rate state remains uninspected in B-001.
23. No dead-time correction.
24. Exact one-sided local Poisson LRT is used.
25. Per-scan max-statistic bootstrap controls multiplicity.
26. Exactly 2048 deterministic replicates and alpha=0.05.
27. Adjacent-scale persistence is required.
28. Single-scan candidates cannot enter blind catalogue.
29. Catalogue features require within-control-mode reproducibility.
30. Cross-mode recurrence uses position only.
31. Different grids are not interpolated for testing.
32. Lattice/UB/acquisition-state context is retained.
33. No ki/kf correction.
34. No physical background subtraction.
35. No candidate-driven background model.
36. No resolution calculation or line-shape fitting.
37. No historical energy/assignment influences discovery.
38. Holdout detector values remain inaccessible until blind catalogue freeze.
39. Empty catalogue is a valid PASS outcome if usable discovery scans exist and no Tier-1 feature is found.
40. Zero usable discovery scans causes STOP, not a null scientific interpretation.
41. B001-T01 through B001-T16 all PASS.

## STOP_CONDITION

Stop immediately after exposure semantic verification, geometry/QC
classification, algorithmic holdout seal, discovery-only exposure representation,
per-scan blind candidates, within-count-control reproducibility, neutral blind
catalogue and its checksum, with required outputs and tests complete.

Do NOT proceed to holdout detector inspection, confirmatory line-shape fitting,
candidate centroid refinement, candidate-specific background modelling,
resolution convolution or TAS resolution calculation, ki/kf-corrected intensity,
cross-mode amplitude calibration, historical target comparison, physical
level/transition assignment or fitting, or exchange interpretation.

Required transition:

```text
W02-02R-B-001
→ STOP
→ 02 - TAIPAN Data Reduction / Scientific Review
→ only after blind catalogue capture
→ T-02R-05
```

The discovery catalogue becomes immutable input to T-02R-05 before any
historical comparison. This specification and B-001 completion do not authorize
downstream execution or opening holdout detector data within B-001.

## DEFERRED_DECISIONS

No blocking scientific design decision remains for B-001. Intentionally deferred:

- `det_err` physical semantics.
- Cross-mode numerical calibration bridge.
- Detector dead-time correction model.
- ki/kf quantitative intensity correction.
- TAS resolution treatment.
- Confirmatory peak line shape.
- CEF/exchange interpretation.

## DETERMINISTIC_CONFIGURATION

The complete frozen configuration is:

```yaml
configuration_version: stage02r_b001_discovery_v1

exposure_preflight:
  control_required_fraction_within_tolerance: 0.95
  control_relative_tolerance: 0.10
  control_max_relative_deviation: 0.25
  timestamp_rounding_slack_seconds: 2.0

geometry:
  minimum_usable_points: 9
  central_width_points: [1, 3, 5, 7]
  left_flank_points: 3
  right_flank_points: 3
  maximum_local_gap_ratio: 3.0
  maximum_center_shift_points: 1

local_statistic:
  model: poisson_log_link_with_exposure_offset
  primary_test: one_sided_central_excess
  nuisance_trend_order: 1

optimizer:
  implementation: scipy.optimize.minimize
  method: L-BFGS-B
  maxiter: 500
  ftol: 1.0e-12
  gtol: 1.0e-8

bootstrap:
  baseline_neighborhood_points: 9
  replicates: 2048
  familywise_alpha: 0.05
  rng: PCG64
  seed_version: stage02r_b001_bootstrap_seed_v1
  master_seed_text: "CEF-Dy:T-02R-04:W02-02R-B-001:bootstrap-v1"

holdout:
  identity_version: stage02r_b001_holdout_v1
  salt: "CEF-Dy:T-02R-04:W02-02R-B-001:algorithmic-holdout-v1"
  stratification:
    - count_control_mode
    - acquisition_state_id
  fraction: 0.25
  minimum_stratum_size: 4
  detector_access_before_catalogue_freeze: forbidden
  holdout_backfill: false

high_rate_qc:
  documented_saturation_warning_cps: 35000
  approaching_warning_fraction: 0.80
  approaching_warning_cps: 28000
  stop_at_or_above_warning: true
  dead_time_correction: false
  apply_to_split_role: discovery_only

synthetic_null_test:
  scans: 100
  points: 31
  mean_counts_at_center: 25
  log_rate_slope_per_grid_unit: 0.015
  max_false_positive_scans: 10

synthetic_injection_test:
  scans: 100
  points: 31
  central_width_points: 3
  rate_multiplier: 2.5
  minimum_recovered_scans: 85

reproducibility:
  minimum_distinct_scans_within_control_mode: 2
  tier2_requires_multiple_acquisition_states: true
  cross_mode_amplitude_comparison: false
  cross_mode_position_annotation_only: true

blind_feature_catalogue:
  zero_features_allowed: true
```

## EXECUTION_CONTRACT

```yaml
job_id: W02-02R-B-001
stage_id: M02R
task_id: T-02R-04
job_title: Blind exposure-aware energy-scan feature discovery
execution_class: blind_spectral_discovery

goal: >
  Verify canonical exposure semantics without detector-structure inspection,
  establish deterministic geometry eligibility and an algorithmic holdout,
  perform count-control-specific per-scan Poisson multiscale blind discovery
  on discovery scans only, assess within-count-control reproducibility, and
  freeze a neutral blind spectral-feature catalogue.

raw_data_access: none_by_default
raw_reparse: false
historical_target_access: forbidden
cross_mode_amplitude_combination: forbidden
common_normalization_scale: forbidden
ki_kf_correction: false
dead_time_correction: false
background_subtraction: false
resolution_calculation: false
peak_fitting: false
cef_analysis: false
execution_authorized: false
```

Execution requires separate Project Control authorization. Materialization
does not enqueue B-001, set `next_work_job`, modify scientific registers,
or authorize any analysis.
