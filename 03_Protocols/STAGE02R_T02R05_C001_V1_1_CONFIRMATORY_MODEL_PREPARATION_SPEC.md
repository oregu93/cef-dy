# W02-02R-C-001 v1.1

```yaml
stage_id: M02R
task_id: T-02R-05
job_id: W02-02R-C-001
specification_version: "1.1"

document_status: frozen
design_status: approved
scientific_design_status: accepted
specification_status: frozen
execution_status: not_started
implementation_status: not_prepared

canonical_main: 9fe295fbb7af26b8c88cfacef17965a8bcda5d09

A1_status: failed_nonconforming_diagnostic_attempt
A2_authorized: false

C001_execution_authorized: false
C002_execution_authorized: false
holdout_detector_access_authorized: false

dataset_id: EXP-TAIPAN-001
```

C001 v1.1 supersedes C001 v1 for all future execution.

C001 v1 remains retained as historical provenance and is not modified by this specification.

```yaml
C001_v1:
  status: superseded_for_future_execution
  historical_provenance_retained: true
  rerun_authorized: false

C001_v1_1:
  specification_status: frozen
  scientific_design_status: accepted
  execution_status: not_started
  implementation_status: not_prepared
  execution_authorized: false
```

---

# GOAL

Цель C001 v1.1 — подготовить воспроизводимый, TAS-aware и CEF-blind phenomenological description замороженных B001 spectral complexes и detector-blind confirmatory package для будущего C002.

Основной scientific target:

```text
reliable experimental spectral observations
for later physical / CEF interpretation
```

C001 v1.1 должен установить, насколько позволяют TAIPAN data:

```yaml
per_complex:
  usable_discovery_scans:
  exposure_class:
  phenomenological_component_structure:
  scan_specific_centroids:
  scan_specific_integrated_areas:
  scan_specific_observed_widths:
  uncertainty_status:
  background_sensitivity:
  cross_scan_reproducibility:
  resolution_status:
  component_resolution_status:
  holdout_metadata_coverage:
  future_C002_hypotheses:
```

C001 v1.1 НЕ устанавливает:

```text
CEF level identity
CEF transition assignment
magnon assignment
phonon assignment
CEF Hamiltonian parameters
exchange interpretation
intrinsic linewidth without justified resolution treatment
```

---

# SCOPE

C001 v1.1 охватывает:

```text
frozen B001 catalogue
        ↓
metadata/grid eligibility
        ↓
per-scan exposure semantics
        ↓
complex-first phenomenological fitting
        ↓
component-development assessment
        ↓
uncertainty / ambiguity
        ↓
resolution semantics
        ↓
cross-scan reproducibility
        ↓
metadata-only holdout eligibility
        ↓
future C002 hypothesis freeze
        ↓
STOP
```

C001 v1.1 НЕ включает:

```text
holdout detector analysis
C002 execution
discovery + holdout combined re-estimation
historical CEF comparison
CEF/magnon/phonon assignment
Stage03R / Stage03D inference
```

---

# INPUTS

## Canonical experimental inputs

```text
Stage02R A-001 inventory
Stage02R A-002 parsed scans / scan points
Stage02R A-003 acquisition/instrument classification
Stage02R B-001 blind split
Stage02R B-001 frozen feature catalogue
Stage02R B-001 scan usability status
canonical raw-derived metadata
```

## Allowed instrument/provenance inputs

```text
official TAIPAN / ANSTO documentation
established TAS methodology
experimentalist-provided experimental provenance
facility records
proposal/logbook information if independently recovered
instrument-scientist information if recovered
```

## External complementary experiment

```yaml
external_experiment:
  facility: ILL
  instrument: IN20
  proposal: 4-01-1772

  role:
    - complementary_experiment
    - post_blind_external_validation

  C001_model_input: forbidden
```

IN20 peak positions, assignments, calculated levels or interpretations MUST NOT determine:

```text
C001 centroids
C001 K
B001 merging/splitting
C001 significance
C001 fit windows
```

---

# FROZEN\_INPUT\_IDENTITIES

```yaml
canonical_main:
  9fe295fbb7af26b8c88cfacef17965a8bcda5d09

dataset_id:
  EXP-TAIPAN-001

B001_catalogue_sha256:
  f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5

B001_feature_ids:
  - BF-001
  - BF-002
  - BF-003
  - BF-004
  - BF-005
  - BF-006
  - BF-007
  - BF-008

B001_excluded_scan:
  SCAN-02R-7acd4c14a0007418
```

Frozen overlap complexes:

```yaml
CX-01:
  source_bf_ids: [BF-001, BF-002, BF-003]
  frozen_union_meV: [2.49870, 6.99865]
  maximum_BF_defined_K: 3

CX-02:
  source_bf_ids: [BF-004, BF-005]
  frozen_union_meV: [17.49800, 20.49835]
  maximum_BF_defined_K: 2

CX-03:
  source_bf_ids: [BF-006, BF-007, BF-008]
  frozen_union_meV: [40.49835, 46.49775]
  maximum_BF_defined_K: 3
```

These intervals are algorithmic blind-discovery structures.

They are NOT physical excitation assignments.

The following are immutable during C001 v1.1:

```yaml
B001_catalogue_bytes: immutable
BF_intervals: immutable
overlap_complex_definitions: immutable
discovery_holdout_assignment: immutable
B001_exclusion_status: immutable
parsed_scan_identity: immutable
```

---

# BLINDNESS\_BOUNDARY

