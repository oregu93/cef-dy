---
title: "DyFeO3 — Project State: CEF + TAIPAN INS"
aliases:
  - DyFeO3_PROJECT_STATE
  - CEF Dy Project State
tags:
  - DyFeO3
  - CEF
  - crystal-field
  - INS
  - TAIPAN
  - PyCrystalField
  - CrysFieldExplorer
  - McPhase
  - Hutchings
  - Klementyev
status: active
version: "1.1"
updated: 2026-08-21
---

# DyFeO3 — состояние проекта по CEF-анализу и INS-фитированию

> [!abstract] Назначение документа
> Этот файл — единая точка состояния проекта: физическая постановка, экспериментальные данные, соглашения о параметрах и системах координат, результаты выполненных расчётов, принятые и отвергнутые стратегии, открытые вопросы и исследовательский logbook.
>
> При переносе работы в новый чат этот файл должен рассматриваться как основной контекст проекта. Численные результаты, помеченные как **рабочие**, не следует автоматически считать окончательной физической моделью.

---

# 1. Цель проекта

Главная задача — получить воспроизводимую и физически интерпретируемую модель кристаллического электрического поля (CEF) иона Dy\(^{3+}\) в ортоферрите DyFeO\(_3\), согласованную с данными неупругого нейтронного рассеяния и независимыми магнитными observables.

Искомый результат должен включать:

1. CEF-гамильтониан в явно зафиксированном операторном соглашении;
2. восемь крамерсовских дублетов Dy\(^{3+}\);
3. воспроизводимые волновые функции всех уровней;
4. матричные элементы нейтронных переходов;
5. интенсивности INS-переходов с учётом геометрии \(\mathbf Q\);
6. \(g\)-тензор основного и, при необходимости, возбуждённых дублетов;
7. ансамбль/многообразие допустимых наборов CEF-параметров, а не только один численный минимум;
8. кросс-проверку между PyCrystalField, CrysFieldExplorer и McPhase;
9. независимую последующую проверку по bulk magnetization \(M(H)\), когда эти данные будут добавлены.

Основной методологический принцип проекта:

> **Energy-only fit недостаточен для определения низкосимметричного CEF и волновых функций. Финальная модель должна одновременно описывать энергии, INS-интенсивности и независимые магнитные observables.**

---

# 2. Физическая система

## 2.1. Ион Dy\(^{3+}\)

Для Dy\(^{3+}\):

$$
4f^9,
\qquad
{}^6H_{15/2},
\qquad
J=\frac{15}{2}.
$$

Размерность пространства основного \(J\)-мультиплета:

$$
2J+1=16.
$$

В отсутствие поля и при сохранении обращения времени полуцелый \(J\) даёт восемь крамерсовских дублетов:

$$
E_0,E_1,\ldots,E_7.
$$

В расчётах используется сдвиг:

$$
E_0=0.
$$

## 2.2. Кристалл

Система: DyFeO\(_3\), редкоземельный ортоферрит.

Рабочее кристаллографическое описание:

$$
Pbnm/Pnma
$$

с необходимостью всегда указывать конкретную setting при сравнении координат, осей и параметров.

Локальное окружение Dy низкосимметричное; в проекте используется описание локальной симметрии типа \(C_s\).

---

# 3. Теоретическая основа: Hutchings / Stevens

Базовый CEF-гамильтониан:

$$
\hat H_{\mathrm{CEF}}
=
\sum_{l,m}
B_l^m \hat O_l^m.
$$

Используются ранги:

$$
l=2,4,6.
$$

Классическая теоретическая основа: M. T. Hutchings, *Solid State Physics* **16**, 227 (1964).

Для \(C_s\) в канонической вещественной записи, используемой в проекте как **физическая Hutchings-нотация**, имеется 15 независимых параметров:

$$
\boxed{B_2^0,\ B_2^{-2},\ B_2^{2}}
$$

$$
\boxed{B_4^0,\ B_4^{-2},\ B_4^{2},\ B_4^{-4},\ B_4^{4}}
$$

$$
\boxed{B_6^0,\ B_6^{-2},\ B_6^{2},\ B_6^{-4},\ B_6^{4},\ B_6^{-6},\ B_6^{6}}
$$

Всего:

$$
3+5+7=15.
$$

В текстовых именах проекта канонический набор следует писать как:

```text
B20, B2n2, B22,
B40, B4n2, B42, B4n4, B44,
B60, B6n2, B62, B6n4, B64, B6n6, B66
```

где `n2`, `n4`, `n6` означают отрицательные индексы \(-2\), \(-4\), \(-6\).

---

# 4. Критическое соглашение о CEF-параметрах

## 4.1. Каноническая физическая нотация проекта

Начиная с версии этого документа, **канонической внешней нотацией проекта** считается Hutchings/\(C_s\)-нотация:

| Каноническое имя | Физический параметр |
|---|---|
| `B20` | \(B_2^0\) |
| `B2n2` | \(B_2^{-2}\) |
| `B22` | \(B_2^{2}\) |
| `B40` | \(B_4^0\) |
| `B4n2` | \(B_4^{-2}\) |
| `B42` | \(B_4^{2}\) |
| `B4n4` | \(B_4^{-4}\) |
| `B44` | \(B_4^{4}\) |
| `B60` | \(B_6^0\) |
| `B6n2` | \(B_6^{-2}\) |
| `B62` | \(B_6^{2}\) |
| `B6n4` | \(B_6^{-4}\) |
| `B64` | \(B_6^{4}\) |
| `B6n6` | \(B_6^{-6}\) |
| `B66` | \(B_6^{6}\) |

Эта нотация должна использоваться в публикационных таблицах и при сравнении с Hutchings/McPhase после корректного преобразования осей и нормировки.

---

# 5. Legacy direct PCF/CFE basis — важное исправление

Предыдущие скрипты поиска использовали массив из 15 коэффициентов:

```text
B20 B21 B22
B40 B41 B42 B43 B44
B60 B61 B62 B63 B64 B65 B66
```

и операторный список:

```python
(2,0), (2,1), (2,2),
(4,0), (4,1), (4,2), (4,3), (4,4),
(6,0), (6,1), (6,2), (6,3), (6,4), (6,5), (6,6)
```

То есть в legacy-пайплайне `B21` является коэффициентом оператора

$$
\hat O_2^{q=1}
=
\texttt{StevensOp}(J,2,1)
$$

в **direct PCF/CFE local frame**.

> [!warning] Нельзя делать простое переименование
> `B21 -> B2n2`, `B41 -> B4n2`, `B43 -> B4n4`, ... .
>
> Между direct positive-\(q\) базисом старых скриптов и каноническим \(C_s\)-базисом Hutchings требуется **операторное преобразование/поворот системы координат**.

Это исправляет неоднозначность ранней версии project-state.

---

# 6. Что показывает исходный код PyCrystalField

PyCrystalField умеет работать как с положительными, так и с отрицательными \(m\).

В `PointChargeModel` при

```python
suppressminusm = False
```

используется:

$$
m=-l,\ldots,+l,
$$

а при

```python
suppressminusm = True
```

используется:

$$
m=0,\ldots,l.
$$

Для каждой компоненты гамильтониан строится через:

```python
StevensOp(J,l,m)
```

и tesseral harmonic `TessHarm(l,m,...)`.

Следовательно, отрицательные \(m\) в PCF существуют **явно**, а legacy-набор `B20...B66` возник из выбранного прямого 15-компонентного базиса, а не потому, что программа кодирует отрицательные \(m\) нечётными положительными индексами.

---

# 7. PCF ↔ CFE convention benchmark

Был выполнен специальный `CEF convention benchmark`.

## 7.1. Direct PCF parameters для PCM

$$
\begin{aligned}
B20 &= 1.285087570267\times10^{-1},\\
B21 &=-1.129034462883,\\
B22 &=-2.201173965902\times10^{-1},\\
B40 &= 2.539804667970\times10^{-4},\\
B41 &= 9.255467282875\times10^{-3},\\
B42 &=-1.046948325456\times10^{-3},\\
B43 &= 3.624988663850\times10^{-3},\\
B44 &= 2.620149629519\times10^{-3},\\
B60 &= 2.173632262699\times10^{-6},\\
B61 &=-5.165309894613\times10^{-7},\\
B62 &= 6.323321739774\times10^{-6},\\
B63 &= 4.389120488447\times10^{-6},\\
B64 &=-9.905617327743\times10^{-6},\\
B65 &= 1.238963374618\times10^{-5},\\
B66 &= 8.413698085317\times10^{-6}.
\end{aligned}
$$

