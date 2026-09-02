---
title: "DyFeO3 — Stage 02R TAIPAN analysis contract"
type: stage_contract
project_id: CEF-Dy
stage_id: M02R
status: active
version: "1.1"
updated: 2026-09-02
language_content: ru
language_metadata: en
---

# Stage 02R — контракт независимого повторного анализа TAIPAN

## 1. GOAL

Цель Stage 02R — построить воспроизводимую и максимально независимую
экспериментальную цепочку

```text
raw TAIPAN data
        ↓
file census / file inventory
        ↓
logical scan inventory
        ↓
TAIPAN/TAS acquisition semantics
        ↓
acquisition / instrument configuration classification
        ↓
provisional normalization-block classification
        ↓
quality control
        ↓
CEF-model-independent feature discovery
        ↓
frozen blind feature catalogue
        ↓
confirmatory spectral analysis
        ↓
targeted post-blind tests
        ↓
canonical experimental observation contract
```

до использования конкретной CEF level scheme, CEF parameters, transition
assignments или microscopic model.

Основной scientific output Stage 02R — не CEF-модель, а экспериментальный
observation set с явным provenance и uncertainty semantics.


## 2. EPISTEMIC BOUNDARY

Stage 02R отвечает на вопросы:

```text
Что реально содержится в TAIPAN data?
Какие spectral features воспроизводимо обнаруживаются?
Какие их параметры можно экспериментально оценить?
Какие области спектра дают meaningful non-detections / upper limits?
Какие scans можно физически сравнивать по intensity?
Какие systematic uncertainties остаются неизвестными?
```

Stage 02R не отвечает на вопросы:

```text
Какой конкретный Dy3+ CEF Hamiltonian является правильным?
Каковы окончательные B_l^m?
Какой observed feature соответствует конкретному CEF transition?
Нужен ли magnetic exchange для окончательной модели?
Какая structural/microscopic CEF model является предпочтительной?
```

Эти вопросы принадлежат последующим Stage 03R / 03D / 05.


## 3. INPUTS

Основной dataset:

```yaml
dataset_id: EXP-TAIPAN-001
instrument: TAIPAN
experiment_id: 1296
```

Primary inputs:

```text
raw TAIPAN .dat files
acquisition metadata
scan headers
available instrument configuration metadata
lattice / orientation / UB metadata
temperature metadata
monitor information
Ei / Ef information
scan-variable definitions
```

### 3.1. Instrument and method prior

Stage 02R должен быть `CEF-blind`, но не `instrument-blind`.

Известное экспериментальное происхождение dataset является допустимой
априорной информацией:

```text
instrument: TAIPAN
method: thermal-neutron triple-axis spectroscopy
facility: ANSTO
```

Поэтому для интерпретации raw metadata и acquisition semantics разрешено
использовать следующий порядок источников:

```text
EXP-TAIPAN-001 raw data and acquisition metadata
        ↓
official TAIPAN / ANSTO documentation
        ↓
established TAS methodology
        ↓
comparative TAS implementations and mature TAS practice
        ↓
historical project spectral information
        POST-BLIND ONLY
```

В качестве comparative implementation references допускаются, в частности:

```text
neutrons/TAVI
me2d09/neutronpy
Mantid neutron / instrument infrastructure
```

Они могут использоваться для понимания общих TAS concepts, data architecture,
geometry / UB handling, monitor/time semantics, provenance и будущего
resolution-analysis design.

Они не являются источником TAIPAN-specific file schema, field names,
normalization rules, geometry conventions или instrument parameters, если
эти детали независимо не подтверждены официальной документацией TAIPAN
и/или `EXP-TAIPAN-001`.

CEF-specific functionality этих пакетов не используется для blind Stage 02R
feature discovery.

Дополнительные instrument documents могут использоваться для интерпретации
полей файлов и конфигурации инструмента.

Stage 02R является `CEF-blind`, но не `instrument-blind`.

Известный experimental method — thermal-neutron triple-axis spectroscopy
на TAIPAN — является допустимой и необходимой априорной информацией для
интерпретации acquisition metadata, TAS kinematics и instrument state.

Разрешённая methodological hierarchy:

```text
EXP-TAIPAN-001 raw data and acquisition metadata
        ↓
official TAIPAN / ANSTO documentation
        ↓
established thermal/cold TAS methodology
        ↓
comparative TAS implementations
        ↓
historical project spectral information
        post-blind only
```

В качестве comparative implementation references разрешено использовать,
в частности:

- neutrons/TAVI
- me2d09/neutronpy
- Mantid neutron/instrument infrastructure

