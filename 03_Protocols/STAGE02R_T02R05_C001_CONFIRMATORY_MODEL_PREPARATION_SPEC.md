---
title: "DyFeO3 — Stage 02R W02-02R-C-001 confirmatory model preparation specification"
type: work_job_specification
project_id: CEF-Dy
stage_id: M02R
task_id: T-02R-05
job_id: W02-02R-C-001
status: frozen
version: "1.0"
updated: 2026-09-05
language_content: ru
language_metadata: en
---

# W02-02R-C-001

## STATUS

```yaml
stage_id: M02R
task_id: T-02R-05
job_id: W02-02R-C-001
job_title: Confirmatory model and holdout-test preparation

status: frozen
design_status: approved
specification_status: frozen
execution_status: not_started
execution_authorized: false
holdout_detector_access_authorized: false
C002_execution_authorized: false
C001_design_open_questions: none

canonical_design_baseline: 31b16b22fc38fc51c063dc1d2908fcb630b8d3cf
dataset_id: EXP-TAIPAN-001
```

This document is the resolved active specification obtained, in increasing
precedence, from the original freeze candidate, authoritative freeze delta,
authoritative final micro-delta and authoritative formal closure delta. Only
the highest-precedence operative rule is retained. The redundant phrase
“scan-local initialization delta” does not identify a fifth source.

This frozen specification records design approval only. It does not authorize
or execute C-001, C-002, or detector access to the holdout.

Цель `W02-02R-C-001` — на данных `discovery` B-001 и detector-blind metadata отложенной выборки сформировать полностью детерминированный confirmatory package для будущего `W02-02R-C-002`.

C-001 должен:

```text
frozen B-001 catalogue
        ↓
verify identities
        ↓
resolution evidence decision tree
        ↓
deterministic complex fit windows
        ↓
discovery-side background/model development
        ↓
maximum preregistered component hierarchy
        ↓
metadata-only holdout coverage/eligibility
        ↓
freeze C-002 hypothesis registry
        ↓
freeze numerical/statistical rules
        ↓
STOP before holdout detector access
```

C-001 НЕ является подтверждающим анализом.

C-001 НЕ принимает решение, подтверждены ли BF-комплексы на отложенной выборке.

C-001 НЕ меняет B-001 catalogue.

---

# INPUTS

## Canonical project inputs

```text
00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml
00_Project/RESULT_REGISTER.yaml
00_Project/EVIDENCE_REGISTER.yaml

03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
```

## Reviewed Stage 02R inputs

```text
02_Work_Checkpoints/W02-02R-A-001.md
02_Work_Checkpoints/W02-02R-A-002.md
02_Work_Checkpoints/W02-02R-A-003.md
02_Work_Checkpoints/W02-02R-B-001.md

04_Results/Stage02R/W02-02R-B-001/SCIENTIFIC_REVIEW.md
04_Results/Stage02R/W02-02R-B-001/blind_feature_catalogue.yaml
04_Results/Stage02R/W02-02R-B-001/blind_split.csv
04_Results/Stage02R/W02-02R-B-001/scan_selection.csv
04_Results/Stage02R/W02-02R-B-001/feature_reproducibility.csv
04_Results/Stage02R/W02-02R-B-001/provenance_manifest.yaml

04_Results/Stage02R/W02-02R-A-002/scan_inventory.csv
04_Results/Stage02R/W02-02R-A-002/scan_points.csv
04_Results/Stage02R/W02-02R-A-002/semantic_verification_report.yaml

04_Results/Stage02R/W02-02R-A-003/scan_classification.csv
04_Results/Stage02R/W02-02R-A-003/instrument_configs.yaml
04_Results/Stage02R/W02-02R-A-003/normalization_compatibility_groups.yaml
```

## Frozen B-001 identity

```yaml
blind_catalogue_sha256:
  f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5

feature_ids:
  - BF-001
  - BF-002
  - BF-003
  - BF-004
  - BF-005
  - BF-006
  - BF-007
  - BF-008
```

The B-001 catalogue bytes MUST remain unchanged.

## Frozen overlap complexes

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

These are algorithmic spectral regions.

They are not physical excitation assignments.

Canonical `DATA_CONTRACTS` requires experimental observation and physical assignment to remain separate, and a common normalization parameter cannot be inferred solely from `instrument_config_id`.

---

# ALLOWED\_DATA\_ACCESS

## Discovery-side detector data

C-001 MAY read detector values only for B-001 scans satisfying:

```text
split_role = discovery
AND
final B-001 discovery outcome usable
```

The B-001 numerical exclusion:

```text
SCAN-02R-7acd4c14a0007418
```

is excluded from primary C-001 spectral-model development.

Its B-001 status is immutable.

## Отложенная выборка

For scans with:

```text
split_role = holdout
```

C-001 MAY read only detector-blind information needed for eligibility:

```text
scan_record_id
raw_scan_id

split_role
pre_detector_status

count_control_mode
acquisition_state_id
lattice_state_id
UB_state_id

point_index
energy_transfer
Ei
Ef
h
k
l

monitor
time

scan_point_count
scan_variable_raw
en_e_mapping_status

instrument_config_id
normalization_epoch_id

monochromator_material
monochromator_reflection
monochromator_reflection_status
monochromator_mosaic
monochromator_mosaic_status

analyzer_material
analyzer_reflection
analyzer_reflection_status
analyzer_mosaic
analyzer_mosaic_status

collimation
focusing metadata
aperture/divergence metadata
where present and required for resolution eligibility
```

Exact canonical source-column names MUST be mapped explicitly in implementation.
For any table containing holdout rows, a generic full-table load is forbidden.
The implementation MUST project the allowlisted columns (`usecols` or equivalent)
before row materialization. `detector`, `detector_counts`, `det_err`, detector/monitor,
detector/time, every detector-derived rate, spectral-fit field and candidate statistic
are denied. Such columns MUST never exist in a C-001 holdout analysis object.

Every request is recorded in `holdout_field_access_log.csv` with fields:

```text
source_artifact
requested_field
access_role
allowed
request_sequence
```

A forbidden-field request MUST hard-fail before decode/materialization and terminate
C-001.

## Resolution evidence

C-001 MAY inspect non-holdout instrument/calibration data.

`EV-006` / scan `104062` may be investigated because it is instrument evidence and canonical B-001 records it on the discovery side, not as part of the отложенная выборка. Its historical value is explicitly documented as incomplete resolution evidence requiring reproduction and applicability assessment.

Detector access to scan `104062` is allowed only for:

```text
resolution_evidence
```

and MUST NOT create cross-mode intensity normalization.

---

# FORBIDDEN\_DATA\_ACCESS

C-001 MUST NOT access detector values from any `holdout` scan.

Forbidden before C-001 STOP:

```text
holdout detector counts
holdout det_err
holdout detector/monitor rates
holdout detector/time rates
holdout spectral plots
holdout fit residuals
holdout peak search
```

Also forbidden:

```text
F002
F004

historical spectral targets
historical target comparison
historical peak centroids as BF mappings

CEF level schemes
CEF assignments
PCM / CFE / PCF predictions
exchange interpretation
Stage 03R / Stage 03D model constraints
```

Exception:

```text
EV-006 historical 0.894 ± 0.025 meV
```

may be used ONLY as a resolution-reproduction reference.

It MUST NOT enter spectral-component hypotheses.

