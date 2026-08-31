---
title: "CEF Dy — Project Control"
type: project_control
project_id: CEF-Dy
status: active
version: "1.0"
updated: 2026-08-27
control_chat: "00 - Project Control"
---

# CEF Dy — Project Control

> [!abstract] Role
> Этот документ управляет roadmap, task queue, decisions, hypotheses, risks, Work jobs и Definition of Done. Он обновляется чаще, чем `PROJECT_STATE`.

# 5-minute re-entry

**NOW:** `Stage 00A` knowledge-base refactor завершается; scientific work возвращается к `Stage 03D design review`.

**NEXT:** в чате `03 - CEF Modelling & Fit Design` формально определить M0/M1 likelihood, censored F002 treatment, nuisance-scale profiling, bounds, model-comparison criterion, profile scans и ensemble acceptance.

**NEXT WORK JOB:** `W03-03D-A-001` — implementation + smoke only. Production optimization, profile scans и ensemble запрещены до review checkpoint.

**BLOCKED:** Stage 03D production fit до утверждения design specification и успешного `03D-A` smoke checkpoint.

**DEFERRED:** exchange-aware fitting, mandatory F004 assignment, unconstrained 15-parameter CEF fit, full magnetic validation.

**LAST MAJOR SCIENTIFIC CHECKPOINT:** Stage 03C intensity audit and effective-charge PCM seed analysis.

---

# 1. Current milestone map

| Milestone | Status | Purpose |
|---|---|---|
| `M00` Knowledge-base refactor | completing | Разделить state/control/logbook/checkpoints и сделать систему автономной от ChatGPT. |
| `M03` Stage 03D effective-charge fit | active | Nested M0/M1 fit to energy + detected/censored F002. |
| `M04` broader CEF refinement | planned | Перейти к более общему Hamiltonian только если observation set поддерживает identifiability. |
| `M05` magnetic validation | planned | McPhase, $g$, $M(H)$, susceptibility, exchange. |
| `M06` structural/R-series transfer | later | $A_l^m$, local multipoles, Dy/Ho/Tb/Tm comparison. |
| `M07` publication/dissertation | ongoing/later | Publication-grade Methods, Results, figures, provenance. |

# 2. Active task queue

| Task ID | Type | Status | Task | Owner context |
|---|---|---|---|---|
| `T-00A-01` | knowledge | completing | Migrate Project State v1.2 into v2 knowledge architecture. | `00 - Project Control` |
| `T-03D-01` | design | next | Formal M0/M1 definition and nesting proof. | `03 - CEF Modelling & Fit Design` |
| `T-03D-02` | design | next | Detected/censored F002 likelihood and upper-limit semantics. | `03 - CEF Modelling & Fit Design` |
| `T-03D-03` | design | next | Nuisance-scale profiling per `instrument_block_id`. | `03 - CEF Modelling & Fit Design` |
| `T-03D-04` | design | queued | Parameter bounds/priors and optimizer strategy. | `03 - CEF Modelling & Fit Design` |
| `T-03D-05` | design | queued | Model comparison, profile scans and ensemble acceptance. | `03 - CEF Modelling & Fit Design` |
| `W03-03D-A-001` | work | blocked | Implement Stage 03D architecture + smoke tests only. | `W03 - CEF Compute` |
| `W03-03D-B-001` | work | blocked | Production M0/M1 optimization after A review. | `W03 - CEF Compute` |
| `W03-03D-C-001` | work | blocked | Coarse profile scans after B review. | `W03 - CEF Compute` |
| `W03-03D-D-001` | work | blocked | Adaptive profile refinement. | `W03 - CEF Compute` |
| `W03-03D-E-001` | work | blocked | Accepted ensemble + diagnostics. | `W03 - CEF Compute` |

# 3. Decision Register

| ID | Status | Decision | Rationale / consequence |
|---|---|---|---|
| `D-001` | active | Energy-only fit не считать финальным CEF criterion. | 15D inverse problem demonstrably degenerate. |
| `D-002` | active | Direct PCF/CFE и canonical Hutchings parameters связывать explicit transform, не rename. | Prevent convention corruption. |
| `D-003` | active | Intensity scale shared per physically justified `instrument_block_id`. | Independent scale per scan destroys identifiability. |
| `D-004` | active | Non-detections использовать как censored/upper-limit data. | Absence of predicted strong line is informative. |
| `D-005` | active | `F004`/44.4 meV не использовать как mandatory Stage 03D CEF level. | Assignment remains unassigned/possibly mixed. |
| `D-006` | active | Exchange не включать в Stage 03D. | First isolate structural/effective-charge identifiability; exchange addressed later. |
| `D-007` | active | Stage 03D starts with nested low-dimensional M0/M1, not unconstrained 15D fit. | Current observation set is insufficiently identifiable. |
| `D-008` | active | Work jobs are segmented and stop at explicit checkpoint boundaries. | Preserve Work/Codex budget and scientific control. |
| `D-009` | active | Project knowledge uses `PROJECT_STATE / PROJECT_CONTROL / WORK_CHECKPOINTS + RESEARCH_LOGBOOK`. | Improve re-entry, provenance, autonomy from ChatGPT. |
| `D-010` | active | Git is version-history master; Yandex.Disk is backup/data transport layer. | Avoid competing version masters. |
| `D-011` | active | Technical metadata in English; descriptive/physical content primarily in Russian. | Machine processing + readable scientific notes. |