Stage02R v1.1 is:

```text
CEF-BLIND
but
TAS-AWARE
```

Pre-beamtime selection of energy ranges using literature or exploratory modelling is legitimate experimental provenance.

It does NOT invalidate blind analysis.

However, after acquisition, historical expectations MUST NOT determine:

```text
B001 intervals
fit centroid initialization from expected CEF energy
number of components K
BF merging/splitting
significance threshold
background order
holdout selection
physical assignment
```

Permitted statement:

```text
"This energy region was deliberately measured before analysis."
```

Forbidden analytical step:

```text
"A CEF excitation was expected at E0,
therefore place or retain a component at E0."
```

---


# ACQUISITION\_COVERAGE\_AND\_EXPERIMENTAL\_PROVENANCE

The acquired TAIPAN dataset is a purpose-driven targeted scan set, not an exhaustive continuous energy survey.

```yaml
acquisition_coverage_semantics:
  dataset_type: purpose_driven_targeted_TAIPAN_scan_set
  exhaustive_continuous_energy_survey: false

spectral_completeness_claim: forbidden
```

C001 v1.1 characterizes phenomenological spectral structure only within sufficiently sampled portions of the acquired TAIPAN dataset.

C001 MUST NOT infer:

```text
completeness of the Dy3+ CEF level scheme
absence of an excitation outside measured energy regions
absence of a physical level from insufficient local coverage
exhaustive one-to-one mapping of B001 structures to physical excitations
```

Possible causes of non-observation may be recorded only as unresolved alternatives:

```yaml
possible_nonobservation_causes:
  - energy_interval_not_measured
  - insufficient_local_coverage
  - insufficient_counting_statistics
  - weak_transition_matrix_element_or_selection_rule
  - Q_dependence
  - instrumental_configuration
  - spectral_overlap
  - different_physical_origin
  - other_unresolved_experimental_or_physical_factor
```

No particular cause is established without direct Stage02R experimental support.

The TAIPAN experiment/proposal provenance is frozen conservatively:

```yaml
TAIPAN_proposal:
  experiment_id: 1296
  candidate_proposal_number: 15702
  proposal_header_schema_recognized: true
  explicit_canonical_proposal_value: not_established
  experiment_to_proposal_mapping: unresolved
  status: unresolved_historical_clue
```

Proposal number `15702` is not a frozen input identity and MUST NOT be represented as an established proposal ID.

Deidentified participant recollection may provide contextual provenance only:

```yaml
beamtime_context:
  broader_INS_objectives: true
  high_energy_magnon_component:
    provenance: participant_recollection
  scan_coverage:
    purpose_driven: plausible
    exhaustive_energy_survey: false
```

This context MUST NOT alter B001, choose centroids or K, assign spectral origin, or infer missing peaks.

---

# ALLOWED\_TAS\_PRIORS

Allowed information includes:

```yaml
instrument_method:
  instrument: TAIPAN
  method: thermal_neutron_triple_axis_spectroscopy

scan_metadata:
  - scan_variable
  - energy_transfer
  - Ei
  - Ef
  - h
  - k
  - l
  - Q_trajectory
  - lattice
  - UB
  - monitor
  - time
  - temperature

instrument_metadata:
  - monochromator_material
  - monochromator_reflection_if_verified
  - monochromator_mosaic_if_verified
  - analyzer_material
  - analyzer_reflection_if_verified
  - analyzer_mosaic_if_verified
  - collimation
  - focusing_if_verified
  - filters_if_verified
  - apertures_if_verified

experimental_provenance:
  - documented_scan_purpose
  - documented_repeat_scan_relationship
  - documented_alignment_scan
  - documented_background_scan
  - documented_resolution_scan
  - documented_instrument_intervention
```

TAS prior information may be used to determine:

```text
exposure semantics
fixed-Ei/fixed-Ef status
instrument-state grouping
whether resolution evidence is physically applicable
whether intensities are comparable
```

It may NOT be replaced by recollection when canonical metadata contradict or fail to establish it.

---

# FORBIDDEN\_PRIORS

Forbidden as C001 model-design inputs:

```yaml
forbidden:
  - historical_CEF_target_energies
  - historical_F002_mapping
  - historical_F004_mapping
  - previous_CEF_level_scheme
  - previous_CEF_fit
  - exploratory_PCF_predicted_levels
  - exploratory_PCF_B_l_m
  - expected_transition_intensity
  - exchange_model_prediction
  - IN20_peak_position
  - IN20_assignment
```

Historical preliminary PCF work may be represented only in deidentified abstract form:

```yaml
nature: preliminary_exploratory_estimate
CEF_fit: false
use_in_Stage02R_model_design: forbidden
```

No private parameter values or unpublished model outputs are C001 inputs.

---

# SCAN\_ELIGIBILITY

## Discovery-side primary eligibility

A scan is eligible for phenomenological fitting for a complex only if:

```yaml
split_role: discovery
B001_discovery_runtime_status: discovery_usable

energy_transfer_semantics: verified
exposure_semantics: verified

energy_values:
  finite: true
  duplicates: false

grid:
  monotonic_increasing_or_decreasing: true

frozen_complex_union:
  fully_covered: true
```

Descending scans are permitted.

The acquisition ordering may be converted to increasing energy for numerical fitting only when the grid is strictly monotonic and identity of all points is retained.

---

## Local coverage default

Operational minimum:

```yaml
native_points_inside_frozen_complex_union_min: 3
lower_background_anchor_points_min: 2
upper_background_anchor_points_min: 2
```

