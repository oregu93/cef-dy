---
id: SU-000002
title: "Kramers degeneracy and CEF doublets"
knowledge_kind: concept
review_status: working
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
scope:
  level: RARE_EARTH_CLASS
  rare_earth_ions:
    - "half-integer-J ions"
transferability:
  status: CONDITIONAL
  conditions:
    - "The ion has half-integer total angular momentum."
    - "Time-reversal symmetry is not broken."
  exclusions:
    - "Integer-J non-Kramers ions are not covered by the degeneracy statement."
  facets:
    kramers_class: KRAMERS
    magnetic_order: DISORDERED
    exchange_treatment: NEGLECTED
    temperature_regime: null
    field_regime: "zero field or another time-reversal-symmetric condition"
relations:
  depends_on: []
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples: []
  related_concepts:
    - SU-000003
sources:
  background: []
  claim_support: []
convention_refs: []
convention_binding:
  status: NOT_APPLICABLE
common_confusions:
  - "Kramers degeneracy does not apply to every rare-earth ion."
  - "A Kramers doublet is not a prerequisite for defining a transition tensor."
dissertation_roles:
  - theoretical_background
---

# Kramers degeneracy and CEF doublets

## Statement

Для системы с полуцелым $J$ и сохраняющейся симметрией обращения времени
теорема Крамерса требует как минимум двукратного вырождения энергетических
уровней. В CEF-задаче такие пары состояний называют Kramers doublets.

## Conditions and limits

Утверждение зависит одновременно от класса иона и симметрии гамильтониана.
Внешнее магнитное поле или эффективное обменное поле могут нарушить исходные
предпосылки и снять вырождение. Поэтому принадлежность соединения к семейству
RFeO3 сама по себе не устанавливает Kramers-класс конкретного R-иона и не
гарантирует сохранение дублетов в магнитоупорядоченном состоянии.

## Relation to transition physics

Kramers doublet часто задаёт двумерное начальное или конечное подпространство,
но определение $M_{\alpha\beta}^{(i\to f)}$ применимо и к подпространствам иной
кратности. Следовательно, эта заметка связана с `SU-000003`, но не является её
обязательной предпосылкой.
