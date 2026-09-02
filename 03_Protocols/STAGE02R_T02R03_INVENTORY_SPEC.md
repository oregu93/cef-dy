---
title: "DyFeO3 — Stage 02R T-02R-03 inventory and TAIPAN reconnaissance specification"
type: task_specification
project_id: CEF-Dy
stage_id: M02R
task_id: T-02R-03
status: frozen
version: "1.0"
updated: 2026-09-02
language_content: ru
language_metadata: en
---

# Stage 02R — T-02R-03 inventory and TAIPAN reconnaissance specification

## 1. STATUS

```yaml
stage_id: M02R
task_id: T-02R-03
task_status: frozen
design_status: approved
execution_status: not_started
dataset_id: EXP-TAIPAN-001
instrument: TAIPAN
experiment_id: 1296
```

Эта спецификация фиксирует утверждённый Project Control дизайн задачи:

```text
T-02R-03
Independent raw TAIPAN scan inventory
and acquisition / instrument classification
```

а также полную спецификацию первого Work job:

```text
W02-02R-A-001
TAIPAN/TAS-AWARE RAW CENSUS
+ FORMAT/ACQUISITION RECONNAISSANCE
```

Scientific design является frozen.

Любое существенное изменение:

- parser semantics;
- evidence hierarchy;
- blind-analysis boundary;
- file/scan identity model;
- instrument grouping model;
- raw-data access policy;
- scope W02 jobs;

требует нового Project Control review.

---

# PART I — T-02R-03 SCIENTIFIC AND DATA-ARCHITECTURE SPECIFICATION

## 2. GOAL

Цель `T-02R-03` — построить с нуля воспроизводимое, TAIPAN-aware, но CEF-blind представление raw dataset:

```text
EXP-TAIPAN-001
      ↓
file census
      ↓
raw-format reconnaissance
      ↓
verified parser
      ↓
logical scan inventory
      ↓
TAS acquisition semantics
      ↓
acquisition_block_id
      ↓
instrument_config_id
      ↓
provisional instrument_block_id
```

Основной reconnaissance question:

> **Какие TAS-релевантные величины действительно записаны в EXP-TAIPAN-001, как они закодированы и какие из них позволяют воспроизводимо классифицировать acquisition semantics и instrument state?**

`T-02R-03` должен:

1. дать disposition каждому обнаруженному regular file;
2. отделить filesystem-level file identity от logical scan identity;
3. установить фактические raw-format families;
4. установить фактическое отношение `file ↔ logical scan`;
5. сохранить исходную metadata semantics до normalization;
6. восстановить TAS-relevant acquisition metadata;
7. классифицировать scans только по acquisition semantics;
8. различить exact duplicates и independently repeated acquisitions;
9. реконструировать acquisition chronology;
10. реконструировать verified instrument configurations;
11. предложить conservative provisional `instrument_block_id`;
12. создать provenance foundation для последующего blind spectral analysis.

`T-02R-03` **не определяет наличие или отсутствие CEF spectral features**.

---

## 3. CORE METHODOLOGICAL PRINCIPLE

Stage 02R должен быть:

```text
CEF-BLIND
but
TAS-AWARE
```

Известно a priori, что:

```yaml
dataset_id: EXP-TAIPAN-001
instrument: TAIPAN
facility: ANSTO
instrument_class: thermal-neutron triple-axis spectrometer
```

Это легитимное prior method knowledge и оно должно использоваться.

Blindness относится к:

- historical CEF target energies;
- historical spectral assignments;
- historical F002/F004 locations;
- previous CEF level schemes;
- previous PCM/CEF predictions;
- previously fitted peak positions.

Blindness **не требует** игнорировать:

- физику triple-axis spectroscopy;
- TAS kinematics;
- TAIPAN instrument semantics;
- официальную документацию ANSTO;
- общепринятые neutron-data abstractions;
- generic instrument/data provenance methodology.

---

## 4. EPISTEMIC BOUNDARY

`T-02R-03` отвечает на вопросы:

```text
Какие raw files имеются?

Какие raw format families реально присутствуют?

Как представлены logical scans?

Какие acquisition commands и scanned variables записаны?

Какие TAS coordinates и instrument states записаны?

Какие detector / monitor / counting metadata доступны?

Какие UB / lattice / orientation metadata доступны?

Как реконструируется chronology?

Какие scans являются exact duplicates?

Какие scans являются repeated acquisitions?

Какие instrument configurations можно восстановить?

Какие provisional normalization groups допустимо предложить?
```

`T-02R-03` не отвечает на вопросы:

```text
Есть ли пик около заранее известной энергии?

Какой feature является CEF transition?

Каков CEF Hamiltonian?

Каковы B_l^m?

Каковы wavefunctions?

Какова правильная microscopic CEF model?

Нужен ли exchange для описания конкретной spectral feature?

Какова production TAS resolution function?
```

---

## 5. INPUTS

Основной dataset:

```yaml
dataset_id: EXP-TAIPAN-001
instrument: TAIPAN
experiment_id: 1296
```

Machine-local mapping:

```text
EXP-TAIPAN-001
      ↓
configs/local_paths.yaml
      ↓
machine-local dataset root
```

Canonical scientific identifier всегда:

```text
EXP-TAIPAN-001
```

Machine-local absolute path:

- разрешается использовать только runtime;
- не является scientific identifier;
- не помещается в Git-tracked output;
- не hard-code в analysis code.

---

## 6. METHOD-KNOWLEDGE HIERARCHY

Используется следующая иерархия источников.

### 6.1. PRIMARY EMPIRICAL SOURCE

```text
1. Actual EXP-TAIPAN-001 raw files
   and their acquisition metadata
```

Это главный источник ответа на вопрос:

> Что реально записано в данном экспериментальном архиве?

---

### 6.2. PRIMARY INSTRUMENT SEMANTICS

```text
2. Official TAIPAN / ANSTO instrument documentation
```

Используется для интерпретации:

- field names;
- scan commands;
- SICS semantics;
- motor semantics;
- TAS modes;
- monitor/detector concepts;
- filter/focusing/collimation semantics;
- instrument configuration.

---

### 6.3. GENERAL METHOD SUPPORT

```text
3. Established thermal/cold triple-axis spectroscopy methodology
```

Разрешено использовать:

- TAS kinematics;
- fixed-Ei / fixed-Ef concepts;
- reciprocal-space scanning concepts;
- standard monitor/time acquisition concepts;
- generic resolution metadata requirements;
- general distinction between scan coordinates and hardware state.

---

### 6.4. COMPARATIVE TAS PRACTICE

```text
4. Mature TAS environments / facilities
```

В том числе, где полезно:

```text
ANSTO
ILL
MLZ
PSI
ORNL
ESS-related TAS methodology
other mature TAS environments
```

Они могут информировать generic methodology, но не определяют TAIPAN-specific schema.

---

### 6.5. COMPARATIVE TAS IMPLEMENTATION REFERENCES

#### `neutrons/TAVI`

TAVI может информировать:

- TAS experiment / scan architecture;
- geometry handling;
- UB handling;
- metadata organization;
- later resolution-test architecture;
- regression-test design.

TAVI **не может** без независимой проверки определять:

- TAIPAN raw-file schema;
- TAIPAN field names;
- TAIPAN monitor normalization;
- TAIPAN geometry conventions;
- TAIPAN instrument parameters.

TAVI resolution calculations остаются вне scope `T-02R-03` и `W02-02R-A-001`.

#### `me2d09/neutronpy`

NeutronPy может информировать:

- TAS data-handling patterns;
- monitor-controlled versus time-controlled normalization semantics;
- ResLib-derived resolution concepts;
- generic TAS regression-test ideas.

NeutronPy **не может** без независимой проверки определять:

- TAIPAN raw-file schema;
- TAIPAN field names;
- TAIPAN normalization rules;
- TAIPAN detector corrections;
- TAIPAN geometry conventions;
- TAIPAN instrument parameters.

NeutronPy / ResLib resolution calculations остаются вне scope `T-02R-03` и `W02-02R-A-001`.

---

### 6.6. OPEN-SOURCE NEUTRON INFRASTRUCTURE REFERENCE

```text
5. mantidproject/mantid
```

Для Stage 02R Mantid может использоваться как reference для:

