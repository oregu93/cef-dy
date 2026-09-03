---
title: "DyFeO3 — Stage 02R W02-02R-A-003 acquisition/configuration classification specification"
type: work_job_specification
project_id: CEF-Dy
stage_id: M02R
task_id: T-02R-03
job_id: W02-02R-A-003
status: frozen
version: "1.0"
updated: 2026-09-03
language_content: ru
language_metadata: en
---

# W02-02R-A-003

## STATUS

```yaml
stage_id: M02R
task_id: T-02R-03
job_id: W02-02R-A-003
dataset_id: EXP-TAIPAN-001
design_status: approved
specification_status: frozen
execution_status: not_started
execution_authorized: false
parent_checkpoint: W02-02R-A-002
canonical_design_input_commit: 68bd7eb7958e9f35e26525b8f4e80cb968f458d9
governance_mode: lean_delta
required_tests: 16
pairwise_decisions_expected: 20100
```

No A-003 execution is authorized by this specification.

## PURPOSE / SCOPE

This job-specific DELTA uses the reviewed A-002 canonical acquisition layer to reconstruct
acquisition-state and recorded instrument-configuration structure, normalization-relevant
chronological epochs, pairwise normalization compatibility and candidate compatibility groups.
It classifies metadata compatibility without normalization or spectral analysis.

The shared protocols listed in §AUTHORITATIVE INPUTS remain authoritative.
A-003 MUST NOT restate or override them except for the job-specific logic frozen here.

Allowed evidence: reviewed A-002 canonical metadata, verified A-002 semantic
mappings, recorded acquisition chronology, `lattice_state_id`, `UB_state_id`,
`count_control_mode`, recorded instrument fields and bounded metadata consistency checks.
Forbidden evidence: spectral shape, detector intensity similarity, peak position,
peak area, background level, historical target energies, F002/F004 assignments,
previous normalization factors and CEF predictions. Prohibited operations are
defined once in §STOP CONDITION; they apply throughout A-003.

Absence of a recorded configuration field MUST NOT be interpreted as evidence
of identical physical configuration: missing/not-recorded values are not
equality evidence. This includes shared missing filter, attenuation, reflection,
mosaic, hardware-identity and other unresolved beam-path values; they MUST NOT
enter either acquisition-state or instrument-config v1 identity fingerprint.

## AUTHORITATIVE INPUTS

Canonical design baseline: `68bd7eb7958e9f35e26525b8f4e80cb968f458d9` (`chore(stage02r): capture reviewed A002 parser results`).

Canonical project inputs and shared protocols:

```text
00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml
00_Project/RESULT_REGISTER.yaml
02_Work_Checkpoints/W02-02R-A-001.md
02_Work_Checkpoints/W02-02R-A-002.md
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
```

Primary A-002 inputs, all under `04_Results/Stage02R/W02-02R-A-002/`:

```text
scan_inventory.csv
file_scan_map.csv
lattice_states.yaml
UB_states.yaml
parsed_header_metadata.jsonl
semantic_verification_report.yaml
parser_diagnostics.csv
quality_diagnostics.csv
provenance_manifest.yaml
```

Point-level A-002 tables may be inspected only where required to verify a
recorded configuration field already represented in the canonical acquisition layer.
Read `scan_points.csv` from the tracked A-002 result directory above.
Resolve external `scan_point_auxiliary.csv` ONLY through
`04_Results/Stage02R/W02-02R-A-002/external_artifacts.yaml`.
Before reading it, verify its exact byte size and SHA-256 against that manifest.
Do NOT hard-code an absolute machine-local path.
If it is unavailable or fails identity verification, A-003 may proceed without
it only if none of the frozen classification fields requires it; otherwise
execution MUST stop rather than silently substitute raw-data analysis.
A-003 MUST NOT perform new raw-data analysis.

Reviewed baseline: 201 logical scans (103 monitor-controlled, 98 time-controlled),
2 lattice states, 4 UB states; monochromator/analyzer material PG,
collimation `o-40-40-o`. `mode=0` and raw q remain unresolved;
filter/attenuation are not recorded or unresolved; reflection/mosaic are unverified.

