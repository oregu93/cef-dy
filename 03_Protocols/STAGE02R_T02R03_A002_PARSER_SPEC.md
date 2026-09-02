---
title: "DyFeO3 — Stage 02R W02-02R-A-002 verified parser specification"
type: work_job_specification
project_id: CEF-Dy
stage_id: M02R
task_id: T-02R-03
job_id: W02-02R-A-002
status: frozen
version: "1.0"
updated: 2026-09-02
language_content: ru
language_metadata: en
---

# W02-02R-A-002 — VERIFIED PARSER + CANONICAL FILE/SCAN INVENTORIES

## STATUS

```yaml
stage_id: M02R
task_id: T-02R-03
job_id: W02-02R-A-002
job_title: Verified parser + canonical file/scan inventories
dataset_id: EXP-TAIPAN-001

design_status: approved
specification_status: frozen
execution_status: not_started
execution_authorized: true_after_canonical_commit

parent_checkpoint: W02-02R-A-001
execution_context_target: W02-Lin

raw_data_access: read_only
execution_class: production_parser_and_inventory

scan_identity_version: stage02r_scan_record_v1
lattice_state_identity_version: stage02r_lattice_state_v1
ub_state_identity_version: stage02r_ub_state_v1
serialization_contract_version: stage02r_a002_serialization_v1
```

Эта спецификация фиксирует утверждённый Project Control design для второго Work job задачи `T-02R-03`.

Execution разрешается только после canonical Git commit этой frozen specification и отдельного re-entry в W02-Lin.

A-002 не должен расширять scope до:

- acquisition-block reconstruction;
- instrument-configuration inference;
- instrument-block inference;
- normalization;
- resolution calculation;
- spectral feature discovery;
- CEF analysis.

---

# GOAL

Цель `W02-02R-A-002` — превратить reviewed reconnaissance `W02-02R-A-001` в воспроизводимый verified parser и canonical inventory layer для `EXP-TAIPAN-001`, сохранив существенную TAS acquisition information без normalization, instrument-block inference, spectral interpretation или CEF analysis.

Рабочая цепочка:

```text
EXP-TAIPAN-001 raw files
        ↓
verified format-aware parser
        ↓
canonical file inventory
        ↓
verified 1:1 file ↔ logical-scan mapping
        ↓
canonical scan inventory
        ↓
point-level TAS acquisition tables
        ↓
quality / semantic diagnostics
        ↓
reviewable A-002 checkpoint
```

A-002 должен:

1. production-parse все 201 raw files;
2. поддержать все 21 structural format families, выявленные A-001;
3. сохранить deterministic archive-entry identity и source checksums;
4. реализовать verified `1 file = 1 logical scan` relationship для данного archive;
5. сохранить general `file_scan_map` provenance abstraction;
6. извлечь canonical scan-level metadata;
7. извлечь point-level TAS data без spectral reduction;
8. проверить semantic relationships:
   - `e / Ei / Ef`;
   - `en / e`;
   - `h/k/l / q`;
   - `mode=0`;
9. оставить quantities unresolved, если evidence недостаточно;
10. сохранить raw:
    - `detector`;
    - `monitor`;
    - `time`;
    - `det_err`;
11. сохранить distinction:
    - monitor-controlled acquisition;
    - time-controlled acquisition;
12. сохранить multiplicity lattice/UB states;
13. сохранить unresolved filter/higher-order metadata без synthetic defaults;
14. различать verified `PG` material и unverified reflection/mosaic;
15. сохранить unresolved auxiliary motors;
16. реализовать duplicate/collision semantics и diagnostic-only repeat signatures;
17. обеспечить deterministic identifiers и cross-platform deterministic outputs;
18. завершиться до A-003.

Основной scientific question:

> **Можно ли воспроизводимо и без CEF assumptions преобразовать каждый raw TAIPAN file в canonical scan-level и point-level acquisition representation с verified TAS semantics и explicit unresolved metadata?**

---

# INPUTS

## Canonical repository state

Canonical reviewed A-001 capture:

```yaml
repository: oregu93/cef-dy
branch: main
A001_canonical_capture_commit: 55b54c9b9e4510cf993cb2b968b44aeefd497893
```

Execution A-002 должен начинаться от canonical commit, в котором зафиксирована эта frozen specification.

Исполнитель должен записать exact execution commit в checkpoint/provenance.

---

## Dataset

```yaml
dataset_id: EXP-TAIPAN-001
instrument: TAIPAN
experiment_id: 1296
```

Dataset root разрешается только через:

```text
configs/local_paths.yaml
```

Machine-local absolute path:

- runtime only;
- не является project identity;
- не участвует в deterministic identifiers;
- не помещается в tracked outputs как execution-machine path.

---

## Canonical project inputs

Минимально:

```text
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
03_Protocols/STAGE02R_T02R03_A002_PARSER_SPEC.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md

00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml
```

---

## Reviewed A-001 empirical inputs

Canonical checkpoint:

```text
02_Work_Checkpoints/W02-02R-A-001.md
```

Canonical reviewed result directory:

```text
04_Results/Stage02R/W02-02R-A-001/
```

Required A-001 inputs:

```text
file_inventory_preliminary.csv
format_catalogue.yaml
parsed_header_metadata_sample.jsonl
field_semantics_report.yaml
reconnaissance_diagnostics.csv
provenance_manifest.yaml
test_report.yaml
```

A-002 MUST verify the reviewed checksums before relying on these artifacts.

A-002 MUST NOT silently regenerate A-001 and replace the reviewed empirical baseline.

---

## Source code / configuration

Required A-002 source/configuration includes at minimum:

```text
scripts/stage02r/a002_parser.py
scripts/stage02r/a002_schema_registry.yaml
```

Executable schema registry:

```text
scripts/stage02r/a002_schema_registry.yaml
```

Result package MUST contain the exact execution snapshot:

```text
04_Results/Stage02R/W02-02R-A-002/parser_schema_registry.yaml
```

There must be one source registry and one immutable execution snapshot of that registry, not two independently edited registries.

---

## Raw source access

```yaml
RAW_DATA_ACCESS: read_only
```

A-002 may:

```text
read
stat
hash
parse
```

raw archive files.

A-002 MUST NOT:

```text
modify raw files
rename raw files
move raw files
delete raw files
write outputs inside raw tree
write caches inside raw tree
write temporary files inside raw tree
```

---

## Execution environment

Execution target:

```yaml
execution_context: W02-Lin
```

A-002 MUST use a local isolated Python environment.

Preferred repository-local environment:

```text
.venv/
```

Create when needed using:

```bash
python3 -m venv .venv
```

or use an already existing equivalent project `.venv`.

Install dependencies from canonical:

```text
requirements.txt
```

The `.venv/` directory is machine-local and MUST NOT be tracked.

No Parquet dependency is required or added for A-002.

Checkpoint/provenance MUST record:

```text
python_version
python_implementation
execution_context
platform
requirements_file_checksum
installed_dependency_versions
```

The absolute `.venv` path MUST NOT be treated as project identity.

---

# VERIFIED A-001 FACTS

Следующие facts являются reviewed empirical inputs A-002.

Они могут и должны проходить production consistency checks, но не являются speculative assumptions.

## Archive census

```yaml
regular_files: 201
readable_files: 201
file_extension: .dat
exact_content_duplicates: 0
raw_tree_integrity: unchanged
```

Reviewed pre/post census digest:

```text
bb7a3f99710a9463a7697ebbf23cce3fd5c02936b9788df72cac3cc0f90a1e95
```

---

## File ↔ logical scan relationship

Для `EXP-TAIPAN-001` verified:

```text
1 archive file = 1 logical scan
```

A-001 evidence:

```text
one numeric data block per file
one unique scan ID per file
scan ID matches filename identity
one unique raw_file reference
```

A-002 может использовать эту relationship как reviewed dataset-specific fact.

General provenance abstraction `file_scan_map.csv` сохраняется обязательно.

---

## Structural format families

```yaml
structural_format_families: 21
deterministic_representatives: 38
```

Все families используют один broad UTF-8 text/header grammar и различаются главным образом:

```text
declared-column schemas
scan-variable schemas
```

Full SHA-256 raw-format fingerprints сохранены A-001.

A-002 MUST support all 21 reviewed families.

---

## Scanned-variable semantics

A-001 выявил 19 значений `def_x`.

Основные:

```text
en   85
s1   33
qk   16
s2   14
sgl  12
ql    9
sgu   9
```

плюс lower-frequency angular/aperture variables.

Во всех 201 files:

```text
def_y = detector
```

Fields:

```text
command
builtin_command
```

существуют, но пусты.

Следовательно, A-002 не должен полагаться на command strings для primary scan-variable semantics.

---

## Stable/common point-level fields

Во всех 201 files объявлены:

```text
q
h
k
l
e
ei
vei
ef

time
detector
det_err
monitor
```

Это raw/archive facts.

Не все физические interpretations этих fields уже verified.

---

## Counting control

A-001 verified:

```yaml
monitor_controlled_files: 103
time_controlled_files: 98
```

через `preset_channel`.

Эта distinction должна сохраняться.

---

## TAS motors

Recorded:

```text
M1
M2
S1
S2
A1
A2
```

и additional:

```text
tilt
translation
goniometer
aperture-related fields
```

Часть auxiliary motor semantics остаётся unresolved.

---

## Monochromator / analyser / collimation

Во всех files recorded:

```yaml
monochromator_material: PG
analyzer_material: PG
collimation: o-40-40-o
```

Focusing-related PG/Cu columns также присутствуют.

Это не подтверждает автоматически:

```text
monochromator reflection
analyser reflection
monochromator mosaic
analyser mosaic
```

---

## Lattice / UB multiplicity

A-001 identified:

```yaml
lattice_parameter_sets: 2
UB_matrices: 4
```

A-002 MUST NOT assign one global lattice or UB matrix to the complete dataset.

---

## Environment

Throughout archive:

```text
temperature
4 sensor channels
4 setpoint channels
```

A-002 сохраняет raw channels и отдельно verified canonical mappings.

---

## Chronology

Verified proper header timestamps cover:

```text
2023-08-29 11:53:06
through
2023-09-06 07:44:52
```

Filesystem modification times:

```text
filesystem_metadata_only
```

и не являются acquisition timestamps.

---

# UNRESOLVED SEMANTICS

Главный conservative rule:

> Semantic verification проверяет корректность decision procedure.
> A-002 не обязан разрешить каждый raw field.

Допустимые исходы:

```text
verified
partially_verified
unresolved
not_recorded
not_applicable
```

Unresolved status является корректным результатом, если уникальная physical meaning не доказана.

---

## 1. `mode=0`

Observed:

```text
mode = 0
```

throughout archive.

Current status:

```text
raw field present
meaning unresolved
```

A-002 MUST NOT assume:

```text
mode=0 → fixed Ef
mode=0 → fixed Ei
mode=0 → elastic
mode=0 → TAS
```

без независимой проверки.

Bounded verification может использовать:

1. official TAIPAN/SICS semantics;
2. point-level `Ei`, `Ef`, `e`;
3. constant/variable behavior;
4. `def_x`;
5. cross-scan consistency.

Если unique interpretation не установлена:

```yaml
mode_raw: 0
mode_semantics:
mode_semantics_status: unresolved
```

---

## 2. `e / Ei / Ef`

Raw columns:

```text
e
ei
ef
```

present throughout.

A-002 должен проверить candidate relation, например:

\[
e = E_i-E_f.
\]

Relation не должна приниматься только из generic TAS convention.

### Frozen numerical tolerance rule

Raw numeric preservation не должен зависеть от uncontrolled binary floating-point round-trip.

Для semantic relation использовать raw token precision и Decimal-compatible parsing where practical.

Для source tokens `e`, `Ei`, `Ef`:

\[
\mathrm{tol}
=
\frac{1}{2}\mathrm{ulp}_{decimal}(e)
+
\frac{1}{2}\mathrm{ulp}_{decimal}(E_i)
+
\frac{1}{2}\mathrm{ulp}_{decimal}(E_f)
+
\mathrm{numerical\_guard}.
\]

Где:

```text
ulp_decimal(x)
```

— unit in the last represented decimal place source token.

`numerical_guard`:

- документируется;
- является negligible arithmetic guard;
- не основан на expected spectroscopy;
- не используется для скрытого расширения tolerance.

Для каждой checked row сохранять/репортировать:

```text
raw residual
row-level tolerance
pass/fail/status
```

Source values не изменяются для принудительного выполнения relation.

---

## 3. `en` versus `e`

`en` observed as `def_x` in 85 files.

`e` — numeric point-level column во всех 201 files.

A-002 должен проверить:

```text
meaning of def_x=en
mapping to raw e column
sign convention
units
point progression
```

Allowed result:

```text
en_e_mapping_status:
  verified
  partially_verified
  unresolved
```

String-name similarity недостаточна для alias mapping.

---

## 4. `h/k/l` versus `q`

Point-level:

```text
h
k
l
q
```

present.

`h/k/l` должны пройти bounded consistency checks как reciprocal-space coordinates.

Разрешается использовать:

```text
verified lattice
verified UB metadata
scan variable
recorded TAS geometry
general TAS kinematics
```

Не разрешается:

```text
UB refinement
lattice refinement
sample re-indexing
instrument-angle calibration
intensity-based geometry selection
```

Raw `q` remains unresolved until a unique documented/kinematic meaning is established.

Если meaning не established:

```yaml
q_semantics_status: unresolved
```

Это является successful conservative outcome.

---

## 5. `qh`

Explicit `qh` field не установлен A-001.

Это не означает absence reciprocal \(h\), поскольку point-level `h` записан.

A-002 должен различать:

```text
raw virtual/scanned-variable naming
```

и

```text
point-level reciprocal coordinate h
```

Synthetic raw `qh` field не создаётся.

---

## 6. Filters / higher-order suppression

Not explicitly recorded:

```text
filter identity
filter type
filter insertion/removal
PG-filter state
sapphire-filter state
higher-order suppression configuration
```

A-002 MUST NOT infer filter state from:

```text
TAIPAN default
manual examples
historical experiment knowledge
spectral appearance
```

Canonical status:

```text
filter_state: null
filter_state_status: not_recorded
```

или `unresolved`, если raw evidence существует, но meaning ambiguous.

---

## 7. Attenuation

Explicit attenuation state/identity not established.

Must remain:

```text
attenuation_state: null
attenuation_state_status: not_recorded_or_unresolved
```

если A-002 не обнаружит independently verifiable raw semantics.

---

## 8. PG reflection / mosaic

Verified:

```text
monochromator material = PG
analyzer material = PG
```

Not verified:

```text
reflection
mosaic
```

Required distinction:

```text
monochromator_material = PG
monochromator_reflection = null
monochromator_reflection_status = unverified

analyzer_material = PG
analyzer_reflection = null
analyzer_reflection_status = unverified
```

и analogous mosaic status.

---

## 9. Auxiliary motors

At least these semantics remain unresolved:

```text
sgl
sgu
stl
stu
PS_*
PA_*
```

A-002 preserves:

```text
raw field name
raw value/token
raw unit if declared
source column
semantic status
```

Verified mappings may be promoted only from legitimate TAS/TAIPAN evidence.

---

## 10. Detector / monitor hardware identity

Raw:

```text
detector
monitor
```

are verified count fields.

Hardware identity/configuration not established.

Do not invent:

```text
detector model
monitor model
dead-time correction
efficiency
absolute calibration
```

---

## 11. Exposure semantics

Count-control mode is verified.

Raw `time` must remain preserved.

A-002 MUST NOT assume one universal interpretation of `time` for both monitor- and time-controlled acquisition until semantics are verified.

---

## 12. Orientation auxiliary fields

Present but empty:

```text
plane_normal
ubconf
```

Keep them empty/unresolved.

Reference reflections remain not recorded unless raw evidence is newly verified.

---

## 13. Operating mode

Explicit TAS/two-axis/elastic/Be-filter flag was not identified.

`mode=0` cannot substitute for such a mode without proof.

---

# DATA MODEL