- neutron-data abstractions;
- separation of instrument / run / sample information;
- run/sample metadata handling;
- scan-variable semantics;
- instrument-definition concepts;
- monitor normalization as a separate processing operation;
- reproducibility architecture;
- data-loading patterns;
- moving-instrument / scan abstractions;
- fixed-energy-mode representation.

Нельзя предполагать native TAIPAN support.

Перед использованием любой TAIPAN-specific Mantid functionality она должна быть отдельно подтверждена.

Mantid не может автоматически определять для EXP-TAIPAN-001:

- raw-file schema;
- field names;
- monitor normalization;
- detector corrections;
- geometry convention;
- resolution parameters;
- instrument definition.

Mantid `CrystalField` functionality является потенциальным инструментом для later Stage 03R / 03D / 05, но **не является input Stage 02R blind analysis**.

---

### 6.7. POST-BLIND ONLY

```text
6. Historical project spectral information
```

Historical project artifacts разрешены только для:

```text
parser regression
provenance recovery
post-blind comparison
```

Они не могут определять expected answer inventory/classification.

---

## 7. BLIND-INDEPENDENCE RULE

До freeze нового blind feature catalogue нельзя использовать как guide:

```text
6.45 meV
~18.2 meV
27.90 meV
~44.4 meV
```

или historical F002/F004 positions.

Они не должны влиять на:

- порядок просмотра scans;
- file-role classification;
- parser architecture;
- scan classification;
- duplicate/repeat grouping;
- acquisition blocks;
- instrument configurations;
- instrument blocks;
- spectral search windows;
- candidate feature selection.

Historical raw-file counts также не являются expected answers для fresh census.

---

# 8. TAS/TAIPAN METHODOLOGY TARGETS

## 8.1. General TAS representation

Experimental point не должен концептуально редуцироваться к:

```text
energy + counts
```

Нужно сохранять, где возможно:

$$
(\mathbf Q,\hbar\omega)
\longleftrightarrow
(\mathbf k_i,\mathbf k_f,\text{scattering geometry},\text{instrument state}).
$$

В standard TAS notation:

$$
\mathbf Q=\mathbf k_i-\mathbf k_f.
$$

Нужно сохранить информацию, необходимую позже для определения:

- \(E_i\);
- \(E_f\);
- \(k_i\);
- \(k_f\);
- energy-transfer convention;
- reciprocal-space coordinates;
- scattering geometry;
- sample orientation;
- fixed-energy mode;
- relevant instrument state.

---

## 8.2. TAIPAN/SICS vocabulary to search for

Reconnaissance должен явно искать и проверять, где применимо:

### Acquisition

```text
scan command
runscan / mscan / equivalent
scanned variable
scan range
number of points
time-controlled acquisition
monitor-controlled acquisition
title / comment
```

### Reciprocal space / energy

```text
qh
qk
ql
en / energy-transfer variable
Ei
Ef
ki
kf
fixed-Ei
fixed-Ef
elastic mode
```

### TAS angles / coordinates

```text
M1
M2
S1
S2
A1
A2
other physical or virtual motors
```

### Monochromator

```text
material
reflection
monochromator selection
horizontal focusing
vertical focusing
focusing state
mosaic if available
```

### Analyser

```text
material
reflection
horizontal focusing
vertical focusing
mosaic if available
```

### Beam definition

```text
collimation
slits
apertures
virtual-source settings
attenuation
```

### Filters / higher-order suppression

```text
filter type
filter identity
filter insertion/removal state
PG filter state
sapphire filter state
additional filter state
higher-order suppression configuration
```

### Detection / normalization metadata

```text
detector configuration
detector raw field
monitor configuration
monitor raw field
counting/exposure metadata
monitor preset
time preset
```

### Crystallography / orientation

```text
UB matrix
lattice parameters
reference reflections
scattering plane
sample orientation
```

### Sample environment

```text
temperature
temperature setpoint
cryostat
furnace
magnet
magnetic field
other state variables
```

### Chronology

```text
acquisition start time
acquisition end time
scan sequence
explicit instrument reconfiguration events
```

### Operating mode

```text
TAS
two-axis
elastic
Be-filter
other explicitly recorded modes
```

Не предполагается, что все перечисленные quantities присутствуют.

Reconnaissance question:

> **Which of these TAS-relevant quantities are actually recorded in EXP-TAIPAN-001, and how are they encoded?**

---

# 9. HIGHER-ORDER / FILTER STATE

Higher-order contamination control является first-class TAS metadata issue.

Нужно явно искать и сохранять:

```text
filter type
filter insertion/removal state
higher-order suppression configuration
changes of filter configuration between scans
```

Не следует смешивать автоматически:

```text
primary-beam / monochromator-related filtering
```

и

```text
higher-order suppression filtering in TAS operation
```

если raw/official semantics различают их.

Filter state может быть `instrument_config_id`-defining.

Нельзя предполагать constant filter state для всего `EXP-TAIPAN-001`.

---

# 10. FUTURE RESOLUTION METADATA

`T-02R-03` не выполняет TAS resolution calculations.

Запрещены на этом task:

```text
Cooper-Nathans calculation
Popovici calculation
ResLib calculation
Takin resolution
TAVI resolution calculation
NeutronPy resolution calculation
Mantid resolution calculation
RESTRAX / ResCal-style production resolution modelling
```

Однако следует сохранить, если доступно:

```text
Ei / Ef
ki / kf
monochromator material/reflection
analyser material/reflection
collimation
horizontal focusing
vertical focusing
monochromator mosaic
analyser mosaic
sample mosaic
Q
scan direction
sample geometry
sample orientation
slits/apertures
```

Один empirical elastic width не должен интерпретироваться как global TAS resolution function.

---

# 11. RAW DATA ACCESS POLICY

```yaml
RAW_DATA_ACCESS: read_only
```

Все W02 jobs должны рассматривать `EXP-TAIPAN-001` как strictly read-only.

Запрещено:

```text
create files inside raw dataset
modify raw files
rename raw files
move raw files
delete raw files
write caches into raw dataset
write temporary files into raw dataset
```

Derived outputs записываются только вне raw dataset root.

Где practically feasible, выполняется pre/post raw census:

```text
relative path
file size
SHA-256
```

и проверяется неизменность raw archive.

---

# 12. RAW_FILE_DISCOVERY

## 12.1. Separate file and scan layers

Не предполагается:

```text
1 raw file = 1 logical scan
```

Используются две сущности:

```text
file_inventory.csv
    one record per discovered regular file

scan_inventory.csv
    one record per logical acquisition / scan
```

и явная relationship table:

```text
file_scan_map.csv
```

Минимальные поля:

```text
file_record_id
scan_record_id
source_file
relationship_role
```

Архитектура должна допускать:

```text
1 file  → 1 scan
1 file  → N scans
N files → 1 logical acquisition
```

Если raw reconnaissance доказывает:

```text
1 file = 1 logical scan
```

это становится verified result.

---

## 12.2. Filesystem census

Каждый discovered regular file получает record до semantic parsing.

Минимально:

```text
file_record_id
dataset_id

source_file
source_checksum
file_size_bytes
file_extension

filesystem_mtime
filesystem_mtime_trust

file_role
parse_status
parse_message
```

`source_file` хранится как dataset-relative path.

Canonical separator:

```text
/
```

`filesystem_mtime` является low-trust filesystem metadata:

```text
filesystem_mtime_trust: filesystem_metadata_only
```

Он не заменяет proper instrument/header acquisition timestamp.

---

# 13. DETERMINISTIC IDENTIFIERS

## 13.1. `file_record_id`

`file_record_id` является **dataset archive-entry identity**, а не content identity.

Определение:

```text
file_record_id
    = identity of one dataset-relative source location
```

Conceptual construction:

```text
file_record_id =
    FILE-02R-<stable hash(
        dataset_id
        + canonical dataset-relative source_file
    )>
```

Это означает:

```text
same logical source location + changed bytes
    → same file_record_id
    → different source_checksum
```

---

## 13.2. `source_checksum`

```text
source_checksum
    = SHA-256 identity of file byte content
```

Он является content identity, а не archive-entry identity.

---

## 13.3. `duplicate_group_id`

```text
duplicate_group_id
    = equal-content relationship
      across distinct archive entries
```

Например:

```text
path A → bytes X
path B → bytes X
```

должно давать:

```text
file_record_id(A) != file_record_id(B)

source_checksum(A) == source_checksum(B)

duplicate_group_id(A) == duplicate_group_id(B)
```