These values are:

```yaml
role: minimum_estimability_and_local_coverage_rule
physical_resolution_statement: false
physical_truth: false
```

The background anchors are the nearest usable native-energy points outside the frozen complex union on each side.

Primary local fit window is bounded by the outermost selected lower and upper anchors.

Additionally, for every concrete scan/model:

```text
n_fit_points > n_free_parameters
```

is mandatory.

If either coverage or model estimability fails:

```yaml
spectral_fit_status: insufficient_local_coverage
```

The scan:

```text
MUST NOT
```

be converted into:

```text
non-detection
zero intensity
censored observation
```

merely because coverage is inadequate.

Its status is coverage failure only.

---

# COUNT\_CONTROL\_POLICY

Both verified acquisition classes are allowed:

```yaml
monitor_controlled:
  exposure: monitor

time_controlled:
  exposure: acquisition_time
```

For both:

```math
D_{si}\sim\mathrm{Poisson}(E_{si}\lambda_{si}).
```

`E_si` is the verified exposure variable for that scan.

The classes may coexist in joint evidence because each scan has independent phenomenological parameters.

Forbidden unless later supported by independent instrument evidence:

```text
shared amplitude across count-control classes
shared normalization factor
monitor/time conversion factor inferred from spectra
cross-mode relative-intensity claim
```

Default:

```yaml
cross_scan_intensity_comparability: not_established
cross_mode_intensity_comparability: not_established
```

No global fixed-`Ef` assumption is permitted.

`Ei` and `Ef` must be recovered:

```text
per scan
or
per independently verified internally homogeneous acquisition block
```

One block's `Ef` MUST NOT be propagated to the entire experiment.

---

# MODEL

Primary observed phenomenological model:

```math
D_{si} \sim \mathrm{Poisson}(\mu_{si}),
```

```math
\mu_{si} = E_{si} \left[ B_s(E_i) + \sum_{k=1}^{K} A_{sk}G(E_i;c_{sk},w_{sk}) \right].
```

`G` is a unit-area Gaussian observed-profile component.

Primary background:

```math
\log B_s(x)=b_{0s}+b_{1s}x,
```

with local scaled coordinate:

```math
x\in[-1,1].
```

All spectral parameters are scan-specific:

```yaml
scan_specific:
  - background
  - integrated_area
  - centroid
  - observed_fwhm
```

Shared across scans only:

```yaml
shared_model_structure:
  - complex_id
  - K
  - component_family
  - primary_background_family
  - parameter_domain_rules
```

No cross-scan equality of centroid, width or intensity is assumed.

---

# PARAMETERS

For scan `s`, component `k`:

```yaml
b0_s:
  meaning: local_log_background_intercept

b1_s:
  meaning: local_log_background_slope

A_sk:
  meaning: integrated_observed_component_area

c_sk:
  meaning: observed_component_centroid

w_sk:
  meaning: observed_empirical_FWHM
```

Machine output MUST distinguish:

```text
observed_empirical_fwhm
```

from:

```text
intrinsic_linewidth
instrument_resolution
```

---

# PARAMETER\_DOMAINS

```yaml
b0_s:
  domain: (-infinity, +infinity)

b1_s:
  domain: (-infinity, +infinity)

A_sk:
  domain: [0, +infinity)

w_sk:
  domain: (0, +infinity)

c_sk:
  domain: inside_frozen_complex_union
```

No detector-derived hard bound is allowed.

Count-derived quantities may be used only for deterministic initialization.

---

## Ordered-centroid transform

For `K>1`, centroids are structurally ordered without a physical minimum-separation threshold.

Use exactly `K` free logits:

```text
eta_0 ... eta_(K-1)
```

plus fixed reference:

```text
eta_K = 0
```

Define positive softmax gap fractions:

```math
q_j>0, \qquad \sum_{j=0}^{K}q_j=1.
```

Then:

```math
c_k = L + (U-L) \sum_{j=0}^{k-1}q_j, \qquad k=1,\ldots,K.
```

This guarantees:

```math
L<c_1<c_2<...<c_K<U.
```

No `delta_E_ref` minimum separation is imposed.

Post-fit centroid sorting is forbidden.

---

# BACKGROUND\_POLICY

Primary background is always:

```yaml
primary_background: B1_log_linear
```

There is no discovery-side bootstrap hierarchy for polynomial order.

For the final selected phenomenological component structure, perform sensitivity refits where estimable:

```yaml
B0:
  role: sensitivity

B2:
  role: sensitivity
  minimum_lower_anchor_points: 3
  minimum_upper_anchor_points: 3
```

If B2 does not have sufficient local support:

```yaml
B2_sensitivity_status: not_estimable
```

This is not a failure.

For `K>1`, background sensitivity is `material` if an estimable B0 or B2 refit causes either:

```text
optimizer instability after the frozen observed-fit escalation
or
loss of finite ordered-centroid identifiability
or
non-overlap of the corresponding 95% centroid profile interval
with the primary B1 interval
```

Otherwise:

```yaml
background_sensitivity_status: acceptable
```

A split with:

```yaml
background_sensitivity_status: material
```

is not promoted as a stable phenomenological split.

For `K=1`, B0/B2 sensitivity is recorded diagnostically and does not determine whether the future K0→K1 presence hypothesis exists.

---

# COMPONENT\_DEVELOPMENT\_POLICY

## Presence concept

For every discovery complex with adequate primary C001 coverage:

```text
K0 = primary background only
K1 = primary background + one positive component
```

K0→K1 is the required future presence/null concept.

Discovery-side significance is NOT required to decide whether future presence testing exists.

---

## Maximum K

```yaml
K_cap:
  CX-01: 3
  CX-02: 2
  CX-03: 3
```

The cap derives only from the frozen number of algorithmic B001 structures.

It MUST NOT be interpreted as expected physical line count.

Every K must additionally satisfy per-scan estimability:

```text
n_fit_points > n_free_parameters
```

---

## Split development

Sequential only:

```text
K1 → K2
then, only if promoted:
K2 → K3
```

A candidate `K→K+1` split is promoted phenomenologically only if:

```yaml
requirements:
  parent_observed_fit_stable: true
  child_observed_fit_stable: true
  discovery_bootstrap_support: true
  cross_scan_recurrence: true
  centroid_identifiability: true
  background_sensitivity_status: acceptable
```

If any condition fails:

```text
retain parent K
stop deeper splitting
```

---

## Cross-scan recurrence

After a candidate child passes discovery bootstrap support, evaluate scan-level structure.

A discovery scan is `supportive` for child K if:

```yaml
observed_child_fit_stable: true
all_component_areas:
  strictly_above_active_lower_bound: true
required_centroid_profile_intervals:
  finite: true
```

For `K>1`, all adjacent primary B1 centroid 95% profile intervals in that scan must be non-identical and at least one adjacent pair must have non-overlapping intervals.

Phenomenological recurrence requires:

```yaml
supportive_discovery_scans_min: 2
```

No equality of component centroid across those scans is required.

This allows dispersive phenomenology without assigning it as magnon or CEF.

---

# OBSERVED\_OPTIMIZER\_POLICY

Primary optimizer:

```yaml
implementation: scipy.optimize.minimize
method: L-BFGS-B
parameter_coordinates: physical_model_coordinates
post_optimizer_polishing: forbidden
```

## Deterministic start bank

Initial:

```yaml
observed_multistarts_initial: 8
```

Construction:

```text
Start 1:
  deterministic model-local baseline

Starts 2...8:
  first seven vectors of one deterministic unscrambled Sobol bank
```

If the best observed solution is not reproduced:

```yaml
observed_multistarts_escalated: 16
```

using:

```text
Start 1
+
first fifteen vectors of the same Sobol bank
```

No new random start bank is generated.

---

## Scientific stability criterion

The number `8` or `16` is an implementation convention.

The scientific criterion is observed-solution reproducibility.

The best likelihood is considered reproduced if at least two distinct starts produce:

```math
|\ell_j-\ell_{\rm best}| \le 10^{-6} \max(1,|\ell_{\rm best}|).
```

If this fails after 8 starts:

```text
escalate to 16
```

If it still fails:

```yaml
optimizer_stability_status: unresolved
```

Such a model cannot justify a component split.

Implementation tie rule:

if:

```math
|\ell_a-\ell_b|\le10^{-8},
```

select the lexically smallest physical parameter vector after rounding to 12 decimal places.

This tie rule is deterministic implementation provenance, not a scientific criterion.

---

# BOOTSTRAP\_OPTIMIZER\_POLICY

For every bootstrap dataset and every fitted model use exactly four deterministic model-local starts:

```text
1. same-model observed-data MLE

2. bootstrap-dataset deterministic baseline

3. deterministic positive perturbation of baseline

4. deterministic negative perturbation of baseline
```

The starts are constructed independently in each model's own dimensionality.

Forbidden:

```text
parent→child embedding
child→parent projection
4→8→16→33 bootstrap escalation
33-start bootstrap reference
64-replicate optimizer adequacy benchmark
```

Bootstrap-fit validity requires only:

```yaml
optimizer_success: true
log_likelihood_finite: true
model_expectations_finite: true
model_expectations_positive: true
physical_parameter_domains_satisfied: true
```

KKT is not a bootstrap validity gate.

---

## Bootstrap numerical failure

If either nested model cannot be fit validly on a bootstrap replicate:

```text
T_b = +infinity
```

for tail counting.

Always record:

```yaml
bootstrap_failed_replicates:
bootstrap_failure_fraction:
```

No fixed 1% failure fraction is a scientific rejection threshold in v1.1.

If numerical failures are numerous enough that the test becomes practically uninformative, record:

```yaml
test_limitation: numerically_limited
```

but do not delete the test or hypothesis.

---

# DISCOVERY\_BOOTSTRAP\_POLICY

Discovery bootstrap is used only for:

```text
K → K+1 component-addition development
```

It is NOT used to choose B0/B1/B2.

Frozen:

```yaml
discovery_component_bootstrap_replicates: 1024
development_alpha: 0.10
p_value_convention: plus_one
RNG: numpy.random.PCG64
```

For B=1024:

```math
p = \frac{1+\#\{T_b\ge T_{\rm obs}\}} {1025}.
```

A candidate split passes the bootstrap gate if:

```math
p_{\rm dev}\le0.10.```

The bootstrap p-value is a development decision quantity, not a final experimental significance claim.

Seed payload MUST include:

```text
specification_version
complex_id
comparison_id
replicate_count
```

and be SHA-256-derived deterministically before execution.

---

# KKT\_POLICY

Projected-gradient/KKT assessment is retained as an observed-final-fit diagnostic.

For:

```math
f(\theta)=-\ell(\theta),
```

finite-difference step:

```math
h_j = 10^{-6}\max(1,|\theta_j|).
```

Finite active bound `b_j`:

```math
|\theta_j-b_j| \le 10^{-8} \max(1,|\theta_j|,|b_j|).
```

Projected-gradient reference:

```math
\max_j|g_j^{proj}| \le10^{-4}.
```

Role:

```yaml
observed_final_fit: diagnostic
bootstrap_fit: not_required
component_selection_gate: false
```

If a final observed fit exceeds the reference tolerance:

1. if only 8 starts have been used, escalate to 16;
2. if 16-start solution remains stable but the diagnostic still exceeds the reference tolerance:

```yaml
numerical_convergence_status: warning
```

The fit may remain in C001 outputs with explicit warning.

No theta modification, KKT polishing or secondary optimizer is permitted.

---

# IDENTIFIABILITY\_POLICY

Every final reported component MUST carry explicit uncertainty status.

Required output fields:

```yaml
centroid_uncertainty:
area_uncertainty:
observed_width_uncertainty:
uncertainty_method:
uncertainty_status:
```

`not_estimated` is allowed only with an explicit reason.

---

## Centroid profiles

Profile likelihood is NOT required for every transient candidate.

Required for:

```text
every final K>1 promoted model
every final model flagged ambiguous by optimizer/background diagnostics
```

Profile rule:

```yaml
profile_grid_points: 41
profile_95_delta_minus2logL: 3.841458820694124
```

A final K>1 component model is centroid-identifiable only if every required centroid has finite in-domain 95% profile crossings.

For ordinary stable K=1 fits, profile likelihood is optional unless uncertainty diagnostics indicate non-quadratic or boundary behaviour.

---

## Hessian

```yaml
hessian_condition_number:
  role: optional_non_gating_diagnostic
```

A large condition number alone cannot reject a component or fail C001.

---

# RESOLUTION\_POLICY

Resolution is scientific-context dependent.

Hierarchy:

```text
R1 experimental provenance
        ↓
R2 directly justified empirical resolution
        ↓
R3 approximate/local resolution plausibility
        ↓
R4 resolution_not_established
        ↓
R5 full Cooper-Nathans/Popovici only when required by claim
```

---

## R1 — provenance

Use:

```text
canonical metadata
facility records
verified proposal/logbook if recovered
instrument-scientist information if recovered
```

No unverified proposal identifier may be promoted.

Current TAIPAN proposal status:

```yaml
candidate_proposal_number: 15702
verification_status: unverified
canonical_provenance_role: none
```

---

## R2 — direct empirical resolution

A scan may define an instrumental resolution scale only if its calibration role and physical applicability are independently established.

A fitted narrow peak alone is insufficient.

---

## R3 — resolution plausibility

Instrument knowledge and empirical effective widths may support qualitative statements such as:

```text
candidate splitting is comparable to plausible TAS resolution

or

observed structure is much broader than plausible local instrumental width
```

but may not be used for intrinsic deconvolution.

---

## R4 — resolution not established

Allowed status:

```yaml
resolution_status: resolution_not_established
```

This does NOT block:

```text
centroid extraction
integrated-area extraction
observed empirical FWHM extraction
K0→K1 presence modelling
phenomenological complex modelling
```

It DOES block:

```text
intrinsic linewidth claim
resolution-limited claim
intrinsically broadened claim
claim of physically resolved close levels solely from Gaussian decomposition
```

---

## R5 — full TAS resolution calculation

Full Cooper-Nathans/Popovici-type calculation is required only if a scientific claim depends on:

```yaml
triggers:
  - intrinsic_linewidth
  - close_unresolved_splitting
  - appreciable_dispersion_convolution
  - detailed_line_shape_or_asymmetry_interpretation
```

If no such claim is made:

```yaml
full_resolution_calculation_required: false
```

Its absence MUST NOT block ordinary C001 centroid/area extraction.

If such a claim becomes necessary but full resolution is unavailable:

```yaml
claim_status: unresolved
```

The ordinary phenomenological observation remains valid.

---

# SCAN\_104062\_POLICY

```yaml
scan_104062:
  scan_class: ordinary_energy_scan
  elastic_zero_covered: true

  possible_alignment_orientation_purpose:
    provenance: participant_recollection
    status: unverified

  calibration_role: unresolved
  established_calibration_purpose: false

  allowed_role:
    - empirical_elastic_peak_width_context
    - resolution_plausibility_context

  forbidden_role:
    - established_calibration_scan
    - established_resolution_scan
    - global_instrument_resolution_function
    - intrinsic_linewidth_deconvolution_reference

  transfer_to_production_resolution_function:
    forbidden_without_independent_applicability_evidence
```

Any empirical width reported from scan `104062` MUST state the available recorded configuration and kinematics.

Permitted semantics:

```text
empirical elastic-peak width observed for scan 104062
under its recorded configuration and kinematics
```

No fitted width from `104062` may be transferred to another scan as an instrumental-resolution kernel without independent applicability evidence.

---

# HOLDOUT\_POLICY

The discovery/holdout assignment remains immutable.

```yaml
holdout_role:
  - anti_circularity
  - internal_confirmation

holdout_interpretation:
  independent_beamtime: false
  independent_experimental_replication: false
  random_unbiased_sample_of_complete_spectrum: false
```

The holdout protects model development from confirmatory detector data and supports internal confirmation within the acquired TAIPAN dataset. It is not external experimental replication.

The complementary ILL/IN20 experiment is external post-blind validation context and cannot be substituted for the frozen TAIPAN holdout.