A-002 canonical data layer consists of:

```text
file_inventory.csv
scan_inventory.csv
file_scan_map.csv

scan_points.csv
scan_point_auxiliary.csv

parsed_header_metadata.jsonl

lattice_states.yaml
UB_states.yaml
```

No Parquet artifact is canonical or required.

---

## 1. `file_inventory.csv`

One row per archive entry.

Expected:

```text
201 rows
```

Frozen column order:

```text
file_record_id
dataset_id
source_file
source_checksum
file_size_bytes
file_extension
filesystem_mtime
filesystem_mtime_trust
raw_format_id
raw_format_fingerprint
file_role
parse_status
parse_message
duplicate_status
duplicate_group_id
raw_scan_id
file_scan_cardinality_status
quality_flag
quality_reasons
```

Definitions:

```text
file_record_id
    dataset-relative archive-entry identity

source_checksum
    byte-content identity

duplicate_group_id
    equal-content relationship across archive entries
```

For unchanged archive entries A-002 MUST preserve A-001 `file_record_id` exactly.

---

## 2. `scan_inventory.csv`

One row per logical scan.

Expected from reviewed A-001:

```text
201 rows
```

### Identity

Frozen fields include:

```text
scan_record_id
scan_record_fingerprint
scan_identity_version

dataset_id
experiment_id

raw_scan_id
scan_identity_status

primary_file_record_id
source_file
source_checksum
```

### Chronology

```text
acquisition_start_time
acquisition_end_time
acquisition_timestamp_source

sequence_index
sequence_status

filesystem_mtime
filesystem_mtime_trust
```

`sequence_index` is ZERO-BASED.

### Scan structure

```text
raw_format_id

scan_variable_raw
scan_variable_canonical
scan_coordinate_type

scan_start_derived
scan_stop_derived
scan_range_status
scan_point_count

def_x_raw
def_y_raw

command_raw
builtin_command_raw
```

`scan_start_derived` / `scan_stop_derived` may be populated only when raw scanned variable has a verified mapping to a point-level column.

Otherwise:

```text
scan_start_derived:
scan_stop_derived:
scan_range_status: unresolved_mapping
```

No range is derived from assumed aliases.

### Counting

```text
preset_channel_raw
count_control_mode
count_control_status

raw_time_field_status
raw_monitor_field_status
raw_detector_field_status
```

`count_control_mode`:

```text
monitor_controlled
time_controlled
unknown
```

### Energy

```text
mode_raw
mode_semantics
mode_semantics_status

Ei_summary_meV
Ef_summary_meV
Ei_variation_status
Ef_variation_status

energy_transfer_field_raw
energy_transfer_convention
energy_relation_status

en_e_mapping_status
```

Scan-level summary does not replace point-level values.

### Reciprocal space / geometry

```text
h_variation_status
k_variation_status
l_variation_status
q_semantics_status

lattice_state_id
UB_state_id

orientation_status
```

### Instrument metadata

```text
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

filter_state
filter_state_status

attenuation_state
attenuation_state_status
```

No:

```text
instrument_config_id
instrument_block_id
```

in A-002.

### Environment

```text
temperature_summary_K
temperature_variation_status

sensor_metadata_ref
setpoint_metadata_ref
```

### Repeat diagnostics

Allowed diagnostic fields:

```text
repeat_candidate_status
repeat_metadata_signature
repeat_candidate_count
repeat_candidate_basis
```

Forbidden:

```text
repeat_candidate_group_id
```

No repeat group is promoted in A-002.

### Quality

```text
quality_flag
quality_reasons

parser_schema_version
point_data_ref
```

---

## 3. `file_scan_map.csv`

Even though current archive is verified 1:1, preserve explicit general mapping.

Frozen columns:

```text
file_record_id
scan_record_id
relationship_role
mapping_status
mapping_evidence
```

Expected current result:

```text
201 mappings
relationship_role: primary
mapping_status: verified_1_to_1
```

---

## 4. Exact scan identity algorithm

Frozen version:

```yaml
scan_identity_version: stage02r_scan_record_v1
```

Canonical UTF-8 payload:

```text
stage02r_scan_record_v1
<dataset_id>
<file_record_id>
<raw_scan_id>
```

with:

- LF between lines;
- one final LF.

Conceptually exact bytes:

```text
stage02r_scan_record_v1\n
<dataset_id>\n
<file_record_id>\n
<raw_scan_id>\n
```

Compute:

```text
scan_record_fingerprint =
    SHA256(canonical_identity_payload)
```

Store full 64-hex SHA-256.

Initial display ID:

```text
SCAN-02R-<first 16 hex characters>
```

If a display-prefix collision occurs within dataset:

1. identify all colliding full fingerprints;
2. extend all colliding display IDs by two hex characters;
3. repeat deterministically until unique.

Algorithm MUST NOT depend on:

```text
absolute path
path separator
file traversal order
filesystem metadata
machine identity
```

`raw_scan_id` is stored independently and never replaced by `scan_record_id`.

---

## 5. `scan_points.csv`

This is canonical deterministic wide point-level table for stable/common fields.

Frozen column order:

```text
dataset_id
scan_record_id
file_record_id
point_index

q_raw
h_raw
k_raw
l_raw
e_raw
ei_raw
vei_raw
ef_raw

time_raw
detector_raw
det_err_raw
monitor_raw

M1_raw
M2_raw
S1_raw
S2_raw
A1_raw
A2_raw

source_data_line_number
```

Columns not available in a given structural schema remain empty canonical fields.

Schema does not change between rows/formats.

### Point indexing

```text
point_index
```

is:

```text
ZERO-BASED
```

and follows numeric-block source order exactly.

### Source line

```text
source_data_line_number
```

is:

```text
ONE-BASED physical source-file line number
```

where recoverable.

If not recoverable:

```text
empty canonical field
```

rather than an invented line number.

---

## 6. Raw numeric token preservation

Raw numeric preservation must avoid uncontrolled binary-float round-trip.

Parser should preserve raw token provenance and use Decimal-compatible parsing for deterministic decimal serialization where practical.

Canonical raw fields in `scan_points.csv` should preserve numeric source meaning without arbitrary precision reduction.

No thousands separators.

No locale-dependent formatting.

Numerically distinct source values must remain distinct.

---

## 7. `scan_point_auxiliary.csv`

This is REQUIRED.

Every declared point-level field not included in the frozen `scan_points.csv` wide schema must be preserved here.

Frozen columns:

```text
dataset_id
scan_record_id
file_record_id
point_index
raw_field_name
raw_value
raw_unit
semantic_status
source_column_index
```

`source_column_index` is the deterministic numeric-block column index according to declared source schema.

Its base convention MUST be documented by the parser. For this specification it is frozen as:

```text
source_column_index: ZERO-BASED
```

No declared numeric field may disappear merely because it lacks canonical physical semantics.

Examples include:

```text
auxiliary motors
temperature/environment channels
focusing-related fields
aperture fields
other format-specific numeric columns
```

---

## 8. Full header representation

Canonical artifact:

```text
parsed_header_metadata.jsonl
```

One JSON object per file/scan.

Raw header MUST NOT be reduced to a lossy dictionary.

Each object includes:

```text
file_record_id
scan_record_id
source_file
source_checksum
raw_format_id
```

and an ordered structure:

```yaml
raw_header_records:
  - source_line_number:
    raw_key:
    raw_value:
```

This preserves:

```text
duplicate keys
source order
empty values
```

Verified canonical mappings may additionally be represented as a mapping:

```text
canonical_header_mappings
```

but cannot replace `raw_header_records`.

Original raw file remains authoritative source.

---

## 9. Lattice states

Canonical state identity version:

```yaml
lattice_state_identity_version: stage02r_lattice_state_v1
```

Identity is based on ordered tuple:

```text
a
b
c
alpha
beta
gamma
```

### Numeric representation

Must:

- be locale independent;
- derive from parsed decimal source values;
- normalize numerical negative zero to zero;
- preserve numerically distinct source values;
- use no arbitrary merge tolerance.

Nearby but numerically distinct values remain distinct states unless exact canonical decimal representation is equal.

