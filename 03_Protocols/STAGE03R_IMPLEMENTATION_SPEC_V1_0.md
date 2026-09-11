# Stage03R Implementation Specification v1.0

```yaml
SPECIFICATION_ID: STAGE03R-IMPLEMENTATION-SPEC
SPECIFICATION_VERSION: "1.0"
SPECIFICATION_STATUS: frozen
updated: 2026-09-11

source_draft:
  id: STAGE03R-IMPLEMENTATION-SPEC-DRAFT-001
  version: "0.1-draft"

accepted_corrections:
  - STAGE03R-IMPLEMENTATION-SPEC-CORR-001
  - STAGE03R-IMPLEMENTATION-SPEC-CORR-002

final_review:
  id: STAGE03R-IMPL-SPEC-REVIEW-001
  decision: B_NARROW_PRE_FREEZE_CORRECTION_REQUIRED
  remaining_freeze_blockers: []

canonical_path: 03_Protocols/STAGE03R_IMPLEMENTATION_SPEC_V1_0.md
```

---

# PARENT\_SCIENTIFIC\_SPEC

```yaml
parent_scientific_specification:
  id: STAGE03R-INFERENCE-SPEC
  version: "1.0"
  status: frozen
  path: 03_Protocols/STAGE03R_INFERENCE_SPEC_V1_0.md
  sha256: aa67a08bbfd1894dfaad13488cb48ab57b6cf0f44d51567a9c61191e55f2e2ac

canonical_repository: oregu93/cef-dy
canonical_branch: main
scientific_provenance_baseline: 330a17236fbbf1c91957e6e990eb8470c71a9c5f
future_implementation_starting_head: set_by_later_Project_Control_authorization
```

This implementation specification is subordinate to `STAGE03R-INFERENCE-SPEC v1.0`.

Where an implementation detail could be interpreted in more than one way, the epistemic and scientific semantics of the parent specification take precedence.

---

# PARENT\_IMPLEMENTATION\_DESIGN\_REVIEW

```yaml
parent_implementation_design_review:
  id: STAGE03R-IMPL-DR-001
  decision: A_READY_TO_DEFINE_STAGE03R_IMPLEMENTATION_SPEC
```

The accepted design defines the first implementation as:

```text
deterministic
inspectable
compatibility-oriented
assignment-aware
negative-result-capable
```

and explicitly not as a production fitting pipeline.

---

# GOAL

Implement the smallest deterministic Stage03R compatibility kernel capable of answering:

```text
Which explicitly admitted model / assignment families are compatible
with the currently admitted SUPPORT_REGION evidence?

Which ambiguities arise from:
- experimental information deficit,
- assignment or multiplicity ambiguity,
- model-parameter degeneracy,
- supplied-solution multimodality,
- convention/frame equivalence?

Which additional observable class would reduce each important ambiguity?
```

The implementation shall operate on frozen or explicitly admitted machine-readable inputs and produce deterministic compatibility and identifiability summaries.

The first implementation shall not require an optimizer.

The central computational chain is:

```text
frozen SUPPORT_REGION observations
        +
explicit assignment families
        +
validated forward-prediction bundles
        ↓
deterministic compatibility relations
        ↓
assignment-conditioned compatible sets
        ↓
registered convention-equivalence collapse
        ↓
identifiability / ambiguity classification
        ↓
additional-observable requirements
```

---

# NON\_GOALS

The following are explicitly outside this implementation specification:

```text
production CEF fitting
maximum-likelihood estimation
least-squares fitting
Bayesian inference
MCMC
posterior sampling
profile likelihood
AIC/BIC
LRT
bootstrap model comparison
raw TAIPAN reduction
holdout reanalysis
peak extraction
Gaussian centroid fitting
censored-intensity inference
absolute or relative intensity fitting
normalization fitting
TAS resolution convolution
M1 inference against current experimental observations
CS15 inverse parameter search
exchange-field fitting
structural refinement
automatic exhaustive assignment search
```

The implementation must not expose an undocumented route that performs any of these operations.

---

# CANONICAL\_INPUT\_IDENTITIES

## CI-1. Repository baseline

```yaml
repository: oregu93/cef-dy
branch: main
scientific_provenance_baseline_commit: 330a17236fbbf1c91957e6e990eb8470c71a9c5f
future_implementation_starting_head: set_by_later_Project_Control_authorization
```

The scientific provenance baseline fixes the scientific identities used to
define this specification. It is not a requirement that a future
implementation `HEAD` equal that earlier commit. Project Control shall set the
exact implementation starting `HEAD` in a separate authorization transition.

## CI-2. Parent scientific specification

```yaml
path: 03_Protocols/STAGE03R_INFERENCE_SPEC_V1_0.md
sha256: aa67a08bbfd1894dfaad13488cb48ab57b6cf0f44d51567a9c61191e55f2e2ac
```

## CI-3. Stage02R B-001 evidence

```yaml
path: 04_Results/Stage02R/W02-02R-B-001/blind_feature_catalogue.yaml
sha256: f428ddc47b00c23cbbf8829ea2a5db5ef582af5ef68e3447b7fa3dd05535fcd5
feature_namespace: BF
feature_count: 8
```

Active support-region IDs:

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

Bookkeeping complex IDs:

```text
CX-01
CX-02
CX-03
```

## CI-4. Model identities

The implementation shall recognize only the following relevant canonical IDs:

```text
MOD-PCM-FORMAL
MOD-PCM-M0
MOD-PCM-M1
MOD-CEF-CS15
MOD-CEF-EXCHANGE
```

Model identity and scientific role are read against:

```text
00_Project/MODEL_REGISTER.yaml
```

at the required baseline commit.

No model shall be activated merely because a similarly named external software object exists.

## CI-5. Convention metadata

A prediction requiring convention-sensitive comparison shall provide the convention metadata required by this specification.

No implicit "project default" convention shall be assumed where metadata are absent.

---

# INPUT\_VALIDATION\_RULES

## IV-1. Identity validation

Before any scientific compatibility evaluation, validate:

```text
canonical commit
parent specification identity
parent specification SHA-256
B-001 catalogue SHA-256
model IDs
config schema version
```

Mismatch shall terminate that run before scientific interpretation.

## IV-2. Active observation-role validation

For v1.0, the only automatically admitted experimental role is:

```text
SUPPORT_REGION
```

Any attempt to automatically populate:

```text
CONFIRMATORY_ENERGY
RELATIVE_INTENSITY
CENSORED_INTENSITY
Q_DEPENDENCE
TEMPERATURE_DEPENDENCE
INDEPENDENT_VALIDATION
```

shall fail validation unless a later superseding specification explicitly activates it.

## IV-3. Legacy namespace prohibition

The active observation namespace shall reject:

```text
F002
F004
```

Historical prose/provenance may contain these strings.

They may not be active observation IDs or automatic aliases of any BF.

## IV-4. Historical target prohibition

The implementation shall not automatically admit historical energies such as:

```text
~6.45 meV
~18.23 meV
~18.247178 meV
~27.90 meV
```

as current Stage03R fitting or compatibility targets.

## IV-5. Detector-data prohibition

No input path may target raw or holdout detector-level data.

The implementation is expected to consume canonical Stage02R products only.

## IV-6. Stage03D inheritance prohibition

The implementation shall reject implicit inheritance of:

```text
Stage03D objective functions
Stage03D M0/M1 bounds
historical nuisance scales
historical F002/F004 mappings
historical likelihood terms
```

unless a future superseding specification explicitly re-admits them.

---

# SUPPORT\_REGION\_SCHEMA

Canonical machine representation:

```yaml
schema_type: stage03r_support_region
schema_version: "1.0"

observation_id: BF-004
role: SUPPORT_REGION

energy_region_meV:
  lower: 17.49800
  upper: 18.49815

source_bf_id: BF-004
complex_id: CX-02

interval_semantics:
  closed_lower: true
  closed_upper: true
  probability_density_defined: false
  confidence_interval: false
  centroid_measurement: false
  linewidth_measurement: false
  likelihood_defined: false

assignment_status: unassigned

provenance:
  source_artifact:
    path:
    sha256:
```

Required validation:

```text
lower <= upper
observation_id == source_bf_id for current BF records
role == SUPPORT_REGION
complex_id belongs to frozen BF/CX mapping
provenance identity present
```

## Forbidden derived observation fields

The following shall not be generated from a SUPPORT\_REGION record:

```text
centroid
centroid_meV
sigma
sigma_meV
Gaussian_energy
physical_fwhm
transition_energy
measured_peak_energy
```

In particular:

```math
\frac{L+U}{2}
```

shall never be persisted or passed downstream as an experimental energy observation.

---

# PREDICTION\_BUNDLE\_SCHEMA

A `PredictionBundle` is the implementation boundary between CEF-generating software and the deterministic compatibility kernel.

The kernel shall not depend on PyCrystalField-, McPhase-, CrysFieldExplorer-, or other provider-specific internal formats.

Minimum schema:

```yaml
schema_type: stage03r_prediction_bundle
schema_version: "1.0"

prediction_bundle_id:

model_id:
parameter_set_id:
parameter_source:

provenance:
  source_artifact:
  source_identity:
  generator_name:
  generator_version:
  generation_method:
  evidence_used_to_generate: []
  generated_from_current_stage03r_observations: false

convention:
  cef_convention_id:
  stevens_normalization_id:
  coefficient_units:
  crystallographic_setting:
  global_frame_id:
  local_frame_id:
  local_to_global_matrix:
  canonical_parameter_order:

parameters: null

levels:
  - level_id:
    energy_meV:
    degeneracy:

transitions:
  - transition_id:
    initial_level_id:
    final_level_id:
    energy_meV:
    strength: null
    transition_tensor: null

transition_inventory:
  status: complete_for_declared_scope
  declared_scope:

derived:
  principal_g_values: null
  other_invariants: null
```

## PB-1. Parameter source

Allowed examples:

```text
fixed_model
analytic_parameter
external_candidate_set
external_candidate_ensemble
synthetic_fixture
```

## PB-2. Evidence provenance

`evidence_used_to_generate` is mandatory for external fitted/generated candidate sets.

It exists to prevent circular use of a solution as "independent" confirmation of evidence that generated the solution.

## PB-3. Transition inventory

Allowed:

```text
complete_for_declared_scope
partial
```

A `partial` inventory may support local compatibility diagnostics but cannot support model-level falsification based on missing possible matches.

## PB-4. Optional strengths

`strength` and `transition_tensor` may be carried for future or derived-observable diagnostics.

They are not current experimental likelihood quantities.

---

# ASSIGNMENT\_FAMILY\_SCHEMA

A deterministic assignment family represents a reviewed scientific hypothesis.

Minimum schema:

```yaml
schema_type: stage03r_assignment_family
schema_version: "1.0"

assignment_family_id:
origin: real_scientific | synthetic_test
review_status:

complexes:
  - complex_id:

    multiplicity_hypothesis:

    components:
      - component_id:

        source_support_constraint:
          mode: ALL_OF | ANY_OF
          support_ids: []

        classification:
          UNCLASSIFIED |
          CEF_CANDIDATE |
          NON_CEF_CANDIDATE |
          MIXED_OR_UNRESOLVED

        cef_transition_mapping:
          mode: ONE_OF | UNASSIGNED
          candidate_transition_ids: []

        required_cef_explanation: true | false

unassigned_support_ids: []

status:
  admission_status:
```

## AF-1. No continuous phenomenological component energy

The first implementation shall not introduce a free component-energy variable.

A candidate component is symbolic and constrained by one or more SUPPORT\_REGION sets.

## AF-2. `ALL_OF`

For one mapped transition `t`:

```math
E_t\in\bigcap_{j\in J}I_j.
```

## AF-3. `ANY_OF`

For one mapped transition `t`:

```math
E_t\in\bigcup_{j\in J}I_j.
```

## AF-4. `ONE_OF`

If several transition IDs are supplied:

```text
candidate_transition_ids: [T1, T2, ...]
```

the component may be explained by any one of those explicitly enumerated mappings.

No nearest-transition rule is permitted.

## AF-5. Unassigned structures

A BF may remain in:

```text
unassigned_support_ids
```

without making the assignment-family schema invalid.

## AF-6. Zero-obligation family

Define the required CEF component set:

```math
R_A=\{c\in A:\mathrm{required\_cef\_explanation}(c)=\mathrm{true}\}.
```

If `|R_A|=0` within the declared tested scope, the family is:

```text
NOT_TESTABLE
```

It must not produce `FAMILY_COMPATIBLE` or `MODEL_COMPATIBLE`, and it is
not assigned an unconstrained model-parameter region. In particular, M0 must
not construct `S_A=(0,\infty)` for such a family. Compatibility cannot be
established by an empty set of required experimental CEF obligations.

---

# ASSIGNMENT\_ADMISSION\_POLICY

Three layers shall remain separate.

## AP-1. Schema implementation

The software implements and validates the assignment-family schema.

This is mandatory for implementation acceptance.

## AP-2. Synthetic assignment families

Synthetic assignment families used exclusively in unit/synthetic tests are permitted.

They shall be labelled:

```yaml
origin: synthetic_test
```

and shall never appear as real scientific Stage03R conclusions.

## AP-3. Real scientific assignment families

A real family requires:

```text
explicit ID
explicit content
explicit scientific provenance
explicit admission in configuration
reviewed status
```

The implementation shall not construct real families automatically from:

```text
BF count
CX count
energy ordering
model predictions
nearest predicted transition
```

## AP-4. No assignment priors

No assignment-family probability, prior, weight, or frequency is defined in v1.0.

## AP-5. No combinatorial search

The compatibility program shall not enumerate all combinatorial assignment possibilities.

---

# INITIAL\_ASSIGNMENT\_FAMILY\_SCOPE

For implementation acceptance, the initial real scientific assignment catalogue may be empty:

```yaml
real_assignment_families: []
```

This is explicitly valid.

The first implementation shall contain sufficient synthetic families to test:

```text
many BF → one component
one BF → multiple candidate transitions
multiple components within one complex
unassigned BF structures
non-CEF component
incompatible required mapping
ambiguous alternative assignments
```

If no real scientific family has been admitted during a later scientific run:

```text
real scientific model conclusion: NOT_TESTABLE
```

rather than automatically generating a family.

Therefore:

```text
software implementation acceptance
!=
real Stage03R scientific assignment activation
```

---

# COMPATIBILITY\_PRIMITIVES

Let:

```math
I=[L,U]
```

be a closed SUPPORT\_REGION and `E` a predicted transition energy.

## CP-1. INSIDE

Numerically:

```text
INSIDE
```

when `E` lies inside the closed region, subject only to the configured implementation boundary tolerance.

Mathematical semantics:

```math
L\le E\le U.
```

## CP-2. BELOW\_REGION

```text
BELOW_REGION
```

when `E<L` outside the numerical boundary tolerance.

## CP-3. ABOVE\_REGION

```text
ABOVE_REGION
```

when `E>U` outside the numerical boundary tolerance.

## CP-4. One predicted transition compatible with several BF

Allowed.

No one-to-one BF identity is inferred.

## CP-5. Several predicted transitions compatible with one BF/CX

Allowed.

Output diagnostic:

```text
MULTIPLE_TRANSITION_COMPATIBILITY
```

This is not automatically a multiplicity determination.

## CP-6. Unassigned experimental support

Allowed output:

```text
UNASSIGNED_SUPPORT
```

This may contribute to:

```text
ASSIGNMENT_AMBIGUOUS
MULTIPLICITY_UNRESOLVED
OBSERVATION_CONTRACT_INSUFFICIENT
```

but is not a software failure.

## CP-7. Unmatched predicted transition

Output:

```text
UNMATCHED_PREDICTED_TRANSITION
```

Normative semantics:

```yaml
physical_absence_inference: false
zero_intensity_inference: false
model_falsification_by_itself: false
```

## CP-8. Assignment conflict

Examples:

```text
required candidate transition does not exist in the declared inventory
no candidate mapping satisfies a required support constraint
assignment schema contradicts declared multiplicity
a required CEF component is mapped only to invalid transitions
```

Such a family is:

```text
INCOMPATIBLE
```

for that model/prediction state.

## CP-9. NOT\_TESTABLE

Use when scientific evaluation cannot validly be performed, including:

```text
no admitted real assignment family
missing required PredictionBundle
prediction inventory insufficient for the requested conclusion
required convention information missing
required model provider absent
```

---

# MODEL\_FALSIFICATION\_RULE

This rule is normative and intentionally strict.

## MF-1. Family-level compatibility

For a specific model state `M_\theta` and admitted assignment family `A`:

```text
FAMILY_COMPATIBLE
```

requires a nonempty set of components marked:
```text
required_cef_explanation: true
```

and the existence of at least one jointly valid transition mapping satisfying
all their SUPPORT\_REGION constraints simultaneously.

For required components `R_A={c_1,...,c_K}`, let `T(c_k)` be each explicitly
declared finite candidate-transition set. A valid joint mapping

```math
\phi:R_A\rightarrow T
```

must satisfy

```math
\phi(c_k)\in T(c_k)
```

and, for distinct physical CEF candidate components,

```math
c_i\neq c_j\Rightarrow\phi(c_i)\neq\phi(c_j).
```

Only explicitly declared transition IDs may participate. Component-wise
compatibility is necessary but not sufficient. The implementation must not
generate assignments, optimize them, marginalize probabilistically, or apply
assignment priors.

Extra unmatched predicted transitions are ignored for falsification purposes.

## MF-2. Family-level incompatibility

```text
FAMILY_INCOMPATIBLE
```

may be returned when:

1. the assignment family is valid and admitted;
2. required model predictions exist;
3. the relevant prediction inventory is sufficiently complete for the tested mapping scope;
4. at least one required CEF component cannot be satisfied by any explicitly allowed transition mapping.

## MF-3. Parameterized model family

For a model family such as M0:

```text
MODEL_COMPATIBLE
```

if at least one admissible parameter state exists for at least one admitted assignment family.

A particular assignment family is incompatible if its compatible parameter set is empty.

## MF-4. Model-level falsification across assignment families

`MODEL_FALSIFIED` is allowed only if:

```text
A. at least one real scientific assignment family has been admitted;

B. every admitted real assignment family relevant to the declared
   comparison scope is scientifically testable;

C. all such families are FAMILY_INCOMPATIBLE;

D. prediction inventory completeness is sufficient for every required
   mapping test;

E. the conclusion does not rely on unmatched additional predicted
   transitions;

F. convention/frame validation passed.
```

Formally, for admitted testable assignment families `A_k`:

```math
\forall k,\qquad \mathcal C(M,A_k)=\varnothing
```

is required.

## MF-5. Mixed family outcome

If some admitted assignment families are compatible and some incompatible:

```text
MODEL_COMPATIBLE
ASSIGNMENT_AMBIGUOUS
```

is the appropriate combined scientific result.

## MF-6. Untestable family blocks falsification

If no family is compatible but one or more relevant families are `NOT_TESTABLE`:

```text
NOT_TESTABLE
```

shall supersede `MODEL_FALSIFIED`.

A zero-obligation family defined by AF-6 is `NOT_TESTABLE`; it supports neither
model compatibility nor model falsification. If all admitted real families are
`NOT_TESTABLE`, the model status is `NOT_TESTABLE`.

## MF-7. Unmatched transition prohibition

The implication:

```text
UNMATCHED_PREDICTED_TRANSITION
→ MODEL_FALSIFIED
```

is forbidden.

---

# DISTANCE\_TO\_REGION\_RULE

A per-pair deterministic diagnostic is permitted.

For energy `E` and closed region `[L,U]`:

```math
d(E,[L,U])= \begin{cases} 0,&L\le E\le U,\\ L-E,&E<L,\\ E-U,&E>U. \end{cases}
```

Allowed output fields:

```yaml
relation: INSIDE | BELOW_REGION | ABOVE_REGION
distance_meV:
```

Boundary comparison follows the numerical tolerance policy.

Numerical boundary tolerance is treated as numerical equality with the exact
closed boundary. Therefore the normative relation/distance invariant is:

```text
if relation == INSIDE:
    distance_meV = 0
```

Only `BELOW_REGION` and `ABOVE_REGION` may carry positive `distance_meV`.
For a point classified outside tolerance, distance is measured to the exact
boundary:

```math
d(E,[L,U])=\begin{cases}L-E,&E<L,\\E-U,&E>U.\end{cases}
```

## DR-1. Semantic status

`distance_meV` is only:

```text
deterministic geometric distance to a support set
```

It is not:

```text
residual in units of experimental uncertainty
chi-square contribution
negative log likelihood
probability
confidence
weight
fit score
```

## DR-2. Forbidden aggregations

The implementation shall not produce:

```text
sum_distance
mean_distance
median_distance
RMS_distance
weighted_distance
normalized_distance
total_model_distance
```

## DR-3. Forbidden use

Distance shall not be used for:

```text
model ranking
assignment ranking
parameter optimization
best-s selection
best-CS15-member selection
```

The distance must not be interpreted as likelihood, probability, uncertainty,
linewidth, or instrument resolution.

---

# FORMAL\_PCM\_IMPLEMENTATION\_CONTRACT

```yaml
model_id: MOD-PCM-FORMAL
implementation_scope: fixed_forward_compatibility
fitted_parameters: 0
optimizer: forbidden
```

## FPC-1. Input

A scientifically meaningful real run requires a validated `PredictionBundle` with:

```text
model_id == MOD-PCM-FORMAL
parameter_source == fixed_model
valid structure/convention provenance
declared transition inventory
```

## FPC-2. No bundle at freeze/implementation time

If no validated real FORMAL bundle exists:

```text
implementation support: PASSABLE
scientific model result: NOT_TESTABLE
```

The implementation task shall not regenerate or fabricate that bundle.

## FPC-3. Outputs

Permitted:

```text
transition/support compatibility relations
assignment-family compatibility
UNMATCHED_PREDICTED_TRANSITION diagnostics
UNASSIGNED_SUPPORT diagnostics
per-pair distance-to-region
```

## FPC-4. Interpretation

An inside-region transition establishes:

```text
energy-support compatibility
```

only.

It does not establish:

```text
physical CEF assignment
model validation
spectral completeness
```

---

# M0\_IMPLEMENTATION\_CONTRACT

```yaml
model_id: MOD-PCM-M0
implementation_scope: analytic_set_compatibility
active_parameter:
  name: s
  domain: positive
optimizer: forbidden
best_parameter_estimator: forbidden
```

For positive scaling:

```math
H(s)=sH_0, \qquad s>0.
```

For each positive reference transition gap:

```math
\Delta_t^{(0)}>0.
```

For support region:

```math
I_j=[L_j,U_j],
```

compatibility is:

```math
s\Delta_t^{(0)}\in[L_j,U_j].
```

Therefore:

```math
S_{tj} = \left[ \frac{L_j}{\Delta_t^{(0)}}, \frac{U_j}{\Delta_t^{(0)}} \right] \cap (0,\infty).
```

## M0-1. Closed interval semantics

The finite compatibility interval produced by one positive transition and one closed support region is closed:

```math
\left[ L/\Delta,\, U/\Delta \right].
```

The global scale-domain restriction remains:

```math
s>0.
```

Since all current BF energy bounds are positive and valid transition gaps must be positive, derived finite lower bounds should also be positive.

## M0-2. Invalid transition gap

A reference transition with:

```math
\Delta_t^{(0)}\le0
```

shall not enter M0 interval propagation.

It shall be treated as invalid for this positive-energy transition contract.

## M0-3. `ALL_OF` support relation

For a fixed transition `t` required to satisfy BF set `J`:

```math
S_t^{ALL} = \bigcap_{j\in J}S_{tj}.
```

## M0-4. `ANY_OF` support relation

```math
S_t^{ANY} = \bigcup_{j\in J}S_{tj}.
```

## M0-5. Alternative transition mapping

For candidate transition set `T_c`, retain transition identity rather than
forming an identity-free component union.

For every valid joint mapping `\phi`, compute the mapped component set
`S_{c,\phi(c)}` and then:

```math
S_{A,\phi}=\bigcap_{c\in R_A}S_{c,\phi(c)}.
```

An empty intersection rejects that joint mapping.

## M0-6. Several required components

The complete family-compatible set is:

```math
S_A=\bigcup_{\phi\in\Phi_A^{\mathrm{valid}}}S_{A,\phi}
```

for assignment family `A`, with disconnected intervals preserved. Evaluation
is finite, deterministic, and restricted to explicitly declared candidate
transition IDs. If `R_A` is empty, AF-6 applies and no `(0,\infty)` set is
constructed.

## M0-7. Canonical interval representation

Every compatible set is represented as an ordered list of pairwise-disjoint closed intervals:

```yaml
compatible_s:
  - [lower_1, upper_1]
  - [lower_2, upper_2]
```

Canonicalization:

```text
1. reject invalid interval lower > upper beyond numerical tolerance;
2. sort by lower endpoint, then upper endpoint;
3. merge intervals that overlap;
4. merge intervals that only numerically touch within the
   configured merge tolerance;
5. preserve genuinely separated intervals;
6. return [] for the empty set.
```

## M0-8. Disconnected regions

Disconnected regions are first-class results.

Example:

```yaml
compatible_s:
  - [0.51, 0.55]
  - [0.87, 0.92]
```

shall not be collapsed to:

```text
0.51–0.92
```

and shall not be averaged.

## M0-9. Empty set

```yaml
compatible_s: []
```

means:

```text
this assignment-conditioned M0 compatible set is empty
```

It does not by itself establish model-level falsification until the full `MODEL_FALSIFICATION_RULE` is applied.

## M0-10. No best `s`

Forbidden:

```text
best_s
optimal_s
mean_s
midpoint_s
MLE_s
least_squares_s
```

## M0-11. No confidence interpretation

An M0 compatibility interval is not:

```text
confidence interval
credible interval
uncertainty interval
profile interval
```

It is a deterministic set satisfying the admitted support constraints.

---

# M1\_SYNTHETIC\_CONTRACT

```yaml
model_id: MOD-PCM-M1
real_data_inference: forbidden
real_data_grid_search: forbidden
real_data_optimizer: forbidden
historical_Stage03D_bounds: forbidden
synthetic_identifiability_only: true
```

The first implementation need only contain synthetic logic sufficient to demonstrate:

```text
two free structural parameters can leave an extended compatible manifold
under energy/support-like constraints
```

Required synthetic fixture:

```text
SYN-M1-E
```

Purpose:

```text
verify that software does not collapse an extended two-parameter
compatible set into a falsely identified point.
```

`SYN-M1-EI` is deferred until eigenvector-sensitive/intensity observations are activated by a later specification.

---

# CS15\_SUPPLIED\_BUNDLE\_CONTRACT

```yaml
model_id: MOD-CEF-CS15

schema_support: true
real_ensemble_admission: explicit_per_input
inverse_generation: forbidden
optimizer: forbidden
sampling_density_is_probability: false
```

## CS-1. Allowed operations

```text
validate supplied parameter-set metadata
consume supplied PredictionBundles
evaluate SUPPORT_REGION compatibility
classify assignment-conditioned compatibility
collapse registered convention-equivalent solutions
group remaining physically distinct candidates
summarize derived-observable spread
consume explicitly supplied forward sensitivities where provenance permits
```

## CS-2. Forbidden operations

```text
15-dimensional global search
local minimization
random-start search
genetic algorithm
MCMC
posterior construction
profile objective
parameter-bound search
regularization-based selection
automatic preferred solution selection
```

## CS-3. Required ensemble metadata

```yaml
ensemble_id:
model_id: MOD-CEF-CS15

source:
  artifact:
  identity:
  generation_method:
  generation_software:
  evidence_used_to_generate: []

convention:
  cef_convention_id:
  stevens_normalization_id:
  units:
  crystallographic_setting:
  global_frame_id:
  local_frame_id:
  local_to_global_matrix:
  canonical_parameter_order:

members:
  - parameter_set_id:
    B_lm:
    prediction_bundle_id:

sampling_semantics:
  posterior_sample: false
  likelihood_region: false
  probability_density_defined: false
  description:
```

Fields may be set true only when a future explicitly authorized statistical contract supports that meaning.

## CS-4. Sampling density

The number or density of supplied candidate sets in any region shall not be interpreted as relative probability.

## CS-5. Evidence provenance

An ensemble must state which observations or external data were used to generate it.

The compatibility kernel shall preserve this metadata in output to permit circularity review.

## CS-6. No real convention registry

If required real convention transformations are not validated:

```text
schema support: allowed
synthetic CS15 tests: allowed
real CS15 equivalence evaluation:
  CONVENTION_CONTRACT_INCOMPLETE
```

---

# CONVENTION\_REGISTRY\_CONTRACT

The first implementation shall use an explicit registry rather than automatic convention discovery.

Minimum registered transformation record:

```yaml
transform_id:

from:
  cef_convention_id:
  stevens_normalization_id:
  units:
  crystallographic_setting:
  global_frame_id:
  local_frame_id:

to:
  cef_convention_id:
  stevens_normalization_id:
  units:
  crystallographic_setting:
  global_frame_id:
  local_frame_id:

parameter_transform:
frame_transform:

provenance:
  source:
  review_status:

status: active | synthetic_only | inactive
```

## CR-1. Reviewed transformations only

A real transformation may be `active` only if scientifically reviewed.

## CR-2. Synthetic registry

Synthetic transformations may be included for mandatory tests:

```yaml
status: synthetic_only
```

They shall not authorize real scientific canonicalization.

## CR-3. Missing real registry

Absence of real validated transformations is acceptable for implementation acceptance.

Result:

```text
real CS15 equivalence evaluation blocked
```

not a guessed transform.

## CR-4. No automatic equivalence discovery

The software shall not infer a transformation because two parameter sets:

```text
look similar
produce similar energies
have similar signs
```

---

# EQUIVALENCE\_COLLAPSE\_RULES

Different CFP vectors shall not automatically be treated as different physical solutions.

## EC-1. Explicit registered transformation

Preferred route:

```text
raw representation
→ registered reviewed transformation
→ canonical representation
```

If two representations map to the same canonical Hamiltonian within numerical tolerance, they belong to one convention-equivalence class.

## EC-2. Hamiltonian comparison

