---
title: "Stage03R: принятый научный checkpoint r2"
version: "1.0"
updated: 2026-09-16
review_status: reviewed
provenance_status: partial
---

# Принятый научный checkpoint r2

Этот checkpoint материализует принятые Project Control результаты без нового
расчёта. Точные структурированные значения находятся в
[CHECKPOINT.yaml](CHECKPOINT.yaml), а статусы задач - в
[TASK_STATUS_INDEX.yaml](TASK_STATUS_INDEX.yaml). Исторический
[checkpoint r1](../STAGE03R-R1-CHECKPOINT-MATERIALIZATION-001/SCIENTIFIC_DECISION_TRAIL.md)
сохраняется без изменений, включая первый неавторитетный FAIL_CLOSED запуск и
авторитетный clean rerun.

## Уровни evidence около 38 meV

- LEVEL_0 установлен: experimental coverage.
- LEVEL_1 установлен: fixed-window experimental null.
- LEVEL_2 установлен: experimental-observable sensitivity.
- LEVEL_3 не установлен: отсутствует quantitative model-to-TAIPAN bridge.
- LEVEL_4 не установлен.

Для LEVEL_2 point estimate равен -9.263645033151e-05, standard error -
3.839081288474e-05, а zero-signal expected one-sided 95% sensitivity -
6.314726781508e-05 в native normalized count-rate/excess units. Последняя
величина не является physical nonnegative signal upper limit и сама по себе
не является model-rejection threshold. Physical upper limit не установлен.

## Probe ensemble и forward visibility

`CS15-HIST-B2-MINI-001` - historical exploratory probe ensemble. R3/R5/R7
служат methodological probes для построения model-to-experiment discrimination
machinery. Они не являются current models, preferred candidates, posterior
ensemble или representative allowed parameter-space population.

Review `STAGE03R-CS15-38MEV-FORWARD-VISIBILITY-001` принят с correction.
Forward comparison BLOCKED, LEVEL_3 NOT_ESTABLISHED. CEF tensors можно
детерминированно восстановить без refit, но остаются два независимых слоя:
instrument resolution/acceptance и перевод cross-section в detector/monitor
scale. Ни experimental null, ни LEVEL_2 sensitivity пока не отвергают модели.

## TAIPAN response и instrument provenance

Для exact 21-scan population hash равен
`e19e41e794b51dcb631dfff9a8751c7a828c37f55d063043e4807dfc45781a30`.
Kinematic layer substantially recoverable. Exact validated 38-meV resolution
kernel и absolute detector/monitor scale не установлены.

Experiment-specific поддержаны PG(002) monochromator и analyzer,
`o-40-40-o`, fixed $E_f \approx 14.87$ meV, downstream PG filter, point He3
detector и наличие focus-control channels. Не закрыты mono/analyzer mosaic,
реальное focusing/autofocus state и curvature, apertures/slits, exact detector
geometry, physical sample-mosaic semantics и absolute calibration. Proposal
`15702` остаётся `UNVERIFIED`.

Доступный public/existing provenance не закрывает exact resolution
reconstruction. Текущее состояние: `RESOLUTION_READINESS:
SENSITIVITY_ENVELOPE_ONLY`, `absolute_scale_status: CALIBRATION_REQUIRED`.
Основной внешний шаг - запросить архивные instrument setup/log/SICS records
experiment 1296 у ANSTO. Если они недоступны, допустимый следующий design -
preregistered assumption-transparent resolution sensitivity envelope.
McStas/RESTRAX могут быть полезны позднее; production execution не разрешена.

## Coordinate и site contract

Single-ion CEF contract: Pbnm #62, Dy orbit 4c, CEF axes X=b, Y=c, Z=a.
Site tensor transport: $M_s=R_sM_{\rm ref}R_s^T$; для независимых sites
$I=\sum_s I_s$. Это правило нельзя автоматически переносить на coherent или
exchange-coupled modes. Structure-A для этого не требуется возобновлять.

TAIPAN HKL записаны в Pbnm: $(h,k,l)_{\rm TAIPAN}=(h,k,l)_{\rm Pbnm}$.
Publication HK0 согласуется через
$(H,K,L)_{\rm Pnma}=(k,l,h)_{\rm Pbnm}$. Поэтому Q contract valid as written,
а CEF mapping остаётся $2\pi(k/b,l/c,h/a)$.

## Текущая граница

Главный scientific/provenance blocker - experiment-specific TAIPAN
resolution/acceptance и intensity-scale bridge. Stage02R остаётся
COMPLETED_WITH_LIMITATIONS; Stage03D suspended; exchange, 54-55 meV и
Structure-A deferred/paused; holdout unauthorized. SUPPORT_REGION нигде не
трактуется как physical excitation energy.
