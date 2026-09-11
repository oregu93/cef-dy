# Stage03R Inference Specification v1.0

```yaml
SPECIFICATION_ID: STAGE03R-INFERENCE-SPEC
SPECIFICATION_VERSION: "1.0"
SPECIFICATION_STATUS: frozen
updated: 2026-09-11

parent_design_review:
  id: STAGE03R-DR-001
  decision: A

source_draft:
  id: STAGE03R-INFERENCE-SPEC-DRAFT-001
  version: "0.1-draft"

freeze_review:
  id: STAGE03R-SPEC-REVIEW-001
  decision: A

canonical_repository: oregu93/cef-dy
canonical_branch: main
canonical_baseline: beaacdc54cad3c3aaa4ec76ceca4199fb1b8db99

stage_role:
  - assignment-aware
  - interval-aware
  - identifiability-first
  - multi-model CEF compatibility analysis

execution_authorization:
  Stage03R_execution_authorized: false
  W03_authorized: false
  Stage03D_resumed: false
  production_CEF_fit_authorized: false
  raw_detector_access_authorized: false
  holdout_reanalysis_authorized: false
```

---

# GOAL

Stage03R должен определить, какие свойства эффективного CEF-гамильтониана Dy`^{3+}` в DyFeO`_3` действительно ограничиваются текущим экспериментальным evidence layer и какие остаются неидентифицируемыми.

Stage03R **не является production CEF fitting stage**.

Его primary scientific outputs:

```text
experimental ↔ model compatibility
assignment ambiguity
multiplicity ambiguity
structural identifiability
practical identifiability
model discrimination capability
derived-observable stability
requirements for additional measurements
```

Stage03R должен допускать научно успешное завершение без получения единственного или вообще какого-либо fitted набора `B_l^m`.

Главный принцип:

```math
\boxed{ \text{optimizer solution} \neq \text{identified physical model} }
```

и

```math
\boxed{ \text{experimental support region} \neq \text{measured CEF transition energy}. }
```

---

# INPUTS

## I1. Canonical governance/state inputs

Обязательные logical inputs:

```text
00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml
00_Project/MODEL_REGISTER.yaml
00_Project/EVIDENCE_REGISTER.yaml
00_Project/RESULT_REGISTER.yaml
03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md
```

Current Project Control фиксирует:

```text
M02R: completed_with_limitations
M03R: planned
M03D: suspended
production Stage03D: not authorized
exchange modelling: deferred
```

## I2. Accepted Stage02R inputs

Primary evidence package:

```text
04_Results/Stage02R/W02-02R-B-001/blind_feature_catalogue.yaml
04_Results/Stage02R/W02-02R-B-001/SCIENTIFIC_REVIEW.md
```

Canonical B-001 catalogue identity:

```yaml
sha256: f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5
feature_count: 8
feature_namespace: BF
```

Relevant C-001 material:

```text
03_Protocols/STAGE02R_T02R05_C001_V1_1_CONFIRMATORY_MODEL_PREPARATION_SPEC.md
04_Results/Stage02R/W02-02R-C-001-v1.1/
```

C-001 complex definitions may be used for bookkeeping but not promoted to physical multiplicity. Its accepted result leaves reliable centroid/FWHM unresolved and promotes no `K\ge2` decomposition.

C002 may enter Stage03R only as:

```yaml
role: terminal_numerical_failure_context
physical_evidence_role: none
```

Its `raw_p_value: 1.0` under `numerical_failure` must not be interpreted as an experimental non-detection.

---

# EPISTEMIC\_INPUT\_CONTRACT

## EIC-1. BF namespace

Active Stage03R experimental namespace:

```text
BF-001
BF-002
BF-003
BF-004
BF-005
BF-006
BF-007
BF-008
```

Each BF is normatively defined as:

```yaml
entity_class: algorithmic_reproducibility_structure
scientific_role: SUPPORT_REGION
physical_excitation_identity: not_established
CEF_assignment: not_established
centroid_measurement: false
physical_linewidth_measurement: false
```

Exact frozen support regions:

| IDsupport region, meV |                   |
| --------------------- | ----------------- |
| BF-001                | 2.49870–3.49865   |
| BF-002                | 2.49900–5.49850   |
| BF-003                | 4.99860–6.99865   |
| BF-004                | 17.49800–18.49815 |
| BF-005                | 17.49830–20.49835 |
| BF-006                | 40.49835–44.49830 |
| BF-007                | 43.49685–46.49775 |
| BF-008                | 45.49645–46.49710 |

The intervals are discovery-support structures and explicitly are **not confidence intervals of physical peak centroids**.

The machine field

```text
discovery_location_not_confirmatory_centroid
```

must retain exactly that semantic meaning and must not be renamed or imported as:

```text
energy
peak_energy
CEF_energy
centroid
transition_energy
```

---

## EIC-2. Complex namespace

Stage03R may use:

```yaml
CX-01:
  source_bf_ids: [BF-001, BF-002, BF-003]
  support_union_meV: [2.49870, 6.99865]

CX-02:
  source_bf_ids: [BF-004, BF-005]
  support_union_meV: [17.49800, 20.49835]

CX-03:
  source_bf_ids: [BF-006, BF-007, BF-008]
  support_union_meV: [40.49835, 46.49775]
```

These are bookkeeping groups arising from overlapping BF support regions.

Normative semantics:

```yaml
physical_component_count: unresolved
CEF_transition_count: unresolved
single_excitation_claim: forbidden
multiple_excitation_claim: forbidden
```

C-001's historical `maximum_BF_defined_K` values are model-development limits, not measurements of physical multiplicity.

---

## EIC-3. Legacy namespace prohibition

The following labels are prohibited as **active Stage03R observation IDs**:

```text
F002
F004
```

Allowed use:

```yaml
historical_provenance: allowed
legacy_analysis_description: allowed
active_observation_namespace: forbidden
automatic_BF_mapping: forbidden
```

No mapping

```math
F002/F004 \leftrightarrow BF-*
```

is implied by similar energy regions.

The current project state explicitly separates the legacy and BF namespaces.

---

# OBSERVATION\_ROLE\_TAXONOMY

Canonical Stage03R machine roles:

```text
SUPPORT_REGION
CONFIRMATORY_ENERGY
RELATIVE_INTENSITY
CENSORED_INTENSITY
Q_DEPENDENCE
TEMPERATURE_DEPENDENCE
INDEPENDENT_VALIDATION
```

Every admitted observable must additionally carry:

```yaml
observation_id:
role:
availability_status:
origin_type:
source_artifact:
uncertainty_semantics:
assignment_status:
likelihood_status:
```

## OR-1. SUPPORT\_REGION

```yaml
availability_status: available
current_source: Stage02R_B001
probability_density_defined: false
centroid_defined: false
```

Permitted Stage03R operations:

```text
compatibility test
set intersection
assignment enumeration
coverage diagnostics
```

Not permitted:

```math
E_{\rm BF} = \frac{E_{\min}+E_{\max}}{2}
```

as an invented energy measurement.

---

## OR-2. CONFIRMATORY\_ENERGY

Current baseline:

```yaml
availability_status: not_automatically_populated
```

Activation requires explicit evidence contract defining at least:

```text
physical/phenomenological component identity
centroid
statistical uncertainty
model/background uncertainty
energy-scale systematic uncertainty or explicit unknown status
source artifact
assignment independence
```

Only after activation may a Gaussian or alternative energy likelihood be designed.

---

## OR-3. RELATIVE\_INTENSITY

Current baseline:

```yaml
availability_status: not_automatically_populated
```

Activation requires:

```text
integrated-area definition
uncertainty semantics
Q/T association
instrument comparability evidence
normalization grouping decision
component multiplicity treatment
```

---

## OR-4. CENSORED\_INTENSITY

Current baseline:

```yaml
availability_status: not_automatically_populated
```

Activation requires distinction among:

```text
detected
censored
not_covered
excluded
```

as required by the canonical data contract.

A missing BF is **not** automatically a censored zero-intensity measurement.

---

## OR-5. Q\_DEPENDENCE

Current baseline:

```yaml
availability_status: not_automatically_populated
```

Activation requires evidence that several observations correspond to the same physical component or a properly latent component family.

Geometry metadata alone are insufficient.

---

## OR-6. TEMPERATURE\_DEPENDENCE

Same rule:

```yaml
availability_status: not_automatically_populated
```

Temperature metadata are not equivalent to an established cross-temperature transition correspondence.

---

## OR-7. INDEPENDENT\_VALIDATION

Examples:

```text
directional M(H)
χ(T)
heat capacity
independent INS experiment
```

An observable ceases to be independent validation if it was used to choose or fit the same model parameters unless an explicitly separated training/validation design exists.

---

# ASSIGNMENT\_STATE\_ARCHITECTURE

Four conceptually distinct latent states must be represented independently.

## A1. Complex multiplicity

For complex `c`:

```math
K_c\in\mathcal K_c.
```

Example:

```yaml
CX-01:
  admissible_multiplicity_family: unresolved

CX-02:
  admissible_multiplicity_family: unresolved

CX-03:
  admissible_multiplicity_family: unresolved
```

The specification does not yet freeze numerical allowed sets such as `[1,2,3]` as physical claims.

---

## A2. Physical-component identity

If a multiplicity hypothesis creates components

```math
X_{c1},X_{c2},\ldots,
```

these are phenomenological candidate physical components, not yet CEF transitions.

---

## A3. CEF/non-CEF classification

For every component:

```text
UNCLASSIFIED
CEF_CANDIDATE
NON_CEF_CANDIDATE
MIXED_OR_UNRESOLVED
```

`CEF_CANDIDATE` does not mean established CEF assignment.

---

## A4. CEF transition assignment

For a model with doublets `n`:

```math
X_{ck}\leftrightarrow (i\rightarrow j)
```

is a separate assignment hypothesis.

No automatic ordering rule such as