Where both Hamiltonians are represented in the same basis/frame:

```math
H_1 \sim H_2
```

if the configured Hamiltonian absolute/relative numerical comparison passes.

This is a numerical equivalence test, not an experimental fit criterion.

## EC-3. Energy equality alone

The condition:

```math
E_n^{(1)}\approx E_n^{(2)}
```

is insufficient for physical equivalence.

Iso-spectral but wavefunction-distinct Hamiltonians shall not be collapsed solely from energies.

## EC-4. Gauge-robust observables

Where Hamiltonian comparison is unavailable, equivalence evidence may include agreement of:

```text
ordered energy levels
doublet projectors
transition tensors in a common frame
principal g invariants
other registered invariants
```

The exact equivalence claim shall record which comparison level was used.

## EC-5. Class representation

Output:

```yaml
equivalence_class_id:
members: []
canonical_member:
equivalence_basis:
```

`canonical_member` is a deterministic representational choice only, not a scientifically preferred solution.

---

# KRAMERS\_GAUGE\_INVARIANCE\_RULES

For CEF-only Dy`^{3+}` Kramers doublet `a`, basis vectors inside the doublet are not unique.

For unitary `U_a`:

```math
|\psi_{a\mu}'\rangle = \sum_\nu (U_a)_{\mu\nu} |\psi_{a\nu}\rangle.
```

Raw eigenvector coefficients shall therefore not be compared as unique physical observables.

## KG-1. Doublet projector

Preferred invariant:

```math
P_a = \sum_{\mu=1}^{2} |\psi_{a\mu}\rangle \langle\psi_{a\mu}|.
```

Synthetic gauge rotation must satisfy:

```math
P_a'=P_a
```

within numerical projector tolerance.

## KG-2. Transition tensor

A gauge-robust transition object may be constructed as:

```math
T_{\alpha\beta}^{ab} = {\rm Tr} \left( P_aJ_\alpha P_bJ_\beta \right).
```

Equivalent gauge choices must yield equal tensors within the configured invariant tolerance.

## KG-3. Principal `g` values

Principal `g` values, when computed from a correctly transformed effective-doublet response, are preferred over raw doublet eigenvector coefficients.

## KG-4. Raw eigenvector prohibition

No output may label raw basis coefficients as a uniquely identified physical wavefunction without separately fixing a gauge.

---

# IDENTIFIABILITY\_OUTPUT\_SEMANTICS

The implementation must maintain three separate concepts.

## IO-1. Structural identifiability

Question:

```text
Does the forward model and admitted observable structure permit
uniqueness in principle?
```

Possible diagnostics:

```text
analytic compatible-set dimension
Jacobian rank
exact parameter degeneracy
symmetry/equivalence directions
```

## IO-2. Practical identifiability

Question:

```text
How tightly does the actually admitted evidence restrict the model?
```

Current compatibility-mode outputs may include:

```text
compatible-set geometry
number of connected compatible regions
boundedness
assignment sensitivity
derived-observable spread
```

No likelihood-based confidence claim is allowed.

## IO-3. Numerical search behavior

The first implementation performs no scientific optimizer search.

Therefore it must not manufacture:

```text
optimizer stability
basin convergence
search success rate
```

For an externally supplied ensemble it may report only properties actually observable in that ensemble, such as:

```text
multiple supplied compatible regions
```
without claiming they constitute an exhaustive multimodality search.

## IO-4. M0 geometry

Allowed:

```text
EMPTY
BOUNDED_CONNECTED
BOUNDED_DISCONNECTED
UNBOUNDED
```

where applicable.

## IO-5. `PARAMETER_NONIDENTIFIABLE`

May be emitted when admitted compatibility information leaves more than one physically distinct parameter state or continuous parameter region and no approved rule establishes unique identification.

## IO-6. `PARAMETER_WEAKLY_IDENTIFIABLE`

Inactive in implementation specification v1.0.

```yaml
PARAMETER_WEAKLY_IDENTIFIABLE:
  active: false
  reason: no scientifically justified threshold frozen
```

No compatible-set width shall be arbitrarily labelled "weakly identifiable."

## IO-7. Derived quantities

`DERIVED_QUANTITY_IDENTIFIABLE` may be used when a derived quantity is stable across the full admitted compatible ensemble/set relevant to the claim.

The output must state:

```text
ensemble/set over which stability was assessed
numerical spread
comparison tolerance
assignment-family dependence
```

---

# NEGATIVE\_RESULT\_SEMANTICS

The following are normal scientific results, not software failures:

```text
MODEL_COMPATIBLE
MODEL_FALSIFIED
NOT_TESTABLE
ASSIGNMENT_AMBIGUOUS
MULTIPLICITY_UNRESOLVED
PARAMETER_NONIDENTIFIABLE
DERIVED_QUANTITY_IDENTIFIABLE
ADDITIONAL_OBSERVABLE_REQUIRED
OBSERVATION_CONTRACT_INSUFFICIENT
CEF_ONLY_INADEQUATE
EXCHANGE_TEST_REQUIRED
```

`PARAMETER_WEAKLY_IDENTIFIABLE` remains reserved/inactive.

## Software/governance failure statuses

The implementation shall distinguish actual invalid execution states:

```text
INVALID_PROVENANCE
INVALID_OBSERVATION_ROLE
LEGACY_NAMESPACE_VIOLATION
CONVENTION_CONTRACT_INCOMPLETE
CIRCULAR_ASSIGNMENT
NORMALIZATION_GATE_VIOLATION
EXCHANGE_GATE_VIOLATION
NUMERICAL_DIAGNOSTIC_FAILURE
```

A scientifically negative result shall not be mapped to generic software `FAILED`.

---

# OUTPUT\_ARTIFACT\_SCHEMAS

Exactly five scientific output files are permitted.

---

## OA-1. `input_manifest.yaml`

Purpose: immutable identities only.

Schema:

```yaml
artifact_type: stage03r_input_manifest
schema_version: "1.0"

canonical_repository:
canonical_branch:
canonical_commit:

scientific_specification:
  id:
  version:
  path:
  sha256:

implementation_specification:
  id:
  version:

B001_catalogue:
  path:
  sha256:

config:
  path:
  sha256:

model_register:
  path:
  commit:

prediction_bundles:
  - prediction_bundle_id:
    source_identity:

convention_registry_identity:

real_assignment_family_ids: []

execution_boundary:
  raw_detector_accessed: false
  holdout_accessed: false
  optimizer_used: false
  likelihood_used: false
```

Do not duplicate full canonical model/evidence records.

---

## OA-2. `observation_table.yaml`

Contains only admitted active observations.

For v1.0:

```yaml
artifact_type: stage03r_observation_table
active_roles:
  - SUPPORT_REGION

observations:
  - observation_id:
    role:
    lower_energy_meV:
    upper_energy_meV:
    source_bf_id:
    complex_id:
    assignment_status:
    source_artifact:
    interval_semantics:
```

No historical spectroscopy.

No midpoint.

---

## OA-3. `assignment_families.yaml`

```yaml
artifact_type: stage03r_assignment_families

families:
  - assignment_family_id:
    origin:
    review_status:
    definition:
    admission_status:
    model_conditioned_results:
```

Synthetic families used only in tests shall not be mixed into a real scientific output package.

---

## OA-4. `model_compatibility.yaml`

```yaml
artifact_type: stage03r_model_compatibility

models:
  - model_id:

    prediction_bundle_ids: []

    assignment_results:
      - assignment_family_id:

        status:
          FAMILY_COMPATIBLE |
          FAMILY_INCOMPATIBLE |
          NOT_TESTABLE

        pairwise_relations:
          - transition_id:
            support_id:
            relation:
            distance_meV:

        compatible_parameter_set:
          type:
          intervals: []

        diagnostics:
          unmatched_predicted_transitions: []
          unassigned_support: []

    model_status:
      MODEL_COMPATIBLE |
      MODEL_FALSIFIED |
      NOT_TESTABLE

    assignment_ambiguity:
```