---

# RESOLUTION\_DECISION\_TREE

Resolution identity is determined at minimum for each:

```text
scan_record_id × complex_id
```

Required fields are:

```yaml
scan_record_id:
complex_id:
resolution_status:
resolution_model_id:
resolution_evidence_id:
applicability_status:
applicability_basis:
missing_resolution_critical_fields:
```

A frozen `resolution_class_id` may replace per-scan models only when every
member scan independently passes the same applicability rule. A complex-wide
model requires the same frozen resolution model to be individually applicable
to every eligible member scan with zero unresolved exceptions. Otherwise the
resolution remains scan-specific.

Allowed final statuses:

```text
resolution_established_empirical
resolution_established_calculated
resolution_not_established
```

Decision order is fixed:

```text
STEP R1:
reproducible + applicable empirical calibration?
    YES → resolution_established_empirical
    NO  → R2

STEP R2:
all required TAS-resolution metadata available
AND validated calculation possible?
    YES → resolution_established_calculated
    NO  → R3

STEP R3:
resolution_not_established
```

No lower-priority branch may override a successful higher-priority branch.

---

## R1 — empirical calibration

### EV-006 reproduction

For scan `104062`, reproduce the elastic-line width from canonical parsed data.

Primary reproduction model:

```math
D_i\sim\mathrm{Poisson}(E_i\lambda_i)
```

with:

```text
E_i = verified time exposure
```

and:

```math
\lambda_i = \exp(b_0+b_1x_i) + A\,G(E_i;c,w),
```

where `G` is a unit-area Gaussian.

Use the numerical optimizer rules in `NUMERICAL_SPECIFICATION`.

Historical reference:

```yaml
EV-006:
  reported_fwhm_meV: 0.894
  reported_sigma_meV: 0.025
```

Reproduction passes only if:

1. fit converges under the frozen multistart rules;
2. fitted FWHM has a finite profile interval;
3. centroid is within two local median energy steps of elastic zero;
4. width agreement satisfies:

```math
|w_{\rm new}-0.894| \le \max\left[ 2\sqrt{\sigma_{\rm new}^2+0.025^2}, 0.10\times0.894 \right].
```

The historical value itself is not refitted or forced.

### Physical basis and suitability of scan `104062`

The mandatory object is:

```yaml
resolution_probe_physical_basis:
  status: established | unresolved
  basis_type:
  provenance:
  scientific_rationale:
```

It MUST be established independently of the measured or fitted width of scan
`104062`. Acceptable `basis_type` values are independently supported categories:

```text
documented_resolution_calibration
documented_instrument_calibration_scan
standard_sample_incoherent_elastic_resolution_measurement
independently_justified_negligible_intrinsic_width
```

Fit stability, reproduction of the historical width, or a statement that the
peak is narrow is insufficient physical basis.

Before scan `104062` can be called a resolution calibration, C-001 must also
establish:

```yaml
resolution_probe_suitability:
  status: suitable | unsuitable | unresolved
```

The numerical/geometry suitability requirements are:

```text
verified energy-transfer scan semantics
energy grid covers elastic zero
>=4 usable points below zero
>=4 usable points above zero
closest sampled |E| <= median energy step
valid exposure semantics
no detector high-rate warning
stable elastic-profile fit
```

The reproduced FWHM is tested for stability under `B0` versus `B1`, the nominal
fit window, and a window contracted by one native energy point on each side.
Every valid fitted width must differ from the nominal FWHM by at most `10%`.
No second-component fit, test or model-comparison gate is defined for scan
`104062`.

Promotion to `resolution_probe_suitability: suitable` requires both the frozen
numerical/geometry checks and
`resolution_probe_physical_basis.status: established`. If the physical basis
is absent, ambiguous or unrecovered, the result is:

```yaml
resolution_probe_physical_basis:
  status: unresolved
resolution_probe_suitability: unresolved
scan_104062_role: empirical_effective_width_evidence
```

Fit stability remains diagnostic only. `resolution_not_established` remains an
acceptable outcome.

### Direct empirical applicability

Reproduction and probe suitability are insufficient by themselves. Direct
application to a spectral scan requires verified compatibility of every
resolution-critical field relevant to the claim, including:

```text
fixed-energy mode
Ei
Ef

monochromator material/reflection/mosaic
analyzer material/reflection/mosaic
horizontal collimation
focusing state
sample orientation / scattering plane
UB state where relevant
sample mosaic where available
scattering geometry / relevant TAS angles
resolution-relevant aperture/divergence fields
```

The prior kinematic inequalities remain necessary:

```math
|E_i^{cal}-E_i^{target}|/E_i^{target}\le0.05
```

```math
|E_f^{cal}-E_f^{target}|/E_f^{target}\le0.05
```

```math
\left||Q|_{cal}-|Q|_{target}\right|/ \max(|Q|_{target},0.1) \le0.10.
```

For a future holdout scan `s` and complex `q`, applicability MUST be decided
entirely from metadata before detector access over the frozen domain:

```math
\mathcal D_{sq}=[L_q,U_q]\cap[E_{s,\min},E_{s,\max}],
```

where `[L_q,U_q]` is the full frozen complex union and the scan trajectory is
metadata-derived. Evaluate the frozen kinematic conditions at every native
grid energy in `\mathcal D_{sq}` and at both domain endpoints when an endpoint
is not a native point. Endpoint kinematics may use only the frozen
metadata/trajectory representation.

Any failed evaluated state or any required critical field that is missing,
unverified, unresolved or `not_recorded` yields:

```text
direct_empirical_applicability = not_established
```

Shared missing values are not compatibility evidence. Agreement in `Q/Ei/Ef`
cannot override unknown reflection, mosaic, focusing or geometry metadata.
Applicability MUST NOT be selected after fitting a holdout centroid.

General empirical interpolation and extrapolation are disabled in C-001 v1:

```yaml
empirical_resolution_interpolation_enabled: false
```

Multiple calibration observations may be recorded as evidence but do not define
a general empirical function. The active route is only direct applicable
empirical calibration, otherwise validated calculated resolution, otherwise
`resolution_not_established`.

---

## R2 — calculated TAS resolution

Calculated resolution may be attempted only if the chosen implementation has all required physical inputs.

Mandatory metadata include, as required by the implementation:

```text
Ei / Ef or ki / kf
fixed-energy mode

monochromator material
monochromator reflection
monochromator mosaic

analyzer material
analyzer reflection
analyzer mosaic

horizontal collimation
vertical divergence/collimation if used

sample lattice
UB / orientation
sample mosaic

focusing state / curvature if active

relevant apertures / source dimensions / beam divergence
sample-to-component distances required by the model

scattering geometry / angles
```

Any required field with status:

```text
missing
not_recorded
unverified
unresolved
```

invalidates that calculation branch.

No substitution by assumed instrument defaults is allowed.

Before entering the calculated branch, the runtime configuration MUST contain
one complete immutable implementation lock:

```yaml
calculated_resolution_implementation:
  availability: available | unavailable
  implementation_name:
  implementation_version:
  source_repository:
  source_commit:
  source_sha256:
  coordinate_convention:
    reciprocal_space_basis:
    handedness:
    energy_transfer_sign:
    ki_kf_convention:
    angle_units:
    energy_units:
    momentum_units:
  algorithm_family: Popovici_type
  runtime_configuration_path:
  runtime_configuration_sha256:
  validation_benchmark_id:
  validation_status:
```