## FROZEN IDENTITIES

`acquisition_state_id`, `instrument_config_id` and
`normalization_compatibility_group_id` MUST remain semantically separate.
No extra field may enter any exact frozen vector/key.

### acquisition_state_v1

Identity version: `stage02r_acquisition_state_v1`.
Meaning: recorded acquisition-state equivalence for the frozen v1 dimensions only.
EXACT vector and field order:

```text
1. count_control_mode
2. scan_variable_raw
3. lattice_state_id
4. UB_state_id
```

EXACT canonical payload and order:

```text
stage02r_acquisition_state_v1
count_control_mode=<VALUE>
scan_variable_raw=<VALUE>
lattice_state_id=<VALUE>
UB_state_id=<VALUE>
```

Serialize as UTF-8, no BOM, LF after every line including the final line.
Fingerprint: `SHA256(canonical_payload)`; retain the full 64-hex SHA-256 fingerprint.
Display ID: `ACQSTATE-02R-<prefix>`, where prefix is the shortest even-length
prefix >= 16 hex characters unique within the A-003 result package.
Extend all colliding fingerprints deterministically: `16 → 18 → 20 → ...`,
independently of input order. Shuffling MUST NOT change IDs or memberships.

Excluded from this identity: `sequence_index`, timestamps, filesystem mtime,
`raw_format_id`; h/k/l, q, e, Ei, Ef; `scan_start`, `scan_stop`, point count;
temperature, `mode_raw`, `repeat_metadata_signature`; detector, monitor, time;
monochromator material, analyzer material, collimation, filter, attenuation,
reflection and mosaic. Exclusion defines identity scope, not scientific irrelevance.
Temperature lacks a unique sufficiently verified physical-channel mapping;
`mode_raw=0` has unresolved semantics.

The frozen v1 vector MUST NOT be mutated during execution. If additional
evidence motivates another identity, report `candidate_identity_field_for_future_version` instead.

### instrument_config_v1

Identity version: `stage02r_instrument_config_v1`.
Semantic meaning: `recorded_verified_configuration_equivalence_only`.
EXACT vector and field order:

```text
1. monochromator_material
2. analyzer_material
3. collimation
```

EXACT canonical payload and order:

```text
stage02r_instrument_config_v1
monochromator_material=<VALUE>
analyzer_material=<VALUE>
collimation=<VALUE>
```

Serialization, full SHA-256 retention and deterministic collision extension
are identical to §acquisition_state_v1: UTF-8/no BOM/LF including final LF.
Display ID: `INSTCFG-02R-<shortest unique even-length prefix >=16>`.
Shuffling MUST NOT change IDs or memberships.

Excluded: `filter_state`, `attenuation_state`, `monochromator_reflection`,
`analyzer_reflection`, `monochromator_mosaic`, `analyzer_mosaic`;
`count_control_mode`, `lattice_state_id`, `UB_state_id`, scan variable;
h/k/l/q, e/Ei/Ef, temperature, mode, chronology, raw format and spectral/intensity quantities.
Per §PURPOSE / SCOPE, missing/not-recorded values are not equality evidence.
All or most scans may legitimately share one ID: it proves equality only of
the frozen recorded verified vector, not of unrecorded physical instrument state.

Additional recorded fields, including focusing/aperture metadata, may be
inspected for variation diagnostics, candidate boundary evidence and future
semantic work. They MUST NOT enter either v1 identity during execution;
if sufficiently established, report `candidate_identity_field_for_future_version`.

### normalization_group_v1

Identity version: `stage02r_normalization_compatibility_group_v1`.
EXACT deterministic partition key and order:

```text
1. count_control_mode
2. instrument_config_id
3. normalization_epoch_id
```

EXACT canonical payload and order:

```text
stage02r_normalization_compatibility_group_v1
count_control_mode=<VALUE>
instrument_config_id=<VALUE>
normalization_epoch_id=<VALUE>
```

