---
id: SU-000006
title: "Pbnm/Pnma and CEF-frame binding in the DyFeO3 workflow"
knowledge_kind: method_explanation
review_status: working
epistemic_basis:
  primary: PROJECT_DERIVED
  additional: []
scope:
  level: COMPOUND_SPECIFIC
  compounds:
    - DyFeO3
transferability:
  status: BOUND_TO_SCOPE
  conditions:
    - "The Pbnm/Pnma setting map, Dy site and local CEF frame are explicitly verified."
  exclusions:
    - "Another RFeO3 compound requires an independent setting, site-mapping and local-frame check."
  facets:
    kramers_class: NOT_APPLICABLE
    magnetic_order: NOT_APPLICABLE
    exchange_treatment: NOT_APPLICABLE
    temperature_regime: null
    field_regime: null
relations:
  depends_on: []
  specializes:
    - SU-000001
  contrasts_with: []
  derived_from:
    - STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001
    - STAGE03R-TAIPAN-HKL-SETTING-RECONCILIATION-001
  project_examples:
    - STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001
  related_concepts:
    - SU-000003
sources:
  background: []
  claim_support: []
convention_refs:
  - 03_Protocols/SCIENTIFIC_TERMINOLOGY.md
  - 04_Results/Stage03R/STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001/CHECKPOINT.yaml
convention_binding:
  status: EXPLICIT
  crystallographic_setting: "Pbnm #62"
  origin_choice: "current canonical DyFeO3 workflow binding"
  global_frame: "crystallographic axes a, b, c in Pbnm setting"
  local_frame: "CEF frame X=b, Y=c, Z=a"
  site:
    species: Dy
    wyckoff: 4c
    site_symmetry: "Cs / m"
common_confusions:
  - "Pbnm and Pnma labels cannot be interchanged without an explicit index/axis transform."
  - "The DyFeO3 local-frame binding does not define general CEF physics or another RFeO3 compound."
dissertation_roles:
  - analysis_methodology
  - results_interpretation
---

# Pbnm/Pnma and CEF-frame binding in the DyFeO3 workflow

## Active DyFeO3 binding

Текущий reviewed single-ion contract использует:

```text
space group: Pbnm #62
Dy orbit: 4c
site symmetry: Cs / m
CEF frame: X=b, Y=c, Z=a
```

Для записанных TAIPAN индексов действует identity binding

$$
(h,k,l)_{\mathrm{TAIPAN}}=(h,k,l)_{\mathrm{Pbnm}},
$$

а публикационное обозначение Pnma связано явным преобразованием

$$
(H,K,L)_{\mathrm{Pnma}}=(k,l,h)_{\mathrm{Pbnm}}.
$$

При осевом CEF binding $X=b$, $Y=c$, $Z=a$ используемое отображение в
декартовы компоненты имеет вид

$$
2\pi\left(\frac{k}{b},\frac{l}{c},\frac{h}{a}\right).
$$

## Tensor transport

Для симметрийно связанных Dy sites accepted contract использует

$$
M_s=R_sM_{\mathrm{ref}}R_s^T,
$$

и в независимом одноионном приближении суммирует $I=\sum_s I_s$. Последнее
нельзя автоматически переносить на coherent или exchange-coupled modes.

## Transfer boundary

Эта заметка специализирует общий CEF formalism (`SU-000001`) только для
текущего DyFeO3 workflow. Для другого RFeO3 необходимо заново проверить
кристаллографическую установку, Wyckoff mapping, локальные оси и применимость
независимого site sum.
