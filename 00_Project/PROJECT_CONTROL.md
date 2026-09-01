---
title: "CEF Dy — Project Control"
type: project_control
project_id: CEF-Dy
status: active
version: "2.0"
updated: 2026-09-01
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

**Сейчас.** Stage 00C — научный re-baselining проекта. Разделяются экспериментальные observations, результаты обработки, литературные target energies, физические assignments, model calculations и methodological decisions. Уже сформированы scientific terminology, evidence register, model register и новая семантическая версия PROJECT_STATE.

**Почему.** Предыдущая Knowledge Base была технически структурирована, но часть historical exploratory results и внутренних labels попала в центральное состояние проекта без достаточного provenance и без чёткого различия между наблюдением и интерпретацией. Перед следующими вычислениями необходимо восстановить независимую и воспроизводимую цепочку evidence.

**Следующий шаг.** Завершить Stage 00C governance/automation update, проверить согласованность реестров и центральных документов и подготовить один reviewable commit. После Stage 00C сформировать specification для независимого Stage 02R TAIPAN re-analysis.

**Следующий Work job.** Не назначен. Production Work заблокирован до завершения текущего scientific review cycle.

**Заблокировано.**
- W03-03D-A-001 и любая production-оптимизация Stage 03D до завершения Stage 00C и Stage 02R.
- Использование 6.45 и 27.90 meV как обязательных экспериментальных CEF constraints до восстановления provenance и нового анализа.
- Использование F004 около 44.4 meV как обязательного CEF-перехода.
- Promotion новых численных CEF solutions до validated без воспроизводимого evidence.

**Отложено.**
- Production Stage 03D M0/M1 inference.
- Magnetic exchange modelling.
- Свободный 15-параметрический CEF fit как production inference.
- Superposition model.
- Exchange-charge model Малкина.
- Полная магнитная validation.

**Последний научный источник.** Stage 00C audit of TAIPAN feature provenance, CEF terminology and model hierarchy based on current Knowledge Base, legacy analysis artifacts and reviewed methodological literature.

**Последний Work checkpoint.** Для текущего Stage 00C вычислительный checkpoint не требуется.

**Активные гипотезы.**
- `H-001` (`working`): Экспериментальная спектральная особенность около 18.25 meV рассматривается как основной кандидат проекта на переход между CEF-состояниями Dy3+.

**Ключевые риски.** `RSK-001`, `RSK-003`, `RSK-004`, `RSK-005`.
<!-- AUTO:CONTROL_REENTRY:END -->


# 1. Карта этапов

| Milestone | Status | Назначение |
|---|---|---|
| `M00B` | completed | Развёртывание автономной Knowledge Base, Obsidian/Git workflow и базовой automation. |
| `M00C` | active | Scientific re-baselining: терминология, provenance, evidence/model semantics и очистка центрального project state. |
| `M02R` | planned | Независимый повторный анализ TAIPAN от raw/instrument data до model-independent observation tables. |
| `M03R` | planned | Повторный анализ CEF landscape и идентифицируемости на очищенном experimental observation set. |
| `M03D` | suspended | Joint constrained M0/M1 energy + intensity inference; существующий design сохранён, но execution приостановлен. |
| `M05` | planned | Независимая магнитная validation и, при необходимости, CEF + magnetic exchange. |
| `M06` | later | Более глубокая structural/microscopic interpretation и перенос по ряду RFeO$_3$. |
| `M07` | ongoing | Накопление результатов, пригодных для статьи и диссертации, с явным provenance. |


# 2. Stage 00C — текущая очередь

