---
title: "DyFeO3 XRD campaign recovery and provenance normalization"
type: research_log_entry
entry_id: LOG-2026-09-14-01
date: 2026-09-14
status: completed
---

# DyFeO3 XRD campaign recovery and provenance normalization

## Контекст

Восстановлен полный project-local архив лабораторной powder-XRD серии DyFeO3,
полученной на Rigaku SmartLab, вместе с двумя историческими поколениями
FullProf refinements (nov19, mar21) и отдельным декабрьским follow-up.

Private artifact authority материализована в companion repository
oregu93/cef-dy-private.

## Восстановленные raw acquisitions

Идентифицировано восемь уникальных ненулевых .ras byte streams:

- семь cryostat acquisitions основной серии:
  - приблизительно 296-298 K, run 100;
  - приблизительно 4.17 K, run 101;
  - 100 K, run 102;
  - 200 K, run 102;
  - 20 K, run 106;
  - 100 K repeat, run 106;
  - 300 K, run 106;
- отдельный December 2019 standard-geometry follow-up, run 171.

Повторные acquisitions при 100 K и около 300 K сохранены как независимые
измерения, а не как дубликаты.

## Historical refinement lineage

Восстановлены historical FullProf chains nov19 и mar21.

Рабочий review показал:

- nov19 в основном использует полный основной angular range около 20-155 deg;
- mar21 использует существенно сокращённые ranges, обычно около 20-60 deg
  (300 K около 20-65 deg);
- O1/O2 coordinates и nuisance/thermal-factor treatment недостаточно
  устойчивы между historical refinements для принятия этих структур как
  окончательной structural authority;
- historical refinements сохраняются как provenance и возможные starting values.

Новый refinement в рамках recovery/import не выполнялся.

## Private provenance materialization

Controlled private import завершён.

asset: EXP-XRD-DYFEO3-CAMPAIGN-001
private repository: oregu93/cef-dy-private
commit: c5286a0076d01ab4067655eff0102b31a7466a39

Импортировано 104 нормализованных artifact records.

Проверка перед admission:

- 104/104 legacy SHA-256 matches
- 0 internal exact-duplicate groups
- 0 unexplained imported artifacts

Восемь primary raw acquisitions получили stable private artifact IDs.

Существующий ART-XRD4K-CIF-001 связан с raw acquisition run 101 и historical
mar21/4K refinement provenance без хранения второго идентичного CIF byte stream.

## Научное следствие

Наличие собственного low-temperature и temperature-dependent XRD provenance
теперь подтверждено значительно лучше, чем ранее.

Это не делает historical 4 K CIF или другие historical refinements
финально validated structures.

Следующий научный шаг для этой ветви - bounded review в
04 - Structure & Conventions:

- оценить статус STRUCTURE-A;
- отделить подтверждённые acquisition/provenance facts от качества refinement;
- решить, достаточно ли historical structure для ограниченного diagnostic
  использования или требуется новый controlled refinement до structural admission.

Uniform full-range re-refinement научно оправдан, но не выполняется
автоматически и не является условием завершения этого recovery task.
