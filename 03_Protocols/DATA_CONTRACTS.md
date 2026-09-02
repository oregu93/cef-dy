---
title: "CEF Dy — контракты данных"
type: protocol
status: active
version: "2.1"
updated: 2026-09-02
---

# Контракты данных

## 1. Основной принцип

Экспериментальная таблица должна описывать то, что было измерено или
извлечено из данных.

Физическое назначение наблюдаемой особенности хранится отдельно.

```text
measurement
    ↓
observation
    ↓
spectral parameter
    ↓
assignment hypothesis
```

Нельзя кодировать CEF assignment непосредственно в идентификаторе
экспериментального наблюдения.

## 2. TAIPAN raw / scan inventory

Raw-data layer разделяется на file-level и logical scan-level representation.

Не предполагается заранее:

```text
one raw file = one logical scan
```

### 2.1. File inventory

`file_inventory` содержит одну запись на каждый обнаруженный regular file.

Минимальные поля:

```text
file_record_id
dataset_id

source_file
source_checksum
file_size_bytes
file_extension

raw_format_id
raw_format_fingerprint

file_role
parse_status
quality_flag
```

`source_file` задаётся относительно dataset root.

Machine-specific absolute path не является частью canonical provenance.

Identity semantics:

```text
file_record_id
    identity of dataset-relative archive entry / source location

source_checksum
    SHA-256 identity of current byte content

duplicate_group_id
    equal-content relation across distinct archive entries
```

Следовательно:

```text
different paths + identical bytes
    → different file_record_id
    → identical source_checksum
    → same duplicate_group_id where assigned
```

### 2.2. Logical scan inventory

`scan_inventory` содержит одну запись на logical acquisition / scan.

Минимальные поля:

```text
scan_record_id
dataset_id
experiment_id
raw_scan_id

acquisition_start_time
acquisition_end_time
sequence_index

scan_variable
scan_start
scan_stop
scan_points

temperature_K

Ei_meV
Ef_meV
energy_mode
energy_transfer_variable
energy_transfer_convention

h
k
l

lattice_a_A
lattice_b_A
lattice_c_A
alpha_deg
beta_deg
gamma_deg

UB / orientation metadata

monitor / counting metadata

acquisition_block_id
instrument_config_id
instrument_block_id

source_file
source_checksum
quality_flag
classification_status
```

Конкретные TAS instrument metadata сохраняются настолько полно, насколько
это необходимо для воспроизведения acquisition semantics, geometry и
последующей оценки resolution / intensity comparability.

Если metadata меняются между acquisition blocks, lattice / UB / instrument
configuration не должны hard-code одним глобальным значением на весь
experiment.

### 2.3. File-to-scan mapping

Связь raw files и logical scans хранится явно через `file_scan_map`.

Минимально:

```text
file_record_id
scan_record_id
source_file
relationship_role
```

Contract должен поддерживать:

```text
1 file  → 1 scan
1 file  → N scans
N files → 1 logical acquisition
```

Фактическая cardinality определяется из raw format.

### 2.4. TAS kinematic preservation

По возможности сохраняются исходные данные, необходимые для связи:

```text
(Q, energy transfer)
        ↔
(ki, kf, TAS geometry, instrument configuration)
```

В зависимости от реально доступных TAIPAN metadata это может включать:

```text
qh / qk / ql
Ei / Ef
fixed-energy mode
M1 / M2
S1 / S2
A1 / A2
UB / lattice / orientation
monochromator / analyser state
collimation
focusing
filters
detector
monitor
sample-environment state
```

Для point-varying quantities scan-level average не должен уничтожать
исходную variation.

### 2.5. Raw-data access

Canonical raw dataset по умолчанию read-only.

```yaml
raw_data_access: read_only
```

Analysis code не должен создавать, изменять, переименовывать, перемещать
или удалять файлы внутри raw dataset root.

Derived outputs создаются во внешнем output layer / repository working tree
в соответствии с project provenance rules.


## 3. Model-independent spectral feature table

Blind / model-independent feature discovery должна формировать таблицу,
которая не содержит microscopic assignment.

Минимальные поля:

```text
feature_id
feature_namespace

dataset_id
scan_id / scan_group_id
instrument_block_id

temperature_K

h
k
l
Q_Ainv

feature_energy_meV
feature_energy_sigma_meV

detection_status
discovery_method
discovery_version

source_artifact
quality_flag
```

`feature_id` является внутренним последовательным идентификатором.

Для historical Stage 02:

```text
F002 = feature #002
F004 = feature #004
```

Эти labels не являются индексами отражений.

## 4. Confirmatory spectral observation table

После line-shape analysis рекомендуется хранить:

```text
observation_id
feature_id

dataset_id
scan_id / scan_group_id
instrument_block_id

temperature_K

h
k
l
Q_Ainv

peak_energy_meV
peak_energy_sigma_stat_meV
peak_energy_sigma_model_meV
peak_energy_sigma_systematic_meV
peak_energy_sigma_total_meV

peak_area
peak_area_sigma

fwhm_meV
fwhm_sigma_meV

background_model
line_shape_model

monitor
ki_kf_factor

detection_status
upper_limit
upper_limit_confidence

fit_window_meV
fit_quality_flag

analysis_artifact
analysis_version
```

Неизвестный systematic contribution должен храниться явно как `null` /
`not_estimated`, а не неявно считаться нулём.

## 5. Detection status

Рекомендуемые machine values:

```text
detected
censored
not_covered
excluded
```

### `detected`

Спектральная компонента удовлетворяет заранее определённому detection
criterion.

### `censored`

Область спектра экспериментально доступна, но отдельная линия не
обнаружена; информация сохраняется как upper limit / censored likelihood.

### `not_covered`

Эксперимент не даёт достаточной чувствительности или вообще не покрывает
нужную область.

### `excluded`

Observation исключён по заранее установленному quality criterion.

## 6. Targeted upper-limit table

Если энергия проверки задана гипотезой или литературным prior, необходимо
разделять происхождение target energy и результат экспериментального теста.

Минимальные поля:

```text
target_id
target_energy_meV

target_origin_type
target_source_id

dataset_id
scan_id / scan_group_id

upper_limit
upper_limit_confidence

analysis_artifact
analysis_version
```

Например, historical targets 6.45 и 27.90 meV могут иметь:

```yaml
target_origin_type: literature
```

при `provenance_status: missing`, тогда как полученный около них upper limit
имеет:

```yaml
origin_type: experiment_derived
```

Это две разные сущности.

## 7. Assignment table

CEF assignment хранится отдельно от experimental observations.

Рекомендуемые поля:

```text
assignment_id
observation_id / feature_id

hypothesis_id
model_id

initial_state
final_state

assignment_status
supporting_evidence
conflicting_evidence

review_date
```

Рекомендуемые `assignment_status`:

```text
candidate
working
reviewed
rejected
superseded
```

## 8. Instrument configuration and normalization grouping

Для Stage 02R различаются три разные сущности.

### `acquisition_block_id`

Хронологически связанный acquisition segment, границы которого определяются
из measurement sequence и подтверждённых configuration/change events.

### `instrument_config_id`

Восстановленное instrument state на основании фактически доступных metadata.

Candidate config-defining fields могут включать:

```text
operating mode
monochromator / analyser configuration
fixed-Ei / fixed-Ef mode
fixed energy
collimation
focusing
filters / attenuation
detector configuration
monitor / counting mode
explicit instrument reconfiguration
```

Q, ordinary scan motion, energy-transfer coordinate и temperature сами по
себе не должны автоматически создавать новый `instrument_config_id`.

### `instrument_block_id`

Provisional evidence-based group scans, для которых может быть допустим один
общий relative-intensity normalization parameter.

Необходимо явно сохранять:

```text
instrument_block_id
member scan_record_ids
instrument_config_ids
grouping rationale
verified compatible settings
missing / ambiguous settings
normalization_compatibility
normalization_rationale
```

Принцип:

```text
same instrument_config_id
    ≠
automatically same instrument_block_id
```

Общий normalization parameter разрешён только при физически и
instrumentally обоснованной совместимости.

При недостатке critical metadata следует использовать conservative grouping
или:

```text
instrument_block_status: provisional_missing_metadata
```

Нельзя автоматически использовать независимый free scale для каждого scan,
если это уничтожает физически полезную relative-intensity information.

Нельзя также объединять scans только потому, что их spectral shapes похожи.


## 9. CEF model observation contract

Перед production CEF inference должен существовать явный observation
contract, определяющий:

```text
observation_id
observable_type
value
uncertainty
likelihood_role
assignment_status
instrument_block_id
source_artifact
```

В production fit не должны попадать undocumented historical numbers.

## 10. Work checkpoint output

Каждый checkpoint должен указывать:

```text
job_id
parent_checkpoint
logical input IDs
code version / commit
commands
model_id
configuration
tests
outputs
diagnostics
checksums where appropriate
STOP_CONDITION
```

По умолчанию numerical output checkpoint не является автоматически
scientific result.

## 11. Локальные пути

Machine-specific абсолютные пути не следует помещать в публичные project
files.

Используется:

```text
configs/local_paths.yaml
```

который исключён из Git.

Пример:

```yaml
EXP-TAIPAN-001:
  path: "C:/.../CEF_Dy_Data/TAIPAN_raw"
```

Один и тот же `dataset_id` должен сохраняться на разных машинах независимо
от физического пути.