Они могут использоваться для понимания TAS data architecture, geometry,
UB handling, scan semantics, monitor/time acquisition semantics,
resolution-test design и reproducibility patterns.

Они не являются источниками TAIPAN-specific file schema, field names,
normalization rules, detector corrections, geometry conventions или
instrument parameters без независимой проверки по TAIPAN documentation
и `EXP-TAIPAN-001`.

CEF-specific functionality этих программ не используется для blind
experimental discovery Stage 02R.

Historical project artifacts разрешено использовать только:

```text
для parser regression
для provenance recovery
для post-blind comparison
```

но не для выбора энергии или существования spectral feature в blind
discovery.


## 4. INDEPENDENCE RULES

### 4.1. Blind discovery must not use historical target energies

До фиксации blind feature catalogue запрещено использовать как targets:

```text
6.45 meV
~18.2 meV
27.90 meV
~44.4 meV
```

или любые эквивалентные historical aliases.

Эти числа не должны:

- задавать fit windows;
- задавать initial peak centroids;
- определять порядок просмотра scans;
- определять критерий наличия peak;
- определять feature clustering;
- использоваться для ручного отбора candidate features.

### 4.2. Meaning of "model-independent"

`Model-independent` в Stage 02R означает:

> независимый от CEF physical model и historical CEF assignments.

Это не означает математически model-free analysis.

Для обнаружения spectral structure разрешены generic statistical models:

```text
background models
generic positive peak components
generic width families
change-point / residual diagnostics
```

если их параметры не основаны на CEF expectations.

### 4.3. Blind catalogue freeze

До сравнения с historical features должен существовать immutable
blind-catalogue artifact:

```text
blind_catalogue_version
analysis_version
code_commit
configuration
source scans
feature IDs
timestamp / review date
checksum
```

После freeze historical targets можно использовать только как отдельный
post-blind comparison layer.

### 4.4. Historical crosswalk is not discovery

Соответствия вида

```text
new blind feature ↔ historical F002
new blind feature ↔ historical F004
```

создаются только после catalogue freeze.

Такое соответствие является provenance crosswalk, а не частью blind
detection.


## 5. IDENTIFIERS

Не переиспользовать historical `F001`, `F002`, ... как новые feature IDs.

Для Stage 02R использовать отдельный namespace.

Рекомендуемые IDs:

```text
feature_namespace: stage02r_blind_v1

R02F001
R02F002
R02F003
...

OBS-02R-001
OBS-02R-002
...

IB-02R-001
IB-02R-002
...

TGT-02R-001
TGT-02R-002
...
```

Historical IDs сохраняются только в отдельном crosswalk:

```yaml
historical_feature_id:
stage02r_feature_id:
comparison_status:
```


## 6. PIPELINE

### 6.1. Raw file census and logical scan inventory

Сначала выполняется полный read-only census доступного raw dataset.

Не предполагается заранее, что:

```text
one raw file = one logical scan
```

Используются три раздельные сущности:

```text
file_inventory
    one record per discovered regular file

scan_inventory
    one record per logical acquisition / scan

file_scan_map
    explicit relation between source files and logical scans
```

Допустимая cardinality должна определяться из реального формата данных:

```text
1 file  → 1 scan
1 file  → N scans
N files → 1 logical acquisition
```

Если для `EXP-TAIPAN-001` будет установлено строгое соответствие
`1 file = 1 scan`, это является результатом reconnaissance, а не исходным
предположением.

Для file-level provenance сохраняются как минимум:

```text
file_record_id
dataset_id
source_file
source_checksum
file_size_bytes
raw_format_id
raw_format_fingerprint
file_role
parse_status
```

Семантика identity:

```text
file_record_id
    dataset-relative archive-entry / source-location identity

source_checksum
    byte-content identity

duplicate_group_id
    relation between distinct archive entries with identical byte content
```

Для logical scan сохраняются как минимум canonical поля из
`DATA_CONTRACTS.md`, включая scan/acquisition semantics, neutron-energy
metadata, temperature, lattice / UB / orientation, monitor/counting metadata,
instrument configuration и source provenance.

Raw dataset является read-only:

```yaml
raw_data_access: read_only
```

Ни один analysis job не должен создавать, изменять, переименовывать,
перемещать или удалять файлы внутри raw dataset root.

По возможности сохраняется информация, необходимая для последующего
восстановления TAS kinematics:

```text
Q / hkl
energy transfer
Ei / Ef
fixed-energy mode
instrument / sample angles
UB / orientation
monochromator / analyser configuration
collimation
focusing
filters
monitor / detector semantics
```

Для величин, меняющихся внутри scan, scan-level average не заменяет
point-level metadata.

### 6.2. Scan classification