Encoding/fingerprint: UTF-8, LF including final LF, full SHA-256 fingerprint.
Display ID: `NORMCOMP-02R-<shortest unique even-length prefix >=16>`;
deterministic collision extension is `16 → 18 → 20 → ...`, independent of input order.
Do NOT include `acquisition_state_id`, `lattice_state_id`, `UB_state_id`,
scan variable, Ei, Ef or e in the group fingerprint.
Different acquisition/orientation states may share future normalization treatment
if counting regime and recorded normalization-relevant configuration remain compatible.

## NORMALIZATION-RELEVANT UNKNOWN SET

Frozen sets (do not synthesize values; propagate both sets explicitly):

```yaml
critical_unknown_fields:
  - filter_state
  - higher_order_suppression_state
  - attenuation_state
  - monochromator_reflection
  - analyzer_reflection
  - detector_hardware_identity
  - monitor_hardware_identity
relevant_unknown_fields:
  - monochromator_mosaic
  - analyzer_mosaic
  - unresolved_focusing_aperture_configuration_fields
  - other_unresolved_beam_path_configuration_fields
```

Missing critical metadata make `conditionally_supported`, rather than
`supported`, an expected and scientifically acceptable positive result.

## NORMALIZATION EPOCHS

`normalization_epoch_id` is a chronological segmentation construct.
IDs: `NORMEPOCH-02R-0001`, `NORMEPOCH-02R-0002`, ... .
Process scans using verified acquisition chronology.
Begin a new epoch ONLY when there is:

```text
A. verified change in a normalization-relevant recorded instrument field
OR
B. explicit recorded metadata proving a normalization-relevant reconfiguration event
```

Do NOT create a new epoch solely because of a time gap, day change,
scan-variable change, h/k/l/e change, `lattice_state_id` change, `UB_state_id`
change, temperature change, repeat signature change or raw-format change.
A chronological gap alone is never a normalization-hardware boundary.
For an uncertain possible boundary, record `confidence: uncertain_boundary`;
do not silently create a new epoch. Propagate uncertainty into pair/group limitations where relevant.
Epochs MUST be deterministic under input reordering (A003-T13).

## PAIRWISE COMPATIBILITY ALGORITHM

Materialize ALL unordered pairs in `normalization_compatibility.csv`:
`N = 201`; `201 * 200 / 2 = 20100` rows, exactly once per unordered pair.
Canonical pair order: `scan_a_record_id < scan_b_record_id` using lexical comparison.
Sort rows lexically by `scan_a_record_id`, then `scan_b_record_id`.
Evaluate the following six steps in EXACT precedence order for every pair.

### STEP 1 — count-control conflict

If `count_control_mode_A != count_control_mode_B`:

```text
compatibility_status = not_supported
decision_code = count_control_mode_conflict
```

STOP pair evaluation.

### STEP 2 — verified configuration conflict

Compare only normalization-relevant fields whose physical semantics are sufficiently
verified and whose values are actually recorded for both scans.
For v1 this necessarily includes the frozen instrument-config vector.
If any verified normalization-relevant field conflicts:

```text
compatibility_status = not_supported
decision_code = verified_configuration_conflict
```

Record exact fields. STOP pair evaluation.

### STEP 3 — explicit verified reconfiguration boundary

If direct recorded chronological metadata prove a normalization-relevant
instrument reconfiguration separating the scans:

```text
compatibility_status = not_supported
decision_code = explicit_reconfiguration_boundary
```

A time gap alone is insufficient. A lattice or UB change alone is insufficient.
STOP pair evaluation.

### STEP 4 — contradictory or insufficient metadata

If normalization-relevant canonical metadata are contradictory or unusable
such that recorded-equivalence itself cannot be assessed:

```text
compatibility_status = unresolved
decision_code = insufficient_or_contradictory_metadata
```

STOP pair evaluation.

### STEP 5 — recorded equivalence with critical unknowns

If all of the following hold:

```text
count_control_mode agrees
AND instrument_config_id agrees
AND no verified conflict exists
AND one or more critical_unknown_fields remain unresolved/not_recorded
```

