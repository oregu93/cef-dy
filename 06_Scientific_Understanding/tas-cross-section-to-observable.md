---
id: SU-000005
title: "From magnetic neutron cross section to measured triple-axis intensity"
knowledge_kind: method_explanation
review_status: working
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
scope:
  level: METHOD_CLASS
  method_classes:
    - triple_axis_spectroscopy
transferability:
  status: CONDITIONAL
  conditions:
    - "The scan trajectory, instrument state and observable normalization are specified."
  exclusions:
    - "A generic energy-resolution width is not a complete TAS response model."
  facets:
    kramers_class: ANY
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: null
relations:
  depends_on:
    - SU-000004
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples:
    - STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001
  related_concepts:
    - SU-000007
sources:
  background: []
  claim_support: []
convention_refs: []
common_confusions:
  - "Energy resolution width alone != quantitative TAS response."
  - "Experimental sensitivity in detector/monitor units != model exclusion threshold without a scale bridge."
dissertation_roles:
  - experimental_methods
  - analysis_methodology
  - results_interpretation
---

# From magnetic neutron cross section to measured triple-axis intensity

## Conceptual chain

Количественная связь одноионной модели с TAS-данными проходит через несколько
различных слоёв:

```text
single-ion magnetic transition
-> magnetic neutron cross section
-> TAS scan trajectory
-> instrument resolution / acceptance
-> normalization / efficiency / background semantics
-> measured detector/monitor observable
```

Transition tensor и polarization projection (`SU-000004`) задают только часть
первого перехода. Cross section должна быть рассчитана вдоль реальной
траектории $(\mathbf Q,\omega)$ и свёрнута с многомерной функцией отклика.
После этого ещё требуется перевод в семантику наблюдаемой величины конкретного
набора данных.

## Why one resolution width is insufficient

Одна ширина по энергии не задаёт корреляции между $\mathbf Q$ и $\omega$,
acceptance, focusing, collimation, sample mosaic и detector geometry. Поэтому
она не является полной количественной моделью TAS response.

## DyFeO3 project example

В текущем Stage03R около 38 meV experimental sensitivity установлена на уровне
observed detector/monitor quantity, но quantitative model-to-TAIPAN bridge не
установлен: остаются experiment-specific resolution/acceptance и
cross-section-to-detector/monitor scale. Это project example границы метода,
а не новое утверждение о наличии или отсутствии CEF-перехода.
