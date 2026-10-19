# HOLDOUT_CLEAN_ENERGY_ADMISSION_V1 — adjudication

Дата: 2026-10-19. Решение: **MODEL_DEPENDENT_ENERGY**.
Статус: `READY_FOR_ENERGY_ADMISSION_REVIEW`.

Один precise energy constraint не допущен. Сохранённая подвыборка даёт
конечный fitted component около 18 meV при всех рассмотренных вариантах,
но положение существенно зависит от фона и предположения об общей энергии
двух instrument blocks. Это вывод Work-исполнителя для независимого review,
а не разрешение production CEF fitting.

## 1. Checkpoint и происхождение

Использован неизменённый checkpoint
`45a0c7964b12f23806e2a3c128263d0614a7914d`, tree
`d469861a685bedb8811fa877a78da61af80895fc`, parent/base
`dc339abbc70b0e355c7e27beada8474d1af0ba5a`.
Remote main перед adjudication: `c65cfb1daa8edf4ce85684b5093869c0f287d269`.

[Integrity record](checkpoint_integrity.json): 173 assertions PASS. Все 9
исходных файлов совпадают с Git checkpoint. JSON/CSV/parameters/covariances
согласованы: 45 моделей, 54 centroid rows, 45 covariance matrices.
Проверены frozen split/count hashes, source membership и точное совпадение
использованных counts/monitor/energy с discovery source. В окнах ±5/±6/±7
сохранены 400/480/560 points соответственно; каждое содержит 45 scans и
30 profiles. Grid не перезапускался. Новые optimizer calls: 0.

Полные scan IDs, raw IDs, исходные checksums и profile/block membership:
[source_scans.csv](source_scans.csv). Все строки — discovery; holdout access=0.
В V2 уже исключены все смешанные profile groups. Counts в adjudication не
переоценивались: они проверялись только на совпадение с сохранённым source.

## 2. Допустимый ансамбль

Все 45 моделей имеют `NUMERICALLY_VALID` по сохранённым критериям:
optimizer success, finite full-rank covariance, centroid/width внутри bounds,
reduced deviance <2. Межстартовые различия малы относительно statistical sigma.

18 common-centroid fits классифицированы `SCIENTIFICALLY_ADMISSIBLE` **только
как условные варианты ансамбля sensitivity**: фон 0/1/2, окна ±5/±6/±7 meV,
одна общая или две block-specific widths. Ни одна строка не является новой
независимо admitted measurement. Девять separate-centroid и 18 single-block
fits — `DIAGNOSTIC_ONLY` для проверки общей энергии. REJECTED=0.
Индивидуальные решения и причины: [model_adjudication.csv](model_adjudication.csv).

Свободная nonnegative area предусмотрена на каждый профиль. Intensity ratios,
абсолютная нормировка между blocks или CEF transition strengths не связывают
их энергии. Multiplicative response differences поэтому сами по себе не
препятствуют проверке centroid. Однако geometry-dependent line shape или
energy offset могут менять положение и требуют отдельного рассмотрения.

Численная допустимость не доказывает идеальный фон: reduced deviance joint
models составляет приблизительно 1.276–1.731. Constant background обычно
даёт худшие residuals, но проходит ранее заданный diagnostic screen. Он
сохранён в conservative sensitivity ensemble; новый post-hoc cutoff для
получения желаемой энергии не вводился. AICc/BIC не превращены в posterior
weights. Особенно нельзя ранжировать разные окна по абсолютному IC, поскольку
наборы points различаются. Близость к 18.247 или 18.226 нигде не является
критерием допуска или веса.

## 3. Раздельная sensitivity

Общий диапазон joint centroids:
**17.92222252972972–18.13090493378874 meV**.
Медиана 18.05724227224392; среднее 18.032057912219347 meV.
Полный span 0.20868240405902228 meV; descriptive sample SD по grid
0.06992838175133477 meV; максимальное отклонение от медианы
0.13501974251419924 meV. Это описания deterministic grid, не error bar
среднего и не statistical model probabilities.

Компоненты ниже вычислены **попарно при фиксированных остальных dimensions**.
«Максимальный span» — полный размах при изменении только названного параметра,
не ±sigma. Компоненты взаимодействуют, поэтому складывать их в quadrature нельзя.