Before C001 STOP, holdout access is metadata-only.

Allowed:

```text
scan identity
split role
pre-detector QC
energy grid
Ei/Ef
h/k/l
monitor
time
count-control mode
instrument metadata
```

Forbidden:

```text
detector
det_err
detector/monitor
detector/time
any detector-derived rate
spectral residual
peak search
holdout fit
```

Holdout detector fields MUST NOT be materialized in a C001 analysis object.

Every field request must be auditable.

---

## Holdout metadata eligibility

For a future C002 hypothesis, a holdout scan is eligible only if:

```yaml
energy_transfer_semantics: verified
exposure_semantics: verified
grid_valid: true
frozen_complex_union_fully_covered: true

native_points_inside_union_min: 3
lower_background_anchor_points_min: 2
upper_background_anchor_points_min: 2

model_estimability:
  n_fit_points_greater_than_n_free_parameters: true
```

These are operational coverage rules, not physical detection rules.

Poor coverage gives:

```yaml
eligibility_status: insufficient_local_coverage
```

not a non-detection.

Count-control classes allowed:

```text
monitor_controlled
time_controlled
```

when their exposure semantics are verified.

---

# FUTURE\_C002\_HYPOTHESIS\_POLICY

For every complex that has:

```text
adequate C001 discovery model preparation
AND
at least one metadata-eligible holdout scan
```

pre-register:

```text
K0 → K1 presence
```

regardless of discovery-side presence significance.

For each discovery-promoted phenomenological split, also pre-register:

```text
K1 → K2
K2 → K3
```

sequentially.

Each hypothesis freezes:

```yaml
hypothesis_id:
complex_id:
hypothesis_type:
parent_K:
child_K:
background_family: B1_log_linear
component_family: observed_unit_area_Gaussian
eligible_holdout_scan_ids:
exposure_class_per_scan:
parameter_domain_rules:
resolution_status:
bootstrap_rule:
multiplicity_rule:
ancestor_hypothesis_id:
```

No holdout detector value may affect family membership.

---

# FUTURE\_C002\_BOOTSTRAP\_POLICY

Frozen before detector access:

```yaml
future_C002_bootstrap_replicates: 4096
bootstrap_design: fixed
p_value_convention: plus_one
RNG: numpy.random.PCG64
adaptive_extension: forbidden
```

No sequential extension after seeing holdout results.

Bootstrap optimizer:

```yaml
model_local_starts: 4
KKT_bootstrap_gate: false
failed_replicate_T: +infinity
```

Observed C002 parent/child fits SHOULD use the same deterministic:

```text
8 starts → 16 only if best solution not reproduced
```

policy unless Project Control freezes a separate C002 execution specification before detector access.

---

# MULTIPLICITY\_POLICY

The complete C002 family is frozen before holdout detector access.

Use:

```yaml
procedure: Holm
global_alpha: 0.05
```

Let family size be `m`.

Sort by:

```text
raw p ascending
then hypothesis_id lexical ascending
```

For rank `i`:

```math
p_{(i)} \le \frac{0.05}{m-i+1}.
```

Stop rejection at first failure.

A numerically failed hypothesis remains in the family with:

```yaml
raw_p_value: 1.0
test_status: numerical_failure
```

For any split:

```text
scientific pass
=
Holm rejection
AND
all ancestor hypotheses pass
```

No post-holdout family shrinkage is allowed.

---

# PROVENANCE\_POLICY

Required machine-readable provenance:

```yaml
canonical_main:
dataset_id:
B001_catalogue_sha256:

source_sha256:
config_sha256:

scan_ids_per_complex:
split_role_per_scan:
exposure_class_per_scan:
Ei_Ef_status_per_scan:

model_specification:
component_development_result:
background_sensitivity_status:
resolution_status:

bootstrap_B:
bootstrap_seed_payload:
bootstrap_seed_sha256:

holdout_detector_access_count:
C002_executed:

input_artifact_identities:
output_artifact_identities:
```

Numerical failure records require at minimum:

```text
complex_id
model_id_or_comparison_id
scan_id_if_applicable
bootstrap_replicate_if_applicable
fit_status
failure_reason
start_count
```

Failure diagnostics are noncanonical scientific results.

They must not publish partial C001 outputs as accepted observations.

---

## External experiment provenance

Repository-facing metadata may contain:

```yaml
complementary_experiment:
  facility: ILL
  instrument: IN20
  proposal: 4-01-1772
  role: post_blind_external_validation
```

No IN20 peak positions or assignments belong in C001 model configuration.

---

# PRIVATE\_MATERIAL\_POLICY

Repository-facing C001 design and outputs MUST NOT contain:

```text
private manuscript links
personal authorship information
coauthor comments
unpublished manuscript text or figures
unpublished CEF parameters
private editorial discussion
```

Historical preliminary PCF work may appear only as:

```yaml
preliminary_PCF:
  nature: preliminary_exploratory_estimate
  CEF_fit: false
  use_in_Stage02R_model_design: forbidden
```

No private `B_l_m` values or unpublished numerical model outputs may enter repository provenance, configuration, initialization, component construction or scientific interpretation.

---

# ALGORITHM