Оба archive entries остаются в inventory.

---

## 13.4. `scan_record_id`

После того как logical scan boundaries verified:

```text
scan_record_id =
    SCAN-02R-<stable hash(logical acquisition identity)>
```

Identity может включать, где verified:

```text
dataset_id
file_record_id(s)
raw scan/run identifier
stable within-file scan section identity
```

Она не зависит от enumeration order.

Если identity пока нельзя определить:

```yaml
scan_record_id: null
scan_identity_status: unresolved
```

---

## 13.5. `raw_format_id`

Каждый structural raw format имеет:

```text
raw_format_id
raw_format_fingerprint
raw_format_descriptor_version
```

`raw_format_id` не зависит от traversal order.

---

# 14. RAW FORMAT FINGERPRINT

## 14.1. Versioned canonical descriptor

Canonical descriptor version:

```text
stage02r_raw_format_descriptor_v1
```

Fingerprint строится только из format-defining structural properties.

Может включать:

```text
encoding class
header grammar
header delimiters
key-value syntax
section names
section structural order
data-block grammar
column-declaration syntax
normalized declared-column names/order where structurally relevant
row-tokenization structure
other stable grammar-level properties
```

---

## 14.2. Volatile values excluded

Descriptor MUST exclude:

```text
timestamps
scan IDs
run IDs
titles
comments
motor values
sample-environment values
scan-command arguments
scan start/stop/range
run-specific numeric values
Q coordinates
energy coordinates
```

---

## 14.3. Full fingerprint

```text
raw_format_fingerprint =
    SHA256(
        raw_format_descriptor_version
        + canonical_structural_descriptor
    )
```

Full SHA-256 является canonical fingerprint и сохраняется полностью.

---

## 14.4. Display ID

```text
FMT-02R-<prefix>
```

является только display identifier.

Если два distinct full SHA-256 имеют одинаковый текущий prefix:

```text
detect collision
→ deterministically increase prefix length
→ repeat until unique
```

Full SHA-256 никогда не заменяется shortened ID.

---

# 15. PARSER STRATEGY

## 15.1. Phase A — structural reconnaissance

До production parser определить:

```text
encoding
header grammar
section structure
data-section structure
declared column schema
scan-command representation
timestamp representation
file↔scan relationship
```

---

## 15.2. Phase B — verified semantic parser

После A-001 scientific review:

```text
raw field / raw column declaration
        ↓
verified TAIPAN meaning
        ↓
canonical field
```

Запрещено:

```text
column 5 = detector
column 7 = monitor
```

если format semantics этого не подтверждают.

Numeric index может использоваться internally только после того, как соответствующий format schema verified.

---

## 15.3. Raw versus parsed metadata

Original TAIPAN file остаётся raw source.

Parsed derivative:

```text
parsed_header_metadata.jsonl
```

Каждая record сохраняет traceability:

```text
file_record_id
source_file
source_checksum
raw_format_id

original_key
original_value / original_text

normalized_key
normalized_value
semantic_status
```

Нормализация не должна уничтожать исходное representation.

---

## 15.4. Missing metadata

Missing data сохраняются явно:

```text
null
```

с semantic/provenance status:

```text
raw_header
raw_column
dataset_contract
derived
missing
unresolved
```

Нельзя молча брать значение:

- из соседнего scan;
- из previous scan;
- из historical project artifact;
- из global experiment default;

без explicit provenance rule.

---

# 16. ALL-FILE LIGHTWEIGHT HEADER/KEY/COLUMN CENSUS

После raw-format discovery выполняется lightweight pass по **всем readable scan/file candidates**.

Цель:

> определить metadata coverage всего archive, не основывая conclusions только на representative files.

Разрешено собирать:

```text
header keys / labels encountered
section names
declared column names
column-declaration signatures
presence of recognizable scan-command fields
presence of candidate TAS metadata fields
presence of timestamp fields
```

Запрещено на этом pass:

```text
production semantic normalization
intensity normalization
spectral interpretation
background analysis
peak detection
CEF calculation
```

---

## 16.1. Representative deep inspection

Deterministic representative files остаются обязательными для:

- deep grammar inspection;
- parser architecture;
- manual semantic verification;
- regression fixtures.

Но metadata coverage не выводится только из representatives.

---

## 16.2. Coverage fields

Для candidate semantic field и format, где practically feasible:

```text
files_seen
files_total_for_format
variation_status
```

Recommended `variation_status`:

```text
constant_in_seen_files
variable_across_seen_files
partially_present
present_all_files
unresolved
```

---

## 16.3. Explicit absence semantics

`field_semantics_report.yaml` различает:

```text
not_seen_in_representatives
```

и

```text
not_seen_in_full_header_census
```

### `not_seen_in_representatives`

Field отсутствовал в deterministic deep-inspection sample.

Это не означает absence во всём dataset.

### `not_seen_in_full_header_census`

Field/key/column signature не был обнаружен в lightweight census всех readable files relevant format.

Это означает только:

> quantity не обнаружена в available raw archive representation.

Это не доказывает, что physical quantity не существовала в реальном experiment.

---

# 17. TAS-AWARE METADATA MODEL

Для каждого logical scan нужно сохранять, где доступны, следующие classes metadata.

## 17.1. Acquisition

```text
scan_command_raw

scan_variable
scan_variable_raw

scan_start
scan_stop

scan_points_header
scan_points_parsed

count_control_mode
count_control_target

acquisition_start_time
acquisition_end_time
```

---

## 17.2. Neutron kinematics

```text
energy_mode

Ei_meV
Ef_meV

energy_transfer_variable
energy_transfer_convention

ki_Ainv
kf_Ainv
```

`ki_Ainv` / `kf_Ainv` могут быть:

- directly recorded;
- later derived from verified Ei/Ef.

Origin должен быть explicit.

---

## 17.3. Reciprocal space

```text
qh
qk
ql
Q_Ainv where available or independently derived later
```

Если quantities vary point-by-point, scan-level scalar не заменяет point-level metadata.

---

## 17.4. Crystallographic state

```text
lattice_a_A
lattice_b_A
lattice_c_A

alpha_deg
beta_deg
gamma_deg

UB_metadata_ref
orientation_metadata_ref
scattering_plane_ref
```

Нельзя hard-code один lattice/UB для всего experiment, если raw metadata изменяются.

---

## 17.5. TAS angular geometry

Искать и сохранять, где recorded:

```text
M1
M2
S1
S2
A1
A2
other relevant instrument/sample angles
```

---

## 17.6. Monochromator

```text
material
reflection
selection/mode
horizontal focusing
vertical focusing
mosaic
```

---

## 17.7. Analyser

```text
material
reflection
horizontal focusing
vertical focusing
mosaic
```

---

## 17.8. Collimation / apertures

```text
collimation
slits
apertures
virtual source
```

---

## 17.9. Filters / attenuation

```text
filter identity
filter type
inserted/removed state
higher-order suppression configuration
attenuation
```

---

## 17.10. Detector / monitor

```text
detector identity
detector configuration
detector raw fields

monitor identity
monitor configuration
monitor raw fields
```

---

## 17.11. Counting mode

Различать:

```text
time_controlled
monitor_controlled
other
unknown
```

и сохранять preset/exposure semantics.

---

## 17.12. Sample environment

```text
temperature_K
temperature_setpoint_K

sample environment type
magnetic field
other recorded state
```

---

## 17.13. Operating mode

```text
TAS
two_axis
elastic
Be_filter
other
unknown
```

если это можно установить из raw/official semantics.

---

# 18. TAS KINEMATIC PRESERVATION

Inventory/parser architecture должна позволять в последующих stages проверить consistency:

$$
E_i \leftrightarrow k_i
$$

$$
E_f \leftrightarrow k_f
$$

$$
\hbar\omega = E_i-E_f
$$

с учётом verified TAIPAN sign convention.

Также, где geometry allows:

$$
\mathbf Q=\mathbf k_i-\mathbf k_f.
$$

Для этого не следует сводить scan к одному набору:

```text
energy + counts
```

Если scan variables point-dependent, architecture должна сохранять point-level representation.

Recommended logical artifact:

```text
parsed_scan_points.parquet
```

или equivalent external artifact.

Он может содержать:

```text
scan_record_id
point_index

raw detector fields
raw monitor fields

scan coordinates
qh/qk/ql
energy coordinate

Ei/Ef
instrument/sample angles

point-specific environment metadata where available
```

