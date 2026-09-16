---
id: SU-000007
title: "Identifiability of a CEF inverse problem"
knowledge_kind: concept
review_status: working
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional:
    - PROJECT_DERIVED
scope:
  level: GENERAL_PHYSICS
transferability:
  status: GENERAL
  conditions:
    - "Identifiability is assessed for a stated model, observables, conventions and nuisance parameters."
  exclusions: []
  facets:
    kramers_class: ANY
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: null
relations:
  depends_on:
    - SU-000001
  specializes: []
  contrasts_with: []
  derived_from:
    - R-002
  project_examples:
    - 04_Results/Stage03R/STAGE03R-CS15-PREDICTION-BUNDLE-MATERIALIZATION-001/CS15-HIST-B2-MINI-001.yaml
  related_concepts:
    - SU-000003
    - SU-000005
sources:
  background: []
  claim_support: []
convention_refs: []
common_confusions:
  - "good energy fit != unique Hamiltonian"
  - "energy-only non-identifiability != energies contain no information"
  - "intensity-sensitive discrimination != automatically unique parameter identification"
  - "model discrimination != parameter identifiability"
dissertation_roles:
  - theoretical_background
  - analysis_methodology
  - results_interpretation
---

# Identifiability of a CEF inverse problem

## Statement

CEF inverse problem является identifiable только в той мере, в какой
выбранные observables однозначно ограничивают параметры или физически
эквивалентные семейства параметров в заданной модели и convention binding.
Наличие найденного numerical optimum не доказывает ни structural, ни
practical identifiability.

## Distinctions

- Хорошее совпадение энергий не гарантирует уникальный Hamiltonian,
  eigenvectors или transition tensors.
- Energy-only non-identifiability не означает, что энергии не несут
  информации: они могут исключать области параметров и фиксировать некоторые
  комбинации.
- Intensity-sensitive observable может различать модели, но не обязан делать
  все параметры уникальными.
- Model discrimination отвечает, какая из заявленных моделей совместима с
  наблюдаемыми; parameter identifiability отвечает, какие параметры внутри
  модели определены данными.

## DyFeO3 application

Reviewed result `R-002` фиксирует недоопределённость исторической
15-параметрической energy-only CEF-задачи DyFeO3. Материализованный
`CS15-HIST-B2-MINI-001` показывает несколько historical exploratory probe
states с близкими energy-only losses и различными предсказаниями. Это project
application, а не posterior, не current/preferred candidate ensemble и не
репрезентативная выборка всего допустимого parameter space.

Связь с `SU-000003` и `SU-000005` показывает, почему переходные тензоры и
experiment-specific intensity bridge могут дать дополнительную
дискриминацию, но сами по себе не гарантируют полной идентифицируемости.