If `availability: available`, every other field is mandatory and non-null and
`validation_status` MUST already be `passed`. The implementation, version,
source commit/hash, coordinate convention and runtime configuration/hash are
immutable for that C-001 execution. Running multiple implementations and
selecting one by agreement with observed spectral widths is forbidden.

If a single implementation cannot be locked and independently validated before
calculation:

```yaml
calculated_resolution_implementation:
  availability: unavailable
calculated_resolution_branch: unavailable
```

The decision tree proceeds to `resolution_not_established` unless direct
empirical resolution has already passed.

### Calculation method

Frozen theoretical family:

```text
Popovici-type TAS resolution calculation
```

Before scientific use it must pass:

1. unit/coordinate convention tests;
2. an implementation reference benchmark with ≤1% numerical disagreement in reported energy FWHM;
3. at least one applicable experimental instrument-resolution cross-check where available.

If scan `104062` is used as that cross-check, agreement requires:

```math
|w_{\rm calc}-w_{\rm meas}| \le \max(2\sigma_{\rm meas},0.15w_{\rm meas}).
```

A successful calculation is still applied only within its verified metadata/kinematic domain.

If any validation requirement fails:

```text
resolution_status = resolution_not_established
```

---

## R3 — resolution not established

This is an acceptable C-001 outcome.

Consequences:

```text
intrinsic_linewidth_reporting: forbidden
resolution_limited_claim: forbidden
intrinsically_broadened_claim: forbidden
```

C-002 must then use the frozen empirical observed-line model below.

Reported width semantics become:

```text
observed_empirical_fwhm
```

only.

---

# MODEL\_DEVELOPMENT\_RULES

## 1. Confirmatory unit

Primary unit:

```text
overlap complex
```

not individual BF.

One BF MUST NOT automatically equal one fitted component.

---

## 2. Default cross-scan structure

For complex `q`, scan `s`, point `i`:

```math
D_{si}\sim\operatorname{Poisson}(\mu_{si}),
```

```math
\mu_{si}=E_{si}\left[B_s(E_{si}^{tr})+\sum_{k=1}^{K}A_{sk}L_{sk}(E_{si}^{tr};c_{sk},w_{sk},R_{sq})\right].
```

The complex definition, `K`, fit window, background family, line-shape family
and parameter-bound rules are shared model structure. Centroid `c_sk`,
observed/intrinsic width `w_sk`, integrated area `A_sk` and background
parameters are scan-specific by default. For multiple eligible scans:

```math
\ell_{\rm joint}=\sum_s\ell_s.
```

The joint likelihood aggregates evidence without imposing `c_sk=c_tk` or
`w_sk=w_tk` for distinct scans. Common-centroid/common-width models are outside
default C-001/C-002 and deferred to C-003 unless separately frozen by Project
Control.

---

## 3. Discovery modelling scan set

For every complex, define `discovery_model_scan_set` as all and only scans
satisfying:

```text
B-001 split_role = discovery
B-001 final discovery_runtime_status = discovery_usable
count_control_mode = monitor_controlled
verified monitor exposure semantics
full frozen C-001 fit-window coverage
strictly monotonic usable energy grid
no duplicate energy coordinate
>=15 points in final fit window
>=4 native-grid points below frozen BF-complex union
>=4 native-grid points above frozen BF-complex union
```

The set uses only B-001 status, metadata, energy grid and exposure semantics.
Peak appearance, candidate amplitude, residual shape, signal-to-background,
detector-rate magnitude, likelihood and apparent component presence are
forbidden selection inputs. Freeze the set before background or component
development. Record `discovery_model_scan_set_sha256` from lexically sorted
`scan_record_id` values, each LF-terminated.

---

## 4. Deterministic fit-window construction

For each complex `CX`:

1. use only discovery-side monitor-controlled energy scans;
2. select scans whose metadata energy range fully covers the frozen BF-union interval;
3. compute each scan's median positive adjacent energy step;
4. define:

```math
\Delta E_{\rm ref} = \operatorname{median}_s [ \operatorname{median}_i(|E_{i+1}-E_i|) ].
```

Candidate symmetric margins are tested in this fixed order:

```text
5 × ΔE_ref
4 × ΔE_ref
3 × ΔE_ref
```

Choose the **largest** margin for which at least two discovery scans have:

```text
full window coverage
>= 4 grid points below frozen complex union
>= 4 grid points above frozen complex union
>= 15 total points inside fit window
```

Fit window:

```math
[\,L_{\rm CX}-m,\ U_{\rm CX}+m\,].
```

If no margin passes:

```text
complex_model_status =
insufficient_discovery_window_coverage
```

and no confirmatory spectral test may be registered for that complex.

Fit-window selection uses energy grids only.

Detector values cannot alter the chosen window.

---

## 5. Background model development

Candidate background families:

```text
B0: log-rate constant
B1: log-rate linear
B2: log-rate quadratic
```

with:

```math
\log B_s(x)= b_{0s}+b_{1s}x+b_{2s}x^2
```

as applicable.

Scaled coordinate:

```math
x= 2\frac{E-E_{\rm mid}} {E_{\rm high}-E_{\rm low}}
```

so that:

```text
x ∈ [-1,1]
```

Background-family development uses ONLY flank points outside the frozen BF-union region but inside the final fit window.

Sequential rule:

```text
start B0

test B0 → B1
if p_dev <= 0.05:
    promote B1
else:
    freeze B0

if B1 promoted:
    test B1 → B2
    if p_dev <= 0.05:
        promote B2
    else:
        freeze B1
```

Frozen:

```yaml
background_development_alpha: 0.05
background_bootstrap_replicates: 4096
```

A numerically failed child-background test retains the parent and records:

```text
background_selection_limited_by_numerics
```

No AIC/BIC-only promotion is permitted.

AIC/BIC may be recorded as diagnostics only.

---

## 6. Confirmatory spectral profile

### If resolution established

Observed component:

```text
intrinsic Lorentzian
⊗
frozen empirical/calculated resolution kernel
```

For an approximately Gaussian empirical resolution this is a Voigt profile.

Intrinsic width is a nuisance parameter during C-001 model development.

No physical linewidth claim is made in C-001.

### If resolution not established

Use a unit-area empirical Gaussian:

```math
G(E;c,w).
```

Its FWHM is an empirical nuisance parameter.

It has no intrinsic-linewidth interpretation.

---

## 7. K hierarchy

For each complex:

```text
K0 = background only
K1 = background + 1 component
K2 = background + 2 ordered components
...
```

Maximum geometrically possible K:

```math
K_{\rm geometry} = 1+ \left\lfloor \frac{U_{\rm CX}-L_{\rm CX}} {\Delta E_{\rm ref}} \right\rfloor.
```

Absolute development cap:

```math
K_{\rm cap} = \min( K_{\rm geometry}, K_{\rm BF} ).
```

Thus:

```text
CX-01 <= 3
CX-02 <= 2
CX-03 <= 3
```

---

## 8. Presence versus split hypotheses

These are separate hypothesis classes.

### Presence

Always pre-register, where metadata coverage permits:

```text
K0 → K1
```

C-001 discovery significance does NOT decide whether the future presence test exists.

### Component resolution

C-001 determines the maximum split hierarchy using discovery data.

Sequential development:

```text
fit K1

test K1 → K2
if p_dev <= 0.10
AND child identifiable:
    preregister K1 → K2
    continue
else:
    stop

if K2 accepted for development:
    test K2 → K3
    ...
```

Frozen:

```yaml
component_development_alpha: 0.10
component_bootstrap_replicates: 4096
```

Parent model MUST pass before a deeper split enters the registry.

No child can be registered if its parent was not development-accepted.

---

## 9. Future C-002 hierarchy rule

C-002 must retain all pre-registered hypotheses in one global family.

A split may be scientifically declared only when:

```text
its own Holm-adjusted test passes
AND
every ancestor hypothesis passes
```

Examples:

```text
K1→K2 cannot pass scientifically if K0→K1 fails.

K2→K3 cannot pass scientifically unless:
K0→K1 passes
AND
K1→K2 passes.
```

All raw C-002 p-values are nevertheless computed for the complete frozen family where numerically evaluable.

No post-holdout deletion of inconvenient hypotheses is allowed.

---

## 10. Ordered-centroid parameterization

For a scan with `K` components use exactly `K` free logits
`eta_0 ... eta_(K-1)` and one fixed reference logit `eta_K=0`. Define the
stable softmax:

```math
m=\max(0,\eta_0,\ldots,\eta_{K-1}),
```

```math
q_j=\frac{\exp(\eta_j-m)}{\exp(-m)+\sum_{r=0}^{K-1}\exp(\eta_r-m)},
\quad j=0,\ldots,K-1,
```

```math
q_K=\frac{\exp(-m)}{\exp(-m)+\sum_{r=0}^{K-1}\exp(\eta_r-m)}.
```

Let `delta=Delta E_ref` and:

```math
R=(U-L)-(K-1)\delta.
```

`R>0` is required. Centroids are:

```math
c_k=L+(k-1)\delta+R\sum_{j=0}^{k-1}q_j,\qquad k=1,\ldots,K.
```

This gives `L<c_1`, `c_(k+1)-c_k>delta`, and `c_K<U`. The transform is
applied independently to every scan. The free centroid dimension is exactly
`K`; the fixed reference removes the redundant common-scale degree. Post-fit
sorting is forbidden.

---

## 11. Identifiability requirement

A development child K may be promoted only if:

1. observed fit converges;
2. bootstrap development test passes;
3. every required scan-specific centroid has a finite profile interval;
4. profile interval has both threshold crossings inside the allowed complex bounds;
5. the frozen minimum-separation proximity gate passes.

For adjacent components in scan `s`:

```math
d_{sk}=(c_{s,k+1}-c_{sk})-\Delta E_{\rm ref},
```

```math
\tau_{\rm sep}=\max(0.10\,\Delta E_{\rm ref},10^{-6}\ {\rm meV}).
```

```yaml
minimum_separation_proximity_tolerance:
  relative_to_delta_E_ref: 0.10
  absolute_floor_meV: 1.0e-6
```

A scan is informative for a pair only when both corresponding areas are not
active at the lower bound `A=0` under the frozen KKT active-bound tolerance.
For every adjacent pair, at least one informative scan is required and at
least one must satisfy `d_sk > tau_sep`.

No informative scan gives
`component_identifiability_status: rejected_no_informative_scan_for_split`.
If all informative scans have `d_sk <= tau_sep`, use
`component_identifiability_status: rejected_minimum_separation_proximity`.
Either result retains parent `K` and stops deeper development. Otherwise the
proximity gate passes and the profile criteria above remain additionally
required.

Profile diagnostic:

```yaml
profile_grid_points_per_centroid: 41
profile_delta_minus2logL_threshold: 3.841458820694124
```

This is a development identifiability diagnostic, not a final coverage claim.

A finite-difference Hessian condition number is also recorded.

Frozen warning:

```yaml
hessian_condition_warning_threshold: 1.0e10
```

A Hessian warning alone does not reject a component if the profile criteria pass.

---

# HOLDOUT\_METADATA\_ELIGIBILITY

Eligibility is determined after fit windows and C-001 model hierarchy are
finalized but before any holdout detector access. Machine field
`split_role: holdout` remains exact; human-facing text uses «отложенная
выборка».

## Eligibility requirements

A holdout scan is eligible for primary C-002 confirmation only if:

```text
split_role = holdout
count_control_mode = monitor_controlled
verified monitor exposure semantics
pre-detector QC acceptable
strictly monotonic usable energy grid
no duplicate energy coordinate
full final fit-window coverage
>=15 points in the final window
>=4 points below the frozen complex union
>=4 points above the frozen complex union
```

All decisions use the explicit metadata projection defined in
`ALLOWED_DATA_ACCESS`; no detector field may affect eligibility.

## Coverage classification

For each complex:

```text
0 eligible scans:
  coverage_status = not_covered
  holdout_coverage_scope = none
  no C-002 spectral hypothesis registered

1 eligible scan:
  coverage_status = covered
  holdout_coverage_scope = single_scan

>=2 eligible scans:
  coverage_status = covered
  holdout_coverage_scope = multi_scan
```

`holdout_coverage_scope` describes capacity only, not observed support or
replication. Actual confirmatory support is a C-002 result. A single eligible
scan may support a future confirmatory test but cannot be described as
replication within the holdout.

## Dominant-scan diagnostic

For future C-002 `multi_scan` fits record `T_all` and refitted
leave-one-scan-out statistics `T_-s`:

```math
I_s=T_{\rm all}-T_{-s},
```

```math
f_{\rm dominant}=
\frac{\max_s\max(0,I_s)}{\max(T_{\rm all},10^{-12})}.
```

Set `dominant_scan_warning=true` iff `f_dominant>0.50`. This diagnostic is
non-gating. No leave-one-out bootstrap p-values and no p=0.05 crossing rule
are used in v1.

---

# STATISTICAL\_MODEL

For discovery-side model development:

```math
D_{si} \sim \operatorname{Poisson}(\mu_{si}),
```

```math
\mu_{si} = E_{si} \left[ B_s(E_{si}^{tr}) + \sum_{k=1}^{K} A_{sk}L_{sk}(E_{si}^{tr};c_{sk},w_{sk},R_{sq}) \right].
```

For primary monitor-controlled spectroscopy:

```text
E_si = monitor exposure
```

Parameters:

```text
B_s:
  scan-specific background

A_sk:
  scan-specific integrated component area
  A_sk >= 0

c_sk:
  scan-specific component centroid

w_sk / gamma_sk:
  scan-specific component width nuisance
  semantics depend on resolution branch
```

The complex/model structure is shared, but cross-scan equality of centroids or
widths is not imposed. A joint likelihood may sum scan log likelihoods while
retaining scan-specific centroids, widths, areas and backgrounds.

No arbitrary multiplicative `scale_s` is fitted.

No cross-scan common intensity is assumed.

No cross-mode likelihood is constructed.

---

## Intensity semantics

Keep distinct:

```text
raw detector counts
monitor exposure
detector / monitor display rate
fitted scan-level component area
relative experimental INS intensity
calculated transition strength
```

Primary C-001 output:

```text
scan-level fitted area
```

only.

No common cross-scan relative intensity is promoted by C-001.

C-001 MAY produce:

```text
instrument_block_assessment
```

from metadata/instrument evidence only.

Any proposed shared-normalization grouping must remain:

```text
proposed_only
```