Это acquisition representation, а не spectral observation table.

---

# 19. RAW COUNTS / MONITOR / DERIVED QUANTITY SEPARATION

Сохраняются отдельно:

```text
raw detector counts
raw monitor counts
time/exposure metadata
instrument-recorded processed fields
derived monitor-normalized quantities
kinematic corrections
further corrected intensities
```

В `T-02R-03`:

```text
raw detector counts
raw monitor counts
time/exposure metadata
```

могут быть parsed/identified.

Не выполняются production calculations:

```text
counts / monitor
ki/kf correction
background subtraction
absolute normalization
CEF cross-section correction
```

Instrument-recorded processed fields должны сохраняться как instrument outputs, а не ошибочно маркироваться как derived by Stage 02R.

---

# 20. INVENTORY ARCHITECTURE

## 20.1. `file_inventory.csv`

Минимальные поля:

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
```

---

## 20.2. `scan_inventory.csv`

### Identity / provenance

```text
scan_record_id
dataset_id
experiment_id

raw_scan_id
scan_identity_status

primary_file_record_id

source_file
source_checksum
```

---

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

---

### Acquisition semantics

```text
scan_command_raw

scan_variable
scan_variable_raw

scan_start
scan_stop

scan_points_header
scan_points_parsed

count_control_mode
count_control_target
```

---

### TAS kinematics

```text
energy_mode

Ei_meV
Ef_meV

energy_transfer_variable
energy_transfer_convention

qh
qk
ql

kinematic_metadata_ref
```

---

### Geometry / crystallography

```text
lattice_a_A
lattice_b_A
lattice_c_A

alpha_deg
beta_deg
gamma_deg

UB_metadata_ref
orientation_metadata_ref
geometry_metadata_ref
```

---

### Sample environment

```text
temperature_K
sample_environment_ref
```

---

### Classification

```text
scan_coordinate_type
scan_purpose
scan_class

classification_status
classification_reason
classification_evidence
```

---

### Grouping

```text
acquisition_block_id
instrument_config_id
instrument_block_id
instrument_block_status
```

---

### Quality

```text
quality_flag
quality_reasons

parsed_header_metadata_ref
```

---

## 20.3. `file_scan_map.csv`

```text
file_record_id
scan_record_id
source_file
relationship_role
```

Possible `relationship_role`:

```text
primary
contains_scan
continuation
supporting_metadata
unknown
```

Machine values may be refined only after reconnaissance.

---

# 21. SCAN CLASSIFICATION

Classification выполняется только после verified parser semantics.

Conceptual classes:

```text
energy_transfer_scan
Q_scan
rocking_scan
elastic_or_resolution_scan
alignment_scan
calibration_scan
technical_scan
unknown
```

Evidence chain:

```text
raw command / scanned variable
        ↓
verified TAIPAN semantics
        ↓
acquisition interpretation
        ↓
scan class
```

Допустимые evidence examples:

```text
scan of en under verified TAS energy mode
scan of qh/qk/ql
scan of verified rocking motor
explicit alignment acquisition
explicit calibration acquisition
explicit technical operation
```

Запрещённые evidence examples:

```text
contains expected peak
resembles historical feature
matches old scan
spectral shape looks elastic
contains signal at expected CEF energy
```

---

## 21.1. Separate classification dimensions

При необходимости различать:

```text
scan_coordinate_type
scan_purpose
scan_class
```

Например:

```yaml
scan_coordinate_type: angular_scan
scan_purpose: alignment
scan_class: alignment_scan
```

---

## 21.2. Unknown class

Если evidence недостаточно:

```yaml
scan_class: unknown
classification_status: unresolved
```

Guessing запрещён.

---

# 22. DUPLICATES, COLLISIONS, REPEATS

## 22.1. Exact duplicate archive entries

Если:

```text
source_checksum(A) == source_checksum(B)
```

при:

```text
file_record_id(A) != file_record_id(B)
```

то:

```text
duplicate_status: exact_file_duplicate
```

и присваивается общий:

```text
duplicate_group_id
```

Обе file records сохраняются.

---

## 22.2. Scan-ID collision

Если:

```text
same raw_scan_id
different archive identity/content
```

это:

```text
scan_id_collision
```

а не automatic duplicate.

---

## 22.3. Repeated measurement

Repeated acquisition означает отдельное measurement с compatible acquisition semantics.

Candidate grouping может учитывать:

```text
scan command
scan variable
scan range
point structure
geometry
instrument configuration
sample state
```

Spectral similarity не используется.

Каждый acquisition сохраняется самостоятельно.

---

# 23. ACQUISITION CHRONOLOGY

Chronology priority:

```text
1. proper instrument/header acquisition timestamps
2. explicit raw scan/run sequencing
3. acquisition command/log evidence
4. filesystem metadata as low-trust supporting evidence only
```

Canonical fields:

```text
acquisition_start_time
acquisition_end_time
sequence_index
```

`filesystem_mtime` отдельно:

```text
filesystem_mtime
filesystem_mtime_trust
```

Filesystem mtime нельзя подставлять вместо acquisition timestamp без explicit status.

---

# 24. THREE GROUPING LEVELS

Используются три независимых concepts:

```text
acquisition_block_id

instrument_config_id

instrument_block_id
```

---

## 24.1. Acquisition block

Определение:

> Chronological contiguous measurement segment associated with measurement activity and explicit configuration/change events.

Possible boundaries:

```text
instrument restart
explicit reconfiguration
operating-mode change
sample remount
scattering-plane change
monochromator change
analyser change
filter-state change
collimation change
detector/monitor change
major instrument configuration change
```

Temperature change сама по себе не является автоматически instrument reconfiguration.

---

## 24.2. Instrument configuration

Определение:

> Reconstructed verified TAS instrument state based on actual recorded metadata.

Candidate state fields, если present/relevant:

```text
operating mode

monochromator material/reflection
analyser material/reflection

fixed-Ei/fixed-Ef/elastic mode
fixed-energy value

collimation

monochromator horizontal focusing
monochromator vertical focusing

analyser horizontal focusing
analyser vertical focusing

filters
higher-order suppression
attenuation

detector configuration
monitor/counting mode

major sample remount state
scattering-plane state

explicit instrument reconfiguration state
```

---

## 24.3. Scan coordinates are not automatic config changes

Следующие quantities **не должны автоматически** создавать новый `instrument_config_id`:

```text
Q
qh/qk/ql
normal sample-angle motion required by scan
energy-transfer coordinate
temperature
```

Они обычно описывают scan/sample state.

Их instrument relevance может быть reconsidered только при specific documented reason.

---

## 24.4. Configuration fingerprint

`instrument_config_id` строится из verified canonical state vector с explicit missingness.

Conceptually:

```text
configuration_fingerprint =
    SHA256(canonical verified instrument-state descriptor)
```

Но exact state vector утверждается только после A-001/A-002 reconnaissance.

---

# 25. INSTRUMENT BLOCK

`instrument_block_id` означает:

> provisional candidate common-normalization group.

Он **не эквивалентен** `instrument_config_id`.

Одинаковая configuration metadata означает только:

```text
potential normalization compatibility
```

Для actual provisional `instrument_block_id` требуется:

```text
explicit metadata basis
documented grouping rationale
no unresolved critical configuration conflict
monitor/counting compatibility
filter/attenuation compatibility
detector compatibility
relevant instrument-state compatibility
```

Если critical metadata отсутствует:

```yaml
instrument_block_status: provisional_missing_metadata
```

и при необходимости используется singleton provisional block.

Запрещено объединять scans по:

```text
spectral similarity
similar peak amplitudes
similar feature positions
historical CEF expectations
```

---

# 26. INSTRUMENT BLOCK OUTPUT SEMANTICS

`instrument_blocks.yaml` должен хранить, как минимум:

```yaml
instrument_block_id:
status:

member_scan_record_ids:
member_raw_scan_ids:
acquisition_block_ids:
instrument_config_ids:

metadata_basis:

verified_equal_fields:
missing_fields:
critical_unresolved_fields:

split_reasons:
merge_rationale:

normalization_compatibility:
normalization_rationale:

source_metadata_refs:
```

Recommended:

```text
normalization_compatibility:
  candidate
  not_supported
  unresolved