```text
lowest BF → first excited doublet
second BF → second excited doublet
...
```

is permitted.

---

## Assignment-family representation

A Stage03R assignment family should contain:

```yaml
assignment_family_id:
complex_multiplicities:
physical_components:
component_classifications:
cef_transition_mapping:
source_observations:
status:
```

Allowed status:

```text
ADMISSIBLE
INCOMPATIBLE
AMBIGUOUS
NOT_TESTABLE
```

No prior probabilities over families may be introduced unless independently scientifically justified and explicitly reviewed.

Default Stage03R treatment:

```text
parallel explicit assignment families
```

not Bayesian averaging.

---

# MODEL\_HIERARCHY

Every model record in Stage03R must distinguish:

```text
model_role
parameterization_status
activation_condition
comparison_target
```

## MH-0 — MOD-PCM-FORMAL

```yaml
model_id: MOD-PCM-FORMAL
model_role: fixed_structural_falsification_baseline
parameterization:
  fitted_parameters: 0
activation_condition: always_available_if_structure_and_conventions_are_valid
comparison_target:
  - observed support topology
  - predicted energy-scale pattern
  - predicted transition fingerprint
```

Purpose:

> Test what the adopted structural electrostatic model predicts before introducing effective fitted deformation.

The canonical MODEL\_REGISTER already defines it as a no-fit structural baseline.

---

## MH-1 — MOD-PCM-M0

```yaml
model_role: one_parameter_structural_scale_test
parameterization:
  active_parameters: [s]
activation_condition:
  - convention_contract_pass
  - structure_input_valid
comparison_target:
  - MOD-PCM-FORMAL
  - experimental_support_compatibility
```

For fixed structure:

```math
H_{\rm M0}(s)=sH_{\rm formal}.
```

Scientific role:

```text
scale/fingerprint compatibility test
```

not free wavefunction inference.

---

## MH-2 — MOD-PCM-M1

```yaml
model_role: minimally_structured_ligand_deformation_test
parameterization:
  conceptual_parameters: [s_O1, s_O2]
  derived: [s_cat]
parameterization_status: retained_but_inference_not_activated
activation_condition:
  - M0 evaluated
  - observation layer contains eigenvector-sensitive information
    OR
  - explicit scientific justification shows energy information can discriminate M1
comparison_target:
  - MOD-PCM-M0
```

Nesting relation remains conceptually:

```math
s_{\rm O1}=s_{\rm O2}\Rightarrow M1=M0.
```

But the old Stage03D likelihood and bounds are not inherited.

---

## MH-3 — low-dimensional structural/superposition candidate

```yaml
model_role: flexible_structural_intermediate
parameterization_status: not_activated
activation_condition:
  - separate scientific design review
  - explicit physical parameterization
  - dimensionality justified by available independent information
comparison_target:
  - M1
  - CS15-compatible ensemble
```

Forbidden until activation:

```text
free parameter list
bounds
priors
optimizer configuration
production likelihood
```

---

## MH-4 — MOD-CEF-CS15

```yaml
model_role: general_phenomenological_effective_hamiltonian
parameterization:
  count: 15
  family: B_lm
activation_condition:
  - convention_and_gauge_contract_frozen
  - identifiability protocol implemented
comparison_target:
  - experimental compatibility
  - structural-model submanifolds
primary_inferential_object:
  compatible_ensemble_or_equivalence_family
```

One best-fit vector is never the default scientific result.

---

## MH-5 — MOD-CEF-EXCHANGE

```yaml
model_role: later_magnetic_extension
parameterization_status: not_activated
activation_condition: exchange_trigger_passed
comparison_target:
  - corresponding CEF-only baseline
```

No exchange parameter form, dimension or bounds are frozen here.

---

# CONVENTION\_AND\_GAUGE\_CONTRACT

No numerical CS15 inference may begin until the following fields are explicitly frozen.

## CG-1. Operator convention

```text
Stevens operator definition
normalization convention
sign convention
allowed m values
```

## CG-2. Units

Canonical unit for all `B_l^m` must be explicitly frozen.

No implicit software-native unit conversion.

## CG-3. Crystallographic setting

Exactly one active setting must be defined for every calculation:

```text
Pnma
or
Pbnm
```

plus explicit transformation if both appear in source data.

## CG-4. Global frame

Freeze:

```math
(\hat x_g,\hat y_g,\hat z_g)
```

relative to crystallographic axes.

## CG-5. Dy local frame

Freeze:

```math
R_{\mathrm{local}\leftarrow\mathrm{global}}
```

as an explicit orthogonal matrix and state active/passive convention.

## CG-6. Allowed equivalence transformations

Enumerate transformations that represent the same physical Hamiltonian but change raw `B_l^m` coordinates.

Equivalent solutions must not be counted as physically independent minima.

## CG-7. Canonical parameter ordering

Freeze exact machine ordering, for example only after convention review:

```text
B20
B2n2
B22
...
```

No direct-PCF label may be renamed into this basis without an explicit transformation.

## CG-8. Cross-code checks