No scalar global fit score is allowed.

---

## OA-5. `identifiability_summary.yaml`

```yaml
artifact_type: stage03r_identifiability_summary

model_summaries:
  - model_id:

    structural_identifiability:
    practical_identifiability:

    compatible_set_geometry:

    assignment_sensitivity:

    convention_equivalence:
      classes: []

    derived_observable_stability: []

    scientific_statuses: []

    unresolved_ambiguities:
      - ambiguity_id:
        type:
        consequence:
        candidate_additional_observable:
        rationale:

global_summary:
  observation_contract_status:
  major_ambiguities:
  additional_observable_requirements:
```

No separate sixth `additional_observable_requirements.yaml` shall be created in v1.0.

---

# NUMERICAL\_TOLERANCE\_POLICY

Numerical tolerances are implementation safeguards only.

They shall carry:

```yaml
physical_uncertainty_meaning: none
linewidth_meaning: none
instrument_resolution_meaning: none
statistical_confidence_meaning: none
```

Required config keys:

```yaml
numerical_tolerances:
  interval_boundary_abs_meV:
  interval_merge:
    absolute:
    relative:
  hamiltonian_comparison:
    absolute_meV:
    relative:
  projector_comparison:
    absolute_frobenius:
  invariant_comparison:
    absolute:
    relative:
```

## NT-1. Interval-boundary tolerance

Must be:

```text
strictly positive
orders of magnitude smaller than every admitted SUPPORT_REGION width
large enough only to absorb ordinary floating-point boundary noise
```

Freeze requirement:

```math
\tau_E \le 10^{-6} \times \min_j(U_j-L_j)
```

is the normative upper bound for the implementation-time value.

The exact operational value is an implementation-time configuration
value and is not frozen in this specification.

## NT-2. Interval-merge tolerance

Used only to merge endpoints that should numerically coincide.

It shall never bridge a scientifically finite parameter gap.

Comparison shall use an absolute-plus-relative form:

```math
|a-b| \le \tau_{\rm abs} + \tau_{\rm rel}\max(1,|a|,|b|).
```

Exact `\tau_{\rm abs}` and `\tau_{\rm rel}` are implementation-time
configuration values.

## NT-3. Hamiltonian comparison

Use combined absolute and relative matrix criterion in the common canonical basis.

Normatively, using the Frobenius norm:

```math
\|H_1-H_2\|_F \le \tau_H^{abs} + \tau_H^{rel} \max(\|H_1\|_F,\|H_2\|_F).
```

The Frobenius norm is frozen for inspectability.

## NT-4. Projector comparison

Normative:

```math
\|P_1-P_2\|_F \le \tau_P.
```

Exact `\tau_P` is an implementation-time configuration value.

## NT-5. Invariant comparison

Matrix- or tensor-valued invariants use the Frobenius norm with a
combined absolute and relative criterion:

```math
\|X_1-X_2\|_F \le \tau_X^{abs} + \tau_X^{rel}
\max(\|X_1\|_F,\|X_2\|_F).
```

Scalar invariants use:

```math
|x_1-x_2| \le \tau_x^{abs} + \tau_x^{rel}\max(1,|x_1|,|x_2|).
```

The implementation must document the units of dimensional invariants.

## NT-6. Selection rule for implementation-time values

During implementation, candidate tolerance values shall be chosen by the following rule:

```text
1. use deterministic synthetic fixtures with exact known equivalence;
2. determine the smallest tolerance that robustly accepts all
   numerically equivalent fixture pairs in the supported numerical
   environment;
3. verify that deliberately distinct fixture pairs remain distinct;
4. verify that interval-boundary tolerance remains <= 10^-6 of the
   smallest current BF support width;
5. record exact values in stage03r_compatibility_config.yaml;
6. test exact inside/outside/merge behavior at ± tolerance boundaries.
```

Exact operational values belong only in:

```text
scripts/stage03r/stage03r_compatibility_config.yaml
```

No tolerance may be tuned to make a model compatible, merge
scientifically distinct solutions, enlarge compatible parameter regions,
or change model ranking.

---

# TEST\_REQUIREMENTS

All tests below are implementation tests and synthetic scientific-design tests.

They do not constitute Stage03R scientific execution.

## TR-1. Mandatory for implementation acceptance

```text
STAGE03R-T01
STAGE03R-T02
STAGE03R-T03
STAGE03R-T04
STAGE03R-T05
STAGE03R-T06
STAGE03R-T07
STAGE03R-T08
STAGE03R-T09
STAGE03R-T10
STAGE03R-T11
STAGE03R-T12

SYN-M0
SYN-M1-E
SYN-CS15-E7

convention-equivalence fixture
Kramers-gauge fixture
```

## TR-2. Mapping

| Testv1.0 implementation acceptanceScientific execution in implementation taskFuture likelihood stageFuture inverse CS15 |                        |                |                                      |                                               |
| ----------------------------------------------------------------------------------------------------------------------- | ---------------------- | -------------- | ------------------------------------ | --------------------------------------------- |
| T01 midpoint prohibition                                                                                                | MUST PASS              | no             | retain                               | retain                                        |
| T02 legacy namespace                                                                                                    | MUST PASS              | no             | retain                               | retain                                        |
| T03 C002 p=1 semantics                                                                                                  | MUST PASS              | no             | retain                               | retain                                        |
| T04 flexible mapping                                                                                                    | MUST PASS              | no             | retain                               | retain                                        |
| T05 no zero pseudo-observation                                                                                          | MUST PASS              | no             | retain                               | retain                                        |
| T06 normalization gate                                                                                                  | MUST PASS              | no             | expand later                         | retain                                        |
| T07 optimizer ≠ identifiability                                                                                         | MUST PASS semantically | no optimizer   | retain                               | critical                                      |
| T08 circular assignment                                                                                                 | MUST PASS              | no             | retain                               | retain                                        |
| T09 exchange gate                                                                                                       | MUST PASS              | no             | retain                               | retain                                        |
| T10 interval ≠ sigma                                                                                                    | MUST PASS              | no             | retain                               | retain                                        |
| T11 convention equivalence                                                                                              | MUST PASS synthetic    | no             | retain                               | critical                                      |
| T12 Kramers gauge                                                                                                       | MUST PASS synthetic    | no             | retain                               | critical                                      |
| SYN-M0                                                                                                                  | MUST PASS              | synthetic only | retain                               | n/a                                           |
| SYN-M1-E                                                                                                                | MUST PASS              | synthetic only | retain                               | n/a                                           |
| SYN-M1-EI                                                                                                               | deferred               | no             | required before intensity-enabled M1 | n/a                                           |
| SYN-CS15-E7                                                                                                             | MUST PASS              | synthetic only | retain                               | critical                                      |
| SYN-CS15-EI                                                                                                             | deferred               | no             | later                                | required before richer CS15 inverse inference |
| SYN-CS15-FULLER                                                                                                         | deferred               | no             | later                                | future magnetic-observable stage              |

---

# SYNTHETIC\_FIXTURES

All fixtures must be compact and embedded in either:

```text
stage03r_compatibility_config.yaml
```

under a clearly synthetic test section, or directly in:

```text
test_stage03r_compatibility.py
```

No additional fixture files are required for v1.0.

## SF-1. SUPPORT\_REGION boundary fixture

Construct synthetic interval:

```math
[1,2].
```

Check:

```text
inside
exact lower boundary
exact upper boundary
just inside tolerance
just outside tolerance
below
above
relation/distance consistency
```

For all points classified `INSIDE`, including tolerance-equivalent
boundary points, `distance_meV` must be exactly zero. Positive distance
is permitted only for `BELOW_REGION` or `ABOVE_REGION` and is measured
to the exact interval boundary.

No midpoint shall be emitted as observation data.

## SF-2. Assignment topology fixture

Must exercise:

```text
two support regions → one component
one support region → two candidate transitions
unassigned support
two-component complex
non-CEF candidate
```

It shall additionally exercise an injective joint mapping across two
components:

```text
C1 -> ONE_OF [T1,T2]
C2 -> ONE_OF [T1,T2]
```

A mapping that reuses `T1` for both required components is invalid when
no alternative exists; `C1 -> T1, C2 -> T2` is valid when both declared
support constraints are satisfied. Candidate mappings must use only
explicitly declared transition IDs.

It shall also exercise the zero-obligation case:

```text
required_cef_explanation count = 0
-> NOT_TESTABLE
-> not FAMILY_COMPATIBLE
-> not MODEL_COMPATIBLE
```

## SF-3. `SYN-M0`

Provide positive reference gaps and synthetic support regions with known outcomes:

```text
one connected s interval
two disconnected s intervals
empty compatible set
overlapping intervals requiring canonical merge
numerically touching endpoints
```

Verify exact interval algebra.

## SF-4. `SYN-M1-E`

Use a simple deterministic synthetic two-parameter forward map chosen solely to represent an extended degeneracy.

It need not be a production DyFeO3 M1 Hamiltonian calculation.

It must demonstrate:

```text
multiple parameter pairs
→ same/admissibly equivalent support constraints
→ no false point-identification
```

If future reviewers require a physically instantiated M1 synthetic Hamiltonian, that should be a superseding/narrow amendment rather than silently inserted.

## SF-5. `SYN-CS15-E7`

Construct a synthetic sensitivity problem with:

```text
15 parameter directions
7 independent energy-like observables
```

and known Jacobian rank no greater than 7.

The test must verify that the implementation does not report full 15-parameter identification from seven independent scalar gaps.

This fixture tests identifiability machinery; it does not perform DyFeO3 inversion.

## SF-6. Convention-equivalence fixture

Construct two parameter/Hamiltonian representations related by one synthetic registered transform.

Expected:

```text
different raw representation
same physical equivalence class
```

Comparisons shall use the Hamiltonian Frobenius norm, projector
Frobenius norm, matrix/tensor invariant Frobenius norm, and scalar
absolute-plus-relative comparison frozen by this specification.

Also construct an iso-spectral but deliberately physically distinct fixture that must **not** collapse from energy equality alone.

## SF-7. Kramers-gauge fixture

Construct a doublet projector and apply a nontrivial unitary rotation inside the doublet.

Expected:

```text
raw eigenvectors: changed
doublet projector: invariant
registered transition invariant: invariant
```

within numerical tolerance. The nontrivial unitary doublet rotation must
change raw eigenvectors while the projector Frobenius difference and
transition-tensor Frobenius difference pass their configured tolerances.

---

# SOFTWARE\_FILE\_ALLOWLIST

Only the following implementation files are in scope:

```text
scripts/stage03r/stage03r_compatibility.py
scripts/stage03r/stage03r_compatibility_config.yaml
scripts/stage03r/test_stage03r_compatibility.py
```

No additional module is authorized by this specification.

## SW-1. `stage03r_compatibility.py`

May contain functions/sections for:

```text
schema/input validation
SUPPORT_REGION loading
PredictionBundle validation
assignment-family validation
interval operations
distance-to-region
fixed-model compatibility
M0 interval propagation
convention-registry handling
equivalence collapse
gauge-invariant comparison
optional local sensitivity/SVD diagnostics
negative-result classification
output serialization
```

## SW-2. `stage03r_compatibility_config.yaml`

Shall contain:

```text
canonical identities
allowed model scope
active observation role
explicit real assignment-family admission list
synthetic test configuration where appropriate
registered convention transforms
numerical tolerances
execution gates
output settings
```

It shall not contain:

```text
legacy F002/F004 targets
historical mandatory Dy energies
fit bounds inherited from Stage03D
optimizer settings
likelihood settings
exchange fit settings
raw detector paths
```

## SW-3. `test_stage03r_compatibility.py`

Contains mandatory unit, semantic, and synthetic tests.

---

# EXECUTION\_BOUNDARY

This is an implementation specification, not an execution authorization.

```yaml
implementation_status: not_started
implementation_authorized: false
```

The following remain false:

```yaml
Stage03R_execution_authorized: false
W03_authorized: false
Stage03D_resumed: false
production_CEF_fit_authorized: false
raw_detector_access_authorized: false
holdout_reanalysis_authorized: false

optimizer_authorized: false
likelihood_inference_authorized: false
M1_real_data_inference_authorized: false
CS15_inverse_inference_authorized: false
exchange_fit_authorized: false
```

Implementation completion shall not change these values automatically.

A future implementation task may create and test software against synthetic fixtures only if separately authorized.

Real Stage03R scientific execution requires a later explicit Project Control decision.

---

# STOP\_CONDITION

Implementation/runtime shall STOP before scientific output if any of the following occurs:

```text
parent scientific specification identity mismatch
parent scientific specification SHA mismatch
B-001 identity mismatch
legacy F002/F004 active observation input
SUPPORT_REGION midpoint promoted to measurement
unsupported observation role automatically activated
raw detector path requested
holdout detector path requested
Stage03D likelihood imported
optimizer requested
likelihood requested
automatic real assignment generation requested
C002 p=1 converted to physical non-detection
unmatched predicted transition used as falsification evidence
shared normalization activated
exchange parameters instantiated
CS15 inverse search requested
real CS15 equivalence attempted without valid convention contract
model prediction used to establish its own supposedly independent assignment
```

Scientific STOP states that are not implementation failures include:

```text
NOT_TESTABLE
ASSIGNMENT_AMBIGUOUS
MULTIPLICITY_UNRESOLVED
PARAMETER_NONIDENTIFIABLE
OBSERVATION_CONTRACT_INSUFFICIENT
ADDITIONAL_OBSERVABLE_REQUIRED
```

If no real assignment families or no validated real PredictionBundle are admitted, the implementation may terminate scientifically with:

```text
NOT_TESTABLE
```

while the software itself remains fully valid.

---

# IMPLEMENTATION\_ACCEPTANCE\_CRITERIA

A future implementation-only review may return PASS only if all of the following hold:

```text
AC-01
Exact canonical commit, parent specification and B-001 identities
are validated.

AC-02
No raw or holdout detector data are read.

AC-03
SUPPORT_REGION is the only automatically admitted experimental role.

AC-04
No BF midpoint becomes an experimental observation.

AC-05
F002/F004 active observation IDs are rejected.

AC-06
Historical Dy energies are not mandatory targets.

AC-07
C002 numerical_failure / p=1 cannot create absence evidence.

AC-08
Assignment families are explicit and support many-to-many mappings.

AC-08A
Required components are evaluated through an injective joint mapping
using only explicitly declared transition IDs.

AC-08B
An assignment family with zero required CEF-explanation obligations is
NOT_TESTABLE and cannot make a family or model compatible.

AC-09
No real assignment family is automatically generated from BF count,
energy order or model prediction.

AC-10
UNMATCHED_PREDICTED_TRANSITION never causes MODEL_FALSIFIED alone.

AC-11
Family-level and model-level falsification follow the strict
MODEL_FALSIFICATION_RULE.

AC-12
Distance-to-region exists only per transition/support pair.

AC-12A
INSIDE implies distance_meV = 0; positive distance is emitted only for
BELOW_REGION or ABOVE_REGION and is measured to the exact boundary.

AC-13
No aggregate distance score exists.

AC-14
MOD-PCM-FORMAL has no fitted parameter.

AC-15
Absence of a validated FORMAL PredictionBundle produces NOT_TESTABLE,
not fabricated predictions.

AC-16
M0 compatibility is derived by deterministic interval algebra.

AC-17
M0 disconnected compatible regions are preserved.

AC-18
No best-s or midpoint-s field exists.

AC-19
M0 intervals carry no statistical confidence semantics.

AC-20
M1 real-data search is absent.

AC-21
Historical Stage03D M1 bounds/objective are absent.

AC-22
CS15 inverse optimization is absent.

AC-23
CS15 ensemble sampling density is not interpreted probabilistically.

AC-24
External CS15 ensemble provenance records evidence used in generation.
AC-25
Real CS15 equivalence comparison fails safely when convention metadata
are incomplete.

AC-26
Only reviewed real convention transforms may be activated.

AC-27
Synthetic convention-equivalent representations collapse correctly.

AC-28
Iso-spectral but physically distinct synthetic representations do not
collapse solely from energy equality.

AC-29
Kramers-doublet unitary gauge rotation leaves projector/invariant
comparisons unchanged within numerical tolerance.

AC-29A
Hamiltonian, projector and matrix/tensor comparisons use the frozen
Frobenius norms; scalar invariants use absolute-plus-relative comparison.

AC-30
PARAMETER_WEAKLY_IDENTIFIABLE remains inactive.

AC-31
Negative scientific results are treated as normal scientific outputs.

AC-32
No normalization model can activate.

AC-33
No exchange parameters can instantiate.

AC-34
All mandatory STAGE03R-T01...T12 tests pass.

AC-35
SYN-M0 passes.

AC-36
SYN-M1-E passes.

AC-37
SYN-CS15-E7 passes.

AC-38
Convention-equivalence fixture passes.

AC-39
Kramers-gauge fixture passes.

AC-40
Repeated execution on identical deterministic inputs produces
semantically identical output artifacts.

AC-41
Only the three allowlisted implementation files are created/modified
by the implementation job unless a later specification amendment
changes the allowlist.

AC-42
Exactly the five defined scientific output schemas are supported.

AC-43
No production CEF fit is executed during implementation acceptance.

AC-44
Implementation completion does not alter Stage03R/W03 execution
authorization.
```

---

# CONTROLLED\_REVISABILITY

Normative statement:

> This implementation specification is frozen for reproducibility, not immutable scientific truth.

> If later scientific evidence shows that an implementation boundary, assignment rule, model scope, compatibility semantic, convention treatment, or output rule is insufficiently justified or unnecessarily restrictive, it must be revised through an explicit superseding specification rather than silently bypassed.

A future superseding specification shall preserve:

```text
previous specification identity
reason for revision
scientific or technical evidence motivating revision
affected contracts
compatibility/migration consequences
authorization boundary
```

---

# NON\_BLOCKING\_ADMISSION\_QUESTIONS

The specification has no remaining freeze blocker. The following are
inactive scientific gates, not prerequisites for specification freeze or
implementation acceptance:

```yaml
NON_BLOCKING_ADMISSION_QUESTIONS:

  real_assignment_family_admission:
    classification: inactive_scientific_gate
    software_support_required: true
    required_for_spec_freeze: false
    required_for_implementation_acceptance: false
    activation: explicit_future_admission

  validated_MOD_PCM_FORMAL_bundle:
    classification: inactive_scientific_gate
    software_support_required: true
    required_for_spec_freeze: false
    if_absent_at_scientific_execution: NOT_TESTABLE

  real_convention_registry:
    classification: inactive_scientific_gate
    synthetic_registry_support_required: true
    required_for_spec_freeze: false
    if_no_reviewed_real_transform:
      real_CS15_equivalence_evaluation: blocked

  real_CS15_ensemble:
    classification: inactive_scientific_gate
    schema_support_required: true
    required_for_spec_freeze: false
    admission: explicit_per_input
    inverse_generation: forbidden
```

Normative distinction:

```text
feature supported by software
!=
feature scientifically activated
```

Exact numerical tolerance values are implementation-time configuration
values selected and accepted through the mandatory synthetic tests. They
are not unresolved freeze questions.

---

# FREEZE\_REVIEW\_CHECKLIST

```yaml
FREEZE_REVIEW_CHECKLIST:

  identity:
    draft_id_correct: true
    parent_scientific_spec_fixed: true
    parent_design_review_fixed: true
    future_canonical_path_defined: true

  scope:
    deterministic_kernel_only: true
    support_region_only: true
    optimizer_absent: true
    likelihood_absent: true
    raw_detector_access_absent: true
    holdout_access_absent: true
    exchange_fit_absent: true

  inputs:
    canonical_identity_contract_complete: true
    legacy_namespace_blocked: true
    historical_targets_not_active: true

  schemas:
    support_region_schema_complete: true
    prediction_bundle_schema_complete: true
    assignment_family_schema_complete: true

  assignments:
    automatic_real_enumeration_forbidden: true
    empty_real_catalogue_allowed: true
    zero_obligation_is_not_testable: true
    injective_joint_mapping_required: true
    synthetic_vs_real_separated: true

  compatibility:
    primitives_defined: true
    unmatched_transition_semantics_defined: true
    strict_model_falsification_defined: true
    distance_nonprobabilistic: true
    inside_distance_zero: true
    aggregate_distance_forbidden: true

  models:
    formal_contract_complete: true
    m0_exact_interval_algebra_complete: true
    m1_synthetic_only: true
    cs15_supplied_only: true

  conventions:
    registry_contract_complete: true
    equivalence_rules_complete: true
    Kramers_gauge_rules_complete: true
    Frobenius_norms_frozen: true

  identifiability:
    structural_practical_numerical_separated: true
    weak_identifiability_inactive: true
    negative_results_first_class: true

  outputs:
    exact_five_artifacts_defined: true
    canonical_data_duplication_minimized: true

  tests:
    T01_T12_mapped: true
    SYN_M0_required: true
    SYN_M1_E_required: true
    SYN_CS15_E7_required: true
    convention_fixture_required: true
    Kramers_fixture_required: true

  software:
    exact_three_file_allowlist: true
    extra_modules_not_authorized: true

  governance:
    controlled_revisability_defined: true
    remaining_freeze_blockers: []
    implementation_execution_separated: true
    implementation_status: not_started
    implementation_authorized: false
    Stage03R_execution_authorized: false
    W03_authorized: false
    Stage03D_resumed: false
```

---

# SPECIFICATION\_VERSION

```yaml
SPECIFICATION_VERSION: "1.0"
```

# SPECIFICATION\_STATUS

```yaml
SPECIFICATION_STATUS: frozen
```

# RECOMMENDATION

```text
FROZEN — READY_FOR_SEPARATE IMPLEMENTATION AUTHORIZATION REVIEW
```

Rationale:

This canonical document freezes the complete minimal software/scientific
contract without broadening the accepted Stage03R design. Corrections
`STAGE03R-IMPLEMENTATION-SPEC-CORR-001` and
`STAGE03R-IMPLEMENTATION-SPEC-CORR-002` are incorporated, and no freeze
blocker remains.

Exact numerical tolerances and admission of real assignment families,
FORMAL bundles, real convention transforms, or real CS15 ensembles are
controlled later gates. Their software support does not activate their
scientific use.

This freeze does not authorize implementation, Stage03R execution, W03,
detector-data access, a production CEF fit, holdout reanalysis, or resumption
of Stage03D.