```text
A01
Verify canonical main and all frozen identities.

A02
Verify B001 catalogue SHA and frozen complex definitions.

A03
Load discovery and holdout split metadata.
Do not load holdout detector fields.

A04
Recover per-scan:
  energy-transfer semantics,
  monitor/time exposure semantics,
  Ei,
  Ef,
  relevant TAS configuration metadata.

No global fixed-Ef propagation.

A05
Construct discovery scan eligibility using:
  frozen complex coverage,
  >=3 native in-union points,
  >=2 nearest lower anchors,
  >=2 nearest upper anchors,
  n_points > n_free_parameters.

A06
Classify exposure class:
  monitor_controlled
  or
  time_controlled.

A07
For every adequately covered complex:
  fit K0 and K1 primary B1 models.

A08
For every observed model:
  run 8 deterministic starts.

If best likelihood not reproduced:
  extend to 16.

If still not reproduced:
  optimizer_stability_status = unresolved.

A09
Do NOT use discovery K0→K1 significance
to decide future presence registration.

A10
For K1→K2→... candidate splits:
  require stable observed parent/child,
  run B=1024 parametric bootstrap,
  four model-local bootstrap starts,
  failed bootstrap fits -> T=+infinity.

A11
If p_dev > 0.10:
  retain parent K
  stop deeper development.

A12
If p_dev <= 0.10:
  evaluate selective centroid profiles,
  cross-scan recurrence,
  B0/B2 background sensitivity.

A13
If recurrence/identifiability/background stability fail:
  retain parent K
  stop deeper development.

A14
For final phenomenological model:
  estimate centroid/area/observed-width uncertainties;
  record uncertainty method/status.

A15
Evaluate KKT only as final observed-fit diagnostic.

A16
Assign resolution status:
  justified empirical,
  plausibility only,
  or not established.

Do not promote scan 104062 to calibration.

A17
If a proposed physical claim requires full TAS resolution:
  flag full_resolution_analysis_required.

Do not block ordinary phenomenological parameters.

A18
Construct metadata-only holdout eligibility separately
for every frozen future C002 hypothesis.

A19
Freeze future C002 family:
  presence hypotheses,
  discovery-promoted split hypotheses,
  B=4096,
  Holm alpha=0.05.

A20
Verify:
  holdout detector access count = 0
  C002 executed = false
  B001 unchanged.

A21
Write complete provenance and test report.

A22
STOP.
```

---

# TESTS

Exactly 16 mandatory v1.1 tests are proposed.

## C001V11-T01 — Canonical input integrity

Verify:

```text
canonical main
dataset identity
all required A/B inputs
```

---

## C001V11-T02 — B001 immutability

Before and after:

```text
B001 catalogue SHA
=
f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5
```

---

## C001V11-T03 — Holdout detector blindness

Verify:

```text
allowlisted metadata projection only
zero detector materialization
zero det_err materialization
zero detector-derived rate materialization
forbidden request hard-fails before decode
```

---

## C001V11-T04 — CEF-blind / TAS-aware scope

Verify operational absence of:

```text
F002/F004 mapping
historical target-driven centroids
CEF model input
CEF assignment
magnon assignment
IN20-driven model construction
```

Instrument metadata usage remains permitted.

---

## C001V11-T05 — Scan eligibility

Synthetic and real metadata checks verify:

```text
>=3 in-union points
>=2 lower anchors
>=2 upper anchors
n_points > n_free_parameters
```

and that failure produces:

```text
insufficient_local_coverage
```

not non-detection.

---

## C001V11-T06 — Count-control semantics

Verify:

```text
monitor scan -> monitor exposure
time scan -> time exposure
no shared cross-mode intensity normalization
no global fixed-Ef propagation
```

---

## C001V11-T07 — Phenomenological model

Verify:

```text
raw-count/exposure Poisson likelihood
B1 primary background
scan-specific area/centroid/width/background
no arbitrary scan scale
strict centroid ordering
no physical minimum-separation constraint
```

---

## C001V11-T08 — Observed optimizer stability

Verify:

```text
8 deterministic starts
same Sobol bank extended to 16 only if needed
two-start likelihood reproduction criterion
no random restarts
no post-LBFGSB polishing
```

---

## C001V11-T09 — Bootstrap optimizer

Verify:

```text
exactly 4 model-local bootstrap starts
no 33-start reference
no 64-replicate optimizer benchmark
no bootstrap KKT gate
failed replicate -> T=+infinity
```

---

## C001V11-T10 — Discovery component bootstrap

Verify:

```text
B=1024
plus-one p-value
PCG64 deterministic seed
alpha=0.10
parent-gated sequential K
```

No background-order bootstrap is performed.

---

## C001V11-T11 — Identifiability / recurrence

Verify for every promoted K>1:

```text
finite required centroid profile intervals
>=2 supportive discovery scans
background sensitivity acceptable
```

---

## C001V11-T12 — Resolution semantics

Verify:

```text
scan 104062 not calibration
resolution_not_established is valid
centroid/area extraction allowed without established resolution
intrinsic linewidth forbidden without justified resolution
Popovici/Cooper-Nathans not mandatory absent a triggering claim
```

---

## C001V11-T13 — KKT role

Verify projected-gradient calculation is diagnostic only and cannot:

```text
modify theta
repair fit
invalidate bootstrap replicate
select K by itself
```

---

## C001V11-T14 — Holdout eligibility

Verify:

```text
metadata only
same operational local-coverage principle
monitor or time exposure allowed if verified
no detector-dependent inclusion
```

---

## C001V11-T15 — Future C002 family

Verify:

```text
presence registered independently of discovery significance
split hypotheses only from promoted hierarchy
B=4096 fixed
Holm alpha=0.05
family frozen before detector access
```