At minimum, for reference Hamiltonians compare:

```text
Hamiltonian matrix
ordered eigenvalues
doublet projectors
transition tensors
g-tensor invariants
```

Energy-only agreement is insufficient.

## CG-9. Kramers gauge

Within Kramers doublet `a`, raw states

```math
|\psi_{a1}\rangle,\ |\psi_{a2}\rangle
```

are not unique under unitary rotation:

```math
\begin{pmatrix} |\psi'_{a1}\rangle\\ |\psi'_{a2}\rangle \end{pmatrix} = U_a \begin{pmatrix} |\psi_{a1}\rangle\\ |\psi_{a2}\rangle \end{pmatrix}.
```

Therefore raw eigenvector coefficients must not be treated as uniquely physical.

Preferred output objects:

```text
ordered energy gaps
doublet projectors
transition tensors
projected neutron strengths
principal g values
stable spectral/invariant quantities
```

---

# IDENTIFIABILITY\_PROTOCOL

## IP-1. General requirement

Every activated parameterized model must distinguish:

```text
structural identifiability
practical identifiability
numerical optimizer stability
```

These are not synonyms.

---

## IP-2. Local sensitivity

For observables `f(\theta)`, calculate where meaningful:

```math
J_{ij} = \frac{\partial f_i}{\partial\theta_j}.
```

The derivative may be analytic, automatic or carefully controlled numerical.

---

## IP-3. SVD/rank

For appropriately scaled Jacobian:

```math
J=U\Sigma V^\top.
```

Report:

```text
singular values
effective numerical rank
near-null parameter directions
scaling convention
rank threshold
```

The exact numerical rank threshold must later be frozen by implementation review; it is not set in this draft.

---

## IP-4. Profiles

Where a calibrated objective exists:

```math
Q_{\rm prof}(\theta_j) = \min_{\theta_{-j},\eta}Q(\theta_j,\theta_{-j},\eta).
```

Report:

```text
bounded profile
open profile
flat profile
multimodal profile
disconnected accepted regions
```

No Hessian covariance alone may establish identifiability.

---

## IP-5. Multimodality

Search must be capable of distinguishing:

```text
one basin
multiple numerical starts in one basin
physically equivalent convention-related minima
genuinely distinct physical solution families
```

---

## IP-6. Boundary diagnostics

If parameter bounds are eventually introduced:

```text
optimum_at_boundary
profile_hits_boundary
result_sensitive_to_boundary
```

must be explicitly distinguished.

A boundary-truncated interval is not evidence of identification.

---

## IP-7. Correlation structure

Required diagnostics where defined:

```text
profile correlations
local sensitivity correlations
principal poorly constrained combinations
```

Prefer reporting identifiable combinations such as

```math
c_1B_2^0+c_2B_4^2+\cdots
```

when individual coefficients cannot be separately resolved.

---

## IP-8. Derived-observable stability

For an accepted parameter family `\Theta_A`, examine spread of:

```math
E_n,\quad P_n,\quad T_{\alpha\beta}^{if},\quad g_i,\quad I(Q).
```

It is explicitly permitted that:

```text
B_lm: nonidentifiable
g_principal: identifiable
```

or analogous combinations.

---

## IP-9. Assignment-family sensitivity

Every claimed constraint must be tested across admissible assignment families.

If the conclusion changes materially under another currently admissible assignment:

```text
ASSIGNMENT_AMBIGUOUS
```

must supersede a stronger parameter claim.

---

## IP-10. Convention/frame equivalence

Equivalent coordinate representations must collapse into the same physical equivalence class before counting multiple solutions.

---

## IP-11. Optimizer prohibition

Forbidden inference:

```text
optimizer converged
therefore
parameter is identified
```

Optimizer convergence establishes only a numerical property of the chosen objective.

---

## IP-12. CS15 default

For `MOD-CEF-CS15`:

```math
\boxed{ \text{default result} = \text{compatible ensemble/equivalence family} }
```

not

```math
\boxed{ \hat{\mathbf B} = \text{one preferred 15-vector}. }
```

---

# STATISTICAL\_ARCHITECTURE

## SA-1. Two-layer design

```yaml
Stage03R-current:
  mode: compatibility_and_identifiability
  calibrated_parameter_inference: false

Stage03R-likelihood-enabled:
  mode: calibrated_inference
  activation_condition:
    explicit_confirmatory_observation_contract_passed
```

---

## SA-2. Current support-region semantics

For predicted transition energy `E_t(\theta)` and BF region

```math
I_j=[L_j,U_j],
```

Stage03R-current may determine:

```text
compatible
incompatible
assignment_ambiguous
```

Example compatibility primitive:

```math
E_t(\theta)\in I_j.
```

But this **does not define**

```math
p(E_t|BF_j)
```

and no uniform, Gaussian, triangular or other artificial probability density may be assigned across `I_j`.

---

## SA-3. Gaussian energy likelihood

Status:

```yaml
frozen_now: false
```

May only be introduced after a `CONFIRMATORY_ENERGY` observation contract exists.