Canonical payload contains:

```text
stage02r_lattice_state_v1
<a>
<b>
<c>
<alpha>
<beta>
<gamma>
```

with LF separators and final LF.

Compute:

```text
lattice_state_fingerprint =
    SHA256(canonical_payload)
```

Store full 64-hex fingerprint.

Initial display ID:

```text
LAT-02R-<first 16 hex characters>
```

Use same deterministic two-hex-character collision-extension rule as scan IDs.

`lattice_states.yaml` stores:

```yaml
lattice_state_id:
  lattice_state_fingerprint:
  lattice_state_identity_version:
  a_A:
  b_A:
  c_A:
  alpha_deg:
  beta_deg:
  gamma_deg:
  source_scan_record_ids:
```

Expected reviewed A-001 multiplicity:

```text
2 states
```

A discrepancy is reported; it is not silently tolerance-merged.

---

## 10. UB states

Canonical state identity version:

```yaml
ub_state_identity_version: stage02r_ub_state_v1
```

Identity is based on canonical row-major 3×3 matrix:

```text
u11 u12 u13
u21 u22 u23
u31 u32 u33
```

Numeric representation follows same rules:

- locale independent;
- Decimal-compatible source-value basis;
- negative numerical zero → zero;
- no arbitrary tolerance merging;
- numerically distinct source values preserved.

Canonical payload:

```text
stage02r_ub_state_v1
<u11>
<u12>
<u13>
<u21>
<u22>
<u23>
<u31>
<u32>
<u33>
```

with LF separators and final LF.

Compute:

```text
UB_state_fingerprint =
    SHA256(canonical_payload)
```

Store full 64-hex fingerprint.

Display ID starts:

```text
UB-02R-<first 16 hex characters>
```

and uses deterministic two-character collision extension.

`UB_states.yaml` stores:

```yaml
UB_state_id:
  UB_state_fingerprint:
  ub_state_identity_version:
  matrix:
  source_scan_record_ids:
  lattice_state_id:
  semantic_status:
```

Expected reviewed multiplicity:

```text
4 states
```

No UB refinement is allowed.

---

# SERIALIZATION CONTRACT

Frozen version:

```yaml
serialization_contract_version: stage02r_a002_serialization_v1
```

---

## General tracked/generated text artifacts

```yaml
encoding: UTF-8
line_ending: LF
final_newline: yes
```

No platform-specific object tags or serialization.

---

## CSV

Frozen rules:

```yaml
delimiter: ","
quote_character: '"'
line_terminator: LF
column_order: frozen_per_artifact
missing_canonical_value: empty_field
locale_dependent_formatting: forbidden
thousands_separators: forbidden
```

CSV writers must use deterministic quoting under the frozen writer contract.

Raw empty textual header values are represented separately in `parsed_header_metadata.jsonl` and remain distinguishable through raw records/status metadata.

---

## JSONL

Rules:

```text
UTF-8
LF
one JSON object per line
stable key ordering for mapping objects
compact deterministic separators
final newline
```

Raw header record list ordering follows source-file order and MUST NOT be sorted.

---

## YAML

Rules:

```text
UTF-8
LF
stable deterministic key ordering policy
no platform-specific object tags
final newline
```

Mapping ordering policy must be frozen in implementation and documented.

---

## Execution timestamps and determinism

Do not put generation timestamps inside artifacts whose byte identity is required to be deterministic unless timestamp is explicitly excluded from canonical-content comparison.

`provenance_manifest.yaml` may contain execution timestamps.

Deterministic scientific-content digests MUST NOT depend on these timestamps.

---

## Artifact digests

Distinguish:

```text
byte_sha256
```

and where required:

```text
canonical_content_sha256
```

`byte_sha256` may be claimed only if frozen writer contract guarantees byte identity.

If an artifact intentionally contains execution-specific metadata, use a canonical scientific-content digest that excludes explicitly documented non-scientific volatile fields.

---

# PARSER ARCHITECTURE

## 1. Overall design

Use:

```text
common TAIPAN text grammar
        +
reviewed format fingerprint registry
        +
declared-schema parser
        +
verified semantic mapping layer
```

Preferred architecture:

```text
raw bytes
   ↓
encoding validation
   ↓
common ordered header parser
   ↓
format fingerprint verification
   ↓
declared-column schema parser
   ↓
numeric-block parser
   ↓
raw structured representation
   ↓
bounded semantic verification
   ↓
canonical inventories + point tables
```

Do not implement 21 unrelated parsers unless actual format differences require it.

---

## 2. Schema registry

Executable registry:

```text
scripts/stage02r/a002_schema_registry.yaml
```

For every reviewed format:

```yaml
raw_format_id:
raw_format_fingerprint:

column_names:
scan_variable_schema:

verified_mappings:
unresolved_fields:

required_header_keys:
optional_header_keys:

parser_rules:
```

The result package contains exact execution snapshot:

```text
parser_schema_registry.yaml
```

Provenance MUST record:

```text
source_registry_checksum
result_snapshot_checksum
registry_snapshot_match: true
```

The snapshot MUST correspond exactly to registry bytes/content used for execution.

No second independently maintained registry is permitted.

---

## 3. Header parser

Preserve:

```text
source line number
raw key
raw textual value
source order
duplicate keys
empty values
```

Canonical mappings are additive.

Specifically empty:

```text
command
builtin_command
plane_normal
ubconf
```

must not be synthesized from other sources.

---

## 4. Numeric parser

Rules derive from declared source column schema.

For every numeric row:

```text
declared column count
==
parsed token count
```

unless a format-specific reviewed exception exists.

Flag explicitly:

```text
short row
long row
non-numeric token
silent truncation risk
column count mismatch
```

No semantic mapping from unverified index position.

---

## 5. Raw token / numeric architecture

For every numeric token, parser should retain sufficient provenance for:

- deterministic decimal serialization;
- semantic precision tests;
- exact source-value audit where necessary.

Decimal-compatible parsing is preferred for canonical numeric text handling.

Binary floating-point may be used for bounded calculations only if it does not overwrite source-token representation.

---

## 6. Cross-format semantic layer

Canonical field mappings may differ across formats only when explicitly verified.

Same raw spelling does not automatically imply same semantics.

Different raw spellings do not automatically imply equivalence.

Mappings belong in the reviewed schema registry / semantic verification layer.

---

## 7. Deterministic ordering

### `file_inventory.csv`

Frozen ordering:

```text
source_file ascending by canonical dataset-relative UTF-8 representation
```

### `scan_inventory.csv`

Output row ordering is deterministic.

Preferred scientific chronology where verified:

```text
verified acquisition_start_time
raw_scan_id
source_file
```

If timestamp missing/unresolved:

- chronology status remains explicit;
- deterministic archive identity may be used for output ordering;
- output ordering MUST NOT be represented as real acquisition chronology.

### `file_scan_map.csv`

Sort by:

```text
file_record_id
scan_record_id
```

### `scan_points.csv`

Sort by:

```text
scan_record_id
point_index
```

### `scan_point_auxiliary.csv`

Sort by:

```text
scan_record_id
point_index
source_column_index
raw_field_name
```

Output order MUST NOT depend on:

```text
filesystem enumeration order
directory traversal implementation
thread scheduling
hash-map ordering
OS
```

---

## 8. Cross-platform deterministic path handling

Dataset-relative source path canonicalization uses:

```text
/
```

as logical separator.

IDs MUST NOT depend on native separator.

Windows-style and POSIX-style representation of same logical relative path must produce the same archive-entry identity after canonical path normalization.

---

# ALGORITHM

## A002-01 — Re-entry, isolated environment and input verification

1. Verify canonical Git commit containing frozen A-002 specification.
2. Verify branch/repository state.
3. Verify canonical A-001 checkpoint.
4. Verify checksums of all seven reviewed A-001 artifacts.
5. Establish isolated Python environment:
   ```bash
   python3 -m venv .venv
   ```
   or verify existing project `.venv`.
6. Install/use dependencies from canonical:
   ```text
   requirements.txt
   ```
7. Record:
   ```text
   python_version
   python_implementation
   execution_context
   platform
   requirements_file_checksum
   installed_dependency_versions
   ```
