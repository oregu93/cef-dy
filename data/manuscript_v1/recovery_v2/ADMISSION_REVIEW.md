# MANUSCRIPT_INTENSITY_ADMISSION_RECOVERY_V2

Дата: 2026-10-19. Статус: `FAIL_CLEANLY`, `READY_FOR_INTENSITY_ADMISSION_REVIEW`.
Это ограниченное восстановление и решение Work-исполнителя для review;
оно не является независимым научным одобрением или разрешением W03 execution.

## Идентичность и границы

До научных изменений проверены remote `main`
`c65cfb1daa8edf4ce85684b5093869c0f287d269` и V1 commit
`415dd1751b7bf232476674af4e7e2571dd89a113`, tree
`f85afbf06db5daf6f5ae8e1e60b0edc512709420`.
V1 опубликован в `origin/work/manuscript-taipan-input-recovery-v1`.
Основной локальный checkout `main` остался на
`45fcf89f5a2571d534da6cf3f70018d3de620d7e`; четыре audit-only пути не изменялись.
Работа выполнена только в отдельном worktree/branch.

V1 таблица и manifest сохранены в указанном commit; исходный manifest также
вложен в `V1_history` обновлённого [manifest](../manuscript_observables_provenance.yaml).
Исходные численные значения в [таблице](../manuscript_observables.csv) сохранены;
новые оценки имеют отдельные поля `v2_diagnostic_*`.

## Holdout-clean восстановление

Из 46 исходных групп полностью исключены 16, содержащие 17 holdout scans.
Частичное вычитание или восстановление недостающего вклада не выполнялось.
Оставшиеся 30 групп восстановлены из 45 discovery scans. Четыре исходных
`not_applicable` scan не использованы; в двух из восстановленных групп состав
уменьшился, что явно записано в [membership.json](membership.json).
Ещё 10 discovery scans исключены вместе со смешанными группами.

Единственный источник counts для нового fit — канонический
`04_Results/Stage02R/W02-02R-B-001/discovery_point_representation.csv`.
Все его записи проверены против frozen split. Stage03A ZIP и смешанная
Stage01 point table для нового fit не открывались. Holdout detector access: **0**.
Для геометрии из A002 point table выбраны только поля координат, энергий и S2;
detector/monitor поля этой смешанной таблицы в расчёт не передавались.

Все V1 площади, даже у исходно чистых групп, зависели от общего centroid/width,
оценённых с holdout. Ни один из этих fitted parameters не использован в V2.
Сохранены только заданная задача около 18 meV и метаданные группировки.
Это targeted reconstruction; независимое blind discovery не заявляется.

Использована хешированная функция Stage03A donor, SHA256
`09dd945c036a6f9286fc8c7fdcd905a75e73528f7b0ab54082f58ef82db5d9e1`.
Модель: Poisson counts с monitor exposure, Gaussian единичной площади,
общий свободный centroid, свободная width на блок и положительный локальный
фон на группу. Заданы округлённый старт 18.0 meV, окно [12,24] meV и старт
FWHM 2.5 meV. Использованы 480 native-energy points без coaddition;
это диагностическая модификация входного набора, не точное воспроизведение V1.

Свежие fits фона порядков 0/1/2 завершились успешно. BIC:
1052.9742062706393 / 1086.3310008053456 / 1227.15400099784.
Выбран порядок 0; reduced deviance 1.5923877259587946,
rank Jacobian 63/63, конечная covariance. Диагностический centroid
17.92982248698777 ± 0.10204089616676741 meV (statistical covariance только).
Другие фоны дали 18.04519526330068 и 18.130900336217877 meV.
Эта чувствительность сохранена; исходная энергия 18.24717836149484 meV
не заменена новой физической оценкой. Полные covariance и parameter layouts
сохранены для всех трёх fits.

## Q и температурный канал

Dataset-wide A002 статус `q unresolved` не распространяется автоматически
на проверенную F002 подвыборку. Поздний reviewed
[Stage03R checkpoint](../../../04_Results/Stage03R/STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001/CHECKPOINT.yaml)
уже принимает `TAIPAN_HKL_SETTING=Pbnm`, identity mapping и CEF frame
`(X,Y,Z)=(b,c,a)`; [связь систем координат](../../../06_Scientific_Understanding/dyfeo3-pbnm-pnma-cef-frame-binding.md)
содержит явную формулу.