---

## SA-4. Censored likelihood

Status:

```yaml
frozen_now: false
```

Requires calibrated upper-limit and sensitivity semantics.

---

## SA-5. Absolute intensity likelihood

Status:

```yaml
frozen_now: false
```

Requires appropriate normalization/calibration evidence.

---

## SA-6. Direct count-level likelihood

Status:

```yaml
frozen_now: false
```

Would require separately authorized detector-level reprocessing and is outside present Stage03R input permissions.

---

## SA-7. Latent assignment treatment

Current default:

```text
explicit parallel assignment families
```

not probabilistic mixture weighting.

Later possible methods:

```text
profile over discrete assignments
model averaging
Bayesian marginalization
```

require separate statistical justification.

---

# MODEL\_COMPARISON\_DECISION\_TREE

```text
START
  |
  +-- Are models evaluated against the same calibrated likelihood?
  |      |
  |      +-- NO --> compatibility / predictive comparison only
  |      |
  |      +-- YES
  |           |
  |           +-- Nested?
  |           |     |
  |           |     +-- NO --> predictive performance,
  |           |     |          carefully justified information criteria,
  |           |     |          independent validation
  |           |     |
  |           |     +-- YES
  |           |          |
  |           |          +-- Regular identifiable interior case?
  |           |                |
  |           |                +-- YES --> LRT candidate
  |           |                |
  |           |                +-- NO --> calibrated bootstrap
  |           |                           or other justified calibration
  |           |
  |           +-- Assignment uncertain?
  |                 |
  |                 +-- YES --> parallel assignment families first
  |
  +-- Continuous ambiguity?
  |      |
  |      +-- YES --> profiles + accepted ensemble
  |
  +-- Independent observable available?
         |
         +-- YES --> predictive validation
```

## MC-1. LRT

Permitted only for regular nested models with common likelihood and identifiable nuisance structure.

## MC-2. Bootstrap calibration

Preferred when nested comparison has:

```text
boundary effects
nonstandard null
latent/discrete structure
nonregular asymptotics
```

provided a valid generative observation model exists.

## MC-3. AIC/BIC

Secondary only.

Conditions:

```text
well-defined common likelihood
defensible effective sample
comparable fitted data
regular-enough parameter interpretation
```

Not a universal Stage03R ranking mechanism.

## MC-4. Assignment uncertainty

Never collapse model preference across different hidden assignments without reporting assignment sensitivity.

## MC-5. Independent prediction

Strongest model discrimination should preferentially use observables not involved in model construction.

---

# NORMALIZATION\_GATE

No nuisance normalization model is active by default.

A-003 established two conditionally supported same-control-mode compatibility groups but explicitly did **not** establish numerical normalization or complete physical compatibility.

## NG-0. No shared normalization

Default Stage03R-current.

Applicable to support-region compatibility because it does not require intensity amplitudes.

---

## NG-1. One universal TAIPAN scale

Activation requires evidence that all admitted observations share sufficiently equivalent:

```text
count-control semantics
detector/monitor response
attenuation/filter state
relevant TAS configuration
sample illumination
normalization chain
```

Current status:

```text
NOT_AUTHORIZED_BY_EVIDENCE
```

---

## NG-2. Shared scale by group/block

Activation requires:

```yaml
group_definition:
  based_on: instrument_and_physical_evidence
  not_based_on: spectral_similarity

within_group:
  relative_intensity_comparability: justified

between_groups:
  scale_relation: either_known_or_profiled
```

Historical `instrument_block_id` alone is insufficient unless explicitly re-reviewed for the new observation contract.

---

## NG-3. One scale per scan

This structure may only be used if:

1. absolute scan amplitudes genuinely cannot be related;
2. the scientific question does not rely on between-scan relative intensities;
3. loss of identifiability is explicitly acknowledged.

It must never be adopted merely because it improves fit residuals.

---

## NG-4. Hierarchical normalization

A partial-pooling architecture may later be considered, but requires an evidential or explicitly reviewed probabilistic model for the dispersion of scales.

No hierarchical prior is frozen here.

---

# EXCHANGE\_TRIGGER

`MOD-CEF-EXCHANGE` remains inactive.

It may be opened only after at least one scientifically interpretable trigger is established.

Candidate triggers:

```text
ET-1 temperature/magnetic-phase dependence inconsistent with static CEF
ET-2 external-field dependence requiring magnetic term
ET-3 resolved Kramers splitting inconsistent with CEF-only time-reversal symmetry
ET-4 systematic reproducible CEF-only failure across multiple observables
ET-5 independent magnetic evidence for effective Dy-Fe field
```

A trigger must satisfy:

```yaml
origin: independent_or_explicitly_separated_evidence
reproducibility: documented
alternative_instrumental_explanation: assessed
CEF_only_failure: demonstrated_where_applicable
```

### Forbidden exchange use

```text
add exchange because residual decreases
```

without exchange-sensitive evidence.

Also forbidden:

```text
exchange = 0 forever
```