8. Confirm no Parquet-specific dependency is required for A-002.
9. Resolve `EXP-TAIPAN-001` through `configs/local_paths.yaml`.
10. Confirm raw dataset readable.
11. Confirm all output/temp destinations are outside raw root.
12. Capture execution-machine local path values privately for leakage testing, not as canonical project identities.

If A-001 checksums mismatch or canonical requirements state is inconsistent:

```text
STOP
```

before production parsing.

---

## A002-02 — Raw census reconciliation

Perform read-only census:

```text
dataset-relative path
file size
SHA-256
```

Compare with reviewed A-001 archive.

Expected:

```text
201 regular files
same logical source entries
same SHA-256 values
```

Archive mutation is not silently accepted.

If dataset changed relative to reviewed A-001:

```text
STOP / Project Control review required
```

because the empirical baseline has changed.

---

## A002-03 — Verify all format-family memberships

For all 201 files:

1. compute structural descriptor using frozen A-001 descriptor version;
2. compute full fingerprint;
3. map to reviewed format catalogue;
4. verify membership in one of 21 known families.

Expected:

```text
21 reviewed families
201/201 files assigned
0 unknown families
```

New fingerprint:

```text
parse_status: blocked_new_format
```

and A-002 cannot silently continue as PASS.

---

## A002-04 — Production ordered header parsing

Parse every header into non-lossy ordered representation.

Preserve:

```text
source line numbers
raw keys
raw values
duplicate keys
empty fields
declared columns
def_x
def_y
raw scan ID
raw_file
timestamps
instrument metadata
lattice/UB metadata
environment metadata
```

Typed canonical mappings only where verified.

---

## A002-05 — Production numeric-block parsing

For every file:

1. identify exactly one numeric block;
2. parse declared column schema;
3. parse every row;
4. assign:
   ```text
   point_index = ZERO-BASED numeric-block row order
   ```
5. capture:
   ```text
   source_data_line_number = ONE-BASED physical file line number
   ```
   where recoverable;
6. validate row width;
7. preserve all source numeric fields;
8. populate stable/common fields into `scan_points.csv`;
9. populate every remaining declared field into `scan_point_auxiliary.csv`.

No declared numeric field may be silently dropped.

---

## A002-06 — Verify 1:1 file ↔ scan mapping

For every file verify:

```text
one numeric block
one raw scan ID
raw scan ID consistent with source identity
one logical scan
```

Build explicit:

```text
file_scan_map.csv
```

Expected:

```text
201 files
201 logical scans
201 primary mappings
```

If a mismatch appears, do not force reviewed assumption onto changed evidence.

Report and fail/review.

---

## A002-07 — Generate deterministic scan identity

Use exactly:

```yaml
scan_identity_version: stage02r_scan_record_v1
```

Payload:

```text
stage02r_scan_record_v1
<dataset_id>
<file_record_id>
<raw_scan_id>
```

UTF-8, LF separators, one final LF.

Compute full:

```text
scan_record_fingerprint = SHA256(payload)
```

Store all 64 hex characters.

Generate initial:

```text
SCAN-02R-<16 hex>
```

Resolve collisions by extending all colliding IDs by two hex characters per iteration until unique.

Verify independence from:

```text
absolute path
native path separator
traversal order
filesystem mtime
machine identity
```

---

## A002-08 — Build final canonical file inventory

Promote reviewed A-001 preliminary inventory into:

```text
file_inventory.csv
```

Preserve reviewed archive-entry IDs for unchanged inputs.

Add final parse/quality disposition.

No file silently disappears.

---

## A002-09 — Verify counting-control semantics

Using verified `preset_channel` semantics classify:

```text
monitor_controlled
time_controlled
unknown
```

Reviewed expectation:

```text
103 monitor_controlled
98 time_controlled
```

Mismatch must be reported rather than forced.

Preserve point-level:

```text
time_raw
monitor_raw
detector_raw
det_err_raw
```

for every applicable point.

---

## A002-10 — Verify `e / Ei / Ef` convention

Across all usable rows:

1. preserve source numeric tokens;
2. parse Decimal-compatible values where practical;
3. test documented candidate relation(s);
4. calculate raw residual;
5. derive row-level tolerance from represented decimal precision:
   \[
   \mathrm{tol}
   =
   0.5\,\mathrm{ulp}_{decimal}(e)
   +
   0.5\,\mathrm{ulp}_{decimal}(E_i)
   +
   0.5\,\mathrm{ulp}_{decimal}(E_f)
   +
   \mathrm{numerical\_guard};
   \]
6. report residual and tolerance;
7. evaluate consistency across formats/scans.

Classify:

```text
verified_global
verified_with_exceptions
format_dependent
unresolved
```

Do not modify raw source values.

No tolerance may derive from expected peak energies or spectroscopy.

---

## A002-11 — Verify `en ↔ e`

For all scans with:

```text
def_x = en
```

test whether scan control variable maps to point-level `e`.

Use:

```text
raw metadata
point progression
TAIPAN semantics
e/Ei/Ef convention results
```

Do not alias from name similarity alone.

Record:

```text
en_e_mapping_status
```

as:

```text
verified
partially_verified
unresolved
```

---

## A002-12 — Resolve or preserve `mode=0`

Use bounded evidence only:

```text
official TAIPAN / ANSTO semantics
Ei/Ef/e behavior
constant/variable energy patterns
def_x
cross-scan consistency
```

No spectral intensity.

No instrument calibration.

Only promote semantic meaning if unique evidence supports it.

Otherwise preserve:

```yaml
mode_raw: 0
mode_semantics:
mode_semantics_status: unresolved
```

---

## A002-13 — Verify `h/k/l` semantics

Perform bounded reciprocal-coordinate consistency tests using:

```text
qk scans
ql scans
other verified reciprocal scan variables
lattice states
UB states
recorded geometry where appropriate
```

Goal is only field-semantic verification.

MUST NOT perform:

```text
UB refinement
lattice refinement
sample re-indexing
instrument-angle calibration
intensity-based geometry choice
```

---

## A002-14 — Investigate raw `q`

Test only documented or kinematically justified candidate meanings.

Permitted examples:

```text
q versus |Q(hkl,lattice)|
q versus documented TAIPAN virtual coordinate
q variation versus verified scan variable
```

No unrestricted search for a mathematical quantity that happens to correlate.

If unique interpretation not established:

```yaml
q_semantics_status: unresolved
```

Raw `q` remains in `scan_points.csv`.

---

## A002-15 — Build deterministic lattice states

Parse all lattice tuples.

Use identity:

```text
stage02r_lattice_state_v1
```

Canonical ordered tuple:

```text
a b c alpha beta gamma
```

Numeric rules:

```text
Decimal-compatible
locale-independent
negative zero → zero
no tolerance merging
preserve numerical distinctions
```

Compute full SHA-256 and display IDs using frozen collision algorithm.

Reviewed expected multiplicity:

```text
2
```

A different exact multiplicity is diagnostic and requires review rather than forced merging.

---

## A002-16 — Build deterministic UB states

Parse available UB matrices.

Use identity:

```text
stage02r_ub_state_v1
```

Canonical row-major 3×3 values.

Apply same numeric and collision rules as lattice IDs.

No UB refinement.

Reviewed expected multiplicity:

```text
4
```

Unexpected multiplicity is reported.

---

## A002-17 — Preserve optics semantics

Where raw metadata verify:

```text
monochromator_material = PG
analyzer_material = PG
collimation = o-40-40-o
```

preserve those facts.

Do NOT populate from default/manual assumptions:

```text
reflection
mosaic
filter
attenuation
```

Focusing-related numeric fields remain preserved in point-wide or auxiliary representation according to frozen schema.

---

## A002-18 — Preserve auxiliary motors

For every declared motor field:

1. retain raw field name;
2. retain raw token/value;
3. retain unit if declared;
4. retain source column index;
5. assign semantic status.

Verified:

```text
M1/M2
S1/S2
A1/A2
```

are represented in stable wide table.

Unresolved fields such as:

```text
sgl/sgu/stl/stu
PS_*
PA_*
```

