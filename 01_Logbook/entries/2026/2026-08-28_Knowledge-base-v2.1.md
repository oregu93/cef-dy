---
type: logbook_entry
entry_id: LOG-2026-08-28-01
date: 2026-08-28
status: reviewed
---
# Knowledge Base v2.1 и аудит статусов

## Контекст
Монолитный Project State создавал смешение текущего знания, истории, планирования и вычислительного provenance.

## Вопрос
Как сделать исследование быстро восстанавливаемым после пауз и пригодным для Obsidian/Git/автоматизированной проверки?

## Результат
Введены уровни `PROJECT_STATE`, `PROJECT_CONTROL`, `WORK_CHECKPOINTS`, hybrid `RESEARCH_LOGBOOK`, а также machine-readable `RESULT_REGISTER`, `HYPOTHESIS_REGISTER`, `DECISION_REGISTER` и `PROJECT_METADATA`.

Краткие re-entry blocks теперь формируются автоматически. Введён консервативный audit: численные результаты без привязанного воспроизводимого artifact получили `status: reviewed`, а не `validated`.

## Интерпретация
Статус знания теперь зависит не только от формулировки в тексте, но и от сохранённого provenance. Это уменьшает риск незаметного превращения рабочего результата в «установленный факт».

## Решение
Использовать v2.1 как первую Git-ready структуру проекта. Перед существенным commit выполнять `kb_refresh` и `kb_validate`.

## Следующий шаг
Разложить локальную директорию Obsidian/Git и затем перейти к design review Stage 03D.