## 7.2. Численная проверка PCF ↔ CFE

$$
\max|\Delta O|=4.657\times10^{-10},
$$

$$
\max|H_{\mathrm{CFE}}-H_{\mathrm{PCF}}|
=
8.882\times10^{-16}\ \mathrm{meV},
$$

$$
\|H_{\mathrm{CFE}}-H_{\mathrm{PCF}}\|_F
=
2.489\times10^{-15}\ \mathrm{meV},
$$

$$
\max|E_{\mathrm{CFE}}-E_{\mathrm{PCF}}|
=
3.908\times10^{-14}\ \mathrm{meV}.
$$

**Вывод:** direct PCF и direct CFE conventions, использованные в наших скриптах, численно согласованы на уровне машинной точности.

---

# 8. Переход в канонический \(C_s\)-базис

Convention benchmark нашёл каноническое преобразование с углом

$$
-90^\circ
$$

в соглашении benchmark-скрипта.

Важно: перед публикационным использованием необходимо из самого benchmark-кода зафиксировать **ось и порядок этого поворота**. Одного числа \(-90^\circ\) недостаточно для независимого воспроизведения.

После преобразования получен canonical \(C_s\)-набор:

$$
\begin{aligned}
B_2^0 &= 4.580431978176\times10^{-2},\\
B_2^{-2} &= -5.645172314417\times10^{-1},\\
B_2^{2} &= -3.028218338352\times10^{-1},\\
B_4^0 &= 2.918928380568\times10^{-4},\\
B_4^{-2} &= -3.220113986681\times10^{-3},\\
B_4^{2} &= -1.198597810495\times10^{-3},\\
B_4^{-4} &= -7.645410289534\times10^{-3},\\
B_4^{4} &= 2.354763030699\times10^{-3},\\
B_6^0 &= -9.812227381722\times10^{-7},\\
B_6^{-2} &= 3.089612443115\times10^{-6},\\
B_6^{2} &= -4.999821851285\times10^{-6},\\
B_6^{-4} &= -9.648315615325\times10^{-8},\\
B_6^{4} &= -1.937018233037\times10^{-5},\\
B_6^{-6} &= -1.654256696232\times10^{-6},\\
B_6^{6} &= -5.501998330640\times10^{-6}.
\end{aligned}
$$

Residual reconstruction:

$$
2.750\times10^{-11}\ \mathrm{meV}.
$$

Ключевая схема:

$$
\boxed{
\text{legacy direct 15D basis}
\xleftrightarrow[\text{rotation}]{}
\text{canonical Hutchings }C_s\text{ basis}
}
$$

а не простое переименование индексов.

---

# 9. McPhase convention

Для McPhase следует использовать явную Stevens-нотацию. Отрицательные \(m\) задаются `S`-компонентами.

| Hutchings/project | McPhase |
|---|---|
| \(B_2^0\) | `B20` |
| \(B_2^{-2}\) | `B22S` |
| \(B_2^{2}\) | `B22` |
| \(B_4^0\) | `B40` |
| \(B_4^{-2}\) | `B42S` |
| \(B_4^{2}\) | `B42` |
| \(B_4^{-4}\) | `B44S` |
| \(B_4^{4}\) | `B44` |
| \(B_6^0\) | `B60` |
| \(B_6^{-2}\) | `B62S` |
| \(B_6^{2}\) | `B62` |
| \(B_6^{-4}\) | `B64S` |
| \(B_6^{4}\) | `B64` |
| \(B_6^{-6}\) | `B66S` |
| \(B_6^{6}\) | `B66` |

McPhase также различает Stevens и Wybourne normalisation; при переносе параметров необходимо проверять, что используется именно Stevens-normalized \(B_l^m\).

**Правило:** direct PCF/CFE coefficients не копируются непосредственно в McPhase. Сначала выполняется:

$$
\mathbf B_{\rm direct}
\rightarrow
\mathbf B_{\rm canonical}
\rightarrow
\mathbf B_{\rm McPhase}.
$$

---

# 10. Системы координат

Необходимо различать минимум четыре системы:

1. кристаллографическую \((a,b,c)\);
2. локальную direct PCF/CFE frame;
3. каноническую \(C_s\) Hutchings frame;
4. лабораторную/экспериментальную TAIPAN frame.

## 10.1. PCF frame из CIF-import

Для исходного point-charge расчёта PyCrystalField определил:

```text
X axis = [0,1,0]
Y axis = [0,0,1]
Z axis = [1,0,0]
```

в ABC space.

То есть:

$$
x_{\rm PCF}\parallel b,
\qquad
y_{\rm PCF}\parallel c,
\qquad
z_{\rm PCF}\parallel a.
$$

Также PCF сообщил mirror plane:

$$
[0,0,1]_{\rm ABC}.
$$

Этот direct local frame является системой, в которой были выведены исходные PCM coefficients `B20...B66`.

## 10.2. Каноническая \(C_s\)-система

Канонический Hutchings-набор с \(m=0,\pm2,\pm4,\pm6\) получен после дополнительного поворота direct frame.

До фиксации точной rotation matrix в коде не следует публиковать canonical parameters без accompanying matrix.

## 10.3. TAIPAN frame

TAIPAN хранит \(h,k,l\), \(|\mathbf Q|\), UB matrix и ориентацию образца.

Для intensity calculation необходимо использовать:

$$
\mathbf Q_{\rm local}
=
R_{\rm local\leftarrow cryst}
\mathbf Q_{\rm cryst}.
$$

Проектор магнитного нейтронного сечения должен строиться **в той же системе**, что и \(J_x,J_y,J_z\):

$$
P_{\alpha\beta}
=
\delta_{\alpha\beta}
-
\hat Q_\alpha\hat Q_\beta.
$$

---

# 11. Структурная часть проекта

## 11.1. Исходные источники структуры

В проекте имеются:

- XRD powder data с Rigaku SmartLab;
- `.ras` raw diffraction file;
- FullProf refinement outputs;
- `.sum`;
- `.cif`.

Имеющийся refinement рассматривался как рабочий, а не автоматически окончательный.

Была поставлена задача независимо проверить Rietveld refinement, прежде всего координаты O, поскольку CEF point-charge model чувствителен к локальной геометрии Dy–O.

## 11.2. Рабочая структура, использованная PCF

Для одного из refinement/CIF вариантов:

$$
a=5.2926\ \text{\AA},
\qquad
b=5.5882\ \text{\AA},
\qquad
c=7.6037\ \text{\AA}.
$$

Позиция центрального Dy в CIF:

$$
(0.9778,\ 0.0695,\ 0.25).
$$

PCF идентифицировал восемь ближайших O-лигандов.

| № | \(\mathbf R_{\rm O-Dy}\), Å | \(r\), Å |
|---:|---|---:|
| 0 | \((0.7627893,\ 0,\ -2.02283172)\) | 2.161873 |
| 1 | \((1.3886677,\ -1.4142882,\ 0.87751308)\) | 2.167634 |
| 2 | \((1.3886677,\ 1.4142882,\ 0.87751308)\) | 2.167634 |
| 3 | \((-2.0313107,\ 0,\ -0.85845972)\) | 2.205261 |
| 4 | \((-1.4054323,\ 1.4142882,\ 1.53379548)\) | 2.515548 |
| 5 | \((-1.4054323,\ -1.4142882,\ 1.53379548)\) | 2.515548 |
| 6 | \((-0.6119079,\ 2.3875618,\ -1.11250452)\) | 2.704173 |
| 7 | \((-0.6119079,\ -2.3875618,\ -1.11250452)\) | 2.704173 |

Эта геометрия является основой исходного PCM, но не должна считаться окончательно refined structural model без отдельной проверки Rietveld quality.

---

# 12. Point-Charge Model: исходный результат

При стандартном oxygen charge около

$$
q_{\rm O}=-2
$$

PyCrystalField PCM дал дублеты:

$$
\begin{aligned}
E_0 &=0,\\
E_1 &=19.87875\ \mathrm{meV},\\
E_2 &=41.54308\ \mathrm{meV},\\
E_3 &=54.59342\ \mathrm{meV},\\
E_4 &=61.61891\ \mathrm{meV},\\
E_5 &=70.53467\ \mathrm{meV},\\
E_6 &=75.50764\ \mathrm{meV},\\
E_7 &=82.33536\ \mathrm{meV}.
\end{aligned}
$$

Это был важный baseline, но он не воспроизводит рабочую схему \(6.45/18.2/27.9\) meV.

Главный PCM transition из ground doublet — около \(19.88\) meV.

---

# 13. PCM transition strengths

Для baseline PCM были рассчитаны ground-state transition tensors.

| \(E\), meV | \(\mathrm{Tr}\,M\) |
|---:|---:|
| 19.878753 | 11.545655 |
| 41.543081 | 0.615577 |
| 54.593419 | 0.079739 |
| 61.618910 | 0.045379 |
| 70.534673 | 0.037470 |
| 75.507639 | 0.018721 |
| 82.335365 | 0.013170 |

То есть PCM предсказывает резко доминирующий первый переход.

`neutronSpectrum2D()` также дал для первых двух переходов приблизительно постоянное отношение:

$$
\frac{I_2}{I_1}\approx0.04572
$$

по рассмотренной Q-траектории.

---

# 14. PCM и эффективные заряды

Был исследован масштаб oxygen charge.

При uniform \(q_{\rm O}\) энергетическая схема почти линейно масштабируется.

Например:

$$
q_{\rm O}=-1
\Rightarrow
E_1\approx9.94\ \mathrm{meV},
$$

$$
q_{\rm O}=-2
\Rightarrow
E_1\approx19.88\ \mathrm{meV},
$$

$$
q_{\rm O}=-2.5
\Rightarrow
E_1\approx24.85\ \mathrm{meV}.
$$

Это показало, что простое изменение общего effective charge в основном изменяет масштаб CEF и не решает задачу формы низколежащей схемы.

Затем использовались две группы effective oxygen charges \(q_{\rm O1},q_{\rm O2}\). Было найдено множество комбинаций, дающих \(E_1\approx18.2\) meV, но при этом \(E_2\) менялся примерно в диапазоне:

$$
35.35\text{–}41.20\ \mathrm{meV}.
$$

Следовательно:

$$
\boxed{
\text{PCM является structural/chemical prior, но не уникальным inverse solution.}
}
$$

---

# 15. Роль структуры в дальнейшем

Структурная модель нужна для:

1. построения physically informed initial point;
2. определения local axes;
3. ограничения относительных CEF-компонент;
4. проверки разумности phenomenological CEF parameters;
5. исследования чувствительности CEF к oxygen coordinates;
6. возможного введения effective ligand charges.

Однако финальные 15 параметров **не должны принудительно оставаться равными PCM**, если INS требует отклонения.

---

# 16. Эксперимент TAIPAN

## 16.1. Общая сводка

Архив:

- 201 `.dat` scans;
- 7 761 measured points;
- experiment №1296;
- sample: DyFeO\(_3\) single crystal;
- PG monochromator / PG analyzer;
- collimation: `o-40-40-o`;
- типичная фиксированная конечная энергия:
  $$
  E_f\approx14.87\ \mathrm{meV};
  $$
- основные температурные блоки:
  $$
  T\approx3.4\text{–}3.5\ \mathrm{K},
  \qquad
  T\approx10\ \mathrm{K}.
  $$

TAIPAN dataset включает alignment scans, sample rocking/tilt, Q scans и energy scans.

## 16.2. Типичные колонки

```text
Pt.
qk
ql
q
h
k
l
ei
vei
ef
e
time
detector
det_err
monitor
...
temp
```

Для CEF/INS анализа наиболее важны:

$$
E=e,
$$

$$
I_{\rm raw}=\texttt{detector},
$$

$$
\sigma_I=\texttt{det\_err},
$$

$$
M=\texttt{monitor},
$$

а также \((h,k,l)\), \(|\mathbf Q|\), \(E_i,E_f,T\).

Первичная monitor normalization:

$$
I_{\rm norm}
=
\frac{I_{\rm detector}}{I_{\rm monitor}}.
$$

---

# 17. TAIPAN lattice / UB metadata

В раннем TAIPAN orientation block:

$$
a=5.310\ \text{\AA},
\quad
b=5.594\ \text{\AA},
\quad
c=7.629\ \text{\AA}.
$$

В более поздних scans встречается:

$$
a=5.310\ \text{\AA},
\quad
b=5.588\ \text{\AA},
\quad
c=7.617\ \text{\AA}.
$$

Следовательно, при обработке raw data нельзя жёстко подставлять один lattice tuple для всех scans; предпочтительно читать lattice/UB из metadata соответствующего блока.

Пример ранней UB matrix:

$$
UB=
\begin{pmatrix}
0 & 0.177141 & -0.017617\\
0 & -0.024026 & -0.129890\\
-0.188324 & 0 & 0
\end{pmatrix}.
$$

---

# 18. Эмпирическая функция разрешения TAIPAN

Elastic scan 104062 был аппроксимирован Gaussian profile.

Получено:

$$
\boxed{
\mathrm{FWHM}_{\rm elastic}
=
0.894\pm0.025\ \mathrm{meV}
}
$$

при

$$
Q\approx2.26\ \text{\AA}^{-1}.
$$

Это рабочая effective energy resolution для конкретной конфигурации.

> [!warning]
> Это не полная TAS resolution function \(R(\mathbf Q,E)\). Для строгого анализа нужен resolution ellipsoid / Cooper–Nathans/Popovici-like treatment или эквивалентная instrument model.

---

# 19. Экспериментальная линия около 44–45 meV

В low-temperature constant-Q scans при

$$
Q\approx3.2\text{–}5.2\ \text{\AA}^{-1}
$$

обнаружена сильная почти бездисперсионная структура.

Gaussian + linear-background fit:

$$
\boxed{
E\approx44.39\pm0.05\ \mathrm{meV}
}
$$

с типичной fitted FWHM порядка

$$
\sim4\ \mathrm{meV}.
$$

Текущий статус:

$$
\boxed{
44.4\ \mathrm{meV}\ \text{не является жёстко назначенным CEF-уровнем.}
}
$$

Назначение должно проверяться через Q dependence, Dy\(^{3+}\) form factor, temperature dependence, полную CEF scheme, возможный вклад Fe excitations и instrument/background effects.

---

# 20. Q-dependent intensity и form factor

Для transition tensor

$$
M_{\alpha\beta}^{if}
=
\sum_{\mu\in i,\nu\in f}
\langle\mu|J_\alpha|\nu\rangle
\langle\nu|J_\beta|\mu\rangle
$$

магнитный single-crystal INS factor:

$$
I_{if}(\mathbf Q)
\propto
F_{\rm Dy}^2(Q)
\sum_{\alpha\beta}
\left(
\delta_{\alpha\beta}
-
\hat Q_\alpha\hat Q_\beta
\right)
M_{\alpha\beta}^{if}.
$$

Также учитывается:

$$
\frac{k_f}{k_i}.
$$

Термин **polarization factor** здесь означает геометрический фактор магнитного нейтронного сечения, а не использование polarized-neutron experiment.

---

# 21. Температурные population factors

Для начального CEF-состояния:

$$
p_i(T)
=
\frac{e^{-E_i/k_BT}}
{\sum_j e^{-E_j/k_BT}}.
$$

При низких \(T\) большинство наблюдаемых CEF-переходов должны идти из ground doublet.

При сравнении 3.5 K и 10 K следует рассчитывать population factors явно, особенно если появятся transitions между excited levels.

---

# 22. Методология Клементьева

Основной методологический источник проекта:

Е. С. Клементьев, работа по определению параметров кристаллического электрического поля соединений редкоземельных элементов с низкой симметрией локального окружения, РНЦ «Курчатовский институт», ИАЭ-5822/9 (1994).

Ключевые идеи, используемые в проекте:

1. inverse CEF problem в низкой симметрии имеет множество решений;
2. вычислительно выгодно сначала искать допустимые области в пространстве CEF-параметров;
3. следует уменьшать размерность/объём поиска с использованием симметрии и физических ограничений;
4. нельзя полагаться на единственный минимум;
5. после предварительного поиска необходимо проверять полученные наборы на адекватность эксперименту;
6. на финальном этапе нужно вычислять спектральную функцию \(S(E,T)\) и сравнивать её с экспериментом;
7. эксперимент может видеть не все CEF-уровни;
8. отсутствие линии не является автоматически доказательством отсутствия соответствующего уровня;
9. assignments наблюдаемых линий по номеру дублета являются частью inverse problem;
10. интенсивности и дополнительные observables необходимы для снятия неоднозначности волновых функций.

Это особенно важно для Dy\(^{3+}\), поскольку 15 CEF parameters нельзя надёжно определить по 3–5 наблюдаемым энергиям.

---

# 23. Стратегия assignment наблюдаемых уровней

На раннем этапе было принципиально решено не считать автоматически, что наблюдаемая линия около 18.2 meV — первый возбуждённый дублет.

Были введены отдельные assignment tracks.

| Track | Наложенные рабочие энергетические условия |
|---|---|
| A | \(E_1\approx18.20\) meV |
| B0 | \(E_2\approx18.20\) meV |
| B1 | \(E_1\approx6.45\), \(E_2\approx18.20\) meV |
| B2 | \(E_1\approx6.45\), \(E_2\approx18.22\), \(E_3\approx27.90\) meV |

Эти tracks являются **вычислительными гипотезами**, а не равнозначно подтверждёнными экспериментальными фактами.

---

# 24. Статус трёх рабочих landmarks

В текущем pipeline используются:

$$
6.45,\quad18.20,\quad27.90\ \mathrm{meV}.
$$

Их статус различается.

## 24.1. 18.2 meV

Главный CEF reference проекта; имеет наиболее сильное экспериментальное/литературное основание.

## 24.2. 6.45 meV

Используется как рабочий low-energy landmark в B1/B2, но не должен считаться окончательно подтверждённым номером CEF-дублета без intensity/selection-rule проверки.

## 24.3. 27.9 meV

Используется как рабочий high-energy landmark; близок к обсуждаемой литературной/PCM области около 28 meV.

**Правило:** финальный joint refinement должен позволять переоценить assignment этих линий, если интенсивности и полный спектр противоречат текущей B2-схеме.

---

# 25. Global search: CrysFieldExplorer / CMA-ES

Первый полноценный optimized direct-Hamiltonian search:

- 24 restarts;
- 20 000 requested fevals/restart;
- popsize 24;
- около \(4.8\times10^5\) evaluations;
- около \(1.8\times10^3\) evaluations/s.

Energy-only objective с constraint около 18.2 meV дал множество очень разных CEF schemes с почти одинаковым loss.

Лучший формальный loss:

$$
\sim1.14\times10^{-4},
$$

но найденные higher levels могли различаться на сотни meV.

Это стало прямым доказательством того, что:

$$
\boxed{
\text{одна энергия + }g_{\max}\text{ не определяют 15D CEF.}
}
$$

---

# 26. Physical candidate screening

Были исследованы tracks A/B0/B1/B2.

Основной результат:

| Track | best score | типичная схема |
|---|---:|---|
| A | 0.468 | только 18.2 |
| B0 | 0.622 | один hidden lower level + 18.2 |
| B1 | 0.751 | 6.45 + 18.2 |
| B2 | 0.907 | 6.45 + 18.2 + 27.9 |

В рамках **принятых на этом этапе landmarks** B2 оказался наиболее согласованным track.

Это не является доказательством истинности B2 независимо от assumptions; это означает, что B2 — лучший current working manifold для следующего intensity-constrained stage.

---

# 27. Parameter sensitivity

На наборе 12 уникальных screened candidates наиболее сильные correlations с combined score:

| Parameter | Pearson \(r\) |
|---|---:|
| `B66` | \(-0.825\) |
| `B65` | \(-0.489\) |
| `B41` | \(-0.453\) |
| `B64` | \(-0.393\) |
| `B43` | \(-0.326\) |
| `B40` | \(-0.320\) |
| `B63` | \(+0.317\) |

Эти correlations диагностические, а не global derivatives.

После добавления INS intensities sensitivity analysis следует повторить.

---

# 28. B2 manifold до constrained refinement

Три лучших B2 solutions:

| restart | loss | \(E_1\) | \(E_2\) | \(E_3\) | \(g_{\max}\) |
|---:|---:|---:|---:|---:|---:|
| 2 | 0.000237 | 6.450643 | 18.219720 | 27.899601 | 19.699419 |
| 1 | 0.000584 | 6.449070 | 18.220440 | 27.901723 | 19.697363 |
| 0 | 0.000709 | 6.450425 | 18.220097 | 27.901703 | 19.698060 |

Эти решения использовались для оценки центра/ширины B2 manifold.

---

# 29. Constrained B2 refinement

Настройки:

```text
restarts = 16
maxfevals/restart = 12000
popsize = 24
sigma0 = 0.15
manifold weight = 1.0
```

Лучшие решения:

| restart | loss | \(E_1\) | \(E_2\) | \(E_3\) | \(g_{\max}\) | manifold loss |
|---:|---:|---:|---:|---:|---:|---:|
| 6 | 0.414904 | 6.449571 | 18.199919 | 27.894871 | 19.385812 | 0.370924 |
| 4 | 0.421337 | 6.446448 | 18.201315 | 27.898560 | 19.411211 | 0.384104 |
| 2 | 0.432947 | 6.445288 | 18.202396 | 27.903200 | 19.334701 | 0.373287 |

Вывод:

$$
\boxed{
\text{внутри B2 существует устойчивое локальное семейство решений.}
}
$$

Однако energies всё ещё недостаточны для выбора wavefunctions.

---

# 30. Последний energy-dominated best_parameters

В более позднем запуске получен:

$$
loss
=
1.3119868688695735\times10^{-5}.
$$

Principal values, рассчитанные тем конкретным скриптом:

$$
g_{\max}=15.40205098,
$$

$$
g_{\rm mid}=0.30027025,
$$

$$
g_{\min}=0.
$$

Legacy direct parameters:

$$
\begin{aligned}
B20 &= 0.14575084423074527,\\
B21 &= -0.14186321502763344,\\
B22 &= 0.057560074834538164,\\
B40 &= 0.0015283002288844281,\\
B41 &= -0.0026833840237145455,\\
B42 &= -0.0021293064614697917,\\
B43 &= -0.0025503006247384954,\\
B44 &= -0.00023854567658739386,\\
B60 &= -4.2506173139354946\times10^{-6},\\
B61 &= 7.782839640946001\times10^{-5},\\
B62 &= 6.16057562517392\times10^{-5},\\
B63 &= -3.057234124028271\times10^{-5},\\
B64 &= -1.258765448456045\times10^{-4},\\
B65 &= -1.3302134578972472\times10^{-4},\\
B66 &= -4.635969681616601\times10^{-5}.
\end{aligned}
$$

Levels:

$$
\begin{aligned}
E_0&=0,\\
E_1&=6.44976616,\\
E_2&=18.19954748,\\
E_3&=27.90003293,\\
E_4&=38.48288499,\\
E_5&=54.79524586,\\
E_6&=72.36636207,\\
E_7&=81.75387150
\end{aligned}
$$

в meV.

Первые три landmarks воспроизводятся практически точно.

---

# 31. Почему последний best_parameters НЕ является финальной моделью

В том же intensity-related pipeline файл `intensity_ratios` оказался пустым.

Следовательно, очень малый loss мог быть практически полностью определён energy part.

До использования этого набора как физического результата необходимо явно проверить:

1. число intensity observables;
2. ненулевой вклад \(\chi_I^2\);
3. реальные experimental peak areas;
4. model transition intensities;
5. scale/background nuisance parameters;
6. residuals по каждому scan;
7. устойчивость относительно разных B2 starts.

Текущий статус этого набора:

$$
\boxed{
\text{очень хороший energy candidate, но не validated joint-fit solution.}
}
$$

---

# 32. Нейтронные интенсивности: целевая модель

Для перехода \(i\rightarrow f\):

$$
I_{if}(\mathbf Q,T)
\propto
p_i(T)
\frac{k_f}{k_i}
F_{\rm Dy}^2(Q)
\sum_{\alpha,\beta}
\left(
\delta_{\alpha\beta}
-
\hat Q_\alpha\hat Q_\beta
\right)
M_{\alpha\beta}^{if}.
$$

Экспериментальная spectral model:

$$
I_{{\rm exp},s}(E)
=
A_b C_s
\sum_n I_{n,s}^{\rm CEF}
R(E-E_n)
+
B_s(E).
$$

Здесь \(A_b\) — общий fitted scale для физически совместимого acquisition block \(b\), \(C_s\) — известная scan-dependent normalization/correction (monitor, counting time, transmission, \(k_f/k_i\) и т. п.), \(B_s(E)\) — background, \(R\) — instrument/phenomenological lineshape.

> [!danger] Условие идентифицируемости интенсивностей
> Если в каждом scan наблюдается только одна линия и одновременно вводится независимый свободный scale \(A_s\), этот scale полностью поглощает predicted intensity. Тогда \(\chi_I^2\) практически не содержит информации о wavefunctions и \(\mathbf B\). Поэтому scale должен быть общим хотя бы внутри корректно нормированного блока либо иметь внешний calibration/prior; свободный scale на каждый отдельный peak недопустим как основной joint-fit design.

---

# 33. Что следует фитировать: peak areas или raw profiles?

Первый устойчивый intensity stage рекомендуется делать по **интегральным площадям CEF peaks**.

Для каждого scan:

$$
I_{\rm peak}
=
\int_{E_1}^{E_2}
\left[
I(E)-I_{\rm bg}(E)
\right]dE.
$$

Причины:

- ниже чувствительность к небольшим ошибкам resolution model;
- легче сравнивать с PCF transition matrix elements;
- удобнее использовать methodology Клементьева;
- можно отделить spectral extraction от CEF optimization.

После получения устойчивой модели перейти к full-profile fit \(S(E,T)\).

---

# 34. Joint objective

Базовая функция:

$$
\chi_{\rm total}^2
=
w_E\chi_E^2
+
w_I\chi_I^2
+
w_M\chi_M^2
+
w_P\chi_{\rm prior}^2.
$$

## 34.1. Энергии

$$
\chi_E^2
=
\sum_k
\left(
\frac{E_k^{\rm calc}-E_k^{\rm exp}}{\sigma_{E,k}}
\right)^2.
$$

## 34.2. Интенсивности

При корректной relative normalization:

$$
\chi_I^2
=
\sum_{s,k}
\left(
\frac{I_{s,k}^{\rm exp}-A_b C_s I_{s,k}^{\rm calc}}{\sigma_{I,s,k}}
\right)^2.
$$

Либо fitting intensity ratios:

$$
R_k=\frac{I_k}{I_{\rm ref}}.
$$

Ненаблюдённые, но экспериментально доступные transitions следует включать как upper limits/censored observations, а не просто удалять: именно отсутствие сильной predicted line часто лучше всего разделяет energy-degenerate CEF solutions. Для overlapping peaks необходимо переносить в fit covariance площадей с background/neighbor peaks, если она существенна.

## 34.3. Magnetic validation

Bulk magnetization не должна быть жёстко встроена до получения experimental \(M(H)\), но архитектура должна позволять добавить \(\chi_M^2\).

---

# 35. Роль программ

## PyCrystalField

Основной single-ion physical backend:

- Hamiltonian;
- diagonalization;
- wavefunctions;
- Stevens operators;
- neutron transition matrix elements;
- neutron spectrum;
- form factor;
- \(g\)-tensor;
- arbitrary user \(\chi^2\) fitting.

## CrysFieldExplorer

Основная роль:

- global exploration;
- CMA-ES / PSO-like search;
- набор локальных minima;
- визуализация parameter landscape;
- анализ degeneracy/identifiability;
- screening ensembles.

CFE не следует использовать как «чёрный ящик», который получает raw TAIPAN `.dat`; experimental observables лучше извлекать отдельно.

## McPhase

Основная роль:

- независимая cross-check CEF scheme;
- canonical Stevens \(B_l^m\);
- magnetic properties;
- magnetization/susceptibility;
- при дальнейшем развитии — exchange/magnetic excitations.

---

# 36. Рекомендуемая программная архитектура conventions

Создать единый модуль:

```text
cef_conventions.py
```

который содержит:

1. `DIRECT_PCF_CFE_LABELS`;
2. `CANONICAL_CS_LABELS`;
3. direct-to-canonical rotation/conversion;
4. canonical-to-direct inverse;
5. canonical-to-McPhase names;
6. local-axis matrices;
7. tests:
   - Hamiltonian equality;
   - eigenvalue equality;
   - transition tensor consistency.

Ни один новый fit script не должен вручную переопределять mapping индексов.

---

# 37. Минимальный обязательный convention test

Для любого набора \(\mathbf B\) проверять:

$$
\|H_{\rm PCF}-H_{\rm CFE}\| < 10^{-10}\ \mathrm{meV}
$$

и после canonical conversion:

$$
\|H_{\rm direct}-U^\dagger H_{\rm canonical}U\|
<\varepsilon.
$$

Затем проверять \(E_n\), \(g_i\), \(I_{if}\).

Только совпадение energies недостаточно: необходимо проверить transition tensors.

---

# 38. Long-term validation

После получения joint energy + intensity model:

1. bulk \(M(H)\);
2. susceptibility;
3. при наличии — heat capacity;
4. independent McPhase calculation;
5. sensitivity to structural coordinates;
6. possible exchange field effects at low temperature;
7. temperature evolution of CEF/exchange where relevant.

---

# 39. Статус E–Q карты

Исходная цель анализа TAIPAN включала построение карты:

$$
S(Q,E).
$$

На карте ожидаются дисперсионные magnetic modes, в том числе Fe-related magnons, и почти бездисперсионные CEF lines Dy\(^{3+}\).

TAIPAN dataset наиболее надёжен как CEF/low-energy dataset. Полный magnon dispersion может требовать complementary data/configuration.

E–Q map остаётся важным диагностическим продуктом, но текущий приоритет — корректное извлечение CEF observables и joint fit.

---

# 40. Что установлено надёжно

1. Dy\(^{3+}\), \(J=15/2\); для time-reversal-invariant single-ion CEF имеются восемь Kramers doublets.
2. Для low-symmetry CEF требуется 15 independent parameters.
3. Direct PCF/CFE conventions наших benchmarked scripts взаимно согласованы.
4. Legacy labels `B21`, `B41`, ... нельзя просто переименовывать в negative-\(m\) Hutchings parameters.
5. Канонический \(C_s\) набор должен строиться через rotation/convention transform.
6. McPhase negative-\(m\) components задаются `S`-notation.
7. PCM baseline даёт first transition около 19.88 meV и сильно anisotropic/Ising-like ground state.
8. Uniform effective charge в PCM в основном масштабирует energies.
9. Energy-only inverse problem сильно недоопределён.
10. B2 — текущий preferred working manifold при landmarks 6.45/18.2/27.9 meV.
11. Constrained B2 refinement дал несколько близких решений.
12. Последний ultra-low-loss набор пока не прошёл полноценную intensity validation.
13. TAIPAN содержит 201 scans / 7 761 points.
14. Elastic FWHM estimate: \(0.894\pm0.025\) meV.
15. Почти бездисперсионная структура около \(44.39\pm0.05\) meV существует, но её assignment открыт.
16. Оба TAIPAN temperature blocks находятся глубоко внутри Fe-ordered state; блок 3.4–3.5 K дополнительно лежит вблизи/ниже Dy ordering regime, поэтому Kramers degeneracy там не должна считаться автоматически защищённой.
17. Независимый свободный intensity scale на каждый single-peak scan сделал бы wavefunction fit неидентифицируемым; необходимы shared block scales либо внешняя нормировка.

---

# 41. Что НЕ установлено окончательно

1. Истинный assignment всех наблюдаемых lines к номерам doublets.
2. Является ли 6.45 meV обязательным первым CEF doublet.
3. Является ли 27.9 meV обязательным третьим doublet.
4. Природа 44.4 meV feature.
5. Полный experimental table интегральных CEF intensities.
6. Joint-fit optimum.
7. Уникальность wavefunctions.
8. Финальная canonical rotation matrix.
9. Окончательная independently refined oxygen structure.
10. Magnetic/exchange corrections.
11. Bulk magnetization validation.
12. Магнитная фаза именно исследованного TAIPAN crystal при 3.4–3.5 K и 10 K, а также величина/направление локального Dy–Fe exchange field.
13. Достаточность pure Dy\(^{3+}\) form-factor model для Q-зависимости 44.4 meV feature.