remain raw-labelled in `scan_point_auxiliary.csv` unless independently verified.

---

## A002-19 — Parse environment metadata

Preserve:

```text
temperature
sensor channels
setpoint channels
other declared environment numeric fields
```

Stable/common environment fields not in `scan_points.csv` MUST still appear in `scan_point_auxiliary.csv`.

Do not collapse several temperature-like channels into one canonical temperature without evidence.

---

## A002-20 — Construct chronology

Populate:

```text
acquisition_start_time
acquisition_end_time
```

only where corresponding raw timestamps exist and their semantics are verified.

If only one timestamp endpoint exists:

- preserve available endpoint;
- leave other endpoint null.

Never synthesize end time from:

```text
filesystem mtime
assumed duration
point count
count-control preset
```

unless a separately verified raw rule explicitly defines it.

`sequence_index`:

```text
ZERO-BASED
```

Primary chronology ordering:

```text
verified acquisition timestamp
```

Tie breakers:

```text
raw_scan_id
source_file
```

If timestamp missing/unresolved:

- preserve chronology status;
- deterministic archive identity may order output;
- this must not be labelled true acquisition chronology.

Check:

```text
end < start
duplicate timestamps
unresolved timestamp semantics
```

---

## A002-21 — Duplicate semantics

Recalculate SHA-256.

Reviewed expected:

```text
exact_content_duplicates = 0
```

If duplicates appear due changed source state, do not collapse them.

Distinct archive entries with equal content receive:

```text
duplicate_group_id
```

Regression behavior remains implemented independent of current count.

---

## A002-22 — Scan-ID collision semantics

Verify raw scan ID uniqueness.

If same raw scan ID exists in distinct archive entries:

```text
scan_id_collision_status: true
```

Do not merge.

Canonical `scan_record_id` remains unique by frozen identity payload.

---

## A002-23 — Repeat metadata diagnostics only

A-002 MUST NOT produce:

```text
repeat_candidate_group_id
```

because grouping belongs to A-003.

A-002 may calculate deterministic:

```text
repeat_metadata_signature
```

using only verified acquisition metadata.

May report:

```text
repeat_candidate_status
repeat_metadata_signature
repeat_candidate_count
repeat_candidate_basis
```

Possible signature inputs, only when verified:

```text
scan variable
verified scan range
point count
lattice state
UB state
count-control mode
known instrument metadata
temperature/sample state
```

MUST NOT use:

```text
detector intensity
monitor-normalized intensity
peak position
peak shape
spectral similarity
CEF expectations
```

These are diagnostics only.

No repeat signature/group becomes:

```text
acquisition_block
instrument_config
instrument_block
normalization group
```

---

## A002-24 — Quality checks

Per file/scan check:

```text
readability
format identity
header parsing
numeric-block parsing
declared/actual column count
point count reconciliation
detector/monitor/time numeric validity
timestamp validity
raw scan-ID consistency
lattice parse
UB parse
energy relation
count-control semantics
all declared point fields preserved
```

Missing metadata explicit.

No scan/file silently disappears.

---

## A002-25 — Cross-platform determinism validation

At minimum test:

```text
shuffled file traversal
reversed traversal
Windows-style path separators
POSIX-style path separators
stable serialization round-trip
```

If both Windows and Linux execution comparison is available, compare deterministic scientific artifacts.

If not, synthetic path/serialization regressions are mandatory.

Record separately:

```text
byte_sha256
canonical_content_sha256
```

where appropriate.

Do not claim byte identity unless frozen serialization guarantees it.

---

## A002-26 — Raw-data integrity postflight

Repeat complete raw census:

```text
dataset-relative path
size
SHA-256
```

Require equality with A-002 preflight census and reviewed A-001 raw archive identity.

Any raw mutation:

```text
FAIL
```

---

## A002-27 — Blindness, scope and local-path audits

### Blindness/scope audit

Confirm no dependency on:

```text
historical target energies
F002/F004 positions
CEF level schemes
CEF predictions
peak-search code
```

Confirm no:

```text
monitor normalization
count-rate normalization
ki/kf intensity correction
background subtraction
instrument_config inference
instrument_block inference
resolution calculation
spectral fitting
CEF analysis
```

### Machine-local path leakage audit

Detect accidental leakage of execution-machine:

```text
repository root
dataset root
user home path
resolved values from configs/local_paths.yaml
```

Do not reject or delete an instrument-side/raw header path merely because it is syntactically absolute.

Raw instrument metadata remain preserved.

The audit concerns only accidental disclosure of execution-machine local filesystem paths.

---

# OUTPUTS

Canonical result directory:

```text
04_Results/Stage02R/W02-02R-A-002/
```

Required output set:

```text
file_inventory.csv
scan_inventory.csv
file_scan_map.csv

scan_points.csv
scan_point_auxiliary.csv
parsed_header_metadata.jsonl

lattice_states.yaml
UB_states.yaml

parser_schema_registry.yaml
parser_diagnostics.csv
quality_diagnostics.csv

semantic_verification_report.yaml

provenance_manifest.yaml
test_report.yaml
```

Required source/configuration:

```text
scripts/stage02r/a002_parser.py
scripts/stage02r/a002_schema_registry.yaml
```

No:

```text
scan_points.parquet
scan_point_auxiliary.parquet
```

is required or canonical.

---

## `parser_schema_registry.yaml`

Must be exact execution snapshot of:

```text
scripts/stage02r/a002_schema_registry.yaml
```

and include all 21 reviewed format families.

For each:

```yaml
raw_format_id:
raw_format_fingerprint:

declared_columns:
scan_variable_schema:

required_fields:
optional_fields:

verified_semantic_mappings:
unresolved_raw_fields:

parser_version:
```

---

## `semantic_verification_report.yaml`

Must explicitly report:

```text
e_Ei_Ef_relation
en_e_mapping
mode_0_semantics
h_k_l_semantics
q_semantics

count_control_semantics

filter_metadata
attenuation_metadata

monochromator_material
monochromator_reflection
monochromator_mosaic

analyzer_material
analyzer_reflection
analyzer_mosaic

auxiliary_motor_semantics

lattice_state_count
UB_state_count
```

For every topic:

```yaml
status:
evidence:
tests:
exceptions:
canonical_mapping:
remaining_ambiguity:
```

Allowed status:

```text
verified
partially_verified
unresolved
not_recorded
not_applicable
```

---

## `parser_diagnostics.csv`

Recommended frozen columns:

```text
dataset_id
file_record_id
scan_record_id
raw_format_id
diagnostic_type
severity
field_or_section
source_line_number
message
```

---

## `quality_diagnostics.csv`

Recommended frozen columns:

```text
dataset_id
file_record_id
scan_record_id
quality_test
status
affected_point_count
details
```

---

## `provenance_manifest.yaml`

Minimum:

```yaml
job_id: W02-02R-A-002
parent_checkpoint: W02-02R-A-001

dataset_id: EXP-TAIPAN-001

repository:
branch:
code_commit:

execution_context: W02-Lin
platform:
python_version:
python_implementation:

requirements_file:
requirements_file_checksum:
installed_dependency_versions:

A001_capture_commit: 55b54c9b9e4510cf993cb2b968b44aeefd497893
A001_artifact_checksums:

raw_data_access: read_only

input_raw_census_digest:
output_raw_census_digest:

parser_version:
serialization_contract_version: stage02r_a002_serialization_v1

source_schema_registry_checksum:
result_schema_registry_snapshot_checksum:
registry_snapshot_match:

configuration_checksum:

commands:

outputs:
  - logical_name:
    byte_sha256:
    canonical_content_sha256:

stop_condition:
```

Machine-local absolute execution paths MUST NOT be canonicalized into this manifest.

Execution timestamps may be present here.

---

## `test_report.yaml`

For each test:

```yaml
test_id:
status:
evidence:
details:
```

Allowed:

```text
pass
fail
not_applicable
blocked
```

A semantic test may PASS with unresolved semantic outcome if the decision procedure correctly concludes that evidence is insufficient.

---

# TESTS

## A002-T01 — A-001 checkpoint integrity

