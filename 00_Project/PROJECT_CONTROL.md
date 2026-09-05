---
title: "CEF Dy — Project Control"
type: project_control
project_id: CEF-Dy
status: active
version: "2.4"
updated: 2026-09-05
control_chat: "00 - Project Control"
---

# CEF Dy — Project Control

> [!abstract] Назначение
> Этот документ управляет научной дорожной картой, очередью задач,
> зависимостями между этапами, решениями, рисками, Work-задачами
> и критериями завершения.
>
> Текущее научное знание находится в
> [PROJECT_STATE](PROJECT_STATE.md).
> Экспериментальные свидетельства находятся в
> [EVIDENCE_REGISTER](EVIDENCE_REGISTER.yaml),
> а модельная иерархия — в
> [MODEL_REGISTER](MODEL_REGISTER.yaml).

<!-- AUTO:CONTROL_REENTRY:START -->
# 5-minute re-entry

**Сейчас.** W02-02R-B-001 и T-02R-04 завершены. Спецификация W02-02R-C-001 методологически одобрена и заморожена; открытых вопросов проектирования нет. C-001 не выполнялся, а R-012 / EV-007 и каталог B-001 не изменялись.

**Почему.** C-001 фиксирует `complex-first` модельную подготовку на данных для поиска и только метаданных отложенной выборки. Спецификация сохраняет восемь BF как алгоритмические области без допущения «одна BF — одна физическая линия» и не разрешает историческое сопоставление или CEF-назначение.

**Следующий шаг.** Project Control должен отдельно решить вопрос об авторизации исполнения W02-02R-C-001. Исполнение C-001 и C-002 не авторизовано; детекторный доступ ко всем 18 сканам отложенной выборки (`holdout`) не авторизован.

**Следующий Work job.** Не назначен. Production Work заблокирован до завершения текущего scientific review cycle.

**Заблокировано.**
- W03-03D-A-001 и любая production-оптимизация Stage 03D до завершения Stage 02R и последующего Stage 03R review.
- Использование 6.45 и 27.90 meV как обязательных экспериментальных CEF constraints до восстановления provenance и независимого анализа.
- Использование F004 около 44.4 meV как обязательного CEF-перехода.
- Promotion новых численных CEF solutions до validated без воспроизводимого evidence.
- Production CEF fitting внутри Stage 02R.

**Отложено.**
- Production Stage 03D M0/M1 inference.
- Magnetic exchange modelling.
- Свободный 15-параметрический CEF fit как production inference.
- Superposition model.
- Exchange-charge model Малкина.
- Полная магнитная validation.