until explicit Project Control review at the C-001 → C-002 boundary.

---

# NUMERICAL\_SPECIFICATION

## Global deterministic constants

```yaml
numerical_spec_version: stage02r_c001_numerical_v1

discovery_bootstrap_replicates: 4096
future_c002_bootstrap_replicates: 8192

background_development_alpha: 0.05
component_development_alpha: 0.10

future_c002_global_alpha: 0.05

bootstrap_failed_replicate_fraction_max: 0.01

optimizer:
  implementation: scipy.optimize.minimize
  method: L-BFGS-B
  maxiter: 4000
  ftol: 1.0e-12
  gtol: 1.0e-8
  maxls: 50

observed_fit_multistarts: 33
bootstrap_fit_multistarts_candidate_sequence: [4, 8, 16, 33]
bootstrap_reference_multistarts: 33
bootstrap_adequacy_benchmark_replicates: 64
bootstrap_multistarts_selected: determined_by_C001_T12

profile_grid_points: 41
profile_delta_minus2logL_threshold: 3.841458820694124

hessian_condition_warning_threshold: 1.0e10
```

---

## Parameter bounds

### Background

With scaled `x\in[-1,1]`:

```yaml
background_slope_bounds: [-10.0, 10.0]
background_quadratic_bounds: [-10.0, 10.0]
```

For each observed or bootstrap dataset define the initialization-only rate:

```math
r_{0s} = \frac{\sum D_s+0.5}{\sum E_s}.
```

The inferential domain is `b0 in (-infinity,+infinity)`. `log(r0_s)` is only
the background initialization center and never a hard bound.

### Scan-specific integrated areas

```math
A_{sk}\ge0.
```

There is no finite upper bound. Define only the initialization scale:

```math
A_{0s}=W_{\rm fit}\frac{\sum_iD_{si}+1}{\sum_iE_{si}}.
```

Detector-derived `r0_s` and `A0_s` are recomputed from each actual
observed/bootstrap dataset, may change starts only, and never alter bounds or
model nesting.

### Centroids

All centroids remain inside:

```text
frozen complex union
```

not the expanded background window.

Ordering/minimum separation follows `MODEL_DEVELOPMENT_RULES`.

### Empirical Gaussian FWHM

If `resolution_not_established`:

```math
w_{\min}=0.5\Delta E_{\rm ref},
```

```math
w_{\max} = \min \left[ U_{\rm CX}-L_{\rm CX}, 0.5W_{\rm fit} \right].
```

### Intrinsic FWHM

If resolution is established:

```math
0\le\Gamma_k\le \min \left[ U_{\rm CX}-L_{\rm CX}, 0.5W_{\rm fit} \right].
```

---

## Exact multistart and Sobol bank

For each fitted model, scans are ordered by lexical `scan_record_id`. Within
each scan block, the free-vector/Sobol dimensions are exactly:

```text
1. b0
2. b1, only for B1/B2
3. b2, only for B2
4. A_1 ... A_K
5. eta_1 ... eta_K
6. width_1 ... width_K
```

The `K` centroid logits are the free fixed-reference-simplex coordinates;
the reference logit is not a dimension. Component dimensions are absent for
`K=0`; externally fixed resolution-kernel parameters are absent.

The generator is exactly:

```python
scipy.stats.qmc.Sobol(d=d, scramble=False).random_base2(m=5)
```

giving frozen ordered vectors `u[0]...u[31]`, without scrambling or seed.
Initialization constants are:

```yaml
C_b: 4.0
C_A: 4.0
C_eta: 4.0
```

For each scan and each actual observed/bootstrap dataset:

```math
r_0=\frac{\sum_iD_i+0.5}{\sum_iE_i},\qquad
A_0=W_{\rm fit}\frac{\sum_iD_i+1}{\sum_iE_i}.
```

For each Sobol coordinate `u in [0,1)`:

```math
b_{0,start}=\log r_0+4(2u-1),
```

```math
A_{k,start}=A_0\exp[4(2u-1)],\qquad
\eta_{k,start}=4(2u-1).
```

A finite background coefficient with frozen bound `[l,h]` uses
`theta_start=l+u(h-l)`; thus `b1,b2` use `[-10,+10]`. If resolution is
not established, `w_start=w_min+u(w_max-w_min)`; an intrinsic width uses
`Gamma_start=u Gamma_max`. No detector quantity enters a width bound.

Observed Start 1 is the frozen baseline: flank-only background, zero free
centroid logits (the equal-gap arrangement), `A_sk=A0_s/max(K,1)`, and width
midpoint. Starts 2–33 map
`u[n-2]`. Choose the valid maximum-likelihood result; if
`|ell_a-ell_b|<=1e-8`, choose the lexically smallest parameter vector after
12-decimal rounding.

## Model-local bootstrap Starts 1–4

For model `M_K`, scan `s`, replicate `b`, compute scan-local
`r0_s^(b)`, `A0_s^(b)`, then construct `theta_base(M_K,b)` in that
model's native parameter space:

```text
b0 = log(r0_s^(b))
b1 = 0 if active
b2 = 0 if active
A_sk = A0_s^(b) / max(K,1)
eta_sk = 0
empirical width = midpoint(w_min,w_max)
intrinsic Gamma = 0.25 * Gamma_max
```

For `K=0`, component fields do not exist. Zero free logits give the
equal-gap centroid arrangement.

- Start 1: observed-data MLE of the same model `M_K`; if unavailable or
  invalid, replace with `theta_base(M_K,b)` and log the replacement.
- Start 2: `theta_base(M_K,b)`.
- Start 3: from Start 2, add `0.05` to active background coefficients,
  multiply areas and empirical widths by `1.10`, project the width, and set
  intrinsic `Gamma=min(Gamma_max,Gamma_base+0.10 Gamma_max)`. Centroid-logit
  perturbation is
  `Delta eta_sk^(+)=0.25[2(k-1)/max(K-1,1)-1]`; for `K=1`, it is zero.
- Start 4: from Start 2, subtract `0.05` from active background coefficients,
  multiply areas and empirical widths by `0.90`, project the width, use the
  negative centroid-logit perturbation, and set
  `Gamma=max(0,Gamma_base-0.10 Gamma_max)`.

Parent and child banks remain wholly model-local. Parent-to-child embedding,
child-to-parent projection and component-removal mappings are not used.

Bootstrap Starts 5–33 use `u[n-5]` with `r0,A0` recomputed for that
replicate. Candidate banks are strict prefixes `4 -> 8 -> 16 -> 33`.

## Bootstrap optimizer adequacy benchmark

For each distinct frozen parent/child comparison, select exactly 64 replicates
from the deterministic C-001 sequence:

```math
r_j=\left\lfloor\frac{(j+0.5)4096}{64}\right\rfloor,
\qquad j=0,\ldots,63.
```

Fit parent and child at candidate level and with the 33-start reference.
All 64 parent and all 64 child reference fits MUST be valid. One invalid
reference yields:

```yaml
optimizer_adequacy_status: failed
optimizer_adequacy_reason: invalid_33_start_reference
C001_STOP: blocked_for_C002_freeze
```

No failed reference may be discarded, replaced, resampled or removed from the
denominator. Only after reference validity is 64/64 for both models is
candidate agreement assessed. For each valid reference:

```math
|\ell_n-\ell_{33}|\le10^{-6}\max(1,|\ell_{33}|).
```