Каждый scan классифицировать без CEF interpretation.

Допустимые conceptual classes:

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

Machine values уточняются после просмотра реального набора файлов.

Classification должна основываться на acquisition semantics, а не на том,
содержит ли scan интересный peak.


### 6.3. Acquisition, instrument configuration and normalization grouping

Stage 02R различает три уровня grouping.

#### `acquisition_block_id`

Хронологически связанный acquisition segment, границы которого определяются
из raw acquisition chronology и подтверждённых configuration/change events.

#### `instrument_config_id`

Восстановленное состояние TAS instrument configuration.

При наличии metadata candidate configuration fields могут включать:

```text
operating mode
monochromator material / reflection
analyser material / reflection
fixed-Ei / fixed-Ef / elastic mode
fixed-energy value
collimation
monochromator focusing
analyser focusing
filters / higher-order suppression
attenuation
detector configuration
monitor / counting mode
explicit instrument reconfiguration
major sample remount or scattering-plane change
```

Конкретный набор config-defining fields устанавливается только после
reconnaissance реальных TAIPAN metadata.

Следующие величины сами по себе не являются автоматическими основаниями
для создания нового `instrument_config_id`:

```text
Q
qh / qk / ql
ordinary sample-angle motion
energy-transfer scan coordinate
temperature
```

Они обычно характеризуют scan coordinate или sample state, если metadata
не показывают сопутствующей instrument reconfiguration.

#### `instrument_block_id`

`instrument_block_id` означает provisional candidate group, для которого
впоследствии может быть физически оправдан общий relative-intensity
normalization parameter.

Это более сильное утверждение, чем равенство `instrument_config_id`.

Объединение scans в один `instrument_block_id` требует:

```text
explicit metadata basis
documented grouping rationale
compatible monitor / counting semantics
compatible detector state
compatible filter / attenuation state
no unresolved critical configuration conflict
```

При отсутствии критически важных metadata используется conservative handling:

```text
instrument_block_status: provisional_missing_metadata
```

и при необходимости отдельные provisional blocks.

Одинаковый `Ef` или похожий spectral shape сами по себе не являются
достаточным основанием для объединения scans.

### 6.4. Data-quality audit

Минимальные checks:

```text
scan IDs unique or explicitly disambiguated
source files readable
point counts consistent with headers
scan variable monotonicity where expected
no silent truncation
monitor values physically valid
detector/count fields physically valid
Ei/Ef semantics consistent
temperature metadata present or explicitly missing
lattice/orientation metadata internally consistent
units explicitly identified
duplicate/repeated scans identified
```

Любая correction должна быть reversible и provenance-tracked.


### 6.5. Preserve raw and derived intensity representations

Не заменять raw detector counts одной обработанной intensity column.

По возможности сохранять отдельно:

```text
raw detector counts
monitor
counting/exposure metadata
monitor-normalized quantity
ki/kf-related factor if derived and justified
further corrected intensity if used
```

Каждая derived intensity должна иметь явную формулу и units/semantics.

До проверки instrument semantics нельзя автоматически считать
monitor-normalized counts абсолютной или полностью corrected INS intensity.


### 6.6. Blind spectral-feature discovery

Feature discovery выполняется по всему экспериментально покрытому
energy range, а не только около historical energies.

Candidate generation может использовать generic positive components.

Рекомендуемый statistical principle:

```text
background-only hypothesis
        versus
background + generic positive spectral component
```

при свободном centroid внутри анализируемого experimental range.

Width treatment может использовать:

```text
free positive width with justified bounds
or
a predefined multi-scale width grid
```

но не ширину, выбранную специально для известного historical feature.

Для каждого candidate сохранять:

```text
scan_id / scan_group_id
energy
local energy range
candidate width
candidate strength
background model
detection statistic
discovery method
analysis version
quality diagnostics
```


### 6.7. Look-elsewhere / false-positive control

Поскольку centroid ищется по диапазону энергии, local fit significance
нельзя автоматически интерпретировать как global detection significance.

Blind discovery должен включать один из заранее определённых подходов:

```text
parametric-bootstrap null distribution
false-discovery-rate control
equivalent validated multiple-search correction
```

Конкретная реализация фиксируется до freeze blind catalogue.

Не использовать произвольный threshold, выбранный после просмотра известных
historical peaks.


### 6.8. Injection / recovery diagnostics

До научного использования detection threshold провести synthetic tests.

Минимально проверить:

```text
background-only false-positive rate
recovery versus signal strength
recovery versus peak width
recovery versus local background slope/curvature
sensitivity near scan boundaries
sensitivity to irregular monitor/exposure
```