| Изменяемый фактор | Максимальный span, meV | Медиана span по фиксированным strata, meV |
|---|---:|---:|
| background order | 0.20432556583361716 | 0.15371905435265454 |
| fit window | 0.06716753312793955 | 0.02898637509326285 |
| shared/per-block width | 0.035362508697623696 | 0.014834202098835902 |

Все paired strata, ranges, means, medians и descriptive SD записаны в
[summary](energy_admission_summary.yaml). Условные группы имеют следующие диапазоны:

| Dimension | Значение | Joint centroid range, meV | Median, meV |
|---|---|---|---:|
| background | 0 | 17.922222530–17.968110570 | 17.941788029 |
| background | 1 | 18.045200094–18.073980672 | 18.057242272 |
| background | 2 | 18.063737401–18.130904934 | 18.095507083 |
| half-window | 5 | 17.949940232–18.073980672 | 18.064457285 |
| half-window | 6 | 17.929823458–18.130904934 | 18.045515272 |
| half-window | 7 | 17.922222530–18.126548096 | 18.057242272 |
| width | shared | 17.938918397–18.099828579 | 18.058809377 |
| width | per-block | 17.922222530–18.130904934 | 18.055675167 |

Order-0 образует нижнюю полосу, отделённую от orders 1/2. Это структура
дискретного analysis ensemble; она не доказывает несколько физических пиков
и не является оценкой multimodal posterior.

Сохранённые conditional statistical sigma: **0.08344563151350837–
0.1088397538202497 meV**. Они получены из локальной covariance с множителем
`max(deviance/dof,1)`: это approximation с residual-dispersion scaling,
а не чистая Poisson counting sigma или доказанное coverage. Отдельная
unscaled curvature sigma дана для каждого варианта в
[w03_energy_variants.csv](w03_energy_variants.csv). Between-model spread
в эти sigma не включён.

## 4. Block consistency

Block 1=`inst_4615972084`: 38 scans / 23 profiles.
Single-block centroid range **17.802471617584313–18.121740717081202** meV,
median 18.056174164158488; statistical sigma 0.09860404481170074–
0.14545126333345515 meV.

Block 2=`inst_f4703b6bd8`: 7 scans / 7 profiles.
Single-block range **17.934085726266087–18.23511741604134** meV,
median 18.146823346642467; statistical sigma 0.14452132231432432–
0.1683123214210058 meV. Эти medians не составляют пару независимых измерений.

В таблице — matched separate-centroid models; Δ=E(block 1)−E(block 2).
Sigma разности восстановлена как `sqrt(C11+C22−2*C12)` из saved covariance,
а не из предположения о независимости. Из-за pooled residual scaling она
может отличаться от sigma самостоятельных block fits.

| Half-window | Background | E1, meV | E2, meV | Δ ± conditional sigma, meV | Δ deviance | LRT p |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 0 | 17.825082 | 18.235127 | −0.410044 ± 0.218841 | 3.518776 | 0.060677 |
| 5 | 1 | 18.092868 | 18.034886 | +0.057982 ± 0.196797 | 0.085808 | 0.769576 |
| 5 | 2 | 18.101983 | 17.934090 | +0.167893 ± 0.177459 | 0.668328 | 0.413635 |
| 6 | 0 | 17.810409 | 18.166743 | −0.356334 ± 0.220446 | 3.108125 | 0.077903 |
| 6 | 1 | 18.039277 | 18.056147 | −0.016870 ± 0.197965 | 0.007480 | 0.931078 |
| 6 | 2 | 18.121754 | 18.183837 | −0.062083 ± 0.189195 | 0.047144 | 0.828110 |
| 7 | 0 | 17.802480 | 18.146789 | −0.344309 ± 0.233128 | 2.938419 | 0.086495 |
| 7 | 1 | 18.056171 | 18.054771 | +0.001400 ± 0.199694 | 0.000051 | 0.994276 |
| 7 | 2 | 18.105333 | 18.193586 | −0.088253 ± 0.184996 | 0.162266 | 0.687079 |

Точная таблица: [block_consistency.csv](block_consistency.csv).
LRT использует nominal χ²(1). Active nonnegative areas и excess deviance
ограничивают точность этой asymptotic calibration; bootstrap не выполнялся.
Все approximate Δ±1.96sigma интервалы включают 0, но их объединённая оболочка
около [−0.839, +0.516] meV широка. Ни p>0.05, ни пересечение интервалов
не являются equivalence test. Допуск на practically negligible offset заранее
не задан.