then:

```text
compatibility_status = conditionally_supported
decision_code = recorded_equivalence_with_critical_unknowns
```

Record `verified_equal_fields`, `critical_unknown_fields`, `relevant_unknown_fields`
and `limitations`. STOP pair evaluation.

### STEP 6 — supported

Only if all of the following hold:

```text
count_control_mode agrees
AND instrument_config_id agrees
AND no verified conflict exists
AND no explicit verified reconfiguration boundary exists
AND critical_unknown_fields is empty
```

then:

```text
compatibility_status = supported
decision_code = recorded_metadata_supports_shared_treatment
```

Meaning: `supported_by_available_recorded_metadata`, NOT `proven_complete_physical_identity`.
No other path may produce `supported`.

## GROUP CONSTRUCTION AND CLIQUE AUDIT

Construct groups by the exact deterministic key partition in §normalization_group_v1.
Do NOT use graph connected components: pairwise compatibility is not assumed transitive.
After partitioning, check every candidate group against the complete pairwise table.
Every internal member pair MUST be `supported` or `conditionally_supported`;
`not_supported` and `unresolved` are forbidden.
If even one internal pair is forbidden:

1. Do NOT split by discovery-order heuristic.
2. Emit a diagnostic.
3. Mark the exact-key partition unresolved.
4. Fail the group-consistency test.
5. STOP A-003 unless a deterministic frozen rule already explains the split.

This is a full internal clique audit, not connected-component grouping.

For a valid non-singleton group, `status = supported` ONLY if every internal
pair is `supported`. Otherwise `status = conditionally_supported` if all
internal pairs are `supported` or `conditionally_supported` and at least one is conditional.
For a singleton, `status = conditionally_supported` if critical unknown metadata
remain; use `status = supported` only if the same individual supported criteria are satisfied.
Every group MUST explicitly contain `normalization_performed: false`.

## OUTPUTS

Target directory: `04_Results/Stage02R/W02-02R-A-003/`. Required outputs:

```text
acquisition_states.yaml
instrument_configs.yaml
acquisition_boundaries.csv
normalization_compatibility.csv
normalization_compatibility_groups.yaml
scan_classification.csv
classification_diagnostics.csv
provenance_manifest.yaml
test_report.yaml
```

Source: `scripts/stage02r/a003_classify.py`.
Optional compact frozen rule/config source: `scripts/stage02r/a003_classification_rules.yaml`.
No A-002 point/inventory artifact should be duplicated.
Existing canonical scan IDs MUST be preserved; outputs must suffice for scientific
review of T-02R-03 acquisition/configuration structure.

### scan_classification.csv

One row per each of the 201 scans. Required fields include:

```text
scan_record_id
raw_scan_id
sequence_index
acquisition_state_id
acquisition_state_status
instrument_config_id
instrument_config_status
count_control_mode
lattice_state_id
UB_state_id
normalization_epoch_id
critical_unknown_fields
relevant_unknown_fields
normalization_compatibility_status
normalization_compatibility_group_id
classification_notes
```

### acquisition_states.yaml

Each state:

```yaml
acquisition_state_id:
  identity_version: stage02r_acquisition_state_v1
  fingerprint:
  state_vector:
    count_control_mode:
    scan_variable_raw:
    lattice_state_id:
    UB_state_id:
  member_scan_record_ids:
  evidence:
```

### instrument_configs.yaml

Each configuration:

```yaml
instrument_config_id:
  identity_version: stage02r_instrument_config_v1
  fingerprint:
  semantic_meaning: recorded_verified_configuration_equivalence_only
  state_vector:
    monochromator_material:
    analyzer_material:
    collimation:
  member_scan_record_ids:
  critical_unknown_fields:
  relevant_unknown_fields:
  limitation: >
    Same instrument_config_id establishes only equality of the frozen recorded
    verified configuration vector and does not prove equality of unrecorded
    physical instrument state.
```

### acquisition_boundaries.csv

Fields (acquisition boundaries and normalization epochs remain separate concepts):