Synthetic tests предназначены для характеристики detection procedure,
а не для моделирования Dy CEF physics.


### 6.9. Cross-scan feature consolidation

Candidate features из разных scans можно объединять в один global feature
только при явном compatibility criterion.

Нельзя автоматически требовать одинаковый centroid между scans, если
различие Q, temperature или geometry допускает physical dispersion или
energy shift.

Global feature может означать:

> группу статистически связанных spectral observations,

а не обязательно один exact shared-energy peak.


### 6.10. Freeze blind feature catalogue

После candidate review формируется frozen catalogue.

Для каждого feature:

```text
feature_id
feature_namespace
source scans / groups
energy estimate appropriate to discovery stage
detection status
discovery statistic
quality status
analysis version
source artifact
```

После freeze feature IDs не перенумеровывать.

Позднее rejected/superseded features сохранять исторически.


### 6.11. Confirmatory line-shape analysis

После freeze допускается более точный spectral fit.

Допустимы:

```text
shared centroids
shared widths
scan-specific amplitudes
shared background constraints
global profile models
```

только если соответствующие sharing assumptions физически и
instrumentally обоснованы.

Primary fit следует выполнять в наиболее исходном statistical domain,
который поддерживается instrument data.

Если detector counts и exposure/monitor semantics позволяют корректную
count-level likelihood, она предпочтительна.

Если используется Gaussian approximation или fit нормированных данных,
необходимо явно документировать причину и область применимости.


### 6.12. Background-model uncertainty

Не считать выбор одного background model полностью известным.

Для существенного feature проверить разумное семейство local backgrounds,
например:

```text
constant
linear
quadratic
other justified smooth local model
```

и отдельно оценить sensitivity к background choice.

Background-model spread не смешивать автоматически со statistical
covariance без явного правила.


### 6.13. Targeted post-blind tests

Только после blind catalogue freeze разрешены targeted tests historical
energies.

В частности:

```text
6.45 meV
27.90 meV
historical F002 region
historical F004 region
```

Результат targeted test должен храниться отдельно от blind feature table.

Targeted upper limit означает:

> ограничение на signal при заранее выбранной target hypothesis,

а не независимое обнаружение feature.


### 6.14. Controlled execution sequence for T-02R-03

Execution `T-02R-03` выполняется несколькими независимыми Work jobs с review
между ними:

```text
W02-02R-A-001
TAIPAN/TAS-aware raw census + format/acquisition reconnaissance
        ↓
scientific review
        ↓
W02-02R-A-002
verified parser + file/scan inventories
        ↓
scientific review
        ↓
W02-02R-A-003
acquisition / instrument configuration /
provisional instrument-block classification
        ↓
scientific review
        ↓
T-02R-03 acceptance
```

Каждый Work job прекращается на собственном `STOP_CONDITION`.

Следующий job не начинается автоматически после успешного завершения
предыдущего.

Полная specification `T-02R-03` и первого Work job хранится отдельно в:

```text
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
```


## 7. UNCERTAINTY CONTRACT

Для experiment-derived spectral parameters по возможности хранить отдельные
слои:

```text
statistical fit uncertainty
background-model uncertainty
energy-calibration systematic
instrument-resolution uncertainty
geometry / metadata uncertainty where relevant
```

Например:

```text
peak_energy_sigma_stat_meV
peak_energy_sigma_background_model_meV
peak_energy_sigma_calibration_meV
peak_energy_sigma_total_meV
```

`null` означает `not estimated`.

`null` не означает zero.

`total` вычислять только при явно указанном combination rule.


## 8. OUTPUTS

Рекомендуемый tracked layout:

```text
04_Results/Stage02R/
    README.md

    file_inventory.csv
    scan_inventory.csv
    file_scan_map.csv

    format_catalogue.yaml
    parsed_header_metadata.jsonl
    parsed_scan_points artifact/reference

    acquisition_blocks.yaml
    instrument_configs.yaml
    instrument_blocks.yaml

    parser_diagnostics.csv
    quality_diagnostics.csv

    blind_features.csv
    blind_catalogue_freeze.yaml
    observations.csv
    targeted_tests.csv
    historical_feature_crosswalk.yaml

    provenance_manifest.yaml
    test_report.yaml
```

Если artifact слишком велик для Git, он хранится во внешнем data layer,
а в Git помещаются:

```text
artifact_id
relative logical name
checksum
generation command
code version
external storage reference if appropriate
```

Analysis code рекомендуется хранить в:

```text
scripts/stage02r/
```

Конкретная структура может быть уточнена после inventory, но logical
outputs должны сохраняться.


## 9. REQUIRED TESTS