---

## C001V11-T16 — Provenance / privacy / STOP

Verify:

```text
private manuscript information absent
unverified TAIPAN proposal not promoted
IN20 role external/post-blind only
B001 unchanged
holdout detector access = 0
C002 executed = false
STOP reached before holdout detector analysis
```

---

# OUTPUTS

Target logical output set:

```text
experimental_context_assessment.yaml
scan_eligibility.csv
count_control_assessment.yaml

confirmatory_complexes.yaml
phenomenological_model_spec.yaml

discovery_final_fits.csv
component_development.yaml
background_sensitivity.csv
parameter_uncertainty.csv
reproducibility_assessment.csv

resolution_evidence.yaml
resolution_status.csv

holdout_metadata_eligibility.csv
holdout_coverage_summary.yaml
holdout_field_access_log.csv

confirmatory_hypotheses.yaml
future_C002_spec.yaml

numerical_diagnostics.yaml
provenance_manifest.yaml
test_report.yaml
```

No output may contain physical CEF/magnon/phonon assignment.

---

# PASS\_CRITERIA

C001 v1.1 passes only if:
1. canonical inputs are verified;
2. B001 remains byte-identical;
3. discovery/holdout assignment is unchanged;
4. holdout detector access count is zero;
5. no CEF-target-driven post-acquisition model design occurs;
6. no IN20 peak information constructs the C001 model;
7. all primary fitted scans satisfy metadata/grid coverage and model estimability;
8. poor coverage is never converted to non-detection;
9. every fitted scan has verified monitor or time exposure semantics;
10. no unsupported global fixed-`Ef` claim is introduced;
11. no unsupported cross-scan intensity normalization is introduced;
12. raw-count/exposure Poisson likelihood is used;
13. primary background is B1 log-linear;
14. K0/K1 presence model is prepared for every adequately modelled complex;
15. discovery significance does not determine future presence registration;
16. every promoted split satisfies B=1024 development support;
17. every promoted split has required cross-scan recurrence;
18. every promoted K>1 model passes selective centroid identifiability;
19. every promoted split is background-stable under evaluable sensitivity models;
20. observed final model optimizer stability is known or explicitly labelled unresolved;
21. KKT remains diagnostic rather than a universal validity gate;
22. final reported parameters carry explicit uncertainty status;
23. no grid-derived physical resolving-power threshold is used;
24. resolution status is explicit;
25. scan 104062 remains non-calibration evidence;
26. ordinary centroid/area extraction is permitted under `resolution_not_established`;
27. intrinsic linewidth/resolved-close-splitting claims are blocked without adequate resolution treatment;
28. metadata-only holdout eligibility is complete;
29. future C002 family is frozen before detector access;
30. C002 B=4096 fixed bootstrap rule is frozen;
31. Holm global multiplicity control is frozen;
32. private/unpublished material is absent from repository-facing outputs;
33. unverified TAIPAN proposal `15702` is not promoted to established provenance;
34. C002 is not executed;
35. all C001V11-T01...T16 PASS;
36. no exhaustive spectral-completeness claim is made;
37. insufficient or absent acquisition coverage is never converted into physical absence of a level or excitation;
38. B001 structures are not represented as an exhaustive physical excitation list;
39. holdout is described only as internal anti-circularity/confirmation within the acquired dataset, not as independent experimental replication;
40. proposal `15702` is not represented as established provenance;
41. scan `104062` is not represented as an established calibration or production-resolution reference;
42. participant recollection is explicitly distinguished from raw/derived fact and primary facility documentation.

Unresolved scientific observations such as:

```text
unresolved_substructure
resolution_not_established
insufficient_local_coverage
cross_scan_intensity_comparability_not_established
```

do NOT by themselves fail C001.

They are valid experimental outcomes.

---

# STOP\_CONDITION

C001 v1.1 STOP is reached after freezing:

```yaml
final_discovery_complex_status:
final_phenomenological_K_or_unresolved_status:
scan_specific_spectral_parameters:
parameter_uncertainty_status:
background_sensitivity:
cross_scan_reproducibility:
resolution_status:

holdout_metadata_eligibility:
future_C002_hypothesis_family:
future_C002_bootstrap_B: 4096
future_C002_Holm_alpha: 0.05

provenance_manifest:
test_report:

spectral_completeness_claim: forbidden

holdout_interpretation:
  independent_experimental_replication: false

TAIPAN_proposal_status:
  proposal_15702: unresolved_historical_clue

scan_104062:
  calibration_role: unresolved
```

Then:

```text
W02-02R-C-001 v1.1
        ↓
STOP
        ↓
02 - TAIPAN Data Reduction
scientific / methodological review
        ↓
00 - Project Control
```

C001 v1.1 MUST NOT proceed into:

```text
holdout detector access
C002 execution
combined discovery/holdout re-estimation
CEF assignment
magnon assignment
Stage03 inference
```

---

# SPECIFICATION\_STATUS

```yaml
C001_v1_1:
  specification_status: frozen
  scientific_design_status: accepted
  execution_status: not_started
  implementation_status: not_prepared
  execution_authorized: false

C001_v1:
  status: superseded_for_future_execution
  historical_provenance_retained: true
  rerun_authorized: false

A2_authorized: false
C002_execution_authorized: false
holdout_detector_access_authorized: false

design_open_questions: none
```

A new C001 v1.1 implementation and configuration require separate conformance review and explicit execution authorization before any execution.

**Return to:** `00 - Project Control`
