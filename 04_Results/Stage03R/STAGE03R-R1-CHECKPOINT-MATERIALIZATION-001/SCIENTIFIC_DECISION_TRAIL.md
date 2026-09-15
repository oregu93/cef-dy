---
title: "Stage03R: принятый научный checkpoint r1"
version: "1.0"
updated: 2026-09-15
review_status: reviewed
provenance_status: partial
---

# Принятый научный checkpoint r1

Источник capture: принятое задание Project Control
`STAGE03R-R1-CHECKPOINT-MATERIALIZATION-001`, с явным разрешением повторного
запуска после preflight-only остановки. Числа перенесены без повторных расчётов
в [CHECKPOINT.yaml](CHECKPOINT.yaml); статусы задач находятся в
[TASK_STATUS_INDEX.yaml](TASK_STATUS_INDEX.yaml).
Это не независимая artifact-level валидация исходных научных запусков.
Их полные execution artifacts и неизвестные hashes здесь не реконструируются.
Обозначения H1-H5 относятся только к принятому CX-03 review, не заменяют
глобальный HYPOTHESIS_REGISTER и не получают придуманных определений.

## От compatibility к следующему наблюдаемому

1. AF-BASE совместима со всеми R7/R5/R3: ALL_THREE_COMPATIBLE. Это
   historically_conditioned_consistency_test. AF-CX03-CEF несовместима со
   всеми тремя: NONE_COMPATIBLE, stronger_out_of_generation_constraint_test.
   Если CX-03 требует хотя бы одного ground-origin Dy3+ CEF transition,
   ни один из трёх retained historical B2 candidates его не удовлетворяет.
   Это не доказывает non-CEF природу CX-03, не falsifies MOD-CEF-CS15 и
   не исключает все CS15 solutions.
2. CX-03 остаётся underdetermined composite. Исправленный support census:
   BF-006: 14, BF-007: 12, BF-008: 3 scans; объединение содержит 18 scans.
   H1 VIABLE; H2 VIABLE_HIGH_PRIORITY; H3 VIABLE_BUT_UNSUPPORTED;
   H4 VIABLE_AND_WELL_MOTIVATED; H5 STRONGLY_DISFAVOURED.
3. Q topology MIXED_OR_UNRESOLVED: траектория приблизительно (0,k,3),
   k приблизительно 1.8-4.1. При повторной геометрии около (0,3,3)
   decreasing scans поддерживают BF-006 + BF-008, increasing - BF-007.
   Область 38.1-38.5 meV покрыта всеми 18 scans, 54.4-54.8 meV - 10 из 18;
   пересечений с frozen B001 SUPPORT_REGION нет. Coverage не означает detection.
4. Q diagnostic: NO_DETECTED_SYSTEMATIC_TRAJECTORY_CHANGE, только exploratory.
   rho: -0.48333333333333334 и -0.45; exact direction-stratified permutation
   p = 0.06282991515043089; разность направлений при (0,3,3) около 1.9718 sigma.
   Preregistered test не пересёк alpha=0.05. Это не evidence of Q independence;
   post-hoc rescue альтернативными окнами или статистиками не авторизован.
5. Исторические T0-4 predictions: R5 38.1298811227, R3 38.1930563258,
   R7 38.4828849853 meV. Historical conditioning: 6.45, ~18.2, 27.9 meV;
   область ~38 meV не была fit constraint.
6. Первый 38-meV execution FAIL_CLOSED из-за
   population_freeze_before_response_ordering_violation. Его scientific result
   NOT_ESTABLISHED; это только procedural history. Clean rerun
   STAGE03R-CS15-38MEV-PREDICTION-TEST-EXECUTION-001-RERUN-001 является
   authoritative experimental result: 21 eligible scans (11 increasing,
   10 decreasing), sum_X_s = -9.263645033151e-05, Z_global = -2.412984862019,
   one-sided positive p = 0.992088761642, NO_SIGNIFICANT_EXCESS_DETECTED.
   Preregistered existing-data test не устанавливает положительный local
   spectral excess в общей области предсказаний ~38 meV. Он не доказывает
   отсутствие T0-4 и не отвергает R7, R5, R3 или CS15.
7. Visibility/sensitivity review устанавливает только LEVEL_1:
   valid_preregistered_experimental_null. LEVEL_2 и LEVEL_3 ещё не установлены,
   LEVEL_4 не установлен. Решение:
   C_EXPERIMENTAL_SENSITIVITY_LIMIT_REQUIRED_FIRST.

## Visibility bridge и следующий шаг

Авторитетная intrinsic strength:

```text
S_0i = 0.5 * sum_alpha ||P_D0 J_alpha P_Di||_F^2
```

Legacy visibility values имеют статус
LEGACY_VISIBILITY_METRIC_SEMANTICS_UNRESOLVED и не используются количественно.
Intrinsic isotropic S_0i не равна orientation-specific TAS visibility.
Transition tensors не materialized; deterministic regeneration возможна
без нового fit, но здесь не выполняется.

Первый pending task после миграции:
STAGE03R-CS15-38MEV-EXPERIMENTAL-SENSITIVITY-LIMIT-001.
Требуется one-sided upper confidence/sensitivity limit для уже принятого
fixed-window observable в native normalized count-rate/excess units.
Raw detector analysis, holdout, CEF refit, transition-strength input и exchange
не являются входами этой задачи.

Только после валидного LEVEL_2 следует условная задача
STAGE03R-CS15-38MEV-FORWARD-VISIBILITY-001: минимальный orientation-specific
forward calculation, затем сравнение R7/R5/R3 с experimental sensitivity,
и лишь после этого model-level constraint. Тест ~54-55 meV отложен.
Ни одна из этих задач не выполняется и не авторизуется данным capture.

## Обязательные границы интерпретации

- SUPPORT_REGION не является physical excitation energy.
- BF identifier не является physical excitation; midpoint не становится CEF energy.
- CX-03 остаётся underdetermined composite.
- F004 не отображается автоматически на BF-006/BF-007/BF-008.
- Historical rank/loss не являются posterior probability.
- S_0i не является measured TAS intensity.
- Coverage не является detection; lack of BF не означает physical absence.
- Null result не отвергает модель без visibility/sensitivity bridge.
- Exchange physically possible не означает exchange required.
- Post-hoc rescue near-threshold statistical results запрещён.
- Holdout недоступен без отдельного разрешения.
- Первый failed 38-meV run неавторитетен; clean rerun авторитетен.

## Другие ветви

Structure-A PAUSED; quantitative refinement сейчас не требуется.
Stage03D не reopened. MOD-CEF-EXCHANGE DEFERRED и inactive.
Temperature-dependence branch блокирована temperature sensor unit semantics.
IN20 остаётся valuable future independent cross-instrument evidence;
magnetization/g-tensor - later global CEF family validation.

CF-WATCH-PROJECT-ESCALATION-LAYER-001 принят. Обычный search scope Watch
сохраняется; в Project Control передаются только HIGH-relevance findings,
способные изменить scientific priority, stage transition, model-class decision,
interpretation boundary, major provenance authority или next-observable choice.
Сам routing layer не меняет научных выводов.