All reviewed A-001 artifact checksums match canonical checkpoint.

---

## A002-T02 — Raw census continuity

A-002 source census matches reviewed A-001 archive:

```text
201 regular files
same dataset-relative source entries
same SHA-256 values
```

---

## A002-T03 — Raw read-only integrity

A-002 pre/post raw census identical.

---

## A002-T04 — Complete file parsing

```text
201 raw files
==
201 file_inventory rows
```

No silent exclusion.

---

## A002-T05 — Verified file ↔ scan cardinality

Expected:

```text
201 files
==
201 logical scans
==
201 primary file_scan_map rows
```

General mapping table still exists.

---

## A002-T06 — All 21 format families supported

Every reviewed raw-format fingerprint has production parser/schema coverage.

No unknown format silently parsed.

---

## A002-T07 — Format-registry determinism

Same full format fingerprint always resolves to same schema mapping independent of traversal order.

Result snapshot checksum must match registry used at execution.

---

## A002-T08 — Declared-column enforcement

Every numeric row conforms to declared schema or has explicit parse failure.

No positional semantic guessing.

---

## A002-T09 — Numeric-block completeness

Every file has exactly one parsed numeric block.

No silent row truncation.

All declared numeric fields are represented either in:

```text
scan_points.csv
```

or:

```text
scan_point_auxiliary.csv
```

---

## A002-T10 — Deterministic file IDs

Final `file_record_id` values exactly preserve reviewed A-001 archive-entry identity.

---

## A002-T11 — Exact deterministic scan IDs

Verify exact algorithm:

```text
stage02r_scan_record_v1
dataset_id
file_record_id
raw_scan_id
```

with UTF-8/LF/final LF.

Verify:

```text
full SHA-256 stored
initial 16-hex display prefix
deterministic collision extension
```

IDs remain stable under:

```text
shuffled traversal
path-separator changes
filesystem metadata changes
machine identity changes
```

---

## A002-T12 — Source checksum identity

Every final file/scan record preserves traceability to correct source SHA-256.

---

## A002-T13 — Point-level reconciliation and indexing

For every scan:

```text
scan_inventory.scan_point_count
==
number of scan_points rows
```

Verify:

```text
point_index starts at 0
point_index follows numeric-block source order
```

Where recoverable:

```text
source_data_line_number
```

is ONE-BASED physical source line.

---

## A002-T14 — Raw count preservation

For every applicable point:

```text
time_raw
detector_raw
det_err_raw
monitor_raw
```

remain separate raw fields.

No ratio, rate or normalized field is created.

---

## A002-T15 — Count-control classification

Reviewed expectation:

```text
103 monitor_controlled
98 time_controlled
```

A discrepancy must be explicit and cannot be force-corrected to expected count.

---

## A002-T16 — `e / Ei / Ef` semantic relation

For every checked row:

- preserve raw source precision;
- compute raw residual;
- compute frozen decimal-precision-derived tolerance;
- record/report residual and tolerance;
- make no source-value correction.

Test PASSES if decision procedure correctly yields either verified or unresolved/exceptional status.

---

## A002-T17 — `en / e` mapping

For all `def_x=en` scans test control-coordinate versus point-column relation.

No name-only alias assumption.

Unresolved result is allowed when evidence insufficient.

---

## A002-T18 — `mode=0` semantics

A semantic label is permitted only from sufficient TAIPAN/raw/kinematic evidence.

If evidence insufficient, expected correct result is:

```text
mode_semantics_status: unresolved
```

Guessing causes FAIL.

---

## A002-T19 — `h/k/l` semantic consistency

Perform bounded checks using:

```text
verified scan variables
lattice
UB
recorded geometry where appropriate
```

MUST NOT perform:

```text
UB refinement
lattice refinement
sample re-indexing
instrument calibration
intensity-based geometry selection
```

---

## A002-T20 — `q` conservative semantics

Test only documented/kinematically justified candidates.

If no unique meaning:

```text
q_semantics_status: unresolved
```

is correct PASS behavior.

Automatic `q → |Q|` without proof is FAIL.

---

## A002-T21 — Lattice state identity and multiplicity

Verify exact:

```text
stage02r_lattice_state_v1
```

algorithm.

Check:

```text
full SHA-256
16-hex initial ID
collision extension
negative-zero normalization
no tolerance merging
locale independence
```

Reviewed expected count:

```text
2
```

Any exact discrepancy must be reported rather than tolerance-collapsed.

---

## A002-T22 — UB state identity and multiplicity

Verify exact:

```text
stage02r_ub_state_v1
```

algorithm with row-major matrix.

Check same deterministic numeric/collision rules.

Reviewed expected count:

```text
4
```

No UB refinement.

---

## A002-T23 — PG material / reflection separation

Verify parser never promotes:

```text
PG
```

alone into an unrecorded:

```text
reflection
mosaic
```

---

## A002-T24 — Filter-state preservation

No explicit recorded filter state must remain:

```text
not_recorded
```

or:

```text
unresolved
```

rather than a guessed constant.

---

## A002-T25 — Attenuation preservation

Unrecorded attenuation remains null/not-recorded or unresolved.

No default.

---

## A002-T26 — Auxiliary field preservation

Every declared numeric field outside stable wide schema appears in:

```text
scan_point_auxiliary.csv
```

with:

```text
raw_field_name
raw_value
raw_unit
semantic_status
source_column_index
```

Unresolved motor semantics are not discarded.

---

## A002-T27 — Chronology integrity

Verify:

```text
sequence_index ZERO-BASED
```

Primary ordering:

```text
verified acquisition timestamp
```

tie breakers:

```text
raw_scan_id
source_file
```

No synthetic acquisition endpoint from filesystem mtime.

Missing/unresolved timestamp yields explicit chronology status.

---

## A002-T28 — Duplicate semantics

Reviewed expected duplicate count:

```text
0
```

Regression must nevertheless verify:

```text
different file_record_id
same content
→ same duplicate_group_id
```

without row deletion.

---

## A002-T29 — Raw scan-ID uniqueness / collision handling

Verify current raw scan IDs.

Synthetic collision must not merge scans.

---

## A002-T30 — Repeat-metadata blindness

A-002 produces no final repeat group ID.

Changing or permuting detector intensity values while holding acquisition metadata fixed MUST NOT alter:

```text
repeat_metadata_signature
repeat_candidate_status
repeat_candidate_count
repeat_candidate_basis
```

No intensity quantity may enter repeat metadata signature.

---

## A002-T31 — Cross-platform path independence and path-leakage semantics

Verify same logical dataset-relative source path produces same IDs under Windows/POSIX separator forms.

Local path leakage audit must detect execution-machine:

```text
repository root
dataset root
user home
resolved configs/local_paths.yaml values
```

It MUST NOT flag/delete raw instrument metadata merely because a raw header value is syntactically an absolute path.

---

## A002-T32 — Deterministic serialization

Verify frozen:

```text
stage02r_a002_serialization_v1
```

contract.

Repeated identical scientific inputs produce deterministic canonical content.

For each relevant artifact distinguish:

```text
byte_sha256
canonical_content_sha256
```

as appropriate.

No byte-identity claim where writer contract does not guarantee it.

---

## A002-T33 — Full header non-lossiness

Verify `parsed_header_metadata.jsonl` preserves:

```text
source order
duplicate keys
empty values
source line numbers
```

through ordered `raw_header_records`.

No lossy dictionary replacement.

---

## A002-T34 — No normalization

Static/output audit confirms no newly calculated:

```text
detector / monitor
count rate
ki/kf intensity factor
absolute intensity
corrected intensity
```

---

## A002-T35 — No instrument-block inference

No production:

```text
instrument_config_id
instrument_block_id
normalization compatibility grouping
acquisition_block_id
```

is generated.

Repeat metadata diagnostics do not count as block inference.

---

## A002-T36 — No spectral feature discovery

No:

```text
spectral plotting for candidate search
background fit
peak detection
peak centroiding
feature clustering
historical-energy search
```

---

## A002-T37 — No CEF analysis

No:

```text
CEF Hamiltonian
CEF levels
CEF model prediction
PCM calculation
CEF assignment
CEF fitting
Mantid CrystalField
```