as an implicit physical conclusion.

Valid output when CEF-only appears inadequate:

```text
EXCHANGE_TEST_REQUIRED
```

rather than an automatically fitted exchange field.

---

# OUTPUTS

Stage03R implementation must support output classes independent of whether parameters are fitted.

## O1. Input manifest

```text
canonical commit
input artifact identities
BF catalogue checksum
accepted design-review ID
specification version
```

## O2. Epistemic observation table

One row per Stage03R observation entity, including:

```text
observation ID
role
support region/value
uncertainty semantics
availability
assignment status
likelihood eligibility
provenance
```

## O3. Assignment-family registry

```text
family ID
multiplicity hypothesis
component definitions
CEF/non-CEF classifications
transition mappings
compatibility status
```

## O4. Model compatibility results

For every model/family pair:

```text
MODEL_COMPATIBLE
MODEL_FALSIFIED
ASSIGNMENT_AMBIGUOUS
NOT_TESTABLE
```

plus explanation.

## O5. Identifiability diagnostics

Where applicable:

```text
Jacobian
scaled Jacobian
singular values
numerical rank assessment
near-null directions
profiles
correlations
multimodality
boundary status
```

## O6. Compatible ensemble/equivalence families

Especially for CS15.

## O7. Derived-observable stability table

At minimum, where defined:

```text
level gaps
doublet projectors
transition strengths/tensors
principal g values
other stable invariants
```

## O8. Experimental requirement matrix

For each unresolved parameter direction:

```text
degeneracy
affected quantities
candidate observable that breaks it
required precision/geometry where estimable
```

## O9. Negative-result report

Must be first-class output, not an exception path.

---

# TESTS

Specification-level tests are defined now but are **not executed by this task**.

## STAGE03R-T01 — BF midpoint prohibition

Inject a BF with interval `[L,U]`.

PASS only if no active code path generates

```math
(L+U)/2
```

as `CONFIRMATORY_ENERGY` without an explicit separate observation artifact.

---

## STAGE03R-T02 — legacy namespace exclusion

Any active observation with ID:

```text
F002
F004
```

must fail schema validation.

Historical provenance fields may contain them.

---

## STAGE03R-T03 — C002 numerical-failure semantics

Input containing:

```yaml
test_status: numerical_failure
raw_p_value: 1.0
```

must never generate:

```text
ABSENCE_CONFIRMED
NON_DETECTION
CENSORED_INTENSITY
```

or any physical likelihood contribution.

---

## STAGE03R-T04 — no BF→transition one-to-one assumption

Synthetic case with three BF structures and two candidate transitions must permit:

```text
multiple BF ↔ one component
one complex ↔ multiple components
unassigned component
```

without schema failure.

---

## STAGE03R-T05 — no automatic zero intensity

A model-predicted transition outside all BF support intervals must not generate:

```math
I_{\rm obs}=0.
```

Output must distinguish at least:

```text
not_constrained
not_covered
candidate_for_future_non_detection_test
```

depending on observation metadata.

---

## STAGE03R-T06 — normalization gate

Attempt to activate shared amplitude scale without compatibility evidence must fail.

---

## STAGE03R-T07 — optimizer convergence prohibition

Synthetic optimizer result with:

```text
success=true
```

but rank-deficient sensitivity matrix must return:

```text
PARAMETER_NONIDENTIFIABLE
```

or equivalent, never identified solely from optimizer success.

---

## STAGE03R-T08 — circular assignment rejection

If a model-generated prediction is marked as the sole evidence establishing the assignment used to score the same model, validation must fail:

```text
CIRCULAR_ASSIGNMENT
```

---

## STAGE03R-T09 — exchange gate

Attempt to instantiate exchange parameters without a passed trigger must fail.

---

## STAGE03R-T10 — support interval semantics

Changing only the width of a BF support interval must alter compatibility geometry but must not be interpreted as changing a Gaussian `\sigma`.

---

## STAGE03R-T11 — convention equivalence

Two parameter vectors related by a registered allowed frame/convention transformation must be recognized as the same physical equivalence family.

---

## STAGE03R-T12 — raw eigenvector gauge

Unitary rotation inside a Kramers doublet must leave reported gauge-invariant outputs unchanged within numerical tolerance.

---

# SYNTHETIC IDENTIFIABILITY CHECKS

These define future tests only.

## SYN-M0

Construct synthetic observables from M0:

```math
H(s)=sH_0.
```

Check that:

1. energy scale changes with `s`;
2. eigenprojectors/relative transition fingerprint remain invariant;
3. if assignment is unknown, multiple transition-index/`s` combinations can remain compatible;
4. optimizer convergence is not mistaken for assignment resolution.

Expected scientific lesson:

```text
M0 parameter may be conditionally identifiable
while assignment remains ambiguous.
```

---

## SYN-M1

Generate synthetic information in two variants.

### SYN-M1-E

Energy information only.

Test whether `s_{\rm O1},s_{\rm O2}` show correlated/near-null directions.

### SYN-M1-EI