```

На `T-02R-03` nuisance normalization parameter **не вводится**.

---

# 27. QUALITY CHECKS

## 27.1. File-level

```text
all discovered regular files represented
readable files checksummed
empty files retained
unreadable files retained
unexpected extensions retained
```

---

## 27.2. Parser-level

```text
all discovered format families represented
declared columns preserved
no unverified positional semantic guesses
no silent row truncation
header point count checked against parsed point count
missing metadata explicit
```

---

## 27.3. ID-level

```text
file_record_id deterministic
scan_record_id deterministic when resolvable
raw_format_id deterministic
raw_format_fingerprint stable
raw_scan_id collisions explicit
```

---

## 27.4. Numeric/raw-data sanity

Без spectral interpretation:

```text
monitor values finite/valid where expected
detector/count fields valid where expected
row counts sensible
scan-variable monotonicity where semantically expected
units identified
temperature parseable or explicitly missing
```

---

## 27.5. TAS physical metadata

Где possible:

```text
Ei/Ef consistency
energy-transfer convention consistency
Ei ↔ ki
Ef ↔ kf
qh/qk/ql semantics
Q/geometry consistency
UB/lattice internal consistency
```

Failure является diagnostic, а не permission overwrite raw metadata.

---

## 27.6. Filter state

Проверить:

```text
filter metadata coverage
filter-state changes
higher-order suppression configuration
unresolved filter semantics
```

---

## 27.7. Chronology

```text
proper acquisition timestamps preferred
filesystem mtime explicitly low-trust
sequence independent of filesystem traversal order
```

---

## 27.8. Grouping audit

Для block split:

```text
split_reason
```

Для merge:

```text
merge_rationale
metadata_basis
```

Нельзя использовать:

```text
spectra look similar
```

---

# 28. PROVENANCE

Каждый derived artifact должен сохранять:

```text
dataset_id: EXP-TAIPAN-001
repository: oregu93/cef-dy
branch: main

job_id
code_commit
configuration
configuration_checksum

generation command
generated_at

input census digest
output checksums

STOP_CONDITION
```

Каждая file-derived record:

```text
file_record_id
source_file
source_checksum
```

Machine-local dataset root не сохраняется.

---

# 29. PARSED HEADER METADATA

Использовать имя:

```text
parsed_header_metadata.jsonl
```

а не:

```text
raw_metadata.jsonl
```

поскольку JSONL уже является parsed derivative.

Каждая record содержит traceability:

```text
file_record_id
source_file
source_checksum
raw_format_id
```

---

# 30. FINAL LOGICAL OUTPUTS OF T-02R-03

После A-001, A-002 и A-003 expected logical output set:

```text
04_Results/Stage02R/

    file_inventory.csv
    scan_inventory.csv
    file_scan_map.csv

    parsed_header_metadata.jsonl
    [parsed_scan_points artifact/reference]

    format_catalogue.yaml

    acquisition_blocks.yaml
    instrument_configs.yaml
    instrument_blocks.yaml

    parser_diagnostics.csv
    quality_diagnostics.csv

    provenance_manifest.yaml
    test_report.yaml
```

Если parsed artifacts слишком велики для Git:

```text
artifact_id
logical name
checksum
generation command
code commit
external storage reference
```

хранятся в Git вместо raw large artifact.

---

## 30.1. Outputs explicitly not created in T-02R-03

```text
blind_features.csv
blind_catalogue_freeze.yaml
observations.csv
targeted_tests.csv
historical_feature_crosswalk.yaml
CEF fit outputs
```

---

# 31. T-02R-03 TEST SUITE

Итоговый test layer должен включать:

```text
filesystem reconciliation
raw pre/post immutability
checksum stability

deterministic file IDs
deterministic scan IDs
deterministic format fingerprints

format-family coverage
all-file header/key/column census

schema-driven column parsing
missing-metadata preservation

file↔logical-scan mapping validation

scan-ID collision handling
duplicate handling
repeat handling

acquisition chronology checks

Ei/Ef consistency
energy-transfer convention validation
Q/geometry consistency where possible

monitor/detector semantics
time/monitor acquisition mode

filter/higher-order state audit
TAS/two-axis/Be-filter mode audit

instrument-config reconstruction
instrument-block conservative merging

absolute-path leakage audit
blind-independence audit

no normalization
no peak search
no CEF calculation
```

---

# 32. T-02R-03 PASS_CRITERIA

`T-02R-03` считается выполненным только если:

1. Каждый discovered regular file имеет explicit disposition.

2. Fresh file count получен filesystem enumeration и не задан historical inventory.

3. File inventory и logical scan inventory являются разными сущностями.

4. File↔scan cardinality установлена empirically.

5. Все readable source files имеют SHA-256 provenance.

6. `file_record_id` является deterministic dataset-relative archive-entry identity.

7. `source_checksum` является byte-content identity.

8. Equal-content archive entries сохраняются отдельно и связываются через `duplicate_group_id`.

9. IDs/fingerprints не зависят от traversal order.

10. Raw formats определяются structural descriptor, а не extension.

11. Full SHA-256 `raw_format_fingerprint` сохранён.

12. Display-prefix collisions `raw_format_id` обрабатываются deterministically.

13. Volatile acquisition values не влияют на raw-format fingerprint.

14. Каждый semantic column mapping связан с verified format semantics.

15. Metadata coverage основан на all-file lightweight census, а не только representatives.

16. `not_seen_in_representatives` и `not_seen_in_full_header_census` различаются.

17. Raw/header representation остаётся traceable после normalization.

18. Missing metadata сохраняются explicit.

19. TAS acquisition semantics используются где supported.

20. Kinematic metadata, необходимые later, сохранены где доступны.

21. Filter/higher-order state actively audited.

22. Raw detector counts, monitor и derived intensity концептуально разделены.

23. Acquisition timestamps отделены от filesystem timestamps.

24. Exact duplicates и repeated acquisitions различены.

25. Technical/calibration/alignment scans не исчезают из inventory.

26. Scan classification основана только на acquisition semantics.

27. Spectral appearance не участвует в classification.

28. `acquisition_block_id`, `instrument_config_id`, `instrument_block_id` являются отдельными concepts.

29. Q, qh/qk/ql, ordinary scan motion, transfer-energy coordinate и temperature не трактуются автоматически как hardware configuration changes.

30. Instrument configuration основывается на actual verified TAS metadata.

31. Common-normalization grouping имеет explicit rationale.

32. Missing critical metadata не приводят к optimistic merge.

33. TAVI / NeutronPy / Mantid используются только как comparative methodology references и не задают unverified TAIPAN semantics.

34. Raw dataset не изменён.

35. Absolute local path не попадает в tracked outputs.

36. Historical CEF information не определяет inventory/classification/grouping.

37. Production resolution calculation не выполняется.

38. Spectral feature discovery не выполняется.

39. CEF calculation/fitting не выполняется.

40. A-001, A-002 и A-003 проходят отдельный Project/Scientific Review перед следующим subjob.

---

# 33. T-02R-03 EXECUTION SEQUENCE

Task должен выполняться как минимум тремя отдельными Work jobs:

```text
W02-02R-A-001
TAIPAN/TAS-aware raw census
+ format/acquisition reconnaissance
        ↓
Project / Scientific Review
        ↓
W02-02R-A-002
verified parser
+ file/scan inventories
        ↓
Project / Scientific Review
        ↓
W02-02R-A-003
acquisition blocks
+ instrument configurations
+ provisional instrument blocks
        ↓
Project / Scientific Review
        ↓
T-02R-03 acceptance
```

Ни один job не может автоматически переходить к следующему.

---

# 34. T-02R-03 STOP_CONDITION

Task останавливается после reviewed delivery:

```text
verified file inventory
verified scan inventory
verified parser semantics

acquisition chronology
acquisition blocks

instrument configurations
provisional instrument blocks

quality diagnostics
provenance artifacts
test reports
```

и до:

```text
blind spectral feature discovery
background fitting
peak detection
historical feature comparison
targeted upper-limit tests
CEF assignment
CEF calculation
CEF fitting
Stage 03R
Stage 03D
```

---

# PART II — W02-02R-A-001 FORMAL WORK SPECIFICATION

# 35. W02-02R-A-001 IDENTITY

```yaml
stage_id: M02R
task_id: T-02R-03
job_id: W02-02R-A-001
job_title: TAIPAN/TAS-aware raw census + format/acquisition reconnaissance
dataset_id: EXP-TAIPAN-001
execution_class: reconnaissance
raw_data_access: read_only
specification_status: approved
execution_status: not_started
```

---

# 36. GOAL

Выполнить минимальную local filesystem / raw-format reconnaissance, необходимую для замены assumptions о TAIPAN archive на verified facts.

Job должен ответить точно на следующие вопросы:

```text
1. Какие regular files реально существуют в EXP-TAIPAN-001?