---

## A002-T38 — Blind-independence audit

Executable code/configuration contains no historical CEF target energies or historical F002/F004 locations as analysis constants.

Historical spectral values cannot influence:

```text
parser behavior
semantic mapping
quality decisions
repeat diagnostics
scan ordering
```

---

# PASS_CRITERIA

`W02-02R-A-002` passes only if all applicable conditions hold.

1. Frozen A-002 specification and exact execution commit are verified before work.

2. A local isolated Python environment is used.

3. Execution checkpoint records Python/platform/dependency information and canonical requirements checksum.

4. No Parquet dependency is required solely for A-002.

5. Canonical A-001 checkpoint and seven reviewed artifacts pass checksum verification.

6. Raw archive matches reviewed A-001 source identity or execution stops for review.

7. Raw archive remains byte-identical pre/post A-002.

8. All 201 archive entries receive final file inventory records.

9. All 201 logical scans receive scan inventory records.

10. Reviewed `1 file = 1 logical scan` relationship is reproduced.

11. General `file_scan_map.csv` provenance remains explicit.

12. All 21 structural format families have production parser coverage.

13. No semantic field is inferred from an unverified column position.

14. All numeric rows are parsed without silent truncation.

15. Every declared numeric field survives in either stable wide or auxiliary point table.

16. `scan_points.csv` uses one stable frozen schema across all formats.

17. `scan_point_auxiliary.csv` is always produced.

18. `point_index` is ZERO-BASED and source ordered.

19. `source_data_line_number` is ONE-BASED where recoverable.

20. Every parsed point remains traceable to scan/file/source identity.

21. Raw `detector`, `monitor`, `det_err`, `time` remain distinct.

22. Monitor-controlled and time-controlled acquisitions remain explicitly distinct.

23. Count-control totals reconcile with reviewed A-001 result or discrepancy is escalated.

24. Raw numeric token precision/provenance is preserved sufficiently for deterministic semantic testing.

25. `e / Ei / Ef` relation is tested using raw textual decimal precision rather than spectroscopy-based tolerance.

26. Raw residual and row-level tolerance are reported for energy semantic tests.

27. Source energy values are never modified to force consistency.

28. `en / e` is verified, partially verified or explicitly unresolved.

29. `mode=0` remains unresolved unless unique evidence supports semantic promotion.

30. `h/k/l` consistency tests remain bounded to field-semantic verification.

31. No UB refinement occurs.

32. No lattice refinement occurs.

33. No sample re-indexing occurs.

34. No instrument-angle calibration occurs.

35. `q` remains unresolved unless a unique justified meaning is established.

36. Two reviewed lattice states are reproduced using exact deterministic state identity or any discrepancy is surfaced.

37. Four reviewed UB states are reproduced using exact deterministic state identity or any discrepancy is surfaced.

38. State identities use no arbitrary tolerance merging.

39. Numerically distinct lattice/UB source values remain distinct.

40. Full state SHA-256 fingerprints are preserved.

41. Scan IDs use exact frozen `stage02r_scan_record_v1` algorithm.

42. Full scan fingerprints are preserved.

43. Display-ID collisions are handled deterministically.

44. Scan identity is independent of absolute path, OS path separator, traversal order, filesystem metadata and machine identity.

45. `raw_scan_id` remains stored independently.

46. `PG` remains material information only unless reflection/mosaic are independently verified.

47. Filter/higher-order state is not guessed.

48. Attenuation is not guessed.

49. Auxiliary motors/fields are preserved even where unresolved.

50. Empty header values remain explicitly preserved.

51. Full raw header ordering and duplicate keys survive JSONL parsing.

52. Acquisition timestamps are populated only from verified raw timestamp semantics.

53. Missing acquisition endpoints remain null rather than synthesized.

54. `sequence_index` is ZERO-BASED.

55. Missing chronology does not become false acquisition chronology via deterministic output ordering.

56. Duplicate-content semantics are implemented despite current duplicate count zero.

57. Scan-ID collision handling is implemented without merging.

58. A-002 produces no `repeat_candidate_group_id`.

59. Repeat metadata diagnostics use acquisition metadata only.

60. Detector intensity modifications do not alter repeat metadata diagnostics.

61. Executable schema registry and result snapshot correspond exactly.

62. One authoritative executable registry exists; result registry is an execution snapshot, not a second independently edited source.

63. Serialization follows `stage02r_a002_serialization_v1`.

64. Text outputs are UTF-8, LF-terminated and end with final newline.

65. CSV column order and formatting are deterministic.

66. JSONL mapping keys are deterministically ordered while raw header list source order is preserved.

67. YAML uses deterministic ordering and no platform-specific tags.

68. Execution timestamps do not contaminate deterministic scientific-content digests.

69. `byte_sha256` and `canonical_content_sha256` are distinguished where necessary.

70. Cross-platform logical IDs remain stable.

71. Execution-machine repository root does not leak into tracked outputs.

72. Execution-machine dataset root does not leak into tracked outputs.

73. Execution-machine user-home path does not leak into tracked outputs.

74. Resolved local-path config values do not leak into tracked outputs.

75. Raw instrument/header paths are not deleted or altered merely because syntactically absolute.

76. No monitor normalization is performed.

77. No count-rate normalization is performed.

78. No \(k_i/k_f\) intensity correction is performed.

79. No detector-efficiency or absolute-intensity correction is performed.

80. No acquisition-block inference is performed.

81. No `instrument_config_id` is inferred.

82. No `instrument_block_id` is inferred.

83. No normalization compatibility grouping is inferred.

84. No TAS resolution calculation is performed.

85. No background modelling is performed.

86. No spectral feature discovery or peak fitting is performed.

87. No historical CEF target or F002/F004 location guides parsing or diagnostics.

88. No CEF calculation, assignment or fitting is performed.

89. A002-T01 through A002-T38 pass, or any formally permitted `not_applicable`/conservative unresolved result is documented consistently with this specification.

90. Output checkpoint is sufficient for independent scientific review before A-003.

---

# STOP_CONDITION

`W02-02R-A-002` stops immediately after delivery of:

```text
verified production parser

scripts/stage02r/a002_parser.py
scripts/stage02r/a002_schema_registry.yaml

canonical file_inventory.csv
canonical scan_inventory.csv
canonical file_scan_map.csv

canonical scan_points.csv
canonical scan_point_auxiliary.csv

full parsed_header_metadata.jsonl

lattice_states.yaml
UB_states.yaml

parser_schema_registry.yaml execution snapshot

parser_diagnostics.csv
quality_diagnostics.csv

semantic_verification_report.yaml

provenance_manifest.yaml
test_report.yaml
```

and after confirmation:

```text
raw tree unchanged
no normalization performed
no acquisition-block inference performed
no instrument-configuration inference performed
no instrument-block inference performed
no resolution calculation performed
no spectral analysis performed
no CEF analysis performed
```

A-002 MUST NOT proceed to:

```text
acquisition_block_id reconstruction

instrument_config_id reconstruction

instrument_block_id proposal

normalization compatibility inference

shared normalization scales

monitor-normalized spectra

count-rate normalization

ki/kf corrected intensity

detector-efficiency correction

absolute-intensity correction

background subtraction

spectral plotting for blind discovery

peak detection

candidate feature table

resolution calculation

historical feature comparison

targeted upper-limit tests

CEF assignment

CEF modelling

CEF fitting
```

Mandatory transition:

```text
W02-02R-A-002
        ↓
STOP
        ↓
02 - TAIPAN Data Reduction
Project / Scientific Review
        ↓
only after explicit Project Control authorization
W02-02R-A-003
```

Final frozen state:

```yaml
W02-02R-A-002:
  design_status: approved
  specification_status: frozen
  execution_status: not_started
  execution_authorized: true_after_canonical_commit
  parent_checkpoint: W02-02R-A-001
  execution_context_target: W02-Lin

T-02R-03:
  status: active
  A001_status: completed_reviewed
  A002_status: frozen_pending_canonical_commit_and_execution
  A003_status: blocked_pending_A002_execution_and_review
```
