---
title: "CEF Dy / DyFeO3 — Research Knowledge Base"
type: project_index
status: active
schema_version: "2.0"
updated: 2026-08-27
language_content: ru
language_metadata: en
---

# CEF Dy / DyFeO3 — Research Knowledge Base

> [!abstract] Purpose
> Эта папка — автономная knowledge base проекта по CEF Dy$^{3+}$ в DyFeO$_3$. Она рассчитана на работу в Obsidian, Git/GitHub и обычных Markdown-редакторах. ChatGPT используется как рабочий интерфейс, но не является единственным хранилищем состояния исследования.

## 60-second navigation

| Need | Open |
|---|---|
| Быстро понять, что научно известно сейчас | [PROJECT_STATE](00_Project/PROJECT_STATE.md) |
| Понять, что делаем сейчас и что дальше | [PROJECT_CONTROL](00_Project/PROJECT_CONTROL.md) |
| Восстановить историю решений | [RESEARCH_LOGBOOK](01_Logbook/RESEARCH_LOGBOOK.md) |
| Проверить конкретный вычислительный запуск | `02_Work_Checkpoints/` |
| Восстановить роли ChatGPT-чатов | [CHAT_BOOTSTRAPS](03_Protocols/CHAT_BOOTSTRAPS.md) |
| Проверить правила знания и статусов | [KNOWLEDGE_RULES](03_Protocols/KNOWLEDGE_RULES.md) |
| Проверить Markdown/LaTeX convention | [MARKDOWN_LATEX_STYLE](03_Protocols/MARKDOWN_LATEX_STYLE.md) |
| Проверить data contracts | [DATA_CONTRACTS](03_Protocols/DATA_CONTRACTS.md) |
| Понять миграцию из Project State v1.x | [MIGRATION_NOTES](00_Project/MIGRATION_NOTES.md) |

## Current thread

**Active scientific stage:** `Stage 03D — nested neutral effective-charge PCM fit`.

Текущий следующий шаг — design review статистической постановки `M0/M1` для energy + detected/censored `F002`, с одним nuisance scale на `instrument_block_id`. `F004` остаётся diagnostic/alternative-assignment observable; exchange в Stage 03D не включается.

## Repository layout

```text
CEF-Dy/
├── README.md
├── PROJECT_MANIFEST.yaml
├── 00_Project/
│   ├── PROJECT_STATE.md
│   ├── PROJECT_CONTROL.md
│   └── MIGRATION_NOTES.md
├── 01_Logbook/
│   ├── RESEARCH_LOGBOOK.md
│   └── entries/2026/
├── 02_Work_Checkpoints/
├── 03_Protocols/
│   ├── KNOWLEDGE_RULES.md
│   ├── MARKDOWN_LATEX_STYLE.md
│   ├── CHAT_BOOTSTRAPS.md
│   └── DATA_CONTRACTS.md
├── 04_Results/
│   ├── tables/
│   └── figures/
├── 05_References/
├── Templates/
└── Archive/legacy/
```

## Source-of-truth policy

1. **Scientific current state:** `00_Project/PROJECT_STATE.md`.
2. **Research management:** `00_Project/PROJECT_CONTROL.md`.
3. **Execution provenance:** immutable or append-only files in `02_Work_Checkpoints/`.
4. **Chronological memory:** `01_Logbook/`.
5. **Git history:** основной механизм версионирования Markdown knowledge base.
6. **Yandex.Disk:** резервная копия / перенос больших или локальных данных, но не второй независимый master истории.

## Public GitHub safety

Поскольку репозиторий может быть публичным, raw experimental data, большие binary outputs, credentials, private correspondence и материалы с ограничениями не должны попадать в Git по умолчанию. Используйте отдельную локальную папку, например `CEF-Dy-local-data/`, и ссылайтесь на неё через stable dataset IDs.

Рекомендуемая схема:

```text
CEF-Dy/                 # Git-tracked knowledge/code layer
CEF-Dy-local-data/      # raw/private/large data, not tracked
```

## Update workflow

```text
observation / computation
        ↓
WORK_CHECKPOINT
        ↓
scientific review
        ↓
RESEARCH_LOGBOOK
        ↓
DECISION → PROJECT_CONTROL
CURRENT KNOWLEDGE → PROJECT_STATE
```

Численный output не становится scientific fact автоматически.

## Re-entry after a pause

1. Прочитать блок `60-second re-entry` в `PROJECT_STATE`.
2. Прочитать блок `5-minute re-entry` в `PROJECT_CONTROL`.
3. Открыть последний `reviewed` logbook entry.
4. При вычислительном продолжении открыть последний relevant Work checkpoint.
5. Только после этого запускать новый Work job.