Frozen values:

```yaml
log_likelihood_relative_tolerance: 1.0e-6
allowed_likelihood_mismatches_per_model: 1
benchmark_replicates: 64
allowed_mismatch_fraction: 0.015625
```

A candidate also fails immediately when a reference is valid and its
candidate fit is invalid. Candidate-valid/reference-invalid is diagnostic
only and cannot establish adequacy. Test candidates in the exact order
`4,8,16,33` and freeze the first passing value as
`bootstrap_multistarts_selected`. Future C-002 uses at least that count. If
33 fails, C-001 may finish diagnostically but stops
`blocked_for_C002_freeze`.

---


## Fit validity and constrained convergence

A fit is valid only when optimizer state and log likelihood are finite,
all expectations are finite and strictly positive, all parameters lie in the
frozen domain, and the projected-gradient/KKT gate passes for
`f(theta)=-ell(theta)`.

For parameter `theta_j`, use:

```math
h_j=10^{-6}\max(1,|\theta_j|).
```

Use a central finite difference when both perturbations are feasible; otherwise
use a feasible forward difference at a lower bound or backward difference at
an upper bound. A finite bound `b_j` is active when:

```math
|\theta_j-b_j|\le10^{-8}\max(1,|\theta_j|,|b_j|).
```

For gradient `g_j=partial f/partial theta_j`, set `g_j^proj=0` at an
active lower bound when `g_j>=0`, or at an active upper bound when
`g_j<=0`; otherwise `g_j^proj=g_j`. The frozen gate is:

```math
\max_j|g_j^{proj}|\le10^{-4}.
```

Valid boundary optima such as `A_sk=0` or `Gamma_sk=0` are therefore not
rejected merely for a nonzero unconstrained gradient. If no multistart
candidate passes all validity checks, set `fit_status=numerical_failure`.

---


## Bootstrap test statistic

For nested parent `M_0` and child `M_1`:

```math
T_{\rm obs} = 2[ \ell(M_1)-\ell(M_0) ].
```

Numerical negative values with:

```math
T>-10^{-8}
```

are clipped to zero.

Larger negative values invalidate the test.

Bootstrap data are generated from the fitted parent model with the real:

```text
energy grids
exposures
scan membership
```

held fixed.

---

## Discovery bootstrap seed

Canonical payload:

```text
stage02r_c001_bootstrap_seed_v1
master=CEF-Dy:T-02R-05:W02-02R-C-001:discovery-bootstrap-v1
complex_id=<CX-ID>
test_id=<TEST-ID>
replicates=4096
```

Encoding:

```text
UTF-8 without BOM
LF after every line including final line
```

Fingerprint:

```text
SHA-256(payload)
```

Seed:

```text
unsigned integer represented by first 16 hex characters
```

RNG:

```text
numpy.random.PCG64
```

---

## Future C-002 bootstrap seed rule

This is frozen as pre-registration metadata only.

No C-002 calculation is authorized.

Payload:

```text
stage02r_c002_bootstrap_seed_v1
master=CEF-Dy:T-02R-05:W02-02R-C-002:holdout-bootstrap-v1
confirmatory_spec_sha256=<FINAL-C001-CONFIRMATORY-SPEC-SHA256>
hypothesis_id=<HYPOTHESIS-ID>
replicates=8192
```

Same UTF-8/LF/SHA/first-16-hex/PCG64 rule.

---

## Plus-one p-value convention

For B bootstrap replicates:

```math
p= \frac{ 1+\#\{b:T_b\ge T_{\rm obs}\} }{ B+1 }.
```

Mandatory for both:

```text
C-001 development tests
future C-002 confirmatory tests
```

No zero p-values are permitted.

---

## Bootstrap fit failures

For a bootstrap replicate where either required nested model cannot be validly fitted:

```text
T_b = +infinity
```

for p-value counting.

This is conservative.

Calculate:

```math
f_{\rm fail} = N_{\rm failed}/B.
```

If:

```math
f_{\rm fail}>0.01,
```

the bootstrap test is:

```text
numerical_failure
```

and its p-value is not used for scientific promotion.

### C-001 development consequence

Background child test failure:

```text
retain parent background model
```

Component split failure:

```text
retain parent K
stop deeper component development
```

---

## Future C-002 numerical-failure rule

Frozen now only as part of hypothesis pre-registration:

A pre-registered C-002 hypothesis that cannot be numerically evaluated remains in the global testing family and receives:

```yaml
raw_p_value: 1.0
test_status: numerical_failure
```

It cannot be declared confirmed.

Family size MUST NOT shrink after holdout access.

---

## Exact Holm procedure

Future C-002 global family contains every evaluable pre-registered:

```text
presence hypothesis
component-split hypothesis
```

after metadata-only removal of complexes with zero eligible holdout scans.

This metadata-only family is frozen before any holdout detector access and
cannot shrink afterward.

Let total number be `m`.

Sort by:

```text
raw p ascending
then hypothesis_id lexical ascending
```

For rank `i=1...m`:

reject while:

```math
p_{(i)} \le \frac{0.05}{m-i+1}.
```

At the first failure:

```text
stop rejection
all remaining hypotheses not rejected
```

Adjusted p-values:

```math
p^{adj}_{(i)} = \min \left[ 1, \max_{j\le i} \left\{ (m-j+1)p_{(j)} \right\} \right].
```

Map adjusted values back to hypothesis IDs.

Scientific split decision additionally requires:

```text
Holm rejection
AND
all parent hypotheses scientifically passed.
```

Thus global FWER and hierarchy are separate gates.

---

# TESTS

Exactly 18 mandatory tests are active.

## C001-T01 — Canonical input integrity

Verify baseline `31b16b22fc38fc51c063dc1d2908fcb630b8d3cf`,
all A/B checkpoint and artifact identities, and every required input.

## C001-T02 — Catalogue immutability

Before and after C-001,
`blind_feature_catalogue.yaml` MUST have SHA-256
`f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5`.

## C001-T03 — Holdout detector blindness

Instrument the reader. Verify allowlist-only projection before
materialization, zero holdout detector/`det_err` materialization, complete
field-access logging, hard failure before materialization on a forbidden
request, and absence of generic full-table holdout loading.

## C001-T04 — EV-006 isolation

Verify scan `104062` is used only as `resolution_evidence`, never for BF
remapping, historical targets, normalization or spectral-component hypotheses.

## C001-T05 — Resolution decision-tree and granularity

Synthetic fixtures verify direct applicable empirical -> empirical; otherwise
validated calculated -> calculated; otherwise `resolution_not_established`.
Verify scan×complex identity, independently applicable members for every
resolution class, unavailable calculated branch without a complete pre-locked
implementation, and disabled empirical interpolation.

## C001-T06 — EV-006 physical basis, suitability and applicability

Verify reproduction alone is insufficient; independent physical basis is
mandatory; numerical/geometry and <=10% width-stability gates are applied;
no second-component gate exists; every resolution-critical field is verified;
and domain-wide applicability is decided from metadata before detector access.
A failed domain point or missing critical field must yield
`direct_empirical_applicability=not_established`.

## C001-T07 — Discovery sample and fit-window determinism

Verify `discovery_model_scan_set` equals all and only scans satisfying the
frozen criteria. Input ordering and detector-value permutation cannot alter
membership, its SHA-256, `delta_E_ref`, selected margin or fit window.

