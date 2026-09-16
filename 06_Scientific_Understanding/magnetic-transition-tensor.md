---
id: SU-000003
title: "Magnetic transition matrix elements and transition tensor"
knowledge_kind: derivation
review_status: reviewed
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
scope:
  level: GENERAL_PHYSICS
transferability:
  status: GENERAL
  conditions:
    - "Initial-state populations and the final-state projector are specified."
    - "All operator components are expressed in one stated frame."
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
    - STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001
  related_concepts:
    - SU-000001
    - SU-000002
    - SU-000006
    - SU-000007
sources:
  background: []
  claim_support: []
convention_refs: []
convention_binding:
  status: NOT_APPLICABLE
common_confusions:
  - "nonzero J != necessarily nonzero static <J>"
  - "transition matrix element != static moment"
  - "external magnetic field is not required for a magnetic transition matrix element to exist"
  - "transition tensor != measured TAS intensity"
dissertation_roles:
  - theoretical_background
  - analysis_methodology
origin_trail:
  - source_type: chat
    role: "00 - Project Control r2"
    date: 2026-09-16
    locator: "discussion distinguishing static moment from transition matrix elements"
---

# Magnetic transition matrix elements and transition tensor

## General definition

Для начальной матрицы плотности $\rho_i$ и проектора конечного
подпространства $P_f$ определим

$$
M_{\alpha\beta}^{(i\to f)}=
\operatorname{Tr}\!\left(\rho_iJ_\alpha P_fJ_\beta\right).
$$

$\operatorname{Tr}(\rho_i)=1$ внутри выбранного начального manifold.
$\rho_i$ описывает нормированное статистическое состояние при условии
нахождения системы в этом manifold; его полная thermal occupation относится
к последующему cross-section layer, если явно не принято иное соглашение.

$J_\alpha$ и $J_\beta$ - компоненты полного angular-momentum operator,
используемого в фиксированном-$J$ Hilbert-space representation. Magnetic-moment
prefactors, включая $g_J$, относятся к neutron-cross-section layer.
Пространственная система координат задаёт Cartesian indices $\alpha,\beta$ и
компоненты $J_\alpha$; $\rho_i$, $P_f$ и $J$ одновременно являются
операторами выбранного Hilbert-space representation. Проекторы сами по себе
не «используют Cartesian frame».

Тензор удовлетворяет

$$
M_{\beta\alpha}=M_{\alpha\beta}^{*}.
$$

Для физической положительной $\rho_i$ матрица $M$ Hermitian positive
semidefinite. В equal-population/projector representation выражение
инвариантно относительно unitary basis changes внутри вырожденных начального
и конечного подпространств.

## Equal-population specialization

Если $g_i$ начальных состояний равнозаселены,

$$
\rho_i=\frac{P_i}{g_i},\qquad
M_{\alpha\beta}^{(i\to f)}=
\frac{1}{g_i}\operatorname{Tr}\!\left(P_iJ_\alpha P_fJ_\beta\right).
$$

Для Dy3+ ground-doublet application:

$$
g_0=2,\qquad
M_{\alpha\beta}^{(0i)}=
\frac12\operatorname{Tr}\!\left(P_0J_\alpha P_iJ_\beta\right).
$$

Это приложение не превращает Kramers doublet в условие общего определения.

## Physical boundary

Статическое среднее $\langle J_\alpha\rangle$ характеризует состояние, а
матричный элемент перехода связывает разные подпространства. Поэтому нулевой
статический момент не обнуляет автоматически переход. Тензор также ещё не
является neutron cross section или измеренной TAS-интенсивностью: для них
нужны polarization projection и experiment-specific response.

`STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001` - только project example
применения общего определения к DyFeO3; origin trail фиксирует историю
обсуждения, а не научную поддержку формулы.