2. Какие structural raw-format families имеются?

3. Как устроены headers, sections и data blocks?

4. Как объявляются data columns?

5. Как представлен logical scan/acquisition?

6. Верно ли для данного dataset:
   1 file = 1 logical scan?

7. Как представлены scan commands и scanned variables?

8. Какие TAS reciprocal-space coordinates записаны?

9. Какие Ei/Ef/energy-transfer metadata записаны?

10. Как записан fixed-Ei/fixed-Ef/elastic mode?

11. Какие sample/instrument angular coordinates записаны?

12. Какие detector fields записаны?

13. Какие monitor fields записаны?

14. Как представлены time-controlled и monitor-controlled acquisitions?

15. Какие monochromator/analyser configuration fields записаны?

16. Какие focusing fields записаны?

17. Какие collimation / aperture metadata записаны?

18. Какие filter / higher-order suppression states записаны?

19. Какие attenuation states записаны?

20. Какие UB/lattice/orientation metadata записаны?

21. Какие sample-environment/temperature metadata записаны?

22. Какие operating modes записаны?

23. Какие acquisition timestamps и chronology information записаны?

24. Какие важные TAS semantics отсутствуют или остаются ambiguous?
```

A-001 не выполняет final semantic classification scans и block inference.

---

# 37. INPUTS

## 37.1. Logical dataset

```yaml
dataset_id: EXP-TAIPAN-001
```

Resolve only through:

```text
configs/local_paths.yaml
```

---

## 37.2. Canonical project inputs

```text
03_Protocols/CHAT_BOOTSTRAPS.md
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md

00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml
00_Project/EVIDENCE_REGISTER.yaml
```

Historical EVIDENCE_REGISTER spectral entries не являются expected answer source.

---

# 38. ALLOWED_METHOD_KNOWLEDGE

Разрешено:

```text
A. Actual EXP-TAIPAN-001 headers / data structures
   authoritative for dataset content.

B. Official TAIPAN / ANSTO documentation
   authoritative for TAIPAN instrument semantics.

C. Established triple-axis spectroscopy methodology.

D. Comparative mature TAS practices:
   ANSTO
   ILL
   MLZ
   PSI
   ORNL
   ESS-related methods
   other mature environments.

E. neutrons/TAVI
   comparative TAS implementation reference.

F. me2d09/neutronpy
   comparative TAS implementation reference.

G. mantidproject/mantid
   neutron/instrument infrastructure reference.
```

---

## 38.1. TAVI permitted role

TAVI MAY inform:

```text
TAS experiment/scan architecture
geometry handling
UB handling
metadata organization
future resolution-test architecture
regression-test ideas
```

TAVI MUST NOT define without independent TAIPAN verification:

```text
TAIPAN raw schema
TAIPAN field names
TAIPAN normalization rules
TAIPAN geometry conventions
TAIPAN instrument parameters
```

TAVI resolution calculations are out of scope.

---

## 38.2. NeutronPy permitted role

NeutronPy MAY inform:

```text
TAS data-handling architecture
monitor/time normalization concepts
ResLib-derived resolution concepts
regression-test ideas
```

NeutronPy MUST NOT define without independent TAIPAN verification:

```text
TAIPAN raw schema
TAIPAN field names
TAIPAN normalization rules
TAIPAN geometry conventions
TAIPAN instrument parameters
```

NeutronPy/ResLib resolution calculations are out of scope.

---

## 38.3. Mantid permitted role

Mantid MAY inform:

```text
instrument/run/sample metadata separation
scan-variable abstractions
run logs
fixed-energy mode abstraction
instrument metadata handling
reproducibility patterns
loader architecture
```

Mantid MUST NOT define without independent TAIPAN verification:

```text
TAIPAN raw schema
TAIPAN field names
TAIPAN monitor normalization
TAIPAN detector corrections
TAIPAN geometry conventions
TAIPAN resolution parameters
TAIPAN instrument definition
```

Mantid `CrystalField` functionality is prohibited in A-001.

---

# 39. FORBIDDEN METHOD INPUTS

A-001 analysis logic must not depend on:

```text
historical CEF target energies
historical F002/F004 positions
old fitted peak positions
previous CEF assignments
previous CEF level schemes
PCM predictions
CEF predictions
legacy spectral scan rankings
```

Historical artifacts may be used only later for:

```text
parser regression
provenance recovery
post-blind comparison
```

---

# 40. RAW_DATA_ACCESS

```yaml
RAW_DATA_ACCESS: read_only
```

### MUST

```text
read files
stat files
hash files
parse representative files
perform lightweight header/key/column census
```

### MUST NOT

```text
write inside dataset root
create output inside dataset root
create cache inside dataset root
create temp files inside dataset root
rename raw files
move raw files
delete raw files
modify raw bytes
```

All derived outputs go to a separate Work/output location.

---

# 41. ALGORITHM

## A001-01 — Resolve dataset safely

Read:

```text
configs/local_paths.yaml
```

Resolve:

```text
EXP-TAIPAN-001
```

Verify:

```text
path exists
path is directory
path is readable
```

The resolved absolute path may be used only at runtime.

It must not appear in tracked outputs.

---

## A001-02 — Pre-execution raw census

Before deep inspection:

1. recursively enumerate all regular files;
2. canonicalize logical relative paths;
3. obtain file sizes;
4. calculate SHA-256 for readable files.

Record internal preflight census:

```text
canonical dataset-relative path
file size
SHA-256
```

This census is used later for read-only verification.

---

## A001-03 — Deterministic filesystem inventory

Canonical relative path representation:

```text
relative to dataset root
separator: /
```

For every regular file construct:

```text
file_record_id =
    deterministic hash(
        dataset_id
        + canonical dataset-relative path
    )
```

Recommended display:

```text
FILE-02R-<stable hash prefix>
```

ID creation occurs before sorting.

Output order may be sorted for readability but identity cannot depend on sorting/traversal.

Record:

```text
file_record_id
dataset_id

source_file
source_checksum
file_size_bytes
file_extension

filesystem_mtime
filesystem_mtime_trust
```

`filesystem_mtime_trust`:

```text
filesystem_metadata_only
```

---

## A001-04 — Preliminary file-role classification

Allowed provisional roles:

```text
scan_candidate
metadata_candidate
log_candidate
script_candidate
auxiliary_file
empty_file
unreadable_file
unknown_file
```

Classification may use:

```text
filename
extension
small structural inspection
recognizable header grammar
```

но остаётся provisional.

Ни один file не удаляется из inventory из-за extension.

---

## A001-05 — Raw structural format discovery

Для readable scan/file candidates определить structural descriptor.

Descriptor version:

```text
stage02r_raw_format_descriptor_v1
```

Descriptor может содержать:

```text
encoding class
header grammar
delimiter structure
key/value grammar
section markers
section ordering
data-section grammar
column-declaration grammar
normalized declared-column sequence where relevant
row tokenization
other stable structural properties
```

Descriptor не содержит volatile acquisition values.

---

## A001-06 — Volatile-value exclusion

Explicitly exclude from descriptor:

```text
timestamps
scan IDs
run IDs
titles
comments
motor values
sample-environment values
command arguments
scan start/stop/range
Q values
energy values
other run-specific numerical values
```

---

## A001-07 — Format fingerprint and display ID

Compute:

```text
raw_format_fingerprint =
    SHA256(
        stage02r_raw_format_descriptor_v1
        + canonical structural descriptor
    )
```

Preserve complete SHA-256.

Generate display ID:

```text
FMT-02R-<prefix>
```

If prefix collision:

```text
extend prefix deterministically
until unique
```

Extension/filename alone cannot define format identity.

---

## A001-08 — ALL-FILE lightweight header/key/column census

После initial format discovery выполнить lightweight pass по каждому readable candidate file.

Собрать, где возможно:

```text
header keys / labels
section names
declared columns
column-declaration signatures

presence of scan-command fields
presence of scanned-variable fields

presence of TAS-coordinate fields
presence of energy fields

presence of detector fields
presence of monitor fields

