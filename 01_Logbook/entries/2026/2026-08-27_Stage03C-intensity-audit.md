---
type: logbook_entry
entry_id: LOG-2026-08-27-01
date: 2026-08-27
status: reviewed
---
# Stage 03C — intensity audit

## Контекст
Проверялась совместимость screened full-cluster PCM с энергетическим кандидатом около $18.25~\mathrm{meV}$ и с F002/F004 observations.

## Результат
Сильный первый PCM transition может быть настроен к основной энергии, однако обязательные переходы около $6.45$ и $27.90~\mathrm{meV}$ не поддерживаются. Нормировка только по detected profiles создаёт selection bias.

## Интерпретация
Следующий этап должен использовать detected и censored F002 совместно и вложенные низкоразмерные effective-charge models.

## Решение
Stage 03D: `M0/M1`, shared scale per `instrument_block_id`, `F004` diagnostic only, exchange deferred.