---

# 42. Следующий непосредственный computational stage

## Цель

Перейти от:

```text
energy-only / energy-dominated fit
```

к:

```text
experimental TAIPAN peak areas
+ energies
+ Q dependence
+ PCF transition tensors
+ B2 multi-start
+ CFE landscape
```

## Pipeline

```text
TAIPAN raw .dat
    ↓
robust scan inventory
    ↓
energy-scan selection
    ↓
peak extraction + background fit
    ↓
DyFeO3_TAIPAN_CEF_peaks.csv
    ↓
PCF calculated transition tensors
    ↓
joint objective
    ↓
CMA-ES multi-start / MPI
    ↓
accepted ensemble
    ↓
CFE-style visualisation
    ↓
McPhase cross-check
```

---

# 43. Обязательные outputs следующего stage

## Experimental preprocessing

```text
DyFeO3_TAIPAN_scan_inventory.csv
DyFeO3_TAIPAN_CEF_peaks.csv
DyFeO3_TAIPAN_peak_fit_diagnostics.csv
```

## Joint fit

```text
DyFeO3_joint_all_solutions.csv
DyFeO3_joint_top_solutions.csv
DyFeO3_joint_best_parameters_direct.csv
DyFeO3_joint_best_parameters_canonical.csv
DyFeO3_joint_transitions.csv
DyFeO3_joint_intensity_comparison.csv
```

## Convention cross-check

```text
DyFeO3_convention_direct_to_canonical.json
DyFeO3_McPhase_Blms.txt
```

## Visualisation

```text
DyFeO3_energy_vs_intensity_loss.png
DyFeO3_parameter_clusters.png
DyFeO3_parameter_correlations.png
DyFeO3_PCA_manifold.png
DyFeO3_transition_intensity_comparison.png
DyFeO3_E_Q_map.png
```

---

# 44. Критерии приемлемой финальной модели

Финальная модель должна находиться в пересечении:

$$
\boxed{
\mathcal S_{\rm final}
=
\mathcal S_E
\cap
\mathcal S_I
\cap
\mathcal S_{\rm magnetic}
\cap
\mathcal S_{\rm convention}
\cap
\mathcal S_{\rm stable}
}
$$

где \(\mathcal S_E\) — energies, \(\mathcal S_I\) — INS intensities, \(\mathcal S_{\rm magnetic}\) — \(g\), \(M(H)\), etc., \(\mathcal S_{\rm convention}\) — axis/operator consistency, \(\mathcal S_{\rm stable}\) — multiple-start stable manifold.

---

# 45. Project logbook

## 2026-08-13 — первичная инвентаризация TAIPAN

**Сделано**

- разобран архив TAIPAN;
- идентифицировано 201 scans;
- построены scan overview/master-points tables;
- выделены температуры \(\sim3.4\)–3.5 K и \(\sim10\) K;
- определено \(E_f\approx14.87\) meV.

**Стратегическое изменение**

Исходная задача «сразу построить E–Q map и отделить magnons/CEF» была разделена на экспериментальную reduction/классификацию scans, CEF-specific spectroscopy и последующий E–Q analysis.

---

## 2026-08-13 — preliminary INS analysis

**Сделано**

- найден strong near-nondispersive feature около 44–45 meV;
- fitted mean:
  $$
  44.39\pm0.05\ \mathrm{meV};
  $$
- оценена elastic FWHM:
  $$
  0.894\pm0.025\ \mathrm{meV}.
  $$

**Стратегическое изменение**

44.4 meV **не назначать автоматически CEF**. Требовать Q/T/full-scheme validation.

---

## 2026-08 — структура и PCM

**Сделано**

- разобраны CIF/SUM/RAS результаты;
- принято решение не доверять безоговорочно исходному FullProf refinement;
- начата independent structural validation;
- PCF идентифицировал 8 Dy–O neighbours;
- построен PCM.

**Результат**

Baseline PCM:

$$
19.88,\ 41.54,\ 54.59,\ldots\ \mathrm{meV}.
$$

**Стратегическое изменение**

PCM перестал рассматриваться как final model; используется как structural prior / initial point.

---

## 2026-08 — effective-charge PCM scans

**Сделано**

- scan uniform \(q_{\rm O}\);
- scan двух effective ligand charges.

**Результат**

Uniform charge в основном масштабирует energy scale; two-charge model допускает множество решений.

**Стратегическое изменение**

Отказ от идеи определить CEF только effective-charge PCM.

---

## 2026-08 — переход к transition tensors

**Сделано**

- извлечены \(M_{xx},M_{yy},M_{zz},M_{xz}\);
- рассчитаны ground-to-doublet intensities;
- проверен `transitionIntensity`;
- построена Q-dependent magnetic intensity.

**Стратегическое изменение**

Фокус с energies смещён на wavefunctions и neutron intensities.

---

## 2026-08 — convention benchmark PCF/CFE

**Сделано**

- проверены операторы PCF и CFE;
- Hamiltonians совпали до machine precision;
- построен canonical \(C_s\) representation;
- найден benchmark rotation \(-90^\circ\) в соглашении benchmark-script.

**Ключевое методологическое изменение**

Разделены direct PCF/CFE basis и canonical Hutchings \(C_s\) basis. Legacy `B21` больше не интерпретируется как простое имя \(B_2^{-2}\).

---

## 2026-08 — broad global CFE search

**Сделано**

- оптимизирован direct-Hamiltonian CMA-ES;
- скорость повышена примерно до \(1.8\times10^3\) evaluations/s;
- выполнены десятки restarts / сотни тысяч evaluations.

**Результат**

Множество radically different CEF schemes имели почти одинаковый energy-only loss.

**Стратегическое изменение**

Energy-only global minimum признан недостаточным физическим критерием.

---

## 2026-08 — assignment tracks A/B0/B1/B2

**Сделано**

Проверены alternative assignments 18.2 meV и low/high landmarks.

**Стратегическое изменение**

Не предполагать заранее номер наблюдаемого CEF уровня; assignment включён в inverse problem.

---

## 2026-08 — physical screening

**Сделано**

- PCF energies;
- \(g\)-tensors;
- transition strengths;
- Q-dependent intensities;
- form-factor diagnostics.

**Результат**

В рамках текущих landmarks B2 стал preferred working manifold.

---

## 2026-08 — parameter sensitivity

**Сделано**

- correlations;
- distributions;
- top-candidate parameter tables.

**Результат**

На screening sample сильнее всего коррелировал `B66`, далее `B65`, `B41`, `B64`, ...

**Ограничение**

Небольшой sample; correlations не считать global sensitivities.

---

## 2026-08 — constrained B2 refinement

**Сделано**

- 16 restarts;
- 12 000 fevals/restart;
- manifold regularization.

**Результат**

Получено локальное семейство около

$$
6.45,\ 18.20,\ 27.90\ \mathrm{meV}.
$$

**Стратегическое изменение**

Следующий fit должен разделять B2 solutions интенсивностями, а не ещё точнее подгонять energies.

---

## 2026-08 — PCF candidate spectra

**Сделано**

- spectrum calculations at 3.45 K and 10 K;
- resolution-only and phenomenological widths;
- candidate comparisons.

**Результат**

Энергии легко согласуются, но intensity fingerprints различаются и являются следующим ключевым observable.

---

## 2026-08 — preliminary intensity pipeline

**Сделано**

- parser raw TAIPAN;
- monitor normalization;
- candidate spectra;
- scale/background fitting.

**Техническая проблема**

`intensity_ratios` оказался пустым из-за слишком жёсткой логики построения ratios и несовпадения scan coverage.

**Стратегическое изменение**

Не строить joint fit на требовании, чтобы все CEF peaks находились в одном scan. Сначала формировать универсальную таблицу peak observations.

---

## 2026-08 — MPI / technical optimisation

**Сделано пользователем**

- исправлялись parser/runtime issues;
- добавлена debug instrumentation;
- добавлен MPI для ускорения global search.

**Правило**

Техническая оптимизация допускается только при сохранении явной decomposition objective и возможности отдельно вывести

$$
\chi_E^2,\quad
\chi_I^2,\quad
\chi_{\rm prior}^2.
$$

---

## 2026-08-21 — повторная ревизия CEF conventions

**Уточнено**