| Task ID | Status | Задача |
|---|---|---|
| `T-00C-01` | completed | Зафиксировать каноническую научную терминологию и границы понятий observation / fit result / assignment / model. |
| `T-00C-02` | completed | Ввести provenance schema и отделить evidence от вычислительных results и hypotheses. |
| `T-00C-03` | completed | Провести audit experimental landmarks и labels: F002/F004, 18.25, 6.45, 27.90 и 44.4 meV. |
| `T-00C-04` | completed | Провести model-purpose audit и сформировать model hierarchy. |
| `T-00C-05` | completed | Семантически переписать PROJECT_STATE вокруг evidence, interpretation и model hierarchy. |
| `T-00C-06` | active | Обновить PROJECT_METADATA, PROJECT_CONTROL, PROJECT_MANIFEST, protocols и automation. |
| `T-00C-07` | next | Провести consistency review, refresh, strict validation, проверить diff и выполнить Stage 00C commit. |


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
| `RSK-001` | high | Numerical optimizer создаёт иллюзию идентифицируемости. | Landscape analysis, profile diagnostics, ensembles и независимые observables. |
| `RSK-002` | high | Нормировка поглощает физическую информацию об интенсивности. | Физически обоснованные shared normalization groups и explicit nuisance treatment. |
| `RSK-003` | high | Ошибка convention/frame незаметна по энергиям, но портит интенсивности. | Regression tests Hamiltonian + transition tensors. |
| `RSK-004` | high | Historical target energies или assignments загрязняют blind experimental analysis. | Raw-to-observation Stage 02R без CEF targets. |
| `RSK-005` | high | Magnetic exchange или microscopic effects ошибочно поглощаются effective-charge PCM. | Явная model hierarchy и независимая validation. |
| `RSK-006` | medium | Структурная uncertainty смешивается с statistical fit uncertainty. | Отдельные uncertainty layers / ensembles. |
| `RSK-007` | medium | Публичный Git содержит raw/private data. | External data directory, `.gitignore`, pre-commit audit. |


# 9. Open questions

| ID | Priority | Вопрос | Контекст |
|---|---|---|---|
| `Q-001` | high | Каков первичный литературный источник historical targets 6.45 и 27.90 meV? | `01 - Literature & Physics` |
| `Q-002` | high | Какие spectral features воспроизводимо возникают в независимом blind Stage 02R? | `02 - TAIPAN Data Reduction` |
| `Q-003` | high | Какова полная uncertainty энергии особенности около 18.25 meV с учётом calibration systematic? | Stage 02R |
| `Q-004` | high | Какие относительные INS-интенсивности могут использоваться как независимые CEF constraints? | Stage 02R / 03R |
| `Q-005` | high | Требуют ли очищенные данные изменения CEF wavefunctions относительно M0? | Stage 03R |
| `Q-006` | medium | Какова физическая природа особенности около 44.4 meV? | TAIPAN / Physics |
| `Q-007` | deferred | Когда данные требуют введения magnetic exchange? | Stage 05 |
| `Q-008` | deferred | Как переносить structural uncertainty в CEF inference? | Structure / Modelling |


# 10. Контексты чатов

| Chat | Role |
|---|---|
| `00 - Project Control` | Scientific governance, roadmap, review and promotion. |
| `Orthoferrite CF Watch` | Broad literature discovery and triage. |
| `01 - Literature & Physics` | Curated deep literature analysis and physics integration. |
| `02 - TAIPAN Data Reduction` | Independent experimental reduction and observation contract. |
| `03 - CEF Modelling & Fit Design` | CEF inference/model design before Work execution. |
| `W03 - CEF Compute` | Approved numerical execution only. |
| `04 - Structure & Conventions` | Structure, frames and operator conventions. |
| `05 - Validation & McPhase` | Independent magnetic validation and exchange-aware modelling. |
| `06 - Paper & Dissertation` | Publication/dissertation layer using reviewed provenance. |

`02 - TAIPAN Data Reduction` создаётся после завершения Stage 00C и
утверждения Stage 02R contract.


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
- [ ] PROJECT_METADATA и PROJECT_CONTROL синхронизированы;
- [ ] PROJECT_MANIFEST отражает новые authoritative registers;
- [ ] protocols отражают GitHub canonical-state policy и новую chat architecture;
- [ ] kb_refresh поддерживает новый metadata contract;
- [ ] kb_validate проверяет новые registers;
- [ ] generated re-entry blocks синхронизированы;
- [ ] `kb_validate.py --strict` проходит без ошибок и предупреждений;
- [ ] review Git diff не показывает accidental/legacy contamination;
- [ ] выполнен Stage 00C commit и push.


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