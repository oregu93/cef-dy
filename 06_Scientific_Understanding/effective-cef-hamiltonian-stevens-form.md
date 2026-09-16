---
id: SU-000001
title: "Effective CEF Hamiltonian in Stevens-operator form"
knowledge_kind: concept
review_status: reviewed
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
scope:
  level: GENERAL_PHYSICS
transferability:
  status: GENERAL
  conditions:
    - "The operator normalization, parameter units and coordinate frame are stated."
    - "The active ion/J multiplet or equivalent angular-momentum representation is stated."
  exclusions: []
  facets:
    kramers_class: ANY
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: null
relations:
  depends_on: []
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples:
    - MOD-CEF-CS15
    - MOD-PCM-FORMAL
    - MOD-PCM-M0
  related_concepts:
    - SU-000006
    - SU-000007
sources:
  background: []
  claim_support: []
convention_refs:
  - 03_Protocols/SCIENTIFIC_TERMINOLOGY.md
convention_binding:
  status: NOT_APPLICABLE
common_confusions:
  - "Hamiltonian/model object != measured observable"
  - "A numerical B_l^m list without operator normalization, units and axes is not a portable model."
dissertation_roles:
  - theoretical_background
  - analysis_methodology
---

# Effective CEF Hamiltonian in Stevens-operator form

## Statement

Эффективное кристаллическое поле в фиксированном угловом-моментном
пространстве удобно записывать как разложение по операторам Стивенса:

$$
\hat H_{\mathrm{CEF}}=\sum_{l,m} B_l^m\hat O_l^m.
$$

Здесь $\hat O_l^m$ - операторы, построенные из компонент полного углового
момента, а $B_l^m$ - коэффициенты эффективного гамильтониана в выбранных
нормировке и системе координат. Набор разрешённых членов определяется
симметрией и принятым операторным соглашением.

## Meaning and assumptions

- $B_l^m$ описывают эффективную параметризацию CEF, но сами по себе не
  являются измеренными спектральными интенсивностями или энергиями.
- Поворот осей, другая нормировка операторов или иная параметризация могут
  изменить численные коэффициенты без изменения физического гамильтониана.
- Для сравнения параметров необходимо фиксировать единицы, операторную
  нормировку, порядок коэффициентов, глобальные и локальные оси.
- Эта общая заметка сама не выбирает конкретную систему координат или
  нормировку операторов. Численные $B_l^m$ принадлежат явно указанному
  active ion/$J$ manifold и application-specific convention binding.

## Relation to the project

`MOD-CEF-CS15` является project example феноменологического CEF Hamiltonian;
`MOD-PCM-FORMAL` и `MOD-PCM-M0` дают более ограниченные структурно
мотивированные способы получить CEF. Эти примеры иллюстрируют формализм, но
не являются доказательством общего определения и не задают здесь численные
параметры DyFeO3.

## Limits

Диагонализация $\hat H_{\mathrm{CEF}}$ даёт собственные состояния и энергии
модели. Чтобы связать их с экспериментом, отдельно нужны операторы перехода,
геометрия измерения и модель приборного отклика.