```text
boundary_index
previous_scan_record_id
next_scan_record_id
boundary_type
changed_fields
normalization_relevant
supporting_evidence
confidence
```

### normalization_compatibility.csv

Exactly 20,100 rows. Frozen columns:

```text
scan_a_record_id
scan_b_record_id
compatibility_status
decision_code
count_control_compatibility
instrument_config_compatibility
normalization_epoch_compatibility
verified_equal_fields
verified_conflicting_fields
critical_unknown_fields
relevant_unknown_fields
boundary_evidence
decision_reason
```

### normalization_compatibility_groups.yaml

Each group records:

```yaml
normalization_compatibility_group_id:
  identity_version: stage02r_normalization_compatibility_group_v1
  fingerprint:
  status:
  normalization_epoch_id:
  count_control_mode:
  instrument_config_id:
  member_scan_record_ids:
  acquisition_state_ids:
  critical_unknown_fields:
  relevant_unknown_fields:
  pair_count:
  internal_pair_status_counts:
    supported:
    conditionally_supported:
    not_supported:
    unresolved:
  clique_audit_status:
  compatibility_basis:
  limitations:
  normalization_performed: false
```

## TESTS

Mandatory suite: A003-T01 through A003-T16.

### A003-T01 — Canonical A-002 input integrity

Verify reviewed A-002 checkpoint/artifact identities required by execution.
If `scan_point_auxiliary.csv` is used, verify its external identity through
`external_artifacts.yaml` before classification, including exact byte size and SHA-256.

### A003-T02 — Complete scan coverage

Verify `201 A-002 scans == 201 scan_classification rows`. No silent exclusion.

### A003-T03 — Exact acquisition-state identity

Verify the exact vector `count_control_mode`, `scan_variable_raw`, `lattice_state_id`,
`UB_state_id`, and §acquisition_state_v1 canonical payload, UTF-8/no BOM/LF/final LF,
full SHA-256 and deterministic even-length collision extension.
Shuffled input order MUST NOT alter IDs or memberships.

### A003-T04 — Exact instrument-config identity

Verify the exact vector `monochromator_material`, `analyzer_material`, `collimation`
and §instrument_config_v1 canonical serialization/fingerprint/collision behavior.
Shuffled input order MUST NOT alter IDs or memberships.

### A003-T05 — Missing-is-not-equality

Shared missing/not-recorded filter, attenuation, reflection, mosaic, hardware
identity and other unresolved beam-path values MUST NOT enter equality evidence
or either frozen v1 identity fingerprint (§PURPOSE / SCOPE).

### A003-T06 — Complete pairwise count/control-mode separation

Verify `normalization_compatibility rows = 20100`, exactly once per unordered pair.
No cross-count-control-mode pair may be `supported` or `conditionally_supported`.

### A003-T07 — Lattice/UB preservation

All reviewed 2 lattice states and 4 UB states remain represented.
Lattice/UB changes may alter acquisition state but MUST NOT alone create a normalization epoch.

### A003-T08 — Recorded configuration-change detection

Every verified change in a normalization-relevant recorded configuration field
creates/marks a normalization-relevant boundary or has an explicit documented reason why it does not.

### A003-T09 — No coordinate/config over-splitting

Changes solely in scan variable, h/k/l/e, Ei/Ef, ordinary scan coordinates,
temperature or raw format MUST NOT alter `instrument_config_id`.

### A003-T10 — Verified conflict decision rule

A synthetic verified normalization-relevant conflict MUST produce
`compatibility_status = not_supported`, `decision_code = verified_configuration_conflict`,
unless Step 1 correctly takes precedence. Decision-tree ordering MUST be tested.

### A003-T11 — Critical unknowns prevent supported

If count-control mode and instrument-config ID agree, no verified conflict exists
and critical unknowns remain, the result MUST be `conditionally_supported`, NOT `supported`.

### A003-T12 — Spectral blindness

Changing/permuting detector intensity values while holding acquisition metadata
fixed MUST NOT change `acquisition_state_id`, `instrument_config_id`,
`normalization_epoch_id`, pairwise compatibility or normalization group membership.

