---
type: logbook_entry
entry_id: LOG-2026-08-21-01
date: 2026-08-21
status: reviewed
---
# Conventions, exchange и идентифицируемость интенсивностей

## Контекст
Возник риск смешения legacy direct labels с canonical Hutchings notation и риск неидентифицируемости интенсивностей из-за свободных нормировок.

## Результат
Разделены direct PCF/CFE и canonical $C_s$ conventions; зафиксирована необходимость явного rotation/conversion. Для интенсивностей принято правило общего scale на физически обоснованный instrument block и явного учёта non-detections.

## Интерпретация
Корректные energies сами по себе не защищают от frame/convention ошибок в transition tensors. Свободный scale на каждый scan может уничтожить физическую информацию об относительных интенсивностях.

## Решение
Ввести обязательные convention regression tests и shared-block normalization. Exchange выделить в отдельный последующий уровень модели.
