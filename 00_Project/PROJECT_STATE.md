---
title: "DyFeO3 — Project State"
type: project_state
project_id: CEF-Dy
status: active
version: "3.1"
updated: 2026-09-02
review_status: working
---

# DyFeO$_3$ — Project State

> [!abstract] Назначение
> Этот файл содержит текущее научное состояние исследования кристаллического
> поля Dy$^{3+}$ в DyFeO$_3$.
>
> Здесь фиксируется прежде всего:
>
> - что непосредственно следует из эксперимента;
> - что получено обработкой экспериментальных данных;
> - какие физические назначения являются рабочими гипотезами;
> - какие модели рассматриваются и зачем;
> - какие выводы в настоящее время считаются установленными;
> - какие вопросы остаются открытыми.
>
> История исследования находится в
> [RESEARCH_LOGBOOK](../01_Logbook/RESEARCH_LOGBOOK.md),
> управление следующими действиями — в
> [PROJECT_CONTROL](PROJECT_CONTROL.md),
> экспериментальные свидетельства — в
> [EVIDENCE_REGISTER](EVIDENCE_REGISTER.yaml),
> а модельная иерархия — в
> [MODEL_REGISTER](MODEL_REGISTER.yaml).

> [!important] Экспериментальное свидетельство ≠ физическая интерпретация
> Экспериментальная спектральная особенность, её параметры после подгонки и её
> назначение конкретному CEF-переходу являются разными уровнями знания.
>
> Терминология проекта зафиксирована в
> [SCIENTIFIC_TERMINOLOGY](../03_Protocols/SCIENTIFIC_TERMINOLOGY.md).

<!-- AUTO:STATE_REENTRY:START -->
# 60-second re-entry

**Научная задача.** Определить воспроизводимый и физически интерпретируемый эффективный гамильтониан кристаллического поля Dy3+ в DyFeO3, согласованный прежде всего с энергиями и интенсивностями INS-переходов, а затем проверенный независимыми магнитными наблюдаемыми.

**Что непосредственно поддерживают экспериментальные данные.** В blind-анализе TAIPAN обнаружена спектральная особенность F002 около 18.2–18.3 meV. Последующий профильный анализ дал рабочую оценку положения E_peak ≈ 18.25 ± 0.12 meV. F002 является последовательным feature ID, а не индексом отражения. Также наблюдается широкая особенность F004 около 44.4 meV с пока не установленным микроскопическим происхождением.

**Что является физической интерпретацией.** Особенность около 18.25 meV рассматривается как основной кандидат на CEF-переход Dy3+, но это назначение остаётся рабочей гипотезой. Энергии 6.45 и 27.90 meV являются историческими target energies прежних B1/B2 energy-only поисков; их первичный литературный provenance ещё не восстановлен.

**Что показывает текущая модельная картина.** Formal-charge PCM и M0/M1 сохраняются как ограниченные структурно мотивированные модельные семейства. Energy-only 15-параметрическая CEF-задача существенно недоопределена. Stage 03D M0/M1 design сохранён, но production execution приостановлен до независимого повторного анализа экспериментального observation set.

**Основные неопределённости.**
- Не установлен уникальный полный 15-параметрический CEF-гамильтониан и соответствующие волновые функции.
- Окончательное CEF-назначение особенности около 18.25 meV не подтверждено интенсивностями и другими независимыми наблюдаемыми.
- Первичный литературный provenance энергий 6.45 и 27.90 meV не восстановлен.
- Физическая природа особенности около 44.4 meV остаётся открытой.
- Не определены окончательные systematic uncertainty энергетической шкалы и TAS resolution model.
- Не установлена достаточность CEF-only описания низкотемпературных данных.

**Текущий этап.** `M02R` (`active`): Stage 02R — independent TAIPAN re-analysis

**Следующий шаг.** `T-02R-03`: На основе accepted checkpoint W02-02R-A-001 сформировать в чате "02 - TAIPAN Data Reduction" formal specification W02-02R-A-002 — verified parser + canonical file/scan inventories. A-002 execution не запускать до отдельного Project Control approval.