Для 45 использованных scans проверены все 1516 coordinate points:
`Q = 2π sqrt((h/a)^2+(k/b)^2+(l/c)^2)` согласуется с raw q
в интервалах округления четырёхзначных q/h/k/l и шестизначных cell parameters;
ошибок 0. Максимальное |raw q − Q(hkl)| = 0.0001163831691659567 Å⁻¹.
Проверены также recorded UB и кинематическая формула из Ei/Ef/S2;
это consistency checks, не новая калибровка углов.
Статус 30 реконструированных групп: `VERIFIED_HKL_AND_Q`.
Все pointwise значения и векторы находятся в [open_scan_geometry.csv](open_scan_geometry.csv).

W03 для single-crystal intensity требует полный вектор в системе transition
tensor: `Q_CEF=2π(k/b,l/c,h/a)`, а не только |Q|.
Projection `Σ(δαβ−Qhatα Qhatβ) Mαβ` и form factor выполняют разные роли;
см. [reviewed polarization contract](../../../06_Scientific_Understanding/neutron-polarization-intrinsic-strength.md).
Ориентационное усреднение powder не подставлялось. Здесь геометрический слой
восстановлен, но он не заменяет instrument-response layer.

`temp` остаётся **UNKNOWN**, не `SAMPLE_TEMPERATURE` и не доказанный setpoint.
Legacy ingest просто переименовал первый `temp`/`temperature`.
A002 отдельно сохраняет `temp`, `T1_Sensor1..4`, `T1_Setpoint1..4`, но не
выбирает уникальный датчик/единицу. Наличие переменного temp и постоянных
setpoints не устанавливает физическое местоположение датчика.
Поле `temperature_K` не заполнено догадкой.

Отдельный sensitivity calculation при условных 3.4/10 K:

| gap (meV) | exp(−gap/kBT), 3.4 K | при 10 K | относительное изменение p0, two-doublet |
|---|---:|---:|---:|
| 18.24717836149484 | 8.962556902025185e−28 | 6.365416929187217e−10 | 6.365417082321301e−10 |
| 6.447, historical context | 2.777737409848085e−10 | 0.0005634495078134193 | 0.0005631319336288909 |
| 1.0, illustrative only | 0.03293914320924288 | 0.3133445760013402 | 0.21350484702638406 |

Заселение именно уровня 18.25 meV пренебрежимо относительно ошибок площадей
(около 26–30% у трёх свежих detected rows). Но D0→D2..D7 допускает нижние
неустановленные уровни, поэтому эта оценка сама по себе не доказывает
неизменность полной ground population для всего Cs15 ensemble.
При одной линии и общей температуре population factor поглощается A_b.
У пары SG042/SG044 raw temp около 10; температура не объявлена отдельным
доказанным blocker этой пары. Остаётся metadata/reporting limitation и
условие проверки при объединении разных температурных режимов.
Ни 6.447, ни 1.0 meV не назначались физическими уровнями.

## Минимальный контракт instrument blocks

| поле | проверенное состояние / ограничение |
|---|---|
| Ef / kf | inst_4615972084: 14.8709–14.8715 meV; inst_f4703b6bd8: 14.8710–14.8714 meV; малые recorded variations |
| mono/analyzer | PG в headers; поздний checkpoint поддерживает PG(002) для experiment |
| collimation | o-40-40-o во всех кандидатах |
| normalization | actual monitor counts как exposure; разные preset totals не требуют отдельной нормировки площади |
| orientation | одинаковые lattice/UB внутри каждого legacy блока; block-to-block UB различается |
| detector/readout | point He-3 поддержан поздним checkpoint; неизменность monitor/detector gain по scans не установлена |
| filters/higher orders | downstream PG поддержан checkpoint; title «two pg in» не является scan-by-scan state record |
| attenuator, gain | UNRESOLVED; не доказаны постоянными |
| focusing/aperture | channels существуют, фактические state/curvature/apertures не закрыты provenance |
| Q-dependent acceptance | MATERIAL_FOR_RELATIVE_INTENSITY; constancy/correction не установлена |
| absolute scale | NOT_APPLICABLE как требование admission; A_b = CONSTANT_BUT_VALUE_UNKNOWN допустим |