Stage 02R должен иметь как минимум следующие validation layers.

### Parser / inventory tests

```text
every discovered regular file has an explicit file-level disposition
file count reconciles with the fresh filesystem census
raw source files remain unchanged under read-only execution

file_inventory and scan_inventory are distinct
file ↔ logical-scan cardinality is explicitly verified
file_record_id is deterministic and independent of byte checksum
source_checksum represents byte-content identity
exact-content duplicates remain distinct archive entries

raw-format fingerprints are deterministic and traversal-order independent
format identity is based on verified structural grammar, not extension alone
all readable files participate in lightweight header/key/column census
representative files of every discovered format receive deeper inspection

no hard-coded semantic column offsets without format verification
missing metadata remain explicit
TAS metadata semantics are verified or explicitly unresolved

raw detector counts, monitor, exposure and derived quantities remain separate
absolute machine-local data paths do not leak into tracked artifacts

blind-independence static audit passes
```

### Physical metadata tests

```text
Ei/Ef consistency
energy-transfer sign convention
units
temperature consistency
h,k,l / Q consistency where independently computable
UB/lattice block consistency
```

### Blind-independence test

Discovery code/configuration must not depend on:

```text
EV-004
EV-005
historical F002/F004 assignments
hard-coded historical target energies
legacy CEF level tables
```

A code/config review must confirm this before blind catalogue freeze.

### Detection-procedure tests

```text
null false-positive characterization
synthetic signal injection/recovery
threshold stability
background-family sensitivity
scan-boundary sensitivity
```

### Confirmatory-analysis tests

```text
fit convergence
alternative initializations
background-model sensitivity
parameter-boundary diagnostics
sharing-assumption diagnostics
residual diagnostics
```


## 10. PASS_CRITERIA

Stage 02R is scientifically complete only when all of the following hold:

```text
1. Every available raw TAIPAN file has an inventory disposition.

2. Raw parsing and metadata extraction are reproducible.

3. Instrument / geometry blocks are explicitly defined.

4. Blind feature discovery was performed without historical CEF target
   energies or assignments.

5. The blind catalogue was frozen before historical cross-comparison.

6. Detection false-positive behaviour and sensitivity were characterized.

7. Confirmatory spectral fits have explicit line-shape and background
   semantics.

8. Statistical, background-model and known systematic uncertainties are
   separated.

9. Historical target tests are clearly labelled targeted rather than blind.

10. F002/F004 historical IDs are crosswalked only after independent
    Stage 02R discovery.

11. The final observation table contains explicit provenance to source scans
    and analysis artifacts.

12. Non-detections / upper limits have explicit experimental sensitivity
    semantics.

13. No production CEF fit was performed as part of Stage 02R.

14. No experimental feature was automatically promoted to an established
    CEF assignment.

15. Stage 02R outputs have passed scientific review in 00 - Project Control.
```


## 11. STOP_CONDITION

Stage 02R stops after delivery and review of:

```text
scan inventory
instrument-block classification
frozen blind feature catalogue
confirmatory spectral observations
targeted post-blind tests
uncertainty documentation
provenance manifest
canonical experimental observation contract
```

Do not proceed automatically to:

```text
CEF parameter fitting
Stage 03R
Stage 03D
magnetic exchange modelling
physical promotion of assignments
```

A new Project Control review is required before Stage 03R.


## 12. KNOWLEDGE PROMOTION

Outputs created during Stage 02R begin as computational/experimental
artifacts.

After review:

```text
experiment-derived observation
        ↓
EVIDENCE_REGISTER
        ↓
physical interpretation if justified
        ↓
HYPOTHESIS_REGISTER
```

A Stage 02R calculation must not directly create a validated CEF assignment.


## 13. EXECUTION BOUNDARY

Scientific decisions remain in:

```text
02 - TAIPAN Data Reduction
00 - Project Control
```

Heavy file processing, code development, batch analysis or computational
execution may be delegated to Work.

If Work is used, jobs should follow IDs such as:

```text
W02-02R-A-001
W02-02R-B-001
...
```

Every Work job must have:

```text
GOAL
INPUTS
ALGORITHM
TESTS
OUTPUTS
PASS_CRITERIA
STOP_CONDITION
```

Work must stop after the approved job and return artifacts for scientific
review.


## 14. HANDOFF

Successful Stage 02R delivers to Stage 03R:

```text
reviewed experimental observation contract
feature/observation provenance
instrument-block definitions
intensity semantics
uncertainty semantics
non-detection semantics
historical-target test results
explicit unresolved experimental questions
```

Stage 03R then determines which properties of the CEF Hamiltonian are
actually identifiable from that observation set.