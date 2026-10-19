# Manuscript CEF fit v1 implementation audit

## Reentry

- Supplied task directory: no repository checkout; empty `.git` placeholder.
- Canonical project repository inspected read-only at
  `/home/oleg/Документы/CEF/CEF_Dy`.
- Canonical design baseline: `c65cfb1daa8edf4ce85684b5093869c0f287d269`
  (`origin/main`).
- Existing local `main`: `45fcf89f5a2571d534da6cf3f70018d3de620d7e`,
  behind canonical by two commits and dirty. It was not modified.

## Reuse map

| Asset/component | Decision | Reason |
|---|---|---|
| Stage03C axis matrices and explicit active rotation | REUSE_AFTER_TEST | Reviewed metadata; matrix/Hamiltonian/tensor regression still required. |
| Stage03C angular-momentum/Stevens semantics | REIMPLEMENT | Remove PyCrystalField runtime dependency from authoritative kernel; regress against PCF and frozen bundles. |
| Stage03C Kramers grouping | REIMPLEMENT | Add explicit tolerance checks and projector-first representation. |
| Stage03C transition tensors | REUSE_AFTER_TEST | Formula is appropriate; implemented as gauge-invariant projector traces. |
| Stage03C g-tensor and M(H) kernels | REIMPLEMENT | Package APIs, stable thermodynamics, axis metadata, and independent tests required. |
| Stage03C structure/PCM cluster construction | REUSE_AFTER_TEST | Useful later, but structural inputs are not admitted in this first clean skeleton. |
| Stage03C detected-only scale fit | DISCARD | Selection-biased for the intended joint likelihood. |
| Legacy Stage03D censored Gaussian likelihood | REIMPLEMENT | Stable `log_ndtr`, explicit row admission, and component decomposition. |
| Legacy Stage03D instrument-block nuisance scales | REIMPLEMENT | Profiled log-scales with convergence/boundary diagnostics. |
| Legacy Stage03D monolithic Colab architecture | DISCARD | Scientific logic must be importable and testable. |
| Legacy Stage03D AICc mid-refactor/output writers | DISCARD | Known signature mismatch and incomplete selection-policy refactor. |
| R3/R5/R7 frozen parameter/level/strength bundles | REUSE_AS_IS | Historical exploratory regression seeds only; never current/preferred solutions. |
| Accepted Dy-site tensor transform contract | REUSE_AS_IS | Canonical independent-site tensor transport metadata. |

The named `23_stage03d_nested_effective_charge_fit_colab.py` is not present in
the project mirror or canonical tree. Its health summary was available, but no
code was copied from an unavailable mid-refactor artifact.

## Known technical debt

- The W02 energy result is adjudicated as model-dependent: 18 primary joint
  variants and 18 single-block stress variants are admitted only to the
  separate conditional-analysis class. No scalar energy or relative-intensity
  constraint is admitted to the existing production likelihood.
- The admitted low-temperature structural input needed to rebuild formal PCM
  from coordinates is absent from the manuscript table; current PCM smoke uses
  the reviewed legacy formal O8 seed and labels it accordingly.
- Direct-to-canonical Hamiltonian, level, transition-tensor, and g-tensor
  covariance are covered by independent-diagonalization regressions; no label
  renaming is used.
- A representative McPhase numerical cross-check remains required.
- CrysFieldExplorer exposes distribution version 1.0.11 while its runtime
  banner reports 1.0.0; its internal objective is non-authoritative.

## Recorded pre-production gaps

These are recorded only and are not implemented by the bounded review
correction:

1. a reviewed production optimizer/backend adapter (the conditional workflow
   uses seeded CMA-ES only as a diagnostic landscape search);
2. a representative McPhase numerical cross-check;
3. a reviewed W02 relative-intensity admission result.

Production remains disabled in configuration pending independent review and
closure of the applicable input gate.

## Backend capability probe (2026-10-19)

| Backend | Local state | Minimal tested operation | Windows / Colab | Limitation |
|---|---|---|---|---|
| NumPy/SciPy | NumPy 2.3.0, SciPy 1.15.3 in `/home/oleg/work_venv` | Hermitian eigensystem and optimization dependencies exercised by tests | Cross-platform wheels; expected usable on both | Canonical local shell Python lacks SciPy; use a venv. |
| PyCrystalField | 2.3.11 in `/home/oleg/work_venv` | Imported `StevensOp(15/2,2,0)` and verified a 16x16 Hermitian matrix | Python package; expected Windows/Colab after dependency install, not tested here | Optional cross-check only; local source-only copy has incomplete dependencies. |
| CrysFieldExplorer | distribution 1.0.11, runtime banner 1.0.0 | Constructed Dy3+ 15-operator object and a zero 16x16 Hamiltonian | Expected Python use on Windows/Colab, not tested here | API imported from `CrysFieldExplorer.CrysFieldExplorer`; project objective remains authoritative. |
| CMA-ES | `cma` 4.2.0 | One seeded 2D ask/tell generation, 4 evaluations | Cross-platform Python; expected Windows/Colab | Optional; smoke implementation uses bounded SciPy minimization so it remains runnable without CFE. |
| McPhase | version header 5.6; Linux x86-64 binaries | `so1ion -r Ce3p.sipf -l` produced levels | Linux usable; bundled binary is not Windows/Colab portable | Export-only backend in this package; Windows needs a native McPhase install, Colab needs an explicit Linux install. |
