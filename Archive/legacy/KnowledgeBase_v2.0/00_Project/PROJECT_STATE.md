---
title: "DyFeO3 — Project State"
type: project_state
project_id: CEF-Dy
status: active
version: "2.0"
updated: 2026-08-27
source_state: "01-DyFeO3_PROJECT_STATE.md v1.2"
review_status: reviewed
---

# DyFeO$_3$ — Project State

> [!abstract] Scope
> Этот файл содержит только **текущее научное состояние** проекта: validated results, working hypotheses, conventions, datasets, model boundaries, uncertainties и текущий scientific milestone. История того, как к этому пришли, находится в [RESEARCH_LOGBOOK](../01_Logbook/RESEARCH_LOGBOOK.md); управление следующими действиями — в [PROJECT_CONTROL](PROJECT_CONTROL.md).

# 60-second re-entry

**Scientific question.** Получить воспроизводимую и физически интерпретируемую CEF-модель Dy$^{3+}$ в DyFeO$_3$, согласованную с INS и затем проверенную независимыми magnetic observables.

**Current model status.** Energy-only 15-parameter inverse problem показан как сильно недоопределённый. Текущий Stage 03D сознательно возвращается к low-dimensional structural/chemical model: nested neutral effective-charge PCM `M0/M1`, fitted к robust energy + detected/censored `F002`.

**Strongest evidence.** Robust CEF candidate:

$$
E_{\mathrm{CEF}} = 18.247178 \pm 0.119021~\mathrm{meV}.
$$

Stage 03C показывает, что formal/uniform-screened PCM даёт сильный первый transition около этой энергии, но практически не поддерживает обязательные CEF assignments около $6.45$ и $27.90~\mathrm{meV}$.

**Current uncertainty.** Не установлены уникальный full CEF Hamiltonian, assignments всех уровней и достаточность zero-exchange description для low-temperature intensities.

**Current milestone.** `Stage 03D`: identifiable nested `M0/M1` effective-charge fit с correct treatment non-detections и shared instrument-block normalization.

**Immediate next step.** Design review likelihood, nuisance profiling, parameter bounds, nested-model comparison, profile scans и accepted-ensemble criteria в чате `03 - CEF Modelling & Fit Design`.

**Do not assume.** `F004`/44.4 meV не является обязательным CEF level; $6.45$ и $27.90~\mathrm{meV}$ не являются confirmed CEF levels; exchange не включён в Stage 03D; один numerical minimum не определяет физическую модель.

---

# 1. Scientific objective

Искомая финальная модель должна включать:

1. CEF Hamiltonian в явно зафиксированной operator convention;
2. level scheme и wavefunctions;
3. neutron transition tensors и INS intensities;
4. ground-state и при необходимости excited-state $g$ tensors;
5. accepted solution ensemble / uncertainty representation;
6. независимую cross-check через PyCrystalField, CrysFieldExplorer и McPhase;
7. последующую validation по $M(H)$, susceptibility и, если доступно, heat capacity.

Основной принцип:

> **Energy-only fit не является достаточным критерием для low-symmetry CEF inverse problem.**

# 2. Physical system

Для Dy$^{3+}$:

$$
4f^9,\qquad {}^6H_{15/2},\qquad J=\frac{15}{2},\qquad g_J=\frac{4}{3}.
$$

Размерность основного $J$-мультиплета:

$$
2J+1=16.
$$

Для time-reversal-invariant single-ion CEF это соответствует восьми Kramers doublets. При internal exchange field Kramers degeneracy не должна считаться автоматически защищённой.

Рабочее crystallographic описание DyFeO$_3$: `Pbnm/Pnma`; setting должна указываться явно при работе с координатами, axes и CEF parameters. Локальная site symmetry Dy описывается как $C_s$.

# 3. Canonical CEF conventions

## 3.1. Hamiltonian

$$
\hat H_{\mathrm{CEF}}
=
\sum_{l,m} B_l^m \hat O_l^m,
\qquad l=2,4,6.
$$

Canonical external project notation для $C_s$ содержит 15 independent Stevens parameters:

$$
\begin{aligned}
& B_2^0,\ B_2^{-2},\ B_2^2,\\
& B_4^0,\ B_4^{-2},\ B_4^2,\ B_4^{-4},\ B_4^4,\\
& B_6^0,\ B_6^{-2},\ B_6^2,\ B_6^{-4},\ B_6^4,\ B_6^{-6},\ B_6^6.
\end{aligned}
$$

Machine labels:

```text
B20, B2n2, B22,
B40, B4n2, B42, B4n4, B44,
B60, B6n2, B62, B6n4, B64, B6n6, B66
```

## 3.2. Legacy direct PCF/CFE basis

Legacy scripts used:

```text
B20 B21 B22
B40 B41 B42 B43 B44
B60 B61 B62 B63 B64 B65 B66
```

Здесь, например, `B21` — coefficient of direct `StevensOp(J,2,1)`. Это **не** alias для $B_2^{-2}$.

Простое переименование direct positive-$q$ coefficients в canonical negative-$m$ Hutchings labels запрещено. Требуется explicit rotation/convention transform.

## 3.3. Audited frames

Direct PCF axes:

```text
(X,Y,Z) = (b,c,a)
```

Stage 03C audited canonical axes:

```text
(x,y,z) = (b,-a,c)
```

Переход реализован как active $+90^\circ$ rotation about $x\parallel b$ в соглашении Stage 03C. Любое изменение CIF/setting/local-axis adapter требует повторного convention regression test.

## 3.4. Convention benchmark

Direct PCF и direct CFE Hamiltonians benchmarked до machine precision. Для ранее проверенного benchmark:

$$
\max |H_{\mathrm{CFE}}-H_{\mathrm{PCF}}|
\approx 8.9\times10^{-16}~\mathrm{meV}.
$$

Canonical reconstruction residual был порядка:

$$
2.75\times10^{-11}~\mathrm{meV}.
$$

Для публикационного использования недостаточно совпадения eigenvalues: необходимо сохранять axis metadata и проверять transition tensors.

## 3.5. McPhase mapping

В McPhase negative-$m$ Stevens components записываются через `S` suffix, например:

```text
B2n2 -> B22S
B4n4 -> B44S
B6n6 -> B66S
```

Перед переносом всегда проверять Stevens vs Wybourne normalization, units и local frame.

# 4. Structural and PCM baseline

Рабочий low-temperature structural input использует Dy position около $(0.9778,0.0695,0.25)$ и local oxygen environment из refinement/CIF. Эта структура рассматривается как **working**, а не автоматически окончательная независимо refined model.

Baseline formal-charge PCM с $q_{\mathrm O}\approx-2$ давал уровни:

$$
\begin{aligned}
E_0 &= 0,\\
E_1 &\approx 19.879~\mathrm{meV},\\
E_2 &\approx 41.543~\mathrm{meV},\\
E_3 &\approx 54.593~\mathrm{meV},
\end{aligned}
$$

с резко доминирующим первым ground-state transition.

Uniform scaling effective charge главным образом масштабирует energy scale и сохраняет eigenvectors/intensity fingerprint. Поэтому uniform screening является полезным baseline/seed, но не общим решением inverse problem.

Два разных PCM benchmarks нельзя смешивать без reproduction of inputs/conventions: наш reproduced formal-charge PCM даёт first transition около $19.88~\mathrm{meV}$, тогда как отдельный literature/conference PCM benchmark сообщал first excited level около $28.01~\mathrm{meV}$.

# 5. TAIPAN experimental evidence

## 5.1. Dataset

Рабочий TAIPAN dataset:

- experiment `1296`;
- 201 `.dat` scans;
- 7 761 measured points;
- DyFeO$_3$ single crystal;
- PG monochromator / PG analyzer;
- collimation `o-40-40-o`;
- typical fixed final energy $E_f\approx14.87~\mathrm{meV}$;
- основные temperature blocks около $3.4$–$3.5~\mathrm K$ и $10~\mathrm K$.

Lattice/UB metadata меняются между acquisition blocks и должны читаться из соответствующих scan metadata, а не hard-code одним tuple.

## 5.2. Resolution

Elastic scan 104062 дал empirical effective energy resolution:

$$
\mathrm{FWHM}_{\mathrm{elastic}}
=
0.894\pm0.025~\mathrm{meV}
$$

при $Q\approx2.26~\text{\AA}^{-1}$.

Это не полная TAS resolution function.

## 5.3. Robust CEF candidate and other landmarks

Stage 03A robust CEF candidate:

$$
E_{\mathrm{CEF}}=18.247178\pm0.119021~\mathrm{meV}.
$$

Рабочие landmarks $6.45$ и $27.90~\mathrm{meV}$ являются targeted hypotheses / upper-limit tests, а не confirmed observed CEF levels.

## 5.4. 44.4 meV structure

Почти бездисперсионная broad structure наблюдается около:

$$
44.39\pm0.05~\mathrm{meV}.
$$

Stage 03A/03C treatment оставляет её `unassigned / possibly mixed`. Q-dependence уменьшается слабее, чем simple localized-Dy $F_{\rm Dy}^2(Q)P(\mathbf Q)$ prediction. Поэтому pure Dy CEF assignment не используется как mandatory constraint.

# 6. Inverse-problem status before Stage 03D

Broad CFE/CMA-ES searches показали большое число radically different 15-parameter CEF schemes с почти одинаковым energy-only loss. Следовательно, current observation set не идентифицирует unconstrained 15-parameter Hamiltonian.

Working B2 manifold с landmarks около $6.45/18.2/27.9~\mathrm{meV}$ дал energy-consistent candidates, включая strongly Ising-like solutions с $g_{\max}$ около 19–20. Однако этот manifold остаётся **working hypothesis**, а не validated final model.

Последний ultra-low-loss energy candidate также не является финальной моделью, поскольку intensity contribution в соответствующем pipeline не был полноценно validated.

# 7. Stage 03C reviewed result

Stage 03C построил site-symmetry-corrected full-cluster PCM seeds без exchange и audited frames `(b,c,a) -> (b,-a,c)`.

Для uniform screened full-cluster seed:

- $D_1=18.247~\mathrm{meV}$, powder strength $\approx6.071~J^2$;
- $D_2=28.935~\mathrm{meV}$, strength $\approx0.0396~J^2$, то есть около $0.653\%$ от $D_1$;
- predicted signal около targeted $27.90~\mathrm{meV}$ не превышает примерно $0.139\%$ conservative upper limit;
- transition около $6.45~\mathrm{meV}$ отсутствует;
- levels около $43.175$ и $46.385~\mathrm{meV}$ лежат рядом с broad 44.316 meV structure, но соответствующие ground-state transitions very weak.

Intensity audit выявил selection-bias issue: normalization, оцененная только по detected profiles, переоценивает predicted F002 в non-detected profiles.

Diagnostic WLS по всем profile-area estimates дал scales около:

$$
6.706,\qquad22.965,\qquad7.144,
$$

с combined reduced $\chi^2\approx0.973$ при 43 degrees of freedom. Два temperature blocks одного `instrument_block_id` совместимы с shared scale около $7.061$ и reduced $\chi^2=0.640$; отдельный instrument block имеет reduced $\chi^2\approx2.36$.

# 8. Current Stage 03D model boundary

Stage 03D должен использовать nested low-dimensional effective-charge models.

**M0 — uniform effective-charge-scaled full-cluster PCM benchmark.**

**M1 — neutral two-parameter effective-charge model** с independent oxygen scales $s_{\mathrm{O1}}$ и $s_{\mathrm{O2}}$ и common cation scale:

$$
s_{\mathrm{cat}}
=
\frac{s_{\mathrm{O1}}+2s_{\mathrm{O2}}}{3},
$$

что сохраняет charge neutrality crystallographic unit cell.

Stage 03D objective должен включать:

1. energy likelihood для $18.247178\pm0.119021~\mathrm{meV}$;
2. Gaussian/profile likelihood для detected `F002`;
3. one-sided censored likelihood для non-detections и targeted $6.45/27.90~\mathrm{meV}$ hypotheses;
4. один nuisance normalization на `instrument_block_id`;
5. `F004` только как diagnostic/alternative-assignment branch.

После optimum планируются per-parameter profile scans с reoptimization остальных parameters и stochastic accepted-solution ensemble. Structural-coordinate uncertainty и fit/statistical uncertainty должны оцениваться **раздельными ensembles**.

> [!warning] Explicit boundary
> Exchange не включается в Stage 03D. Unconstrained 15-parameter $B_l^m$ fit также не является текущим Stage 03D model.

# 9. Neutron-intensity model

Для transition $i\to f$:

$$
I_{if}(\mathbf Q,T)
\propto
p_i(T)\frac{k_f}{k_i}F_{\mathrm{Dy}}^2(Q)
\sum_{\alpha\beta}
\left(\delta_{\alpha\beta}-\hat Q_\alpha\hat Q_\beta\right)
M_{\alpha\beta}^{if}.
$$

Критическое identifiability rule: независимый unconstrained scale на каждый single-peak scan поглощает predicted intensity и уничтожает информацию о wavefunctions. Scale должен быть shared как минимум внутри physically justified `instrument_block_id` либо иметь внешний prior.

Non-detections должны входить как censored/upper-limit observations, а не просто удаляться из fit.

# 10. Exchange and temperature boundary

Физически полный low-temperature Hamiltonian в дальнейшем должен рассматриваться как:

$$
\hat H(T,\mathbf H)
=
\hat H_{\mathrm{CF}}
+
\hat H_{\mathrm{exch}}^{\mathrm{Dy-Fe}}(T)
+
\hat H_{\mathrm{exch}}^{\mathrm{Dy-Dy}}(T)
+
\hat H_{\mathrm{Zeeman}}(\mathbf H).
$$