## C001-T08 — Background selection

Synthetic B0/B1/B2 fixtures verify 4096 replicates, alpha 0.05, parent-gated
sequential selection, parent retention on numerical child failure, and no
AIC/BIC-only promotion.

## C001-T09 — Component hierarchy

Verify 4096 replicates, split-development alpha 0.10, separation of K0->K1
presence from K1->K2... split development, parent gating and BF/geometry caps.

## C001-T10 — Ordered-centroid transform and proximity

Verify exactly K free logits plus one fixed reference, stable-softmax gaps,
strict order and minimum separation, no redundant scale and no post-fit
sorting. Verify `tau_sep=max(0.10 delta_E_ref,1e-6 meV)`, informative-scan
area-bound logic, exact rejection statuses, parent retention and deeper-stop
behavior.

## C001-T11 — Poisson likelihood and inferential bounds

Verify raw counts with exposure-conditioned Poisson likelihood, scan-specific
centroids/widths/areas/backgrounds, no arbitrary scale, unbounded `b0`,
`A_sk in [0,+infinity)`, frozen detector-independent finite bounds, and
detector-derived `r0/A0` used only for starts.

## C001-T12 — Multistart determinism and optimizer adequacy

Verify exact observed 33-start Sobol bank, model-local bootstrap Starts 1–4,
prefixes 4/8/16/33, tie rule and repeatability. For every comparison verify the
64 fixed benchmark replicates, 64/64 valid parent and child 33-start references,
the exact likelihood tolerance/mismatch rules, escalation sequence and frozen
`bootstrap_multistarts_selected`. Any invalid reference must block C-002
freeze.

## C001-T13 — Bootstrap, seeds and p-values

Verify discovery B=4096, future C-002 B=8192, exact payload serialization,
SHA-256 first-16-hex seed, PCG64 and plus-one p-values.

## C001-T14 — Bootstrap failures and KKT convergence

Synthetic fixtures verify failed replicate -> `T*=+infinity`, failure
fraction >0.01 -> `numerical_failure`, conservative parent retention,
finite-difference and active-bound rules, acceptance of valid A=0/Gamma=0
boundary optima, rejection of feasible inward-gradient violations, and
projected-gradient threshold 1e-4.

## C001-T15 — Profile identifiability

Verify 41-point profiles, threshold 3.841458820694124, both in-bound threshold
crossings, the minimum-separation proximity gate, exact rejection statuses and
Hessian warning semantics.

## C001-T16 — Holdout eligibility and coverage

Synthetic 0/1/2+ fixtures yield respectively
`not_covered/none`, `covered/single_scan`, and
`covered/multi_scan`. Detector mutation cannot change eligibility or scope;
scope cannot be described as observed replication.

## C001-T17 — Holm registry and field-access guard

Verify the complete frozen family, lexical tie-break, exact Holm thresholds
and adjusted p-values, alpha 0.05, numerical-failure p=1, fixed family size and
ancestor gating. Re-verify allowlist projection, access log completeness and
hard failure on forbidden fields.

## C001-T18 — Scope, dominant scan and STOP

Verify `f_dominant` only, threshold 0.50, diagnostic/non-gating status, no
leave-one-out bootstrap or p=0.05 crossing rule. Verify no source/config/output
performs F002/F004 mapping, historical comparison, CEF assignment, holdout
spectral fitting, C-002 execution, combined discovery+holdout fitting or
Stage03R/03D inference, and that C-001 stops before holdout detector access.

---


# OUTPUTS

Target:

```text
04_Results/Stage02R/W02-02R-C-001/
```

Required artifacts:

```text
resolution_evidence.yaml
resolution_applicability.csv
resolution_model.yaml

confirmatory_complexes.yaml
fit_windows.yaml

discovery_model_fits.csv
background_selection.yaml
component_development.yaml
model_identifiability.csv

holdout_metadata_eligibility.csv
holdout_coverage_summary.yaml
holdout_field_access_log.csv

instrument_block_assessment.yaml

confirmatory_hypotheses.yaml
confirmatory_model_spec.yaml

numerical_stability_diagnostics.yaml

provenance_manifest.yaml
test_report.yaml
```

Source:

```text
scripts/stage02r/c001_confirmatory_model_preparation.py
```

Configuration:

```text
scripts/stage02r/c001_confirmatory_config.yaml
```

Checkpoint:

```text
02_Work_Checkpoints/W02-02R-C-001.md
```

---

## `confirmatory_hypotheses.yaml`

Must contain, for every future C-002 hypothesis:

```yaml
hypothesis_id:
complex_id:

hypothesis_type:
  presence | split

parent_model_id:
child_model_id:
parent_hypothesis_id:

fit_window_meV:

eligible_holdout_scan_record_ids:
holdout_eligible_scan_count:
holdout_coverage_scope:

background_model_id:
line_shape_model_id:
resolution_model_id:
resolution_status:
resolution_applicability_basis:

parameter_bounds:

future_bootstrap_replicates: 8192
future_seed_rule: stage02r_c002_bootstrap_seed_v1
raw_p_value_rule: plus_one
global_multiple_testing: holm
global_alpha: 0.05

status:
  preregistered | not_covered
```

No detector-derived holdout quantity is permitted.

---

## `confirmatory_model_spec.yaml`

Must be immutable input for future C-002 and record:

```text
complex definitions
fit windows
resolution branch
background family
line-shape family
maximum K
ordered-centroid rule
parameter bounds
optimizer configuration
bootstrap_multistarts_selected
discovery_model_scan_set and SHA256
future C002 bootstrap constants
exact Holm algorithm
holdout eligible scan IDs
holdout_coverage_scope
dominant-scan diagnostic rule
nondetection semantics
scope prohibitions
```

It must have its own full SHA-256.

That SHA is the future C-002 seed payload input.

---

## `instrument_block_assessment.yaml`

C-001 may report:

```yaml
shared_normalization_promotion:
  status: not_proposed | proposed_for_review

proposed_instrument_block_id:
member_scan_record_ids:
metadata_basis:
missing_critical_metadata:
limitations:
```

It MUST NOT activate a shared normalization parameter.

Default state:

```text
not_proposed
```

unless new metadata evidence meets a separately documented physical rationale.

---

# PASS\_CRITERIA

C-001 passes only if:

1. canonical baseline and all input identities pass;
2. the B-001 catalogue remains byte-identical at the frozen SHA-256;
3. discovery detector access is limited to the frozen eligible scan set;
4. holdout reads use allowlist projection before materialization;
5. holdout detector/`det_err` accesses and materializations equal zero;
6. the holdout field-access log is complete and denylist requests hard-fail;
7. no historical BF/CEF mapping, F002/F004 comparison or assignment is made;
8. EV-006 is isolated as resolution evidence and reproduced before any use;
9. scan 104062 has independent physical-basis evidence before calibration status;
10. probe suitability uses the frozen grid/exposure/QC and <=10% stability gates;
11. no second-component suitability gate is introduced for scan 104062;
12. empirical applicability is scan×complex and metadata-decided over the full
    allowed centroid domain before detector access;
13. every critical empirical-resolution field is verified;
14. empirical interpolation is disabled;
15. direct empirical resolution precedes validated calculated resolution;
16. calculated resolution uses one independently pre-locked validated
    implementation and cannot be selected by agreement with spectra;