# 4. Hypothesis Register

| ID | Status | Hypothesis | Discriminating evidence |
|---|---|---|---|
| `H-001` | working | 18.247 meV is a Dy CEF transition. | Energy stability, profile evidence, CEF consistency. |
| `H-002` | working | Neutral two-oxygen-scale M1 improves F002 compatibility relative to M0. | Nested likelihood comparison + profiles. |
| `H-003` | candidate | B2-like hidden levels near 6.45/27.90 meV exist. | Censored limits, future additional INS, full model. |
| `H-004` | disfavored | 44.4 meV is pure localized Dy CEF. | Q dependence, transition strength, temperature, mixed-mode tests. |

# 5. Open Question Register

| ID | Status | Question | Next owner |
|---|---|---|---|
| `Q-001` | active | Exact censored likelihood form? | Fit Design |
| `Q-002` | active | Analytical vs numerical nuisance profiling? | Fit Design |
| `Q-003` | active | M0/M1 parameter bounds/priors? | Fit Design |
| `Q-004` | active | M0 vs M1 comparison statistic under nesting/bounds? | Fit Design |
| `Q-005` | active | Profile threshold and accepted ensemble policy? | Fit Design |
| `Q-006` | open | Nature of F004 / 44.4 meV feature? | TAIPAN / Physics |
| `Q-007` | deferred | Minimal exchange-aware extension after Stage 03D? | Validation |
| `Q-008` | deferred | Structural-coordinate uncertainty propagation? | Structure |

# 6. Risk Register

| Risk ID | Level | Risk | Mitigation |
|---|---|---|---|
| `RSK-001` | high | Hidden non-identifiability masked by optimizer convergence. | Profiles, ensembles, nesting, censored data. |
| `RSK-002` | high | Nuisance normalization absorbs physical intensity information. | One scale per `instrument_block_id`, explicit profiling diagnostics. |
| `RSK-003` | high | Convention/frame mismatch corrupts intensities while energies look plausible. | Hamiltonian + transition-tensor regression tests. |
| `RSK-004` | medium | 44.4 meV misassignment biases CEF model. | Keep F004 diagnostic only in Stage 03D. |
| `RSK-005` | medium | Low-T exchange effects are misread as lattice CEF. | Stage boundaries + later exchange-aware validation. |
| `RSK-006` | medium | Work budget spent on reasoning/repeated trial-and-error. | Pre-specify jobs; resumable scripts; checkpoint stop conditions. |
| `RSK-007` | medium | Public Git repository leaks raw/private data. | Separate local-data tree + `.gitignore`. |

# 7. Stage 03D Work plan

```text
03D Design Review        [ordinary chat]
        ↓
03D-A Implementation + smoke
        ↓ checkpoint/review
03D-B M0/M1 production optimization
        ↓ checkpoint/review
03D-C Coarse profile scans
        ↓ checkpoint/review
03D-D Adaptive profile refinement
        ↓ checkpoint/review
03D-E Accepted ensemble + diagnostics
        ↓ checkpoint/review
03D-F Final validation/package/state update
```

Each Work job must have:

```text
GOAL
INPUTS
MODEL
LIKELIHOOD
PARAMETERS
BOUNDS
ALGORITHM
TESTS
OUTPUTS
PASS CRITERIA
STOP CONDITION
```

# 8. Definition of Done — Stage 03D

Stage 03D считается завершённым только если:

- [ ] M0 and M1 are mathematically explicit and genuinely nested.
- [ ] Detected F002 and censored non-detections are both included.
- [ ] Nuisance scales are identifiable and stored per `instrument_block_id`.
- [ ] Objective/likelihood decomposition is exported.
- [ ] M0/M1 optimums are reproducible from fixed inputs.
- [ ] Model-comparison result is reported with boundary caveats if relevant.
- [ ] Per-parameter uncertainty profiles are computed or explicitly justified as unnecessary.
- [ ] Accepted-solution ensemble is saved with parameters and derived CEF observables.
- [ ] Structural uncertainty is not silently merged with fit uncertainty.
- [ ] F004 remains diagnostic unless new evidence changes `D-005`.
- [ ] Exchange remains absent unless a new decision supersedes `D-006`.
- [ ] A reviewed checkpoint promotes only supported conclusions into `PROJECT_STATE`.

# 9. Update rules

- `PROJECT_CONTROL` may change after any substantial design/review decision.
- `PROJECT_STATE` changes only when current scientific knowledge changes.
- Work checkpoints are not rewritten after review except for explicit erratum metadata.
- Logbook records why a decision changed, including rejected/deferred paths.
