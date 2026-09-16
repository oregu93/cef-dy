---
id: SU-000004
title: "Magnetic neutron polarization projection and intrinsic transition strength"
knowledge_kind: derivation
review_status: working
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
scope:
  level: METHOD_CLASS
  method_classes:
    - magnetic_neutron_scattering
transferability:
  status: CONDITIONAL
  conditions:
    - "M_alpha_beta and Qhat are expressed in the same orthonormal frame."
  exclusions:
    - "Instrument resolution, normalization and detector response are not included."
  facets:
    kramers_class: ANY
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: null
relations:
  depends_on:
    - SU-000003
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples:
    - STAGE03R-CS15-38MEV-FORWARD-VISIBILITY-001
  related_concepts: []
sources:
  background: []
  claim_support: []
convention_refs:
  - 03_Protocols/SCIENTIFIC_UNDERSTANDING_SCHEMA_V1_0.md
convention_binding:
  status: EXPLICIT
  crystallographic_setting: null
  origin_choice: null
  global_frame: "M_alpha_beta and Qhat must be represented in one common frame."
  local_frame: null
  site:
    species: null
    wyckoff: null
    site_symmetry: null
common_confusions:
  - "S_if != S_if^perp(Qhat)"
  - "Intrinsic strength or polarization projection alone is not a measured TAS intensity."
dissertation_roles:
  - theoretical_background
  - analysis_methodology
---

# Magnetic neutron polarization projection and intrinsic transition strength

## Intrinsic scalar

Из transition tensor (`SU-000003`) можно построить rotational trace:

$$
S_{if}=\operatorname{Tr}M^{(i\to f)}
=\sum_\alpha M_{\alpha\alpha}^{(i\to f)}.
$$

Это intrinsic transition strength в принятом определении. Она не содержит
ориентационной селекции магнитного нейтронного рассеяния.

## Polarization projection

Магнитный нейтрон чувствителен к компонентам, поперечным $\mathbf Q$:

$$
S^\perp_{if}(\hat{\mathbf Q})=
\sum_{\alpha\beta}
\left(\delta_{\alpha\beta}-\hat Q_\alpha\hat Q_\beta\right)
M_{\alpha\beta}^{(i\to f)}.
$$

Здесь $\hat{\mathbf Q}$ - единичный вектор передачи импульса, выраженный в
той же системе координат, что и $M_{\alpha\beta}$. Эта свёртка зависит от
направления $\mathbf Q$.

## Observable hierarchy

$$
S_{if}\ne S^\perp_{if}(\hat{\mathbf Q})
\ne \text{neutron cross section}
\ne \text{measured TAS intensity}.
$$

Для cross section дополнительно нужны populations, form factor и
кинематические множители; измеряемая TAS-величина также требует scan geometry,
resolution/acceptance, normalization, background и detector/monitor response.
