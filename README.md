---
title: "CEF DFO -- база знаний исследования"
type: project_index
project_id: CEF-Dy
status: active
schema_version: "2.2"
version: "3.0"
updated: 2026-09-01
language_content: ru
language_metadata: en
---

# CEF DFO

Исследовательская база знаний (*knowledge base, KB*) проекта по кристаллическому полю
$\rm{Dy}^{3+}$ в ортоферрите $\rm{DyFeO}_3$.

Проект объединяет анализ INS-данных трехосного спектрометра [TAIPAN](https://www.ansto.gov.au/facilities/australian-centre-for-neutron-scattering/neutron-scattering-instruments/taipan), моделирование эффективного
CEF-гамильтониана, структурно обусловленные модели кристаллического поля,
проверку соглашений между вычислительными пакетами и последующую
независимую верификацию по данным макроскопических измерений ($M(H), M(T), \chi(T), \dots$).

*KB* рассчитана на обычный Markdown/YAML, Git/GitHub и Obsidian.
ChatGPT используется как рабочий научный интерфейс, но не является
единственным хранилищем состояния проекта.


## Научная задача

Основная цель — определить воспроизводимый и физически интерпретируемый
эффективный гамильтониан кристаллического поля $\rm{Dy}^{3+}$ в $\rm{DyFeO}_3$,
который одновременно согласуется с:

- энергиями наблюдаемых INS-возбуждений;
- относительными INS-интенсивностями и их зависимостью от $\mathbf Q$;
- температурной зависимостью спектров;
- физически корректными правилами отбора и волновыми функциями;
- последующей независимой проверкой по $M(H)$.

Для позиции Dy с локальной симметрией $C_s$ общий феноменологический
CEF-гамильтониан содержит 15 независимых параметров в принятом
операторном соглашении (формализм Стивенса).

Одна из центральных проблем проекта — идентифицируемость такой
низкосимметричной обратной задачи.


<!-- AUTO:README_STATUS:START -->
## Текущий статус проекта

**Stage:** `M02R` — Stage 02R — independent TAIPAN re-analysis (`active`).

**Current focus:** Stage 02R — независимый повторный анализ TAIPAN. Цель этапа — построить воспроизводимую цепочку от raw instrument data до model-independent spectral features и canonical experimental observation contract до использования CEF assignments и microscopic models.

**Next:** Выполнить в выбранном machine-local W02 execution context утверждённый verified production parser и canonical file/scan inventory job W02-02R-A-002 для EXP-TAIPAN-001, строго до STOP_CONDITION.

**Metadata updated:** `2026-09-02`.
<!-- AUTO:README_STATUS:END -->


## Экспериментальная основа

Основной собственный experimental dataset — INS измерения монокристалла
$\rm{DyFeO}_3$ на трёхосном спектрометре TAIPAN.

Текущий evidence audit различает:

| Объект | Текущий смысл |
|---|---|
| `F002` | sequential feature ID Stage 02 blind analysis около 18.2–18.3 meV |
| $\approx18.25\pm0.12$ meV | experiment-derived peak centroid; CEF assignment остаётся гипотезой |
| `F004` | sequential feature ID broad structure около 44.4 meV |
| 6.45 meV | historical target energy, не blind detection |
| 27.90 meV | historical target energy, не blind detection |

`F002` и `F004` не являются индексами кристаллографических отражений.

Подробное текущее научное состояние:
[PROJECT_STATE](00_Project/PROJECT_STATE.md).


## Модельная стратегия

Проект не использует принцип «чем больше параметров, тем лучше».

Каждая модель должна отвечать на отдельный физический вопрос.

| Model ID | Назначение |
|---|---|
| `MOD-PCM-FORMAL` | простейший structural electrostatic baseline |
| `MOD-PCM-M0` | проверка достаточности одного общего scale и исходного intensity fingerprint |
| `MOD-PCM-M1` | минимальное структурированное различение O1/O2 contributions |
| `MOD-CEF-CS15` | общий phenomenological $C_s$ CEF Hamiltonian и анализ identifiability |
| `MOD-CEF-EXCHANGE` | CEF в magnetic environment; deferred |
| `MOD-SUPERPOSITION` | более общая ligand-based structural model; deferred |
| `MOD-ECM-MALKIN` | microscopic short-range exchange-charge model; conceptual reference only |

Полный model-purpose contract находится в
[MODEL_REGISTER](00_Project/MODEL_REGISTER.yaml).


## Knowledge architecture

Проект разделяет разные уровни знания:

```text
measurement
    ↓
experimental / external evidence
    ↓
physical hypothesis / assignment
    ↓
model test or calculation
    ↓
reviewed result
    ↓
current scientific state
```

Это реализовано отдельными объектами:

```text
EVIDENCE_REGISTER
RESULT_REGISTER
HYPOTHESIS_REGISTER
MODEL_REGISTER
DECISION_REGISTER
```

Экспериментальная особенность, fitted parameter и physical assignment
не должны храниться как одна сущность.


## Быстрая навигация

| Задача | Файл |
|---|---|
| За минуту восстановить scientific state | [PROJECT_STATE](00_Project/PROJECT_STATE.md) |
| Понять текущий roadmap и blockers | [PROJECT_CONTROL](00_Project/PROJECT_CONTROL.md) |
| Проверить experimental/external evidence | [EVIDENCE_REGISTER](00_Project/EVIDENCE_REGISTER.yaml) |
| Проверить analysis/model results | [RESULT_REGISTER](00_Project/RESULT_REGISTER.yaml) |
| Проверить physical hypotheses | [HYPOTHESIS_REGISTER](00_Project/HYPOTHESIS_REGISTER.yaml) |
| Проверить model hierarchy | [MODEL_REGISTER](00_Project/MODEL_REGISTER.yaml) |
| Проверить methodological decisions | [DECISION_REGISTER](00_Project/DECISION_REGISTER.yaml) |
| Восстановить историю исследования | [RESEARCH_LOGBOOK](01_Logbook/RESEARCH_LOGBOOK.md) |
| Проверить execution checkpoint | `02_Work_Checkpoints/` |
| Проверить scientific terminology | [SCIENTIFIC_TERMINOLOGY](03_Protocols/SCIENTIFIC_TERMINOLOGY.md) |
| Проверить Knowledge Base rules | [RESEARCH_KB_GUIDE](03_Protocols/RESEARCH_KB_GUIDE.md) |
| Проверить data contracts | [DATA_CONTRACTS](03_Protocols/DATA_CONTRACTS.md) |
| Восстановить роли project chats | [CHAT_BOOTSTRAPS](03_Protocols/CHAT_BOOTSTRAPS.md) |


## Структура репозитория

```text
CEF_Dy/
├── README.md
├── PROJECT_MANIFEST.yaml
├── requirements.txt
│
├── 00_Project/
│   ├── PROJECT_STATE.md
│   ├── PROJECT_CONTROL.md
│   ├── PROJECT_METADATA.yaml
│   ├── EVIDENCE_REGISTER.yaml
│   ├── RESULT_REGISTER.yaml
│   ├── HYPOTHESIS_REGISTER.yaml
│   ├── MODEL_REGISTER.yaml
│   ├── DECISION_REGISTER.yaml
│   └── MIGRATION_NOTES.md
│
├── 01_Logbook/
├── 02_Work_Checkpoints/
│
├── 03_Protocols/
│   ├── SCIENTIFIC_TERMINOLOGY.md
│   ├── KNOWLEDGE_RULES.md
│   ├── RESEARCH_KB_GUIDE.md
│   ├── DATA_CONTRACTS.md
│   ├── MARKDOWN_LATEX_STYLE.md
│   └── CHAT_BOOTSTRAPS.md
│
├── 04_Results/
├── 05_References/
├── Templates/
├── scripts/
├── configs/
└── Archive/legacy/
```


## Source of truth

Для Git-tracked project layer каноническим текущим состоянием является:

```text
GitHub repository: oregu93/cef-dy
branch: main
```

после успешной validation и `git push`.

Старые версии `PROJECT_STATE`, registers и protocols в ChatGPT File Library
считаются historical snapshots.

`Archive/legacy/` также сохраняется как неизменяемый исторический слой.

Raw и крупные experimental/computational data не хранятся в Git.


## Воспроизводимость

Python dependency bootstrap:

```powershell
python -m pip install -r requirements.txt
```

Обновление generated re-entry blocks:

```powershell
python scripts/kb_refresh.py
```

Проверка:

```powershell
python scripts/kb_refresh.py --check
python scripts/kb_validate.py --strict
```

Перед существенным commit:

```text
refresh
→ validate
→ git diff --check
→ scientific diff review
→ commit
→ push
```


## Работа на нескольких компьютерах

Каждая машина использует собственный clone репозитория и собственный
ignored:

```text
configs/local_paths.yaml
```

Machine-specific absolute paths не входят в каноническую Knowledge Base.

Типичный цикл:

```text
git pull
    ↓
research / analysis
    ↓
refresh
    ↓
validate
    ↓
review
    ↓
commit
    ↓
git push
```


## External data

Raw TAIPAN data, крупные optimizer outputs, промежуточные массивы,
приватные материалы и другие большие binary artifacts хранятся отдельно
от Git repository.

В Knowledge Base они идентифицируются устойчивыми `dataset_id`,
`artifact_id` или checkpoint references вместо абсолютных локальных путей.


## Literature workflow

Literature layer разделён на две роли:

```text
Orthoferrite CF Watch
    discovery / triage
            ↓
01 - Literature & Physics
    curated deep analysis
            ↓
00 - Project Control
    scientific review / promotion
            ↓
Knowledge Base
```

Основные приоритеты:

- энергетические схемы CEF-уровней и $B_l^m$;
- интенсивности INS-возбуждений и правила отбора;
- low-symmetry inverse-problem methodology;
- magnetic exchange;
- structure–CEF relations;
- используемые программные пакеты.


## Текущий roadmap

```text
Stage 00C
scientific re-baselining
        ↓
Stage 02R
independent TAIPAN re-analysis
        ↓
Stage 03R
CEF landscape / identifiability
        ↓
Stage 03D
joint constrained inference
        ↓
Stage 05
independent magnetic validation
        ↓
later microscopic interpretation
```

Stage 03D M0/M1 design сохранён, но production execution не возобновляется
автоматически после Stage 00C.


## Научные ограничения текущего состояния

В настоящее время не установлены:

- уникальный полный набор $B_l^m$;
- уникальные CEF wavefunctions;
- окончательный CEF assignment особенности около 18.25 meV;
- существование CEF transitions около 6.45 и 27.90 meV;
- чистый Dy CEF origin структуры около 44.4 meV;
- величину magnetic Dy–Fe exchange field;
- microscopic exchange-charge description.

Актуальный список ограничений и открытых вопросов находится в
[PROJECT_STATE](00_Project/PROJECT_STATE.md).


## Методологические правила проекта

Численный output программы не становится научным фактом автоматически.

`reviewed` не означает `validated`.

Совпадение energies не доказывает правильность wavefunctions.

Любая таблица $B_l^m$ без operator convention, normalization, units и
coordinate frame считается неполной.

Любое существенное утверждение должно иметь поддающееся восстановлению происхождение.
