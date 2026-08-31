---
title: "Knowledge Base v2.0 -> v2.1"
type: migration_note
status: active
updated: 2026-08-28
---

# Миграция Knowledge Base v2.0 → v2.1

## Причина

Версия 2.0 правильно разделила Project State, Project Control и Logbook, но сохраняла слишком большое количество англоязычной описательной лексики и не имела достаточно строгой автоматизации статусов знания.

## Основные изменения v2.1

1. Содержательный текст почти полностью переведён на русский; английский оставлен главным образом для machine-facing metadata, IDs, filenames и программных сущностей.
2. Добавлен `PROJECT_METADATA.yaml` как источник автоматически формируемых `60-second re-entry` и `5-minute re-entry`.
3. Добавлены `RESULT_REGISTER.yaml`, `HYPOTHESIS_REGISTER.yaml`, `DECISION_REGISTER.yaml`.
4. Добавлен `RESEARCH_KB_GUIDE.md` с инструкциями исследователю.
5. Добавлены `kb_refresh.py` и `kb_validate.py`.
6. Проведён консервативный аудит `reviewed/validated`.
7. Добавлены автономные logbook entries и шаблоны.
8. Усилена Markdown/LaTeX validation.

## Аудит статусов

В v2.1 существенные исторические численные результаты, которые известны из Project State, но пока не связаны в этой базе с отдельным воспроизводимым checkpoint/artifact, имеют `status: reviewed`, а не `validated`.

Это **не является научным downgrade**. Это правило provenance: `validated` в базе знаний означает не только содержательную уверенность, но и наличие сохранённого проверяемого evidence и выполненных validation criteria.

После подключения Stage 03A/03C outputs и benchmark scripts соответствующие результаты можно повысить до `validated` без изменения их численного значения.

## Legacy

Снимок локально доступной Knowledge Base v2.0 сохранён в:

```text
Archive/legacy/KnowledgeBase_v2.0/
```

Локально доступный старый `DyFeO3_PROJECT_STATE.md` сохранён как:

```text
Archive/legacy/DyFeO3_PROJECT_STATE_v1.1.md
```

Указание v2.0 на Project State v1.2 сохранено как историческое provenance, но byte-identical v1.2 в текущем локальном sandbox не подтверждён и потому не объявляется архивированным в этом пакете.
