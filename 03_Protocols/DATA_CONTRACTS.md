---
title: "CEF Dy — контракты данных"
type: protocol
status: active
version: "2.0"
updated: 2026-09-01
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

Минимальные поля scan-level inventory:

```text
dataset_id
experiment_id
scan_id

temperature_K

scan_variable
scan_start
scan_stop
scan_points

Ei_meV
Ef_meV

lattice_a_A
lattice_b_A
lattice_c_A
alpha_deg
beta_deg
gamma_deg

UB / orientation metadata
instrument_block_id

source_file
source_checksum
quality_flag
```

Конкретные instrument metadata сохраняются настолько полно, насколько это
необходимо для воспроизведения геометрии измерения.

Lattice/UB не должны hard-code одним значением на весь experiment, если
metadata меняются между acquisition blocks.

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

## 8. Instrument normalization

Если относительные интенсивности разных scans связаны через общий
instrument configuration, это должно быть выражено явным:

```text
instrument_block_id
```

и отдельной таблицей/metadata, определяющей:

- какие scans входят в block;
- почему для них допустим общий normalization parameter;
- какие настройки инструмента считаются неизменными.

Нельзя автоматически использовать независимый free scale для каждого
scan, если это уничтожает физически полезную относительную intensity
information.

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