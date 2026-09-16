---
id: SU-000006
title: "Pbnm/Pnma and CEF-frame binding in the DyFeO3 workflow"
knowledge_kind: method_explanation
review_status: reviewed
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
    - "The target setting and origin are independently verified."
    - "The target rare-earth orbit and site symmetry are independently verified."
    - "The target local and global frames are explicitly stated."
    - "Operator normalization and coordinates are reconciled before comparing B_l^m."
    - "The independent-site sum is used only when inter-site dynamical cross terms are absent."
    - "Kramers/non-Kramers class and magnetic/exchange state are independently assessed."
  exclusions:
    - "DyFeO3 R_s matrices must not be copied solely from RFeO3 family membership."
  facets:
    kramers_class: NOT_APPLICABLE
    magnetic_order: NOT_APPLICABLE
    exchange_treatment: NOT_APPLICABLE
    temperature_regime: null
    field_regime: null
relations:
  depends_on:
    - SU-000003
  specializes: []
  contrasts_with: []
  derived_from:
    - STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001
    - STAGE03R-TAIPAN-HKL-SETTING-RECONCILIATION-001
  project_examples:
    - STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001
  related_concepts:
    - SU-000001
sources:
  background: []
  claim_support: []
convention_refs:
  - 04_Results/Stage03R/STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001/CHECKPOINT.yaml
  - 04_Results/Stage03R/STAGE03R-DY-SITE-TENSOR-TRANSFORM-CONTRACT-001/CONVENTION_CONTRACT.yaml
convention_binding:
  status: EXPLICIT
  crystallographic_setting: >-
    Pbnm #62, Hall -P 2c 2ab; non-standard setting of #62
  origin_choice: >-
    conventional origin encoded by Hall symbol -P 2c 2ab;
    Pbnm -> standard Pnma uses origin shift (0,0,0)
  global_frame: >-
    right-handed orthonormal crystallographic Cartesian frame
    (a,b,c)_Pbnm
  local_frame: >-
    right-handed CEF frame (X,Y,Z)=(b,c,a)_Pbnm;
    no additional local rotation in the accepted historical direct-BCA
    CEF convention
  site:
    species: Dy
    wyckoff: 4c
    site_symmetry: >-
      m (Cs); reference representative (x_Dy,y_Dy,1/4),
      mirror normal to c_Pbnm
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
space group: Pbnm #62, Hall -P 2c 2ab
Dy orbit: 4c
site symmetry: m (Cs)
CEF frame: X=b, Y=c, Z=a, right-handed
```

Прямые оси и origin связаны как

$$
(a,b,c)_{\mathrm{Pnma}}=(b,c,a)_{\mathrm{Pbnm}},
\qquad \Delta o=(0,0,0),
$$

а соответствующая матрица перестановки

$$
P=
\begin{pmatrix}
0&0&1\\
1&0&0\\
0&1&0
\end{pmatrix},
\qquad \det P=+1.
$$

Для записанных TAIPAN индексов действует identity binding

$$
(h,k,l)_{\mathrm{TAIPAN}}=(h,k,l)_{\mathrm{Pbnm}},
$$

а публикационное обозначение Pnma связано явным преобразованием

$$
(H,K,L)_{\mathrm{Pnma}}=(k,l,h)_{\mathrm{Pbnm}}.
$$

Reference site принят как

```text
Dy1 = (x_Dy,y_Dy,1/4)
Wyckoff 4c
site symmetry m = Cs
stabilizer: (x,y,z) -> (x,y,-z+1/2)
```

В CEF frame зеркальная операция имеет представление

$$
R_m^{XYZ}=\operatorname{diag}(1,-1,1).
$$

При CEF binding $X=b$, $Y=c$, $Z=a$ используемое отображение передачи
импульса имеет вид

$$
\mathbf Q_{\mathrm{CEF}}=
2\pi\left(\frac{k}{b},\frac{l}{c},\frac{h}{a}\right).
$$

## Tensor transport

Для reconstructibility с этой materialization onward принят следующий
порядок sites; он не объявляется исторически замороженной нумерацией прежнего
compact checkpoint:

| site | position | $R_{\mathrm{CEF}}$ |
|---|---|---|
| Dy1 | $(x,y,1/4)$ | $\operatorname{diag}(+1,+1,+1)$ |
| Dy2 | $(x+1/2,1/2-y,3/4)$ | $\operatorname{diag}(-1,-1,+1)$ |
| Dy3 | $(1/2-x,y+1/2,1/4)$ | $\operatorname{diag}(+1,-1,-1)$ |
| Dy4 | $(-x,-y,3/4)$ | $\operatorname{diag}(-1,+1,-1)$ |

Для этих симметрийно связанных Dy sites accepted contract использует

$$
M_s=R_sM_{\mathrm{ref}}R_s^T,
$$

$\mathbf J$ является axial vector. Для improper spatial representative $R$
на $\mathbf J$ действует $A=\det(R)R$, но два parity factors сокращаются в
rank-two transition tensor, поэтому та же формула
$M_s=R_sM_{\mathrm{ref}}R_s^T$ остаётся справедливой.

Four-site table удовлетворяет regression invariant

$$
\sum_{s=1}^{4}R_sMR_s^T=
4\,\operatorname{diag}(M_{XX},M_{YY},M_{ZZ}).
$$

Формула $I=\sum_s I_s$ является дополнительным localized
independent-single-ion approximation, а не следствием одной только
space-group symmetry. Она требует отсутствия $s\ne s'$ dynamical cross
correlations. Coherent, propagating, exchange-coupled или hybridized modes
требуют межсайтовых корреляционных членов и фазовых множителей по отдельному
контракту.

## Transfer boundary

Эта заметка связывает transition tensor (`SU-000003`) с текущим DyFeO3
workflow и относится к общему CEF formalism (`SU-000001`). Для другого RFeO3
необходимо независимо проверить setting/origin, rare-earth orbit и site
symmetry, global/local frames, operator normalization, Kramers class,
magnetic/exchange state и применимость independent-site sum. Семейная
принадлежность сама по себе не разрешает копирование DyFeO3 $R_s$ matrices.