presence of configuration fields
presence of timestamps
```

Это не production parser.

На этом шаге запрещены:

```text
production normalization
monitor normalization
background subtraction
spectral analysis
peak detection
CEF calculation
```

---

## A001-09 — Full-census metadata coverage accounting

Для каждой candidate semantic quantity и format записывать, где practically feasible:

```text
files_seen
files_total_for_format
variation_status
```

Allowed/recommended `variation_status`:

```text
constant_in_seen_files
variable_across_seen_files
partially_present
present_all_files
unresolved
```

Различать:

```text
not_seen_in_representatives
```

и:

```text
not_seen_in_full_header_census
```

---

## A001-10 — Deterministic representative selection

Для каждого `raw_format_id` выбрать deterministic representative files.

Например:

```text
lexically minimal file_record_id
```

плюс дополнительные deterministic samples, если structural variation требует.

Representative selection не зависит от filesystem traversal order.

---

## A001-11 — Deep structural inspection of representatives

Для representatives изучить:

```text
header grammar
sections
data blocks
declared columns

scan command
scan/run identifier

timestamps
experiment/proposal identifiers

candidate TAS metadata
file↔scan structure
```

Output sample:

```text
parsed_header_metadata_sample.jsonl
```

Каждая record обязательно:

```text
file_record_id
source_file
source_checksum
raw_format_id
```

---

## A001-12 — TAIPAN/TAS semantics census

Для каждого format и по full-header census + representative inspection определить status для:

### Acquisition

```text
scan command
scanned variable
scan range
scan points
time preset
monitor preset
```

### Kinematics

```text
qh
qk
ql
en / transfer energy
Ei
Ef
fixed energy mode
ki
kf
```

### Angles

```text
M1
M2
S1
S2
A1
A2
```

### Monochromator

```text
material
reflection
selection
horizontal focusing
vertical focusing
mosaic
```

### Analyser

```text
material
reflection
horizontal focusing
vertical focusing
mosaic
```

### Beam optics

```text
collimation
slits
apertures
virtual source
```

### Filters

```text
filter identity
filter type
filter state
PG filter state
sapphire filter state
higher-order suppression
```

### Attenuation

```text
attenuation state
attenuator identity
```

### Detector / monitor

```text
detector identity
detector raw field
monitor identity
monitor raw field
```

### Counting

```text
time-controlled
monitor-controlled
preset semantics
```

### Orientation

```text
lattice
UB
reference reflections
scattering plane
orientation
```

### Environment

```text
temperature
temperature setpoint
sample environment
field
```

### Mode

```text
TAS
two-axis
elastic
Be-filter
other
```

### Chronology

```text
acquisition start time
acquisition end time
run/scan sequence
```

Semantic status:

```text
verified
candidate
ambiguous
not_seen_in_representatives
not_seen_in_full_header_census
not_applicable
```

---

## A001-13 — Determine file↔logical-scan structure

Исследовать:

```text
one acquisition per file
multiple acquisitions per file
continuation/support files
ambiguous relationship
```

Produce:

```text
file_scan_cardinality_status
```

с explicit evidence.

A-001 не создаёт final `scan_inventory.csv`.

---

## A001-14 — Detector / monitor / counting reconnaissance

Identify candidate fields for:

```text
raw detector counts
raw monitor counts
time
preset
exposure/count duration
```

Official TAIPAN documentation может давать semantic hypothesis.

Она должна проверяться по actual raw representation.

Не вычислять:

```text
detector / monitor
count rate
normalized intensity
```

---

## A001-15 — Kinematic metadata reconnaissance

Characterize availability/encoding of:

```text
qh qk ql
energy coordinate
Ei
Ef
fixed-energy mode
sample angles
mono/analyser angles
UB
orientation
```

Не выполнять production transformation в \((Q,\omega)\).

---

## A001-16 — Filter and higher-order reconnaissance

Отдельно проверить:

```text
filter keys
filter values
state changes
higher-order suppression state
possible multiple filter families
```

Отчёт должен различать:

```text
seen
not seen
ambiguous
partially present
```

---

## A001-17 — Chronology reconnaissance

Определить наличие:

```text
proper header/instrument timestamps
scan/run sequencing
command/log chronology
filesystem mtime
```

Filesystem mtime всегда маркируется low-trust.

Final `sequence_index` не строится, если semantics ambiguous.

---

## A001-18 — Configuration coverage matrix

Построить matrix:

```text
candidate TAS field
×
raw format
```

с values:

```text
present
missing
ambiguous
constant_in_seen_files
varying_in_seen_files
partially_present
```

Не строить `instrument_config_id`.

---

## A001-19 — Duplicate-content reconnaissance

На основании SHA-256:

```text
same checksum
different file_record_id
```

выявить equal-content archive entries.

Можно сформировать preliminary:

```text
duplicate_group_id
```

но files не deduplicate physically.

---

## A001-20 — Post-execution raw census

Повторить:

```text
relative path
file size
SHA-256
```

для raw dataset.

Сравнить pre/post census.

Любая необъяснимая mutation:

```text
A-001 FAIL
```

---

## A001-21 — Blind-independence static audit

Проверить analysis code/configuration на dependency от:

```text
historical CEF target energies
historical F002/F004 positions
previous level schemes
previous model predictions
```

Documentation, описывающая prohibition, допускается.

Executable search/config logic, использующее historical targets, запрещено.

---

## A001-22 — Scope audit

Подтвердить отсутствие:

```text
monitor normalization
intensity correction
background modelling
spectral plotting for discovery
peak search
candidate spectral selection
resolution calculation
CEF calculation
```

---

# 42. W02-02R-A-001 OUTPUTS

Только минимальный reconnaissance package:

```text
file_inventory_preliminary.csv

format_catalogue.yaml

parsed_header_metadata_sample.jsonl

field_semantics_report.yaml

reconnaissance_diagnostics.csv

provenance_manifest.yaml

test_report.yaml
```

A-001 не создаёт:

```text
final scan_inventory.csv
acquisition_blocks.yaml
instrument_configs.yaml
instrument_blocks.yaml

blind_features.csv
observations.csv
targeted_tests.csv
```

---

# 43. `file_inventory_preliminary.csv`

Минимально:

```text
file_record_id
dataset_id

source_file
source_checksum

file_size_bytes
file_extension

filesystem_mtime
filesystem_mtime_trust

file_role

raw_format_id
raw_format_fingerprint

parse_status
parse_message

duplicate_status
duplicate_group_id
```

Output documentation должна explicit фиксировать:

```text
file_record_id  → archive-entry/source-location identity
source_checksum → byte-content identity
duplicate_group_id → equal-content relationship
```

---

# 44. `format_catalogue.yaml`

Для каждого format:

```yaml
raw_format_id:
raw_format_fingerprint:
raw_format_descriptor_version:

representative_file_record_ids:

files_total_for_format:

encoding:

header_structure:
data_section_structure:
column_declaration:

known_semantics:
unresolved_semantics:

file_scan_structure_evidence:
```

`raw_format_fingerprint` содержит full SHA-256.

`raw_format_id` является только display alias.

---

# 45. `parsed_header_metadata_sample.jsonl`

Каждая record должна содержать:

```text
file_record_id
source_file
source_checksum
raw_format_id
```

плюс parsed representation representative header/section information.

Этот artifact является parsed derivative.

---

# 46. `field_semantics_report.yaml`

Recommended top-level sections:

```text
acquisition

tas_kinematics
tas_angles

monochromator
analyser

collimation
focusing

filters
attenuation

detector_monitor
count_control

sample_orientation
sample_environment

chronology
operating_mode
```

Для candidate field:

```yaml
raw_names:
observed_formats:
semantic_status:

representative_coverage:
  seen:
  representative_file_record_ids:

full_header_census:
  files_seen:
  files_total_for_format:
  variation_status:
  census_status:

proposed_canonical_name:
evidence:
ambiguity:
```

Required statuses include:

```text
verified
candidate
ambiguous
not_seen_in_representatives
not_seen_in_full_header_census
not_applicable
```

---

# 47. `reconnaissance_diagnostics.csv`

Machine-readable diagnostics, например:

```text
file_record_id
raw_format_id
diagnostic_type
severity
field_or_section
message
```

Diagnostic classes могут включать:

```text
unreadable_file
empty_file
encoding_ambiguity
unknown_format
ambiguous_column_schema
missing_scan_command
missing_timestamp
ambiguous_detector_field
ambiguous_monitor_field
ambiguous_energy_semantics
ambiguous_filter_state
file_scan_cardinality_unresolved
```

---

# 48. `provenance_manifest.yaml`

Минимально:

```yaml
job_id: W02-02R-A-001
stage_id: M02R
task_id: T-02R-03