Add multiple independent eigenvector-sensitive relative intensities.

Expected result:

```text
rank and profiles should improve if the observables genuinely
distinguish the O1/O2 deformation direction.
```

The test must demonstrate information gain rather than assume it.

---

## SYN-CS15

At minimum three designs.

### SYN-CS15-E7

Provide all seven exact CEF gaps.

Expected result:

```text
15 coefficients cannot generically be uniquely determined from seven scalar gaps.
```

The diagnostic should identify a substantial null/near-null manifold.

### SYN-CS15-EI

Add synthetic transition strengths for several independent `Q` directions.

Test whether effective rank increases.

### SYN-CS15-FULLER

Add directional magnetic observables.

Evaluate whether:

```text
individual B_lm
or only invariant/derived combinations
```

become stable.

Success does not require full rank 15; the purpose is to diagnose inferential structure.

---

# PASS\_CRITERIA

A future Stage03R implementation passes if all mandatory epistemic, mathematical and provenance rules are satisfied.

It is **not** required to find an identifiable CEF parameter set.

A scientifically successful PASS may conclude:

```text
PARAMETER_NONIDENTIFIABLE
MULTIPLICITY_UNRESOLVED
ASSIGNMENT_AMBIGUOUS
OBSERVATION_CONTRACT_INSUFFICIENT
ADDITIONAL_OBSERVABLE_REQUIRED
```

provided the implementation correctly identifies:

1. what observations were admitted;
2. what they constrain;
3. what remains unconstrained;
4. structural versus practical degeneracies;
5. dependence on assignment family;
6. dependence on convention/frame choices;
7. which additional observables would resolve the important degeneracies.

Mandatory PASS conditions:

```text
[ ] BF provenance preserved
[ ] BF interval semantics preserved
[ ] legacy active namespace excluded
[ ] C002 numerical failure not converted into physical evidence
[ ] multiplicity represented explicitly
[ ] assignment represented explicitly
[ ] model hierarchy preserved
[ ] convention/gauge contract enforced before CS15
[ ] identifiability assessed independently of optimizer convergence
[ ] normalization gate enforced
[ ] exchange gate enforced
[ ] negative scientific results supported
[ ] production fitting boundary enforced
```

---

# FAILURE / NEGATIVE\_RESULT\_STATUSES

These are scientific statuses, not necessarily software failures.

## Model-level

```text
MODEL_COMPATIBLE
MODEL_FALSIFIED
```

## Assignment-level

```text
ASSIGNMENT_AMBIGUOUS
MULTIPLICITY_UNRESOLVED
```

## Identifiability-level

```text
PARAMETER_NONIDENTIFIABLE
PARAMETER_WEAKLY_IDENTIFIABLE
DERIVED_QUANTITY_IDENTIFIABLE
```

## Experimental-information level

```text
ADDITIONAL_OBSERVABLE_REQUIRED
OBSERVATION_CONTRACT_INSUFFICIENT
```

## Physics-extension level

```text
CEF_ONLY_INADEQUATE
EXCHANGE_TEST_REQUIRED
```

## Suggested implementation-error statuses

Distinct from scientific negative results:

```text
INVALID_PROVENANCE
INVALID_OBSERVATION_ROLE
LEGACY_NAMESPACE_VIOLATION
CIRCULAR_ASSIGNMENT
NORMALIZATION_GATE_VIOLATION
CONVENTION_CONTRACT_INCOMPLETE
EXCHANGE_GATE_VIOLATION
NUMERICAL_DIAGNOSTIC_FAILURE
```

A scientific negative result must never be converted to `FAILED` merely because no fitted parameter vector was produced.

---

# STOP\_CONDITION

The following principle is normative:

> If the currently admitted observables do not support calibrated parameter inference, Stage03R must terminate with an identifiability, compatibility, or experimental-requirements result.

> It must not manufacture a production CEF fit.

Immediate hard STOP before any production-like inference if any of the following occurs:

```text
BF midpoint promoted to energy measurement
legacy F002/F004 used as active observation IDs
C002 p=1 interpreted physically
physical multiplicity silently fixed
BF→CEF one-to-one mapping silently assumed
missing BF interpreted as zero intensity
unvalidated normalization activated
CS15 convention/gauge contract incomplete
optimizer convergence used as identifiability evidence
model prediction used to establish its own assignment
exchange parameters activated without trigger
raw detector access attempted
holdout reanalysis attempted
Stage03D objective imported without new review
```

A normal successful STOP may therefore be:

```yaml
stage03r_result:
  status: OBSERVATION_CONTRACT_INSUFFICIENT
  constrained:
    - coarse_energy_support_topology
  not_identifiable:
    - individual_B_lm
    - physical_multiplicity
    - CEF_assignment
  next_requirement:
    - confirmatory_energy_and_relative_intensity_contract
```

This is a valid scientific endpoint.

---

# EXECUTION\_BOUNDARY

This specification defines architecture only.

The following remain normatively false:

```yaml
Stage03R_execution_authorized: false
W03_authorized: false
Stage03D_resumed: false
production_CEF_fit_authorized: false
raw_detector_access_authorized: false
holdout_reanalysis_authorized: false
```

Additionally:

```yaml
production_optimizer_configuration_frozen: false
production_parameter_bounds_frozen: false
production_likelihood_frozen: false
production_random_seed_policy_frozen: false
production_compute_job_defined: false
```

No future implementation or execution permission follows automatically from specification freeze.

A separate Project Control decision is required for each transition from:

```text
draft
→ specification freeze
→ implementation design/review
→ implementation authorization
→ scientific execution authorization
```

---

# SOURCE\_DRAFT\_IDENTITY

```yaml
STAGE03R_SPEC_DRAFT_ID: STAGE03R-INFERENCE-SPEC-DRAFT-001
SOURCE_DRAFT_VERSION: "0.1-draft"
FROZEN_SPECIFICATION_ID: STAGE03R-INFERENCE-SPEC
FROZEN_SPECIFICATION_VERSION: "1.0"
```

---

# NORMATIVE\_SECTIONS\_COMPLETE

```yaml
NORMATIVE_SECTIONS_COMPLETE:
  GOAL: true
  INPUTS: true
  EPISTEMIC_INPUT_CONTRACT: true
  OBSERVATION_ROLE_TAXONOMY: true
  ASSIGNMENT_STATE_ARCHITECTURE: true
  MODEL_HIERARCHY: true
  CONVENTION_AND_GAUGE_CONTRACT: true
  IDENTIFIABILITY_PROTOCOL: true
  STATISTICAL_ARCHITECTURE: true
  MODEL_COMPARISON_DECISION_TREE: true
  NORMALIZATION_GATE: true
  EXCHANGE_TRIGGER: true
  OUTPUTS: true
  TESTS: true
  PASS_CRITERIA: true
  FAILURE_NEGATIVE_RESULT_STATUSES: true
  STOP_CONDITION: true
  EXECUTION_BOUNDARY: true
```

---

# OPEN\_SPECIFICATION\_QUESTIONS

Only narrow freeze-level questions remain.

## SQ-01 — exact support-region compatibility primitive

Should initial implementation use only binary:

```text
compatible / incompatible
```

or additionally report deterministic distance-to-region quantities such as

```math
d(E,I)= \begin{cases} 0,&E\in I,\\ L-E,&E<L,\\ E-U,&E>U. \end{cases}
```

Recommendation:

```text
allow distance only as diagnostic,
not as pseudo-likelihood.
```

## SQ-02 — admissible multiplicity enumeration bounds

The architecture supports multiple `K`, but the exact candidate set for each CX should not be inferred from BF count alone.

Recommendation:

```text
leave multiplicity bounds outside v1.0 freeze unless
supported by a separate phenomenological-design decision.
```

## SQ-03 — numerical-rank criterion

SVD/rank is mandatory, but the exact scaling and singular-value threshold should be implementation-specific and tested synthetically.

Recommendation:

```text
freeze requirement, not numerical threshold.
```

## SQ-04 — flexible structural-model identity

The hierarchy reserves a low-dimensional superposition/structural layer, but its exact model ID and parameters remain undefined.

Recommendation:

```text
keep inactive in v1.0.
```

These questions do not require reopening `STAGE03R-DR-001`.

---

# DEPENDENCIES

Before any later Stage03R numerical inference:

```text
D1 complete convention/gauge freeze
D2 reviewed Stage03R observation contract
D3 explicit activation decision for any role beyond SUPPORT_REGION
D4 normalization decision if intensities are used
D5 assignment-family construction rules
D6 model-specific parameterization/bounds only for models actually activated
D7 implementation tests including synthetic identifiability checks
D8 independent scientific review of implementation before execution
```

For likelihood-enabled Stage03R additionally:

```text
D9 calibrated uncertainty semantics
D10 explicit likelihood derivation
D11 treatment of unresolved multiplicity
D12 justified censoring semantics if used
D13 resolution model where line overlap requires it
```

---

# EXECUTION\_PREREQUISITES

Specification freeze alone is insufficient.

Minimum governance sequence:

```text
STAGE03R-INFERENCE-SPEC freeze review
        ↓
Project Control acceptance of frozen spec
        ↓
implementation-only task definition
        ↓
implementation review + synthetic tests
        ↓
scientific checkpoint
        ↓
separate Project Control execution decision
```

No execution step may be inferred from predecessor completion.

---

# FREEZE\_REVIEW

```yaml
review_id: STAGE03R-SPEC-REVIEW-001
decision: A
status: APPROVED_FOR_SPECIFICATION_FREEZE
```

Reason:

The draft now fixes the epistemic boundary, observation taxonomy, latent assignment architecture, model roles, convention/gauge prerequisites, identifiability requirements, statistical two-layer design, comparison logic, normalization and exchange gates, valid negative outcomes, hard-stop semantics and execution boundary.

The remaining questions are narrow implementation details and do not alter the scientific architecture accepted in `STAGE03R-DR-001`.