### A003-T13 — Normalization-epoch determinism

Epochs MUST be deterministic under input reordering. A time gap/day boundary
alone MUST NOT create an epoch; neither may lattice/UB/scan-variable/temperature/raw-format changes alone.

### A003-T14 — No normalization arithmetic

Static/output audit confirms no detector / monitor, counts / time, relative scale,
absolute scale or ki/kf correction calculation (§STOP CONDITION).

### A003-T15 — No spectral / CEF scope

Source/configuration contains no background model, peak search, peak fit,
historical target-energy logic, F002/F004 matching, resolution calculation
or CEF model/assignment/fitting (§STOP CONDITION).

### A003-T16 — Exact-key group clique audit

Every emitted group has all internal pair statuses in `{supported, conditionally_supported}`;
none may be `not_supported` or `unresolved`. Group status MUST reproduce the frozen
group-status rules. No connected-component grouping is allowed.

## PASS CRITERIA

A-003 passes iff:

1. A003-T01 through A003-T16 all PASS.
2. All frozen identity, serialization, epoch, ordered pairwise-decision and grouping contracts above are satisfied.
3. All 201 scans and exactly 20100 unordered pair decisions are represented; canonical scan IDs are preserved.
4. Every emitted group passes the full internal clique audit and frozen status rules.
5. All unresolved/missing metadata rules and both frozen unknown-field sets are preserved and propagated.
6. No operation prohibited by §STOP CONDITION is performed.
7. Required deterministic outputs, provenance and test report are complete and sufficient for scientific review.
8. If the external A-002 auxiliary artifact is used, its exact byte size and SHA-256 match the canonical `external_artifacts.yaml` identity.

## STOP CONDITION

A-003 stops after production and validation of all nine required artifacts in §OUTPUTS.
It MUST stop before any of the following prohibited operations:

- Detector/monitor normalization; counts/time normalization.
- Relative or absolute intensity scaling; ki/kf correction.
- Background subtraction or modelling; TAS resolution calculation.
- Spectral plotting for discovery; feature discovery/search, peak search or peak fitting.
- Historical-target comparison/energy logic; F002/F004 matching.
- CEF analysis, assignment, modelling or fitting.

Mandatory transition: `W02-02R-A-003 → STOP → 02 - TAIPAN Data Reduction → Project / Scientific Review`.
A-003 completion MUST NOT authorize downstream execution automatically.

## UNRESOLVED SEMANTICS

A-003 does not need to resolve `mode=0`, raw q, filter state, higher-order suppression,
attenuation, monochromator/analyzer reflection or mosaic, detector/monitor hardware
identity, unresolved focusing/aperture fields, other unresolved auxiliary motors
or temperature-channel physical mapping. These unknowns MUST remain explicit.
A successful A-003 may legitimately yield predominantly `conditionally_supported` compatibility.

## RISKS

### R1 — false physical equivalence

Risk: the same instrument-config ID is mistaken for complete hardware equality.
Control: `recorded_verified_configuration_equivalence_only` and explicit unknown-field propagation.

### R2 — missing metadata treated as equality

Risk: absent filter/attenuation/reflection/hardware metadata become equality evidence.
Control: §PURPOSE / SCOPE and A003-T05/A003-T11; critical unknowns block `supported`.

### R3 — counting-mode conflation

Risk: both monitor- and time-controlled scans contain detector/monitor/time fields.
Control: pairwise Step 1 terminates count-control conflicts as `not_supported`.

### R4 — false transitivity

Risk: pair compatibility is incorrectly assumed transitive.
Control: all 20,100 decisions, exact-key partition and full clique audit; no connected components.

### R5 — over-fragmentation by acquisition coordinates

Risk: Q/energy/lattice/UB/sample state is mistaken for normalization hardware state.
Control: frozen instrument-config vector, normalization-epoch rules and normalization-group key.

### R6 — premature normalization

Risk: compatibility classification drifts into detector/monitor arithmetic.
Control: A003-T14, §STOP CONDITION and `normalization_performed: false`.