dataset_id: EXP-TAIPAN-001

repository: oregu93/cef-dy
branch: main
code_commit:

configuration:
configuration_checksum:

generation_command:

raw_data_access: read_only

pre_execution_census_digest:
post_execution_census_digest:

outputs:
  - logical_name:
    checksum:

stop_condition:
```

Absolute machine-local dataset path отсутствует.

---

# 49. `test_report.yaml`

Для каждого test:

```yaml
test_id:
status:
evidence:
details:
```

Statuses:

```text
pass
fail
not_applicable
blocked
```

`blocked` допускается только если отсутствие raw semantics делает test невозможным и это не нарушает PASS_CRITERIA.

---

# 50. W02-02R-A-001 TESTS

## A001-T01 — reproducible filesystem enumeration

Повторное enumeration даёт одинаковый canonical set:

```text
dataset-relative regular-file paths
```

---

## A001-T02 — census reconciliation

```text
N discovered regular files
==
N file_inventory_preliminary records
```

---

## A001-T03 — checksum coverage

Every readable regular source file has:

```text
SHA-256
```

---

## A001-T04 — raw dataset immutability

Pre/post:

```text
relative path
file size
SHA-256
```

identical.

---

## A001-T05 — format-family order independence

Different traversal orders reproduce:

```text
same full raw_format_fingerprint
same resolved raw_format_id
same format membership
```

---

## A001-T06 — representative coverage

Every discovered `raw_format_id` has deterministic representative file(s).

---

## A001-T07 — no positional semantic guessing

No canonical semantic field:

```text
detector
monitor
energy
Q
motor
temperature
```

is inferred solely from unexplained positional column index.

---

## A001-T08 — no absolute-path leakage

Tracked outputs contain no resolved machine-local dataset root.

---

## A001-T09 — blind-independence audit

Executable code/configuration contains no dependency on:

```text
historical CEF energies
historical F002/F004 positions
CEF level tables
CEF predictions
PCM predictions
```

---

## A001-T10 — analysis-scope audit

Confirm no:

```text
peak search
background fit
spectral candidate selection
monitor normalization
resolution calculation
CEF calculation
```

occurred.

---

## A001-T11 — deterministic archive-entry identifiers

Traversal-order changes preserve:

```text
file_record_id
```

for unchanged dataset-relative source location.

Confirm explicitly:

```text
file_record_id does not derive from source_checksum
```

---

## A001-T12 — deterministic format fingerprints

Verify:

```text
same canonical structural descriptor
→ same full SHA-256 fingerprint
```

Changes only in:

```text
timestamp
scan ID
title
comment
motor value
command argument
scan range
```

must not alter format fingerprint.

---

## A001-T13 — parsed-metadata provenance

Every parsed-header sample resolves uniquely to:

```text
file_record_id
source_file
source_checksum
```

---

## A001-T14 — filesystem timestamp semantics

`filesystem_mtime` is never labelled as proper acquisition timestamp.

---

## A001-T15 — file↔scan assumption test

Code does not assume:

```text
one file = one scan
```

before reconnaissance conclusion.

---

## A001-T16 — filter-state reconnaissance

`field_semantics_report.yaml` explicitly reports filter/higher-order fields and status.

---

## A001-T17 — TAS kinematic-field reconnaissance

Report explicitly covers:

```text
qh
qk
ql

energy-transfer field

Ei
Ef

fixed-energy mode

instrument/sample angles

UB
orientation
```

regardless of whether each field is found.

---

## A001-T18 — all-file header/key/column census coverage

Every readable file assigned to discovered format:

```text
participates in lightweight census
```

или имеет explicit census failure.

For each format:

```text
files_total_for_format
```

reconciles with format membership.

---

## A001-T19 — format display-ID collision handling

Synthetic/test fingerprints sharing initial prefix must trigger:

```text
collision detection
deterministic prefix extension
unique raw_format_id
unchanged full SHA-256
```

---

## A001-T20 — archive-entry/content/duplicate identity separation

Regression case:

```text
path A → bytes X
path B → bytes X
```

must produce:

```text
file_record_id(A) != file_record_id(B)

source_checksum(A) == source_checksum(B)

duplicate_group_id(A) == duplicate_group_id(B)
```

Changed-content case:

```text
same path A → bytes Y
```

must preserve logical `file_record_id(A)` and change `source_checksum`.

---

# 51. W02-02R-A-001 PASS_CRITERIA

A-001 passes only if all applicable conditions hold:

1. Filesystem census complete and reproducible.

2. Every discovered regular file has preliminary file record.

3. Every readable source has SHA-256 provenance.

4. Raw dataset remains unchanged.

5. `file_record_id` is deterministic archive-entry/source-location identity.

6. `source_checksum` is distinct byte-content identity.

7. Equal-content entries are represented via `duplicate_group_id`.

8. Raw-format families have deterministic full fingerprints.

9. Raw-format fingerprint descriptor is versioned.

10. Volatile run-specific values are excluded from format identity.

11. Display-prefix collisions are detected and resolved deterministically.

12. Every format family has deterministic representative evidence.

13. All readable relevant files participate in lightweight header/key/column census or have explicit failure reason.

14. Metadata coverage conclusions are not inferred solely from representatives.

15. `field_semantics_report.yaml` distinguishes:
    - `not_seen_in_representatives`;
    - `not_seen_in_full_header_census`.

16. `files_seen`, `files_total_for_format`, `variation_status` are recorded where practical.

17. Header/data/column structure is described for every format.

18. No unverified positional column semantics are introduced.

19. TAIPAN/TAS metadata coverage is explicitly characterized.

20. Detector / monitor / count-control semantics are identified or explicitly unresolved.

21. Kinematic metadata coverage is identified or explicitly unresolved.

22. Filter/higher-order suppression receives explicit reconnaissance.

23. Acquisition timestamp semantics are characterized separately from filesystem timestamps.

24. File↔logical-scan relationship is reported as verified or unresolved, not assumed.

25. Missing and ambiguous semantics remain machine-readable.

26. TAVI, NeutronPy and Mantid, if consulted, are used only as comparative methodology references.

27. No comparative package silently supplies TAIPAN-specific schema, normalization or instrument parameters.

28. No absolute machine-local path leaks into tracked artifacts.

29. Blind-independence audit passes.

30. No normalization, spectral analysis, resolution calculation or CEF computation occurs.

31. Outputs are sufficient to design/authorize `W02-02R-A-002` without speculative assumptions about TAIPAN file semantics.

---

# 52. W02-02R-A-001 STOP_CONDITION

A-001 stops immediately after delivery of:

```text
raw file census

format-family reconnaissance

all-file lightweight header/key/column census

deterministic representative inspection

TAIPAN/TAS field-semantics coverage report

file↔logical-scan relationship assessment

detector/monitor/counting reconnaissance

kinematic metadata reconnaissance

filter/higher-order reconnaissance

chronology reconnaissance

configuration metadata coverage matrix

read-only raw integrity verification

provenance manifest

test report
```

A-001 MUST NOT proceed to:

```text
final scan_inventory.csv

production semantic parser

final scan classification

acquisition_block_id construction

instrument_config_id construction

instrument_block_id construction

normalization compatibility inference

monitor normalization

ki/kf intensity correction

spectral plotting for feature discovery

background modelling

peak detection

blind feature catalogue

historical feature comparison

targeted upper-limit analysis

TAS resolution calculation

CEF calculation

CEF fitting
```

Transition is strictly:

```text
W02-02R-A-001
        ↓
Project / Scientific Review
        ↓
only after explicit authorization
W02-02R-A-002
```

---

# 53. CURRENT EXECUTION STATE

```yaml
T-02R-03:
  design_status: frozen
  project_control_status: approved
  execution_status: not_started

W02-02R-A-001:
  specification_status: approved
  execution_authorized: false
  execution_status: not_started
```

На момент freeze этой спецификации raw-data execution не выполнялся.

`EXP-TAIPAN-001` в рамках `W02-02R-A-001` ещё не инспектировался и не обрабатывался.