Заключение: **BLOCK_DEPENDENCE_UNRESOLVED**. Общий centroid допустим как
условная модель для sensitivity comparison, но его физическая общность
не установлена достаточно для одного precise manuscript constraint.
Saved fits проверяют эмпирический сдвиг; они не отделяют calibration offset
от background, geometry-induced line-shape или возможной физической разницы.
Absolute energy-calibration systematic остаётся unavailable, не нулевой.

## 5. W03 representation и решение

Выбран ровно один terminal state: `MODEL_DEPENDENT_ENERGY`.
`ADMITTED_ENERGY_MEV=null`, единая `STAT_SIGMA_MEV=null`, единая
`MODEL_SYSTEMATIC_MEV=null`. Ни median, ни midpoint не объявлены measurement.
Исходные observables CSV и provenance manifest остаются byte-identical checkpoint;
старый holdout-mixed aggregate не возвращён в likelihood.

Для последующего разрешённого ENERGY_ONLY sensitivity workflow подготовлен
[конечный набор вариантов](w03_energy_variants.csv): 18 joint variants и
18 labelled single-block stress variants. Для каждого фиксированного m:

`q_m(theta) = (DeltaE_CEF(theta) − E_m)^2 / s_m^2`.

Это conditional Gaussian approximation с указанными выше ограничениями sigma.
Весь PCM/Cs15 run использует один заранее фиксированный m. Для всех m должны
быть одинаковы разрешённые CEF settings, assignment policy, restart budget
и критерии отбора. Все результаты сохраняются с variant_id. Нельзя сложить
18 terms как независимые measurements, менять m внутри оптимизации, выбрать
run с желаемой wavefunction или ближайший к historical/literature centroid.

Нужно публиковать per-variant supports, их union («совместимо хотя бы с одним
вариантом») и intersection («совместимо со всеми») при одинаковой threshold
policy. Вывод считается robust только при устойчивости по всему joint ensemble
и single-block stress tests. Пустое intersection прямо сообщается. Grid
frequency не задаёт prior weights. Отдельные block fits не являются двумя
дополнительными независимыми constraints поверх joint fit.

Этот representation поддерживает **diagnostic sensitivity propagation**;
он не является разрешением W03 execution, scalar admission или утверждением
об абсолютной шкале энергии. Ни CEF fitting, ни intensity/censor admission
в этой задаче не выполнялись.

## 6. Сравнения после фиксации решения

Сначала записан [energy_decision_frozen.json](energy_decision_frozen.json),
SHA256 `d8005b50a224d40d6aa658fcb755e4dfc5a27211184ddc443d08acfb8d0a27a5`;
только затем вычислены следующие differences:

| Comparator | Joint variant − comparator, meV | Median difference, meV |
|---|---|---:|
| old TAIPAN 18.24717836149484 | [−0.32495583176512, −0.11627342770609772] | −0.18993608925091898 |
| literature ~18.226 | [−0.3037774702702798, −0.09509506621125752] | −0.16875772775607878 |

Это описательные differences, не independent significance test. Old aggregate
перекрывается по scans с текущим набором и содержит holdout. Для literature
здесь не установлена полная uncertainty model. Сравнения не меняют ensemble,
decision, sigmas или weights.

## 7. Температура и завершение

`TEMPERATURE_SEMANTICS=UNKNOWN`; sample T не придумана. Фитируемая позиционная
модель не содержит T, а amplitudes свободны по профилям. Поэтому неизвестная
sensor binding сама по себе не блокирует **условную centroid extraction**.
Это не доказательство физической T-независимости линии и не основание
пренебречь lower-level populations в general Cs15 intensity model.
`Q_STATUS=VERIFIED_HKL_AND_Q` наследуется от V2 для ровно этих 45 scans.

Следующий точный шаг — независимый review конечного model-dependent
representation и block limitations перед отдельным решением о W03 execution.
Новые измерения, расширение grid, коррекция main и разрешение production
в текущую adjudication не входят.

Для воспроизведения только этого adjudication: `adjudicate_saved_grid.py`;
для bounded проверки outputs: `validate_adjudication.py`.
Оба скрипта не импортируют fit engine и не вызывают optimizer.
Hashes исходного checkpoint и новых артефактов:
[ADJUDICATION_SHA256SUMS](ADJUDICATION_SHA256SUMS).
