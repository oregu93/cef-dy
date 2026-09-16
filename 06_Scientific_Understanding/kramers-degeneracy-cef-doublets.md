---
id: SU-000002
title: "Kramers degeneracy and CEF doublets"
knowledge_kind: concept
review_status: reviewed
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
    - "The ion/effective multiplet has half-integer total angular momentum."
    - "The Hamiltonian under consideration preserves time-reversal symmetry."
  exclusions:
    - "Integer-J non-Kramers ions are not covered by the degeneracy statement."
  facets:
    kramers_class: KRAMERS
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: "Hamiltonian under consideration preserves time-reversal symmetry."
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
  - "Integer-J/non-Kramers ions may have symmetry-protected or accidental doublets; these are not Kramers-protected."
  - "Zero external field does not ensure time-reversal symmetry when an internal time-reversal-breaking exchange field is present."
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

Integer-$J$/non-Kramers ions всё же могут иметь symmetry-protected или
accidental doublets, но эти дублеты не защищены теоремой Крамерса. Нулевое
внешнее поле также не гарантирует time-reversal symmetry, если действует
внутреннее нарушающее её обменное поле.

## Relation to transition physics

Kramers doublet часто задаёт двумерное начальное или конечное подпространство,
но определение $M_{\alpha\beta}^{(i\to f)}$ применимо и к подпространствам иной
кратности. Следовательно, эта заметка связана с `SU-000003`, но не является её
обязательной предпосылкой.