Теоретический \(C_s\)-набор Hutchings

$$
B_2^0,B_2^{-2},B_2^2,\ldots
$$

не совпадает по именам с legacy direct list

```text
B20 B21 B22 ...
```

**Ключевая фиксация**

- `B21` в legacy scripts = coefficient of PCF/CFE direct `StevensOp(J,2,1)`;
- negative-\(m\) в PCF существуют отдельно;
- связь direct ↔ canonical задаётся rotation/conversion;
- McPhase использует `S` suffix для negative components.

Это соглашение считается обязательным для всех дальнейших scripts.

---

## 2026-08-21 — ревизия exchange/intensity identifiability

**Добавлено**

- граница применимости zero-exchange Kramers-doublet model при 3.4–3.5 K;
- обязательная decomposition \(\hat H=\hat H_{\rm CF}+\hat H_{\rm exch}^{\rm Dy-Fe}+\hat H_{\rm exch}^{\rm Dy-Dy}+\hat H_{\rm Zeeman}\);
- shared-block intensity scale вместо unconstrained scale на каждый single-peak scan;
- upper limits для ненаблюдённых transitions;
- quantitative Q diagnostic 44.4 meV feature;
- перенос по \(R\)FeO\(_3\) через \(A_l^m\), а не direct transfer \(B_l^m\).

**Стратегическое изменение**

Temperature-dependent \(B_l^m\) не интерпретировать как lattice CEF evolution до отделения exchange/domain/population effects. Линия 44.4 meV остаётся unassigned/possibly mixed.

---

# 46. Технические lessons learned

1. Не использовать `scan_overview` как обязательный внешний dependency, если новый environment может его не содержать.
2. Raw TAIPAN parser должен читать metadata/header непосредственно из `.dat`.
3. Не использовать hard-coded column indices.
4. Не сравнивать float energy keys через exact equality.
5. Не требовать все peaks внутри одного scan.
6. Nuisance scale/background не смешивать с 15 CEF parameters без необходимости.
7. Всегда сохранять `loss decomposition`.
8. Всегда сохранять полный solution ensemble.
9. Любой новый convention conversion подтверждать Hamiltonian benchmark.
10. Имена `Bnm` без axis/convention metadata недостаточны для публикации.

---

# 47. Минимальный контекст для нового чата

Загрузить/найти:

1. `DyFeO3_PROJECT_STATE.md`;
2. latest working joint-fit script;
3. `cfe_DyFeO3_constrained_B2_full_top.csv`;
4. latest `best_parameters.csv`;
5. TAIPAN `Datafiles` или relevant raw scans;
6. convention benchmark JSON/script;
7. при необходимости CIF/structure files.

Первый запрос нового чата:

> Продолжить DyFeO3 project от этапа joint energy + TAIPAN intensity refinement. Не возвращаться к чистому energy-only fitting как финальному критерию. Сначала проверить conventions/direct-to-canonical mapping и experimental peak table, затем выполнять multi-start joint fit и CFE-style manifold analysis.

---

# 48. References / provenance

## Теория