**Не следует предполагать.**
- Особенность около 18.25 meV уже окончательно доказана как CEF-переход Dy3+.
- Энергии 6.45 и 27.90 meV являются blind experimental detections или подтверждёнными CEF-уровнями.
- F002 и F004 являются индексами кристаллографических отражений.
- Особенность около 44.4 meV является чистым локализованным Dy CEF-переходом.
- Один energy-only optimum определяет физическую CEF-модель.
- Параметры effective-charge PCM являются непосредственно измеренными ионными зарядами.
- Magnetic exchange уже включён в текущий CEF baseline.
- Exchange-charge model Малкина является активной моделью текущего цикла.
<!-- AUTO:STATE_REENTRY:END -->


# 1. Научная задача

Главная задача проекта — определить эффективный одноионный гамильтониан
кристаллического поля Dy$^{3+}$ в DyFeO$_3$, который:

1. воспроизводит экспериментально установленные CEF-related возбуждения;
2. описывает относительные INS-интенсивности и их зависимость от
   $\mathbf Q$ и температуры;
3. имеет явно зафиксированное операторное соглашение и систему координат;
4. даёт воспроизводимые уровни, волновые функции и матричные элементы;
5. допускает количественную оценку неопределённости и неоднозначности;
6. проверяется независимо через другие программные реализации;
7. в дальнейшем проверяется по $g$-тензору, $M(H)$,
   магнитной восприимчивости и, при наличии подходящих данных,
   теплоёмкости.

Финальным результатом проекта не должен быть просто один набор
$B_l^m$ с минимальным значением целевой функции.

Необходимо установить, какие свойства CEF действительно
идентифицируются имеющимися экспериментальными наблюдаемыми и насколько
единственна соответствующая физическая модель.


# 2. Физическая система

## 2.1. Dy$^{3+}$

Для свободного иона Dy$^{3+}$:

$$
4f^9,\qquad
{}^6H_{15/2},\qquad
J=\frac{15}{2},\qquad
g_J=\frac{4}{3}.
$$

Основной $J$-мультиплет содержит

$$
2J+1=16
$$

состояний.

В CEF-only модели, сохраняющей симметрию обращения времени,
они образуют восемь крамерсовских дублетов.

В магнитоупорядоченном DyFeO$_3$ это утверждение нельзя автоматически
переносить на полный низкотемпературный гамильтониан:
эффективное магнитное обменное поле со стороны магнитной подсистемы
может дополнительно расщеплять и смешивать состояния Dy$^{3+}$.

## 2.2. Кристаллическая структура

DyFeO$_3$ является редкоземельным ортоферритом с орторомбической
перовскитоподобной структурой.

В проекте встречаются установки `Pbnm` и `Pnma`; при использовании
координат, направлений, локальных осей или параметров CEF конкретная
установка должна быть указана явно.

Локальная симметрия позиции Dy рассматривается как $C_s$.

Для этой симметрии эффективный CEF-гамильтониан основного
$J=15/2$ мультиплета в принятом проектном соглашении содержит
15 независимых параметров.


# 3. Экспериментальная основа

Основной собственный экспериментальный источник проекта —
INS-данные монокристалла DyFeO$_3$, полученные на трёхосном
спектрометре TAIPAN.

Текущий архив относится к эксперименту `1296`.

Stage 02R `W02-02R-A-001` выполнил fresh CEF-blind reconnaissance raw
archive `EXP-TAIPAN-001`. После отдельного scientific review установлены
следующие archive/acquisition facts:

- 201 regular files, все читаемые `.dat`;
- zero exact-content duplicates;
- для данного archive эмпирически подтверждено
  `1 file = 1 logical scan`;
- обнаружена 21 deterministic structural format family;
- во всех 201 files раздельно присутствуют raw
  `detector`, `monitor`, `time`, `h`, `k`, `l`, `e`, `ei`, `vei`, `ef`;
- 103 acquisitions являются monitor-controlled,
  98 — time-controlled;
- записаны TAS angles `M1/M2`, `S1/S2`, `A1/A2` и дополнительные motors;
- `monochromator=PG`, `analyzer=PG`,
  `collimation=o-40-40-o` представлены во всём archive;
- обнаружены 2 lattice states и 4 UB matrices;
- proper acquisition timestamps покрывают период
  2023-08-29 — 2023-09-06;
- pre/post raw census подтвердил byte-identical source archive.

Canonical provenance:

```text
02_Work_Checkpoints/W02-02R-A-001.md
04_Results/Stage02R/W02-02R-A-001/
```

Эти результаты описывают структуру экспериментального archive и acquisition
metadata и не являются CEF interpretation.

A-001 намеренно не закрыл следующие semantics:

```text
mode=0
q
qh versus h
en versus e
filters / higher-order suppression
PG reflection / mosaic
sgl / sgu / stl / stu
PS_* / PA_*
```

Они должны оставаться unresolved до explicit verification в следующем
parser/inventory cycle.

Исторические quantities:

```text
7 761 measured points
основные low-temperature blocks около 3.4–3.5 K и 10 K
типичная fixed final energy около 14.87 meV
```

не повышаются автоматически до fresh Stage 02R facts только на основании
A-001 и должны проверяться последующими jobs.

Lattice, UB, scan geometry и другие instrument metadata должны
считываться из соответствующего acquisition block и не должны
задаваться единым жёстким набором для всего эксперимента.


# 4. Текущие экспериментальные свидетельства

## 4.1. Спектральная особенность около 18.25 meV

Stage 02 blind feature discovery обнаружил глобальную спектральную
особенность с ID:

```text
F002
```

около $18.2$–$18.3~\mathrm{meV}$.

`F002` является автоматически присвоенным последовательным ID:

```text
feature #002
```

и не связан с кристаллографическим отражением `(002)`.

Последующий Stage 03A joint profile analysis дал рабочую оценку положения:

$$
E_{\mathrm{peak}}
\approx
18.25\pm0.12~\mathrm{meV}.
$$

Legacy machine-readable fit output:

```text
18.247178 ± 0.119021 meV
```

следует сохранять в соответствующем analysis artifact, но не использовать
как физически оправданную точность в основном научном тексте.

Текущая uncertainty включает statistical/profile-fit contribution и
разброс между протестированными локальными background models.
Финальная systematic uncertainty абсолютной energy calibration в эту
оценку не включена.

Текущий статус:

```yaml
origin_type: experiment_derived
review_status: reviewed
provenance_status: partial
```

Независимый повторный fit требуется до повышения результата до
`validated`.

## 4.2. Физическое назначение особенности около 18.25 meV

Рабочая гипотеза проекта:

> Особенность около $18.25~\mathrm{meV}$ связана с переходом между
> CEF-состояниями Dy$^{3+}$.

Это назначение поддерживается энергетическим масштабом, предыдущими
CEF/PCM расчётами и устойчивостью самой спектральной особенности,
но пока не считается окончательно доказанным.

Для более сильного assignment необходима совместимость как минимум с:

- относительными INS-интенсивностями;
- $\mathbf Q$-зависимостью;
- температурной зависимостью;
- selection rules / transition matrix elements;
- общей CEF level scheme.

Поэтому в текущем тексте используется выражение:

**кандидат на CEF-переход около 18.25 meV**,

а не «установленный CEF level 18.25 meV».

## 4.3. Historical target energies 6.45 и 27.90 meV

Энергии

$$
6.45~\mathrm{meV}
\qquad\text{и}\qquad
27.90~\mathrm{meV}
$$

не были первоначально получены из Stage 02 blind feature discovery.

Они использовались в legacy B1/B2 energy-only assignment tracks как
заранее заданные candidate energies и в старом коде обозначались как
литературные priors.

На текущем этапе первичный библиографический источник этих двух
значений ещё не восстановлен.

Поэтому их статус:

```yaml
origin_type: literature
review_status: candidate
provenance_status: missing
```

Экспериментальные upper limits, вычисленные в окрестности этих энергий,
являются отдельными `experiment_derived` наблюдаемыми и не превращают
сами target energies в экспериментальные пики.

До завершения provenance audit эти значения не следует использовать как
обязательные уровни DyFeO$_3$.

## 4.4. Особенность около 44.4 meV

Blind TAIPAN analysis также обнаружил глобальную spectral feature:

```text
F004
```

около

$$
44.4~\mathrm{meV}.
$$

`F004` означает `feature #004`, а не отражение `(004)`.

В legacy analyses использовались несколько близких численных оценок
положения этой структуры, поэтому до независимого повторного анализа
предпочтительно сообщать только:

$$
E_{\mathrm{feature}}\approx44.4~\mathrm{meV}.
$$

Особенность является экспериментально поддержанной, но её физическое
происхождение остаётся открытым.

Предыдущая $\mathbf Q$-зависимость и CEF diagnostics не дают достаточных
оснований использовать её как обязательный чистый локализованный
Dy$^{3+}$ CEF-переход.

## 4.5. Энергетическое разрешение

Для elastic scan `104062` исторический fit дал:

$$
\mathrm{FWHM}_{\mathrm{elastic}}
\approx
0.894\pm0.025~\mathrm{meV}
$$

при $Q\approx2.26~\text{\AA}^{-1}$.

Это эмпирическая эффективная ширина конкретного измерения, а не полная
TAS resolution function.

Результат должен быть заново связан с исходным scan и fit artifact
в будущем TAIPAN audit.


# 5. Обратная задача CEF

Для Dy-site с локальной симметрией $C_s$ общий эффективный CEF-гамильтониан
в проектном базисе содержит 15 независимых параметров:

$$
\hat H_{\mathrm{CEF}}
=
\sum_{l,m}
B_l^m \hat O_l^m,
\qquad
l=2,4,6.
$$

Предыдущие глобальные поиски показали, что подгонка только к нескольким
энергиям допускает существенно различные наборы $B_l^m$, схемы уровней
и волновые функции при близких значениях целевой функции.

Следовательно:

> Energy-only оптимизация является полезным exploratory инструментом,
> но не достаточным методом определения физической CEF-модели DyFeO$_3$.

В дальнейшем энергетические и intensity observables должны
рассматриваться совместно.

При этом наличие формального численного optimum не следует
интерпретировать как доказательство идентифицируемости модели.


# 6. Текущая иерархия моделей

Канонический model register:

[MODEL_REGISTER](MODEL_REGISTER.yaml).

## 6.1. `MOD-PCM-FORMAL`

PCM с формальными ионными зарядами используется как простейший
структурно мотивированный electrostatic baseline.

Он отвечает на вопрос:

> Какой CEF предсказывает заданная локальная структура в простейшем
> ионно-электростатическом приближении?

В предыдущем расчёте первый возбуждённый уровень такого baseline
находился приблизительно около

$$
19.9~\mathrm{meV},
$$

что даёт правильный порядок энергетического масштаба относительно
особенности около $18.25~\mathrm{meV}$.

Этот результат не означает, что реальный CEF является чисто
электростатическим.

PCM не включает явным образом все short-range, covalent,
polarization и другие contributions к эффективному CEF.

## 6.2. `MOD-PCM-M0`

`M0` — uniform effective-charge-scaled full-cluster PCM.

Все внешние lattice charges масштабируются одним положительным
коэффициентом $s$.

При фиксированной структуре:

$$
\hat H_{\mathrm{CEF}}(s)
=
s\,\hat H_{\mathrm{CEF}}(1).
$$

Поэтому `M0` преимущественно меняет общий энергетический масштаб,
сохраняя eigenvectors и относительный single-ion transition fingerprint
исходной PCM.

Научное назначение `M0`:

> Проверить, достаточно ли одного общего масштаба исходного
> structural PCM.

`M0` является baseline/falsification model, а не полноценной моделью
уточнения CEF wavefunctions.

## 6.3. `MOD-PCM-M1`

`M1` — минимальное структурно мотивированное расширение `M0`,
в котором два кристаллографически неэквивалентных oxygen sites имеют
разные effective charge-scaling parameters:

$$
s_{\mathrm{O1}},
\qquad
s_{\mathrm{O2}}.
$$

Для сохранения нейтральности используется:

$$
s_{\mathrm{cat}}
=
\frac{s_{\mathrm{O1}}+2s_{\mathrm{O2}}}{3}.
$$

При

$$
s_{\mathrm{O1}}
=
s_{\mathrm{O2}}
$$

модель сводится к `M0`.

Научный вопрос `M1`:

> Достаточно ли минимального различия effective contributions двух
> неэквивалентных кислородных позиций, чтобы улучшить совместное
> описание CEF energies и INS intensity pattern относительно `M0`?

Даже успешный fit `M1` не означает, что найденные параметры являются
физическими ионными зарядами O1/O2 или однозначно определяют механизм
covalency, screening или overlap.

Текущий статус:

```yaml
status: suspended_pending_rebaseline
```

Математическая Stage 03D specification сохранена, но production fit
не запускается до формирования заново проверенного experimental
observation set.

## 6.4. `MOD-CEF-CS15`

Это общий phenomenological CEF-гамильтониан с 15 независимыми
параметрами $B_l^m$.

Его назначение:

> Определить семейства эффективных CEF-гамильтонианов, совместимых с
> экспериментальными наблюдаемыми без жёсткого предположения конкретной
> PCM parameterization.

В текущем проекте free 15D fit не рассматривается как подход
«найти один лучший набор параметров».

Он должен использоваться для:

- global landscape exploration;
- поиска семейств решений;
- анализа идентифицируемости;
- оценки uncertainty;
- сопоставления с более ограниченными structural models.

## 6.5. `MOD-CEF-EXCHANGE`

Следующий физический уровень:

$$
\hat H
=
\hat H_{\mathrm{CEF}}
+
\hat H_{\mathrm{ex}}.
$$

Он предназначен для описания воздействия магнитоупорядоченной
Fe-подсистемы на состояния Dy$^{3+}$.

Magnetic exchange может менять:

- level splittings;
- wavefunctions;
- transition energies;
- INS intensities;
- магнитные observables.

Он не включён в текущий CEF baseline, чтобы не добавлять новую
неидентифицируемость до более надёжного определения CEF contribution.

## 6.6. Более глубокие модели происхождения CEF

Superposition model и exchange-charge model рассматриваются как
потенциальные последующие уровни structural/microscopic interpretation.

Exchange-charge model в смысле Малкина относится к short-range
ligand-overlap contributions в кристаллическое поле и не имеет
тождественного смысла с magnetic R–Fe exchange field.

На текущем этапе:

```yaml
MOD-SUPERPOSITION:
  status: deferred

MOD-ECM-MALKIN:
  status: deferred
  current_scope: conceptual_reference_only
```

Эти модели используются сейчас только для понимания физических
ограничений простой PCM; их разработка и fit не входят в текущий цикл.


# 7. Соглашения, критические для физической интерпретации

CEF parameters нельзя сравнивать или переносить между программами без
явного указания:

- operator convention;
- normalization;
- local coordinate frame;
- crystallographic setting;
- units.

Канонический внешний project basis для $C_s$ содержит:

$$
\begin{aligned}
& B_2^0,\ B_2^{-2},\ B_2^2,\\
& B_4^0,\ B_4^{-2},\ B_4^2,\ B_4^{-4},\ B_4^4,\\
& B_6^0,\ B_6^{-2},\ B_6^2,\ B_6^{-4},\ B_6^4,\ B_6^{-6},\ B_6^6.
\end{aligned}
$$

Legacy direct PCF/CFE basis использовал другой набор operator labels.
Простое переименование коэффициентов между этими системами запрещено.

Подробности transformation convention должны храниться не здесь, а в
специализированном protocol / `04 - Structure & Conventions`.


# 8. Что в настоящее время считается установленным

На текущем уровне evidence можно утверждать следующее.

1. Dy$^{3+}$ в низкой локальной симметрии требует многопараметрического
   CEF-гамильтониана и строгого convention/frame bookkeeping.

2. В собственных TAIPAN данных существует воспроизводимая spectral feature
   около $18.2$–$18.3~\mathrm{meV}$ (`F002`).

3. Profile analysis этой особенности даёт рабочее положение около

   $$
   18.25\pm0.12~\mathrm{meV},
   $$

   однако полная systematic energy uncertainty ещё не установлена.

4. Особенность около $18.25~\mathrm{meV}$ является главным кандидатом
   проекта на CEF-переход Dy$^{3+}$, но assignment ещё требует проверки
   интенсивностями и другими наблюдаемыми.

5. В данных существует broad feature около $44.4~\mathrm{meV}$ (`F004`),
   происхождение которой остаётся открытым.

6. Энергии $6.45$ и $27.90~\mathrm{meV}$ не являются blind detections
   текущего TAIPAN experiment и не должны использоваться как подтверждённые
   экспериментальные CEF-levels.

7. Energy-only 15D CEF inverse problem существенно недоопределена для
   имеющегося исторического набора constraints.

8. Formal-charge / uniformly scaled PCM полезна как structural baseline,
   но не является полной microscopic CEF model.

9. INS intensities несут принципиально важную информацию о wavefunctions
   и должны участвовать в следующем основном inference cycle.

10. Magnetic exchange и microscopic exchange-charge contributions являются
    физически отличными механизмами и должны вводиться раздельно.


# 9. Что пока не установлено

На текущем этапе не установлены:

1. уникальный полный набор CEF-параметров $B_l^m$;
2. уникальная CEF level scheme и волновые функции;
3. окончательное назначение особенности около $18.25~\mathrm{meV}$;
4. первичный литературный provenance энергий $6.45$ и
   $27.90~\mathrm{meV}$;
5. физическая природа особенности около $44.4~\mathrm{meV}$;
6. полный экспериментальный absolute/relative intensity contract
   для будущего joint fit;
7. окончательная TAS resolution model и absolute energy-calibration
   systematic;
8. достаточность CEF-only описания низкотемпературных данных;
9. величина и направление magnetic Dy–Fe exchange field;
10. независимо проверенная финальная structural model Dy/O для CEF;
11. ансамбль статистически допустимых CEF-гамильтонианов;
12. независимая magnetic validation по $g$, $M(H)$,
    $\chi(T)$ и другим наблюдаемым.


# 10. Текущий научный этап

Текущий milestone:

```yaml
stage_id: 00C
title: Scientific re-baselining and provenance audit
status: active
```

Stage 00C выполняется для устранения накопившегося смешения между:

- экспериментальными observations;
- параметрами spectral fits;
- литературными candidate values;
- physical assignments;
- model outputs;
- методологическими decisions.

Предыдущая Stage 03D specification не отвергнута.

Её статус:

```yaml
design_status: preserved
scientific_status: suspended_pending_rebaseline
```

До возобновления Stage 03D необходимо заново определить experimental
observation set на основе независимого TAIPAN re-analysis.


# 11. Ближайший научный цикл

После завершения Stage 00C предполагается следующая последовательность:

```text
Stage 00C
scientific re-baselining
        ↓
Stage 02R
independent TAIPAN re-analysis
        ↓
Stage 03R
CEF landscape / identifiability re-analysis
        ↓
Stage 03D
joint constrained energy + intensity inference
        ↓
Stage 05
independent magnetic validation
        ↓
later microscopic interpretation
```

Новый TAIPAN analysis должен начинаться с raw/instrument data и
model-independent feature discovery, а не с требования найти заранее
заданные энергии $6.45$, $18.2$, $27.9$ или $44.4~\mathrm{meV}$.

Historical target energies могут использоваться только после blind
analysis как отдельные hypotheses / targeted tests.


# 12. Канонические источники состояния

Текущее знание и его provenance распределены по следующим объектам:

- [EVIDENCE_REGISTER](EVIDENCE_REGISTER.yaml) —
  экспериментальные и внешние свидетельства;
- [RESULT_REGISTER](RESULT_REGISTER.yaml) —
  результаты выполненного анализа и вычислений;
- [HYPOTHESIS_REGISTER](HYPOTHESIS_REGISTER.yaml) —
  физические интерпретации, требующие проверки;
- [MODEL_REGISTER](MODEL_REGISTER.yaml) —
  модельная иерархия, назначение и ограничения моделей;
- [DECISION_REGISTER](DECISION_REGISTER.yaml) —
  принятые методологические решения;
- [PROJECT_CONTROL](PROJECT_CONTROL.md) —
  roadmap и текущие задачи;
- [SCIENTIFIC_TERMINOLOGY](../03_Protocols/SCIENTIFIC_TERMINOLOGY.md) —
  каноническая научная терминология;
- [RESEARCH_LOGBOOK](../01_Logbook/RESEARCH_LOGBOOK.md) —
  хронология исследования;
- `02_Work_Checkpoints/` —
  воспроизводимые вычислительные checkpoints;
- `Archive/legacy/` —
  архив предыдущих состояний и historical provenance.