Неизвестная **постоянная** эффективность допустима: A_b её поглощает.
Отсутствие metadata не доказывает scan-dependent изменение, но также не
доказывает постоянство. Для текущих строк нет evidence, замыкающего второе.
Точный абсолютный resolution kernel или абсолютное сечение не требуются;
нужно лишь обоснование одинакового/исправленного relative response в данной
малой подвыборке. Уже принятый Stage03R checkpoint оставляет именно
acceptance/focusing/aperture provenance незакрытым.
[Официальный TAIPAN manual](https://www.ansto.gov.au/media/1429/download)
подтверждает наличие отдельно управляемых focusing/autofocus и apertures,
но не сообщает их состояние во время experiment 1296.

Оба блока: **NOT_ADMISSIBLE**.
inst_4615972084: 23 восстановленные группы, 38 scans, 2 quality-pass rows,
0 admitted. inst_f4703b6bd8: 7 групп, 7 scans, 1 quality-pass row, 0 admitted;
этот блок также не удовлетворяет минимуму двух detected rows.

## Quality, censoring, calibration и конечное решение

Независимый от CEF фильтр: area/sigma≥3, finite positive covariance sigma,
full-rank finite covariance, successful optimizer, interior centroid/width/area,
0.65<FWHM<8, centroid внутри [12,24], reduced deviance<2,
max |area-background correlation|<0.95. Collapse: active area bound или area≤1e−8.
Правило является V2 diagnostic screen, не frozen production detection test.

| свежая диагностическая строка | area | sigma | z |
|---|---:|---:|---:|
| SG032 | 194.866103 | 50.796212 | 3.836233 |
| SG042 | 50.027606 | 14.439201 | 3.464707 |
| SG044 | 48.268312 | 14.437868 | 3.343174 |

Единицы: counts per 10⁶ monitor × meV. Индивидуальная нормировка каждой
строки не делалась. Точные значения и источник каждой оценки —
[all_background_measurements.csv](all_background_measurements.csv).
Площади коррелированы через shared centroid/width; full covariance сохранена.
Если admission будет пересмотрен, корреляции нельзя молча заменить
независимыми sigma. Проверка чувствительности к другим background orders
также остаётся частью review, а не основанием выбирать больше detected rows.

Все 46 строк получили ровно одно решение в [row_admission.csv](row_admission.csv):
16 HOLDOUT_CONTAMINATED, 1 FIT_COLLAPSE (SG003), 3 NORMALIZATION_AMBIGUOUS,
26 OTHER_EXCLUSION. Из исходных 8 detections: 5 чистых диагностических,
3 holdout-excluded, 0 admitted. Эти счётчики не суммируются с 38 исходными
non-detection rows как независимые категории новых fits.

Все 38 исходных non-detections остаются diagnostic-only; censor admitted = 0.
`A+1.64485 sigma` — Wald upper limit, не detection threshold `z=3`.
Original selection, bounded fit и shared nuisance parameters не дают
калиброванный censoring likelihood автоматически. V1 пометка
`censor_status=CENSOR_ADMISSIBLE` явно **superseded**.

`ENERGY_SYSTEMATIC_UNAVAILABLE`: traceable absolute calibration uncertainty
не найдена в рассмотренных артефактах. Elastic FWHM не является такой
ошибкой. Statistical sigma не увеличена произвольно.

V1 aggregate energy сохранена как историческое значение, но её роль в этой
таблице изменена с ENERGY на EXCLUDED_FROM_BASELINE_LIKELIHOOD: она содержит
holdout contribution. Новый diagnostic centroid не является автоматической
заменой для W03.

`W03_ALLOWED_OBJECTIVE=ENERGY_ONLY` — верхняя граница допустимого класса
objective, **не разрешение запуска** и не admission исторического aggregate.
Для такого запуска нужен отдельно разрешённый energy input. Joint intensity
и censoring objectives не разрешены. Stage03D не открывался; CEF fitting,
назначение уровней, stage transition и новые holdout measurements не выполнялись.

Следующий шаг: независимый review этой ограниченной подвыборки и минимальное
закрытие relative-response evidence для SG042/SG044. Расширять выборку или
выполнять CEF optimization по этим площадям сейчас не следует.

## Воспроизводимость

`reconstruct.py` и `audit.py` запускаются последовательно из доступной Python
среды с NumPy/SciPy/pandas/PyYAML/matplotlib. Donor проверяется по SHA256;
его `main()` не вызывается. Политика и runtime versions сохранены в
[fit_summary.json](fit_summary.json). Машиночитаемое решение —
[admission_summary.yaml](admission_summary.yaml), hashes — в provenance manifest.