**Последний научный источник.** [Рецензированный пакет W02-02R-B-001](../04_Results/Stage02R/W02-02R-B-001/SCIENTIFIC_REVIEW.md): reviewed, accepted_with_limitations; R-012 / EV-007. Канонический переход зафиксирован в [commit 21506b7](https://github.com/oregu93/cef-dy/commit/21506b7df9eb8dc4b340aa6e19eb720e07329e8d). Физическое назначение не выполнялось.

**Последний Work checkpoint.** `W02-02R-B-001`

**Активные гипотезы.**
- `H-001` (`working`): Экспериментальная спектральная особенность около 18.25 meV рассматривается как основной кандидат проекта на переход между CEF-состояниями Dy3+.

**Ключевые риски.** `RSK-008`, `RSK-007`, `RSK-003`.
<!-- AUTO:CONTROL_REENTRY:END -->


# 1. Карта этапов

| Milestone | Status | Назначение |
|---|---|---|
| `M00B` | completed | Развёртывание автономной Knowledge Base, Obsidian/Git workflow и базовой automation. |
| `M00C` | completed | Scientific re-baselining: терминология, provenance, evidence/model semantics и очистка центрального project state. |
| `M02R` | active | Независимый повторный анализ TAIPAN от raw/instrument data до model-independent observation tables. |
| `M03R` | planned | Повторный анализ CEF landscape и идентифицируемости на очищенном experimental observation set. |
| `M03D` | suspended | Joint constrained M0/M1 energy + intensity inference; существующий design сохранён, но execution приостановлен. |
| `M05` | planned | Независимая магнитная validation и, при необходимости, CEF + magnetic exchange. |
| `M06` | later | Более глубокая structural/microscopic interpretation и перенос по ряду RFeO3. |
| `M07` | ongoing | Накопление результатов, пригодных для статьи и диссертации, с явным provenance. |


# 2. Текущая очередь

| Task ID | Status | Задача |
|---|---|---|
| `T-00C-01` | completed | Нормализовать scientific vocabulary и разделение measurement / evidence / result / hypothesis / model / decision. |
| `T-00C-02` | completed | Определить и внедрить provenance schema для experiment, literature и model-derived knowledge. |
| `T-00C-03` | completed | Провести evidence matrix / experimental landmark audit и отделить наблюдения от физических assignments. |
| `T-00C-04` | completed | Провести model-purpose audit и сформировать canonical model cards / MODEL_REGISTER. |
| `T-00C-05` | completed | Переписать `PROJECT_STATE` в соответствии с scientific re-baselining. |
| `T-00C-06` | completed | Переписать `README` и привести repository entry point в соответствие с новой KB architecture. |
| `T-00C-07` | completed | Обновить `PROJECT_METADATA`, `PROJECT_CONTROL`, `PROJECT_MANIFEST` и project protocols. |
| `T-00C-08` | completed | Обновить `kb_refresh.py`, `kb_validate.py` и связанную KB automation. |
| `T-00C-09` | completed | Провести consistency review, refresh, strict validation, diff audit и завершить Stage 00C commit/push. |
| `T-02R-01` | completed | Зафиксировать canonical Stage 02R analysis contract до повторной обработки raw TAIPAN data. |
| `T-02R-02` | completed | Создать чат `02 - TAIPAN Data Reduction`, выполнить canonical re-entry и завершить design review T-02R-03. |
| `T-02R-03` | completed | Построить независимые raw file / logical scan inventories, восстановить TAIPAN acquisition semantics и классифицировать acquisition / instrument configuration / provisional normalization blocks. |
| `W02-02R-A-001` | completed | Fresh TAIPAN/TAS-aware raw census и format/acquisition reconnaissance завершены; 20/20 tests PASS, scientific review accepted, STOP_CONDITION соблюдён. |
| `W02-02R-A-002` | completed | Verified production parser + canonical file/scan inventories завершены; 38/38 tests PASS, scientific review ACCEPT, STOP_CONDITION соблюдён. |
| `W02-02R-A-003` | completed | Acquisition/configuration and normalization-compatibility classification completed; scientific review ACCEPT, 16/16 tests PASS, STOP_CONDITION satisfied. |
| `T-02R-04` | completed | Слепое обнаружение и рецензирование B-001 завершены; результат принят с ограничениями, без физического назначения. |
| `W02-02R-B-001` | completed | Выполнение завершено; scientific review: reviewed; outcome: accepted_with_limitations. Восемь monitor-controlled Tier-1 BF, 16/16 тестов PASS; каталог заморожен, holdout закрыт. |
| `T-02R-05` | design_review_only | Спецификация `W02-02R-C-001` одобрена и заморожена; C-001 не выполнялся. Следующее действие — отдельное решение об авторизации C-001. C-002 и детекторный доступ к отложенной выборке не авторизованы. |


# 3. Roadmap после Stage 00C

```text
Stage 00C
scientific re-baselining
        ↓
Stage 02R
independent TAIPAN re-analysis
        ↓
Stage 03R
CEF landscape / identifiability re-analysis
        ↓
Stage 03D
joint constrained energy + intensity inference
        ↓
Stage 05
independent magnetic validation
        ↓
later structural / microscopic interpretation
```

Ключевой принцип:

> Новый experimental pipeline не должен начинаться с требования найти
> historical energies 6.45, 18.2, 27.9 или 44.4 meV.

Сначала выполняется model-independent feature discovery.
Historical energies могут использоваться только после этого как отдельные
hypotheses или targeted tests.


# 4. Граница Stage 02R

Stage 02R должен начинаться с raw TAIPAN data и instrument metadata.

Минимальная последовательность:

```text
raw TAIPAN
    ↓
scan inventory
    ↓
instrument / geometry classification
    ↓
model-independent feature discovery
    ↓
candidate feature table
    ↓
global/shared line-shape analysis
    ↓
experimental observation contract
    ↓
physical assignments
```

Stage 02R не выполняет production CEF fit.

Основные outputs:

- воспроизводимый scan inventory;
- acquisition / instrument block classification;
- canonical observation tables;
- peak centroids / areas / widths с uncertainty semantics;
- non-detections и upper limits;
- явный provenance каждого observation;
- independent verification семантики F002/F004;
- оценка instrument-energy uncertainty;
- specification данных для Stage 03R/03D.


# 5. Граница Stage 03R

Stage 03R должен ответить на вопрос:

> Какие свойства CEF Hamiltonian реально ограничиваются очищенным
> experimental observation set до введения production structural fit?

Разрешены:

- energy-only landscape как diagnostic;
- joint energy/intensity landscape exploration;
- comparison assignment families;
- identifiability diagnostics;
- convention/frame regression tests;
- проверка, какие наблюдаемые действительно различают wavefunctions.

Не является целью:

- выбрать один minimum как финальную модель;
- автоматически возобновить старую Stage 03D objective;
- вводить magnetic exchange без отдельного решения.


# 6. Статус Stage 03D

Существующая Stage 03D specification сохраняется как результат design work.

Текущий статус:

```yaml
design_status: preserved
execution_status: suspended_pending_rebaseline
```

Модельная ветвь:

- `MOD-PCM-M0`;
- `MOD-PCM-M1`.

Она может быть возобновлена только после:

1. завершения Stage 00C;
2. формирования нового experimental observation contract в Stage 02R;
3. Stage 03R review идентифицируемости;
4. проверки того, что assumptions прежней Stage 03D specification всё ещё применимы.

Ни один старый experimental label не должен автоматически переноситься
в новый likelihood только потому, что он использовался в Stage 03C/03D.


# 7. Модельная стратегия

Канонический реестр:

[MODEL_REGISTER](MODEL_REGISTER.yaml).

Текущая иерархия:

```text
MOD-PCM-FORMAL
    structural electrostatic baseline
        ↓
MOD-PCM-M0
    uniform scale / fingerprint test
        ↓
MOD-PCM-M1
    minimal structured effective-charge deformation

MOD-CEF-CS15
    general phenomenological effective Hamiltonian

MOD-CEF-EXCHANGE
    CEF + magnetic exchange
    deferred

MOD-SUPERPOSITION
    deferred

MOD-ECM-MALKIN
    conceptual reference only / deferred
```

Модели не образуют простую последовательность «чем больше параметров,
тем лучше». Каждая отвечает на отдельный физический вопрос.


# 8. Основные научные риски

| Risk ID | Level | Риск | Контроль |
|---|---|---|---|
| `RSK-001` | high | Numerical optimizer создаёт иллюзию идентифицируемости или скрывает non-identifiability. | Landscape analysis, profile diagnostics, ensembles и независимые observables. |
| `RSK-002` | high | Nuisance normalization поглощает физическую информацию об интенсивности. | Физически обоснованные shared normalization groups и explicit nuisance treatment. |
| `RSK-003` | high | Ошибка convention/frame незаметна по энергиям, но портит интенсивности. | Regression tests Hamiltonian + transition tensors. |
| `RSK-004` | medium | Ошибочное CEF-назначение особенности около 44.4 meV смещает CEF inference. | Сохранять F004 как unassigned/diagnostic до независимого подтверждения. |
| `RSK-005` | medium | Low-temperature magnetic exchange ошибочно интерпретируется как lattice CEF. | Явно разделять single-ion CEF и magnetic-exchange layer; вводить exchange только отдельным model decision. |
| `RSK-006` | medium | Work budget расходуется на uncontrolled reasoning, repeated trial-and-error или вычисления без checkpoint boundaries. | Pre-specified Work jobs, resumable execution и explicit STOP_CONDITION. |
| `RSK-007` | medium | Публичный Git содержит raw/private или machine-local data. | External raw-data tree, `.gitignore`, path-leak checks и pre-commit audit. |
| `RSK-008` | high | Historical target energies, feature locations или assignments загрязняют blind Stage 02R analysis. | CEF-blind raw-to-observation pipeline, static independence audit и post-blind historical crosswalk. |
| `RSK-009` | medium | Non-electrostatic microscopic CEF contributions или structural physics чрезмерно интерпретируются через effective-charge PCM parameters. | Считать effective-charge PCM феноменологической structural model; не трактовать fitted charge scales как буквальные ionic charges или уникальный microscopic mechanism. |
| `RSK-010` | medium | Structural uncertainty смешивается со statistical fit uncertainty. | Раздельные uncertainty layers и structural ensembles / sensitivity analysis. |


# 9. Open questions

| ID | Priority | Вопрос | Контекст |
|---|---|---|---|
| `Q-001` | deferred | Какова корректная форма censored likelihood для недетектированных spectral components? | Stage 03R / 03D |
| `Q-002` | deferred | Следует ли nuisance normalization профилировать аналитически или численно? | Stage 03R / 03D |
| `Q-003` | deferred | Какие физически и статистически оправданные bounds / priors использовать для M0/M1? | Stage 03R / 03D |
| `Q-004` | deferred | Какой statistic корректно использовать для сравнения nested M0/M1 с учётом bounds / boundary effects? | Stage 03R / 03D |
| `Q-005` | deferred | Какие profile thresholds и правила определяют accepted-solution ensemble? | Stage 03R / 03D |
| `Q-006` | medium | Какова физическая природа особенности около 44.4 meV? | TAIPAN / Physics |
| `Q-007` | deferred | Каково минимальное exchange-aware расширение CEF model после single-ion baseline? | Stage 05 |
| `Q-008` | deferred | Как переносить structural-coordinate uncertainty в CEF inference? | Structure / Modelling |
| `Q-009` | deferred | Как переносить structural CEF trends по Dy/Ho/Tb/Tm через $A_l^m$ и local multipoles? | Stage 06 / Structure |
| `Q-010` | high | Каков первичный литературный источник historical targets 6.45 и 27.90 meV? | `01 - Literature & Physics` |
| `Q-011` | high | Какие spectral features воспроизводимо возникают в независимом blind Stage 02R? | `02 - TAIPAN Data Reduction` |
| `Q-012` | high | Какова полная uncertainty энергии особенности около 18.25 meV с учётом calibration systematic? | Stage 02R |
| `Q-013` | high | Какие относительные INS-интенсивности могут использоваться как независимые CEF constraints? | Stage 02R / 03R |
| `Q-014` | high | Требуют ли очищенные данные изменения CEF wavefunctions относительно M0? | Stage 03R |


# 10. Контексты чатов

| Chat | Role |
|---|---|
| `00 - Project Control` | Scientific governance, roadmap, review, promotion и Work authorization. |
| `Orthoferrite CF Watch` | Broad literature discovery and triage. |
| `01 - Literature & Physics` | Curated deep literature analysis and physics integration. |
| `02 - TAIPAN Data Reduction` | Scientific design/review of independent TAIPAN reduction, blind feature discovery and experimental observation contract. |
| `W02 - TAIPAN Data Reduction` | Controlled local execution of approved TAIPAN raw-data, parsing and reduction jobs. |
| `03 - CEF Modelling & Fit Design` | CEF inference/model design before Work execution. |
| `W03 - CEF Compute` | Approved CEF numerical execution only. |
| `04 - Structure & Conventions` | Structure, coordinate frames and operator conventions. |
| `05 - Validation & McPhase` | Independent magnetic / cross-code validation and exchange-aware modelling. |
| `06 - Paper & Dissertation` | Publication/dissertation layer using reviewed provenance. |


# 11. Правила перехода между этапами

Новый stage начинается только после явного review предыдущего.

Production Work не должен самостоятельно:

- менять scientific question;
- добавлять observables;
- изменять physical model;
- повышать статус result;
- переходить к следующему вычислительному этапу.

Каждый Work job должен иметь:

```text
GOAL
INPUTS
MODEL
ALGORITHM
TESTS
OUTPUTS
PASS_CRITERIA
STOP_CONDITION
```


# 12. Definition of Done — Stage 00C

Stage 00C завершён, когда:

- [x] определена каноническая scientific terminology;
- [x] введено явное разделение evidence / result / hypothesis / decision;
- [x] проведён provenance audit основных experimental landmarks;
- [x] F002/F004 получили однозначную семантику feature IDs;
- [x] проведён model-purpose audit;
- [x] PROJECT_STATE переписан на evidence-first основе;
- [x] PROJECT_METADATA и PROJECT_CONTROL синхронизированы;
- [x] PROJECT_MANIFEST отражает новые authoritative registers;
- [x] protocols отражают GitHub canonical-state policy и новую chat architecture;
- [x] kb_refresh поддерживает новый metadata contract;
- [x] kb_validate проверяет новые registers;
- [x] generated re-entry blocks синхронизированы;
- [x] `kb_validate.py --strict` проходит без ошибок и предупреждений;
- [x] review Git diff не показывает accidental/legacy contamination;
- [x] выполнен Stage 00C commit и push.


# 13. Канонические управляющие объекты

- [PROJECT_STATE](PROJECT_STATE.md)
- [PROJECT_METADATA](PROJECT_METADATA.yaml)
- [EVIDENCE_REGISTER](EVIDENCE_REGISTER.yaml)
- [RESULT_REGISTER](RESULT_REGISTER.yaml)
- [HYPOTHESIS_REGISTER](HYPOTHESIS_REGISTER.yaml)
- [MODEL_REGISTER](MODEL_REGISTER.yaml)
- [DECISION_REGISTER](DECISION_REGISTER.yaml)
- [RESEARCH_LOGBOOK](../01_Logbook/RESEARCH_LOGBOOK.md)
- [SCIENTIFIC_TERMINOLOGY](../03_Protocols/SCIENTIFIC_TERMINOLOGY.md)