Оба TAIPAN temperature blocks находятся глубоко внутри Fe-ordered state; блок $3.4$–$3.5~\mathrm K$ дополнительно находится вблизи/ниже Dy ordering regime. Поэтому apparent temperature-dependent CEF effects нельзя интерпретировать как lattice $B_l^m(T)$ до отделения exchange/domain/population effects.

Текущая model hierarchy для later validation:

```text
CEF-0
  -> CEF + Fe exchange
  -> CEF + Fe + Dy exchange
  -> full multi-sublattice magnetic model
```

# 11. Validated / reviewed results

| ID | Status | Result |
|---|---|---|
| `R-001` | validated | Direct PCF/CFE conventions benchmarked to machine precision. |
| `R-002` | validated | Legacy `B21`, `B41`, ... нельзя переименовывать в negative-$m$ canonical parameters. |
| `R-003` | validated | Energy-only low-symmetry 15D inverse problem strongly underdetermined for current data. |
| `R-004` | validated | TAIPAN dataset contains 201 scans / 7 761 points with main blocks near 3.5 K and 10 K. |
| `R-005` | validated | Empirical elastic FWHM $0.894\pm0.025~\mathrm{meV}$. |
| `R-006` | reviewed | Robust CEF candidate $18.247178\pm0.119021~\mathrm{meV}$. |
| `R-007` | reviewed | Shared `instrument_block_id` scale is required for identifiable F002 fitting. |
| `R-008` | reviewed | Stage 03C formal/uniform PCM intensity fingerprint does not support treating 6.45/27.90 meV as mandatory levels. |
| `R-009` | reviewed | 44.4 meV feature remains unassigned/possibly mixed and is not mandatory Stage 03D CEF input. |

# 12. Working hypotheses

| ID | Status | Hypothesis |
|---|---|---|
| `H-001` | working | 18.247 meV feature is a Dy$^{3+}$ CEF transition and should anchor Stage 03D energy likelihood. |
| `H-002` | working | Low-dimensional neutral effective-charge deformation M1 may improve F002 compatibility relative to uniform M0 without introducing unconstrained 15D freedom. |
| `H-003` | candidate | B2-like topology with hidden/weak levels near 6.45 and 27.90 meV may exist, but current data do not require it. |
| `H-004` | disfavored | 44.4 meV is a pure single-component localized Dy CEF transition. |

# 13. Open questions

| ID | Priority | Question |
|---|---|---|
| `Q-001` | high | Как формально определить detected/censored F002 likelihood и upper-limit policy? |
| `Q-002` | high | Как профилировать nuisance scale по `instrument_block_id`: аналитически или numerically? |
| `Q-003` | high | Какие bounds/priors на $s_{\mathrm{O1}},s_{\mathrm{O2}}$ физически и статистически оправданы? |
| `Q-004` | high | Какой nested-model comparison criterion использовать для M0 vs M1? |
| `Q-005` | high | Как определить accepted-solution ensemble и profile thresholds без двойного счёта uncertainty? |
| `Q-006` | medium | Какова физическая природа 44.4 meV feature? |
| `Q-007` | medium | Какая exchange-aware model нужна после завершения zero-exchange structural fit? |
| `Q-008` | medium | Какая structural-coordinate uncertainty доминирует в effective-charge PCM? |
| `Q-009` | later | Как переносить structural CEF trends по Dy/Ho/Tb/Tm через $A_l^m$ и local multipoles? |

# 14. Software and model roles

- **PyCrystalField:** single-ion Hamiltonian, eigenstates, transition tensors, spectra, $g$, PCM.
- **CrysFieldExplorer:** global landscape exploration and ensemble diagnostics.
- **McPhase:** independent Stevens/magnetic-property cross-check and later exchange-aware modelling.
- **Python/Colab:** reproducible data reduction and staged numerical workflows.

# 15. Current scientific milestone

$$
\boxed{
\text{Stage 03D: nested M0/M1 neutral effective-charge fit to energy + detected/censored F002}
}
$$

Definition of success is not a single best vector. Stage 03D must establish whether M1 is statistically and physically supported relative to M0, quantify identifiable parameter ranges, preserve censored information, and export a reproducible accepted-solution ensemble.

# 16. Provenance

Primary migration source: `01-DyFeO3_PROJECT_STATE.md`, version 1.2, updated 2026-08-27.

Historical detailed numerical tables and chronology remain in legacy/project-source documents and should not be duplicated into this concise state file unless they are needed for current interpretation.