17. `resolution_not_established` remains an acceptable outcome;
18. intrinsic-linewidth/resolution-limited claims are absent when resolution is
    not established;
19. `discovery_model_scan_set` and its SHA-256 follow the frozen rules;
20. fit windows follow the frozen detector-independent grid rule;
21. cross-scan centroids, widths, areas and backgrounds are scan-specific by
    default;
22. background selection is B0->B1->B2, B=4096, alpha=0.05 and parent-gated;
23. K0->K1 presence is separated from K1->K2... split development;
24. split development uses B=4096, alpha=0.10 and parent gating;
25. centroid coordinates are exactly K free logits plus one fixed reference;
26. no post-fit sorting is used;
27. the exact minimum-separation informative-scan/proximity gate is applied;
28. inferential bounds are detector-independent, with unbounded `b0` and no
    finite upper bound on `A_sk`;
29. all fit validity uses the frozen projected-gradient/KKT rule;
30. observed and bootstrap multistart banks follow the exact Sobol and
    model-local rules;
31. every optimizer benchmark has valid 33-start parent and child references
    on all 64 replicates;
32. a candidate level passes the frozen likelihood/mismatch rules and
    `bootstrap_multistarts_selected` is frozen;
33. discovery tests use B=4096 and future C-002 is frozen at B=8192;
34. exact SHA-derived PCG64 seeds and plus-one p-values are used;
35. bootstrap failures are handled conservatively;
36. holdout eligibility is metadata-only and uses
    `holdout_coverage_scope: none|single_scan|multi_scan`;
37. coverage scope is not described as observed replication;
38. the dominant-scan diagnostic uses only `f_dominant>0.50`, is non-gating,
    and has no leave-one-out p-values;
39. primary intensities remain scan-level fitted areas;
40. no arbitrary scan scale or cross-mode normalization is introduced;
41. the complete future C-002 Holm family is frozen before detector access,
    numerical failures receive p=1, and hierarchy remains a separate gate;
42. C001-T01...T18 all PASS;
43. C-001 stops before holdout detector access and before C-002 execution.

---

# STOP\_CONDITION

C-001 STOP is reached only after the following are frozen:

```text
resolution decision per scan_record_id × complex_id or frozen class
fit windows
background family
line-shape family
maximum preregistered K

parameter bounds
optimizer/multistart rules
bootstrap_multistarts_selected

holdout metadata eligibility
holdout_coverage_scope
holdout field-access log

future C002 hypothesis registry
future C002 bootstrap rule
future C002 Holm family

confirmatory_model_spec SHA256
```

The 33-start reference must be valid for all 64 parent and all 64 child fits
and an adequacy level must pass. Otherwise C-001 may complete diagnostically
but stops with `blocked_for_C002_freeze`.

Then:

```text
W02-02R-C-001
        ↓
STOP
        ↓
02 - TAIPAN Data Reduction
scientific / methodological review
        ↓
Project Control scientific review
        ↓
separate C-002 freeze boundary
```

C-001 MUST NOT:

```text
read holdout detector values

execute C-002

calculate C-002 holdout p-values

fit discovery + holdout jointly

modify B-001 catalogue

perform historical F002/F004 comparison

perform historical target-energy tests

assign CEF transitions

execute Stage 03R or Stage 03D
```

---

# FAILURE\_MODES

## Resolution evidence not sufficient

```text
resolution_status = resolution_not_established
```

C-001 may still PASS.

Physical linewidth claims remain forbidden.

An unresolved independent physical basis leaves scan `104062` as
`empirical_effective_width_evidence` regardless of fit stability.

---

## EV-006 reproduction fails

Do not repair the historical value.

Record:

```text
EV006_reproduction_status: failed
```

Proceed to calculated-resolution branch.

---

## Resolution-calculation metadata incomplete

Do not infer missing values.

An unavailable, incomplete or not-yet-validated implementation lock makes the
calculated branch unavailable; no alternative implementation may be selected
using agreement with observed spectra.

Result:

```text
resolution_not_established
```

---

## Insufficient discovery fit-window coverage

For that complex:

```text
complex_model_status:
  insufficient_discovery_window_coverage
```

No C-002 spectral hypothesis is registered.

Return for scientific review.

---

## No eligible holdout scans

```text
coverage_status: not_covered
```

This is not a numerical failure.

It is not a non-detection.

---

## One eligible holdout scan

```text
coverage_status: covered
holdout_coverage_scope: single_scan
```

Future confirmation remains possible but cannot be labelled replicated within the отложенная выборка.

---

## Background child numerical failure

Retain parent background.

Record limitation.

Do not try an unregistered replacement family.

---

## Component child numerical failure

Retain parent K.

Stop deeper K development.

---

## K1 itself fails numerically

If holdout coverage is nonzero:

```text
complex_status =
confirmatory_model_not_preparable
```

C-001 cannot be declared fully freeze-ready for C-002.

---

## Identifiability failure

If a child model passes development LRT but fails centroid profile identifiability:

```text
retain parent K
component_development_status:
  rejected_nonidentifiable
```

If an adjacent split has no informative scan, use
`rejected_no_informative_scan_for_split`; if all informative scans remain
within the frozen proximity tolerance, use
`rejected_minimum_separation_proximity`. Both retain parent K and stop deeper
development.

---

## Optimizer adequacy failure

If any 33-start parent or child reference is invalid on the 64-replicate
benchmark, or no candidate through 33 starts passes, record
`optimizer_adequacy_status: failed`. C-001 may finish diagnostically but must
stop `blocked_for_C002_freeze`; no replicate may be removed or replaced.

---

## B-001 excluded scan

`SCAN-02R-7acd4c14a0007418` remains excluded from primary C-001 fitting.

It may be inspected only in a separately labelled numerical-stability diagnostic.

That diagnostic cannot change:

```text
B-001 catalogue
C-001 component hierarchy
C-002 hypothesis registry
```

without a separate Project Control amendment.

---

# PROPOSED\_WORK-LOCAL\_EXECUTION\_SPLIT

C-001 is one scientific Work job, but deterministic heavy computation should be split operationally.

## Work — orchestration / implementation

Use Work for:

```text
canonical preflight
input identity checks
holdout-access guard

resolution decision-tree implementation

fit-window construction
model/hypothesis registry construction

code/config generation
small synthetic tests
output-schema checks
```

No heavy bootstrap loops by default.

---

## Local terminal — heavy deterministic computation

Use local execution for:

```text
EV-006 reproduction fit

resolution calculations if admissible

4096-replicate background tests
4096-replicate component-development tests

multistart spectral fits
profile-likelihood scans
Hessian/identifiability diagnostics
```

Local execution MUST receive frozen:

```text
source SHA256
config SHA256
canonical HEAD
discovery scan IDs
complex IDs
```

and MUST NOT receive holdout detector values.

Parallelization may occur only across:

```text
complex
bootstrap replicate blocks
profile points
```

with deterministic seed/result identities.

Atomic result writes required.

---

## Work — final compact verification

Return to Work for:

```text
artifact identity verification

hypothesis-registry audit
holdout-access audit
B-001 catalogue byte check

C001-T01...T18 final verification
provenance/checkpoint generation
```

Then STOP.

---

```yaml
FREEZE_READINESS: READY

W02-02R-C-001:
  execution_authorized: false
  holdout_detector_access_authorized: false
  C002_execution_prepared: false
  C002_execution_authorized: false
```
