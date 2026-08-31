---
title: "CEF Dy / DyFeO3 — база знаний исследования"
type: project_index
project_id: CEF-Dy
status: active
schema_version: "2.1"
updated: 2026-08-31
language_content: ru
language_metadata: en
---

# CEF Dy / DyFeO$_3$ — база знаний исследования

> [!abstract] Назначение
> Эта папка — автономная база знаний проекта по кристаллическому электрическому полю Dy$^{3+}$ в DyFeO$_3$. Она рассчитана на Obsidian, Git/GitHub и обычные Markdown-редакторы. ChatGPT используется как рабочий интерфейс, но не является единственным хранилищем состояния исследования.

## Быстрая навигация

| Что требуется | Файл |
|---|---|
| За минуту восстановить научное состояние | [PROJECT_STATE](00_Project/PROJECT_STATE.md) |
| За несколько минут понять, что делаем сейчас и почему | [PROJECT_CONTROL](00_Project/PROJECT_CONTROL.md) |
| Проверить реестр существенных результатов | [RESULT_REGISTER](00_Project/RESULT_REGISTER.yaml) |
| Проверить рабочие гипотезы | [HYPOTHESIS_REGISTER](00_Project/HYPOTHESIS_REGISTER.yaml) |
| Проверить принятые решения | [DECISION_REGISTER](00_Project/DECISION_REGISTER.yaml) |
| Восстановить историю исследования | [RESEARCH_LOGBOOK](01_Logbook/RESEARCH_LOGBOOK.md) |
| Проверить конкретный вычислительный запуск | `02_Work_Checkpoints/` |
| Проверить правила ведения базы знаний | [RESEARCH_KB_GUIDE](03_Protocols/RESEARCH_KB_GUIDE.md) |
| Проверить правила Markdown/LaTeX | [MARKDOWN_LATEX_STYLE](03_Protocols/MARKDOWN_LATEX_STYLE.md) |
| Восстановить роли чатов ChatGPT | [CHAT_BOOTSTRAPS](03_Protocols/CHAT_BOOTSTRAPS.md) |

## Текущая ветка исследования

`Stage 03D` — вложенный фит низкоразмерных моделей эффективных зарядов `M0/M1` к энергии CEF-перехода и к обнаруженным/цензурированным данным `F002`, с одним общим параметром нормировки на `instrument_block_id`.

`F004` остаётся диагностическим наблюдением и не используется как обязательный CEF-уровень. Обменное поле на Stage 03D не включается.

## Архитектура знания

```text
наблюдение / расчёт
        ↓
WORK_CHECKPOINT
        ↓
научная проверка
        ↓
RESULT_REGISTER / HYPOTHESIS_REGISTER
        ↓
RESEARCH_LOGBOOK
        ↓
решение → PROJECT_CONTROL
текущее знание → PROJECT_STATE
```

Численный вывод программы не становится научным фактом автоматически.

## Структура репозитория

```text
CEF_Dy/
├── README.md
├── PROJECT_MANIFEST.yaml
├── 00_Project/
│   ├── PROJECT_STATE.md
│   ├── PROJECT_CONTROL.md
│   ├── PROJECT_METADATA.yaml
│   ├── RESULT_REGISTER.yaml
│   ├── HYPOTHESIS_REGISTER.yaml
│   ├── DECISION_REGISTER.yaml
│   └── MIGRATION_NOTES.md
├── 01_Logbook/
│   ├── RESEARCH_LOGBOOK.md
│   └── entries/2026/
├── 02_Work_Checkpoints/
├── 03_Protocols/
│   ├── RESEARCH_KB_GUIDE.md
│   ├── KNOWLEDGE_RULES.md
│   ├── MARKDOWN_LATEX_STYLE.md
│   ├── DATA_CONTRACTS.md
│   └── CHAT_BOOTSTRAPS.md
├── 04_Results/
├── 05_References/
├── Templates/
├── scripts/
├── configs/
└── Archive/legacy/
```

## Источник истины и версионирование

1. Текущее научное состояние — `00_Project/PROJECT_STATE.md`.
2. Управление исследованием — `00_Project/PROJECT_CONTROL.md`.
3. Существенные результаты и их статус — `RESULT_REGISTER.yaml`.
4. Рабочие гипотезы — `HYPOTHESIS_REGISTER.yaml`.
5. Воспроизводимость вычислений — `02_Work_Checkpoints/`.
6. Хронология и логика изменения направления — `01_Logbook/`.
7. Git — основной механизм истории версий текстового слоя проекта.
8. Yandex.Disk — резервное копирование и перенос больших/локальных данных.

## Работа на нескольких компьютерах

Репозиторий может быть клонирован на рабочий компьютер и ноутбук. Каждая
машина имеет собственную локальную копию и собственный
`configs/local_paths.yaml`.

Основное правило:

```text
начало работы → git pull
конец существенной сессии → validate → commit → git push
```

Продробно: [RESEARCH_KB_GUIDE](03_Protocols/RESEARCH_KB_GUIDE.md) 

## Автоматическое обновление кратких блоков

Блоки `60-second re-entry` и `5-minute re-entry` не следует редактировать вручную. Они формируются из `PROJECT_METADATA.yaml` и реестров:

```powershell
python scripts/kb_refresh.py
python scripts/kb_validate.py
```

Перед существенным Git-коммитом рекомендуется:

```powershell
python scripts/kb_refresh.py --check
python scripts/kb_validate.py --strict
```

## Безопасность публичного GitHub

В Git по умолчанию не следует помещать необработанные экспериментальные архивы, большие бинарные выходы оптимизаторов, приватную переписку, материалы с ограничениями, токены и локальные конфигурации путей. Для таких данных используйте отдельную директорию рядом с репозиторием, например `CEF_Dy_Data/`, а внутри базы знаний ссылайтесь на устойчивые `dataset_id`.
