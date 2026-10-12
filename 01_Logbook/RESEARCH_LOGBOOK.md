---
title: "CEF Dy — Research Logbook"
type: logbook_index
status: active
updated: 2026-10-12
format: hybrid
---

# CEF Dy — Research Logbook

> [!abstract] Назначение
> Хронологическая память исследования. Этот master-файл остаётся компактным индексом; существенные исследовательские эпизоды хранятся отдельными автономными Markdown-файлами.

## Текущая ветка

`M03R` — LEVEL_2 experimental sensitivity established, LEVEL_3/LEVEL_4 absent.
Operational RESULT #65–#67 опубликованы 2026-10-12 и ожидают Project Control
review; они не меняют scientific boundary автоматически. Текущий science-first
вопрос — какой bounded successor действительно следует из этих результатов,
при сохранении unresolved resolution/acceptance и intensity-scale bridge.

Stage03D suspended; exchange deferred; raw/holdout unauthorized; Structure-A
paused; McStas/RESTRAX production unauthorized.

## Индекс — 2026

| Дата / период | Entry ID | Тема | Итог |
|---|---|---|---|
| 2026-08-13 | [`LOG-2026-08-13-01`](entries/2026/2026-08-13_TAIPAN-inventory-and-preliminary-INS.md) | Инвентаризация TAIPAN и предварительный INS-анализ | Набор данных классифицирован; 44.4 meV оставлена неназначенной; приоритет смещён к CEF-наблюдаемым. |
| 2026-08 | [`LOG-2026-08-00-01`](entries/2026/2026-08_PCM-and-effective-charge-exploration.md) | PCM и effective-charge exploration | PCM принят как структурный prior/seed, а не уникальное решение обратной задачи. |
| 2026-08 | [`LOG-2026-08-00-02`](entries/2026/2026-08_Global-CEF-search-and-B2-manifold.md) | Глобальный CEF-поиск и B2 manifold | Установлена energy-only degeneracy; B2 оставлен только как working manifold. |
| 2026-08-21 | [`LOG-2026-08-21-01`](entries/2026/2026-08-21_Conventions-exchange-intensity-identifiability.md) | Conventions, exchange и идентифицируемость интенсивностей | Усилены frame/convention checks; adopted shared scales и censored data; formalized exchange caveat. |
| 2026-08-27 | [`LOG-2026-08-27-01`](entries/2026/2026-08-27_Stage03C-intensity-audit.md) | Stage 03C intensity audit | Определено направление `M0/M1` для Stage 03D; `F004` diagnostic only. |
| 2026-08-28 | [`LOG-2026-08-28-01`](entries/2026/2026-08-28_Knowledge-base-v2.1.md) | Knowledge Base v2.1 и аудит статусов | Введены machine-readable реестры, автоматические re-entry blocks и консервативный `reviewed/validated` policy. |
| 2026-08-31 | [`LOG-2026-08-31-01`](entries/2026/2026-08-31_Local-deployment-and-multi-machine-workflow.md) | Локальное развёртывание и multi-machine workflow | Адаптация под GitHub. |
| 2026-09-04 | [`LOG-2026-09-04-01`](entries/2026/2026-09-04_Stage02R-B001-blind-catalogue.md) | Stage 02R B-001 — слепой каталог BF | Восемь BF в режиме `monitor_controlled`, все Tier-1; результат принят с ограничениями, физическое назначение не выполнялось. |
| 2026-09-14 | [`LOG-2026-09-14-01`](entries/2026/2026-09-14_DyFeO3-XRD-campaign-recovery.md) | Восстановление DyFeO3 powder-XRD campaign | Восемь уникальных raw acquisitions и historical FullProf provenance нормализованы в private repo; historical structures не повышены до final authority. |
| 2026-10-12 | [`CEF-WKB-CANONICAL-AUDIT-RECOVERY-2026-10-12`](../02_Work_Checkpoints/CEF-WKB-CANONICAL-AUDIT-RECOVERY-2026-10-12/AUDIT_REPORT.md) | Canonical current-state audit and minimal re-entry repair | Зафиксированы #65–#67 RESULT previews без scientific promotion, science-first freeze, autonomy PARTIAL и scoped materialization debt. |

## Когда создавать отдельную запись

Отдельная запись создаётся, если произошло хотя бы одно:

- получен новый существенный научный результат;
- изменена или отвергнута рабочая гипотеза;
- принято методологическое решение;
- обнаружена существенная ошибка или аномалия;
- завершён вычислительный этап;
- изменилась иерархия моделей;
- новое свидетельство существенно меняет интерпретацию.

Мелкие технические действия остаются в Work checkpoint.