- M. T. Hutchings, *Point-Charge Calculations of Energy Levels of Magnetic Ions in Crystalline Electric Fields*, Solid State Physics **16**, 227 (1964).
- Е. С. Клементьев, *Определение параметров кристаллического электрического поля соединений на основе редкоземельных элементов с низкой симметрией локального окружения*, ИАЭ-5822/9, РНЦ «Курчатовский институт» (1994).
- C. Ritter *et al.*, *The magnetic structure of DyFeO\(_3\) revisited: Fe spin reorientation and Dy incommensurate magnetic order*, J. Phys.: Condens. Matter **34** (2022), [doi:10.1088/1361-648X/ac6787](https://doi.org/10.1088/1361-648X/ac6787).
- B. Biswas *et al.*, *Role of Dy on the magnetic properties of orthorhombic DyFeO\(_3\)*, Phys. Rev. Materials **6**, 074401 (2022), [doi:10.1103/PhysRevMaterials.6.074401](https://doi.org/10.1103/PhysRevMaterials.6.074401).

## Software

- PyCrystalField; project calculations use PCF 2.4.1.
- CrysFieldExplorer 1.0.0, global CEF parameter-space optimisation.
- McPhase, independent Stevens/Wybourne and magnetic-property cross-check.

## Project experimental sources

- `DyFeO3_TAIPAN_analysis_report.md`
- `DyFeO3_TAIPAN_scan_overview.csv`
- `DyFeO3_TAIPAN_master_points.csv`
- raw TAIPAN `.dat` archive
- Rigaku SmartLab `.ras`
- FullProf `.cif` / `.sum`

---

# 49. Exchange, magnetic phases и границы single-ion CEF

Для интерпретации low-temperature spectrum рабочий Hamiltonian должен записываться как

$$
\boxed{
\hat H(T,\mathbf H)
=
\hat H_{\rm CF}
+
\hat H_{\rm exch}^{\rm Dy-Fe}(T)
+
\hat H_{\rm exch}^{\rm Dy-Dy}(T)
+
\hat H_{\rm Zeeman}(\mathbf H)
}
$$

с

$$
\hat H_{\rm CF}=\sum_{l,m}B_l^m\hat O_l^m,
\qquad
\hat H_{\rm Zeeman}=g_J\mu_B\,\mathbf J\cdot\mathbf H,
\qquad
g_J(\mathrm{Dy}^{3+})=\frac43.
$$

На первом exchange-aware уровне Dy–Fe contribution можно параметризовать effective molecular field в energy units:

$$
\hat H_{\rm exch}^{\rm Dy-Fe}
=
\mathbf J\cdot\mathbf h_{\rm ex}^{\rm Fe}(T),
$$

а Dy–Dy contribution — self-consistent mean field/tensor coupling. Знак и компоненты \(\mathbf h_{\rm ex}\), включая связь с эквивалентным magnetic field, должны быть привязаны к выбранной local/crystallographic frame и magnetic domain.

## 49.1. Почему это существенно именно для TAIPAN temperatures

- Fe sublattice в DyFeO\(_3\) упорядочена уже при \(T_N^{\rm Fe}\sim645\) K, поэтому и 10 K, и 3.4–3.5 K не являются truly time-reversal-invariant paramagnetic single-ion conditions.
- Литературный \(T_{\rm SR}\) сильно sample-dependent: опубликованы значения примерно \(37\text{–}75\) K. Поэтому оба TAIPAN temperature blocks должны лежать ниже spin reorientation, но точную magnetic representation исследованного crystal нельзя назначать только по generic literature.
- Dy ordering наблюдается около \(4\) K (в некоторых single-crystal datasets anomaly reported somewhat higher). Следовательно, 3.4–3.5 K находится в критической области Dy ordering, тогда как 10 K является естественным control block above Dy long-range order.
- В neutron diffraction study найден переход Fe \(\Gamma_4(G_xA_yF_z)\rightarrow\Gamma_1(A_xG_yC_z)\) и incommensurate Dy order below 4 K with \(\mathbf k=[0,0,0.028]\). Другие samples показывают отличающиеся \(T_{\rm SR}\), spin directions и exchange scales; sample specificity обязательна.

> [!warning] Kramers terminology below magnetic ordering
> CEF без time-reversal breaking даёт восемь Kramers doublets. При internal exchange field Kramers theorem больше не гарантирует degeneracy: doublets могут split/mix, а при incommensurate Dy order локальный effective field может быть site-dependent. Поэтому «восемь дублетов» — baseline \(\hat H_{\rm CF}\), а не автоматически точное описание spectrum at 3.4–3.5 K.

Опубликованные estimates Dy–Fe/Dy–Dy interaction energies находятся в \(\mu\)eV–\(10^2\,\mu\)eV range и существенно меньше empirical TAIPAN elastic FWHM \(0.894\) meV. Поэтому exchange splitting может быть unresolved в present spectra и почти не менять centroids высокоэнергетических CEF peaks, но всё равно влиять на ground-state polarization, populations, selection rules и relative intensities.

---

# 50. Иерархия моделей для temperature comparison

Сравнение 3.45 K и 10 K следует выполнять ступенчато:

1. **Model CEF-0:** один общий \(\mathbf B\), no exchange; проверка, описываются ли centroids и gross intensities.
2. **Model CEF+Fe:** тот же \(\mathbf B\) плюс \(\mathbf h_{\rm ex}^{\rm Fe}(T)\); проверка улучшения temperature-dependent intensities/splittings.
3. **Model CEF+Fe+Dy:** self-consistent Dy–Dy term только если 3.45 K residuals требуют ordered-Dy physics.
4. **Full magnetic model:** multi-sublattice McPhase calculation для \(M(H,T)\), susceptibility, low-energy modes и phase consistency.

Параметры \(B_l^m(T)\) нельзя объявлять temperature-dependent, пока не проверено, что apparent change не объясняется exchange field, изменением magnetic domain populations, resolution/background или thermal population factors. Физический поиск temperature evolution CEF должен сначала удерживать общий \(\mathbf B\) и вводить независимо constrained exchange/structural contributions.

---

# 51. Физическая интерпретация \(g\)-тензора Dy\(^{3+}\)

Для effective spin-\(\tfrac12\) основного doublet:

$$
\hat H_{\rm eff}
=
\frac{\mu_B}{2}\,
\boldsymbol{\sigma}\cdot\mathbf g\cdot\mathbf H.
$$

Для nearly pure \(\lvert m_J=\pm15/2\rangle\):

$$
g_{\parallel}^{\rm max}
=
2g_JJ
=
2\cdot\frac43\cdot\frac{15}{2}
=20.
$$

Следовательно, principal value \(g_{\max}\approx19\text{–}19.7\) физически разумна и указывает на strongly Ising-like doublet, а не сама по себе на ошибку. Различие между \(g_{\max}\approx19.7\) у B2 candidates и \(15.4\) у последнего energy-dominated candidate отражает различие wavefunctions и подчёркивает необходимость intensity/magnetization discrimination.

Обязательные правила:

1. вычислять principal \(g\)-values как basis-invariant singular/principal values projected magnetic-moment operator внутри doublet;
2. сохранять не только \((g_1,g_2,g_3)\), но и направления principal axes в crystallographic frame;
3. не интерпретировать printed \(g_{\min}=0\) без numerical tolerance и operator-convention test;
4. после включения exchange отдельно различать zero-field CEF \(g\)-tensor и field/exchange-dependent effective response.

---

# 52. Фактический Q-тест 44.4 meV feature

В **DyFeO3_stage6_44meV_model_comparison.csv** experimental и model curves нормированы к первому point:

| \(Q\), Å\(^{-1}\) | experiment | polarization | Dy \(F^2\) | Dy \(F^2\times P\) |
|---:|---:|---:|---:|---:|
| 3.269 | 1.000 | 1.000 | 1.000 | 1.000 |
| 5.232 | 0.545 | 0.568 | 0.281 | 0.160 |

На текущей preprocessing experimental intensity уменьшается значительно слабее, чем simple localized-Dy prediction \(F_{\rm Dy}^2(Q)P(\mathbf Q)\). Это является **предварительным evidence против чистого single-component Dy CEF assignment** линии 44.4 meV, но не окончательным исключением.

До физического вывода необходимо проверить:

1. shared intensity normalization между scans 104199–104210;
2. absorption/self-shielding Dy-containing crystal;
3. background и возможную Fe/multiple-scattering component;
4. exact \(\mathbf Q\)-directions, а не только \(|Q|\);
5. covariance fitted peak area/width/background;
6. 3.5 K versus 10 K difference;
7. совместимость со всеми predicted Dy transitions, включая ненаблюдённые upper limits.

Статус 44.4 meV должен оставаться **unassigned / possibly mixed**, а не **CEF level**.

---

# 53. Минимальный data contract для intensity refinement

**DyFeO3_TAIPAN_CEF_peaks.csv** должен содержать как минимум:

~~~text
scan_id, temperature_K, h, k, l, Q_Ainv,
peak_energy_meV, peak_energy_sigma_meV,
peak_area, peak_area_sigma,
fwhm_meV, background_model,
normalization_block, monitor, ki_kf_factor,
detection_status, upper_limit,
fit_window_meV, fit_quality_flag
~~~

Дополнительно сохранять covariance matrix или compact covariance fields для overlapping peaks/background, если correlation не negligible.

**normalization_block** должен объединять scans, для которых один shared scale \(A_b\) физически оправдан. Один свободный \(A_s\) на scan допускается только как constrained nuisance parameter с внешним prior; иначе Q-dependence и absolute transition strength теряются.

Assignment в joint fit должен храниться как отдельная latent/discrete hypothesis:

~~~text
observed_peak_id -> calculated_transition_(i,f)
~~~

а не кодироваться навсегда в имени energy target. Наблюдаемые peaks, upper limits и scan coverage должны входить в один observation table.

---

# 54. Два PCM benchmarks нельзя смешивать

В проекте существуют два разных ориентировочных результата:

1. **Наш reproduced PCM из рабочего CIF/direct PCF setup:** первый transition \(19.87875\) meV и уровни \(41.54,54.59,\ldots\) meV.
2. **Recent literature/conference PCM:** first excited Dy doublet reported near \(28.01\) meV.

Это не две версии одного и того же parameter set. Различие может происходить из structure/oxygen coordinates, ligand charges, local axes, Stevens normalization, included neighbors и exchange assumptions. До parameter-level comparison нужно воспроизвести чужой input и Hamiltonian convention; число \(28.01\) meV следует использовать как literature benchmark/sensitivity marker, а не как дополнительный жёсткий target B2.

---

# 55. Structural-to-CEF link и перенос по ряду \(R\)FeO\(_3\)

Для сравнения DyFeO\(_3\), HoFeO\(_3\), TbFeO\(_3\) и TmFeO\(_3\) нельзя напрямую переносить fitted \(B_l^m\), поскольку они содержат ion-specific Stevens factors и radial moments:

$$
\boxed{
B_l^m(R)
=
\theta_l(R)\,
\langle r^l\rangle_R\,
A_l^m(R)
}
$$

где \(A_l^m\) описывает lattice/environment contribution в зафиксированной local frame. Для cross-\(R\) comparison сначала следует сравнивать/моделировать \(A_l^m\) и structural multipoles, затем применять \(\theta_l\langle r^l\rangle\) конкретного ion.

Критические ограничения:

1. использовать одну crystallographic setting и воспроизводимое правило local axes для всего ряда;
2. различать local Dy/RO\(_8\) geometry и global FeO\(_6\) tilt/rotation descriptors: octahedral tilts влияют на rare-earth CEF косвенно и не задают однозначно все 15 components;
3. сопоставлять \(A_l^m\) с Dy/R–O distances, angular ligand multipoles, FeO\(_6\) tilts, strain и temperature-dependent oxygen coordinates;
4. не переносить Kramers level topology Dy\(^{3+}\) на Ho\(^{3+}\), Tb\(^{3+}\), Tm\(^{3+}\): это non-Kramers ions, и low \(C_s\) symmetry в общем случае допускает singlet splitting;
5. валидировать перенос не только energies, но также INS matrix elements, \(g\)/Van Vleck response и thermodynamics.

Исследовательская novelty формулируется не как «\(B_l^m\) следует углу наклона октаэдра», а как количественная карта

$$
\{\text{local structural multipoles},\ \text{FeO}_6\text{ distortions}\}
\longrightarrow
\{A_l^m\}
\longrightarrow
\{E_n,\psi_n,I_{if},g\}.
$$

---

# 56. Иерархия structural priors

Рекомендуемый порядок усложнения structural CEF model:

~~~text
formal point charges
    -> uniform effective charge
    -> ligand/site-group effective charges
    -> exchange-charge/covalency correction
    -> free Stevens fit with structural prior
~~~

Для optional exchange-charge model рабочая semi-empirical form записывается как

$$
q_{\rm ex}(r)
=
G_s e^{-r/\rho_s}
+
G_p e^{-r/\rho_p},
$$

где \(G_s,G_p,\rho_s,\rho_p\) кодируют separate \(s/p\)-type covalency contributions. Эти параметры не являются независимо известными charges: они должны оцениваться по spectra/related compounds и использоваться как constrained chemical model, а не как способ скрытно вернуть полные 15 свободных degrees of freedom.

---

# 57. One-line current status

$$
\boxed{
\text{Energy manifold найден; conventions и exchange caveat зафиксированы; следующий шаг — identifiable joint fit energies + normalized TAIPAN peak intensities.}
}
$$
