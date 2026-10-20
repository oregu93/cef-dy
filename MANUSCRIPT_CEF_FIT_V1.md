# DyFeO3 manuscript CEF fit v1

This package is the local, user-visible implementation of the reviewed
`DyFeO3 MANUSCRIPT_CEF_FIT_V1` design.  It implements the single-ion
Dy3+ (`J=15/2`) kernel, explicit transition-assignment branches, objective
components, nuisance scales, PCM and Cs15 smoke workflows, doublet projectors,
g tensors, and frozen-CEF magnetization.

Scientific boundaries are enforced in code and configuration:

- exchange is off;
- no single scalar TAIPAN energy is admitted: the W02 result is represented by
  18 primary joint conditional variants plus 18 single-block stress variants;
- 6.447 and 27.896 meV are historical context only;
- about 44.4 meV is an ambiguous diagnostic only;
- Stage03R sensitivity near 38 meV is not a physical transition-strength limit;
- energy-only Cs15 calculations map a non-identifiable landscape and do not
  establish a unique Hamiltonian;
- production fitting is disabled until the provenance gate and independent
  review are both satisfied.

The separate user-executed exploratory E-Q pipeline is documented in
`docs/USER_EXECUTED_CEF_PIPELINE_V1.md`. Its numerical-map use is authorized
for model discovery, while its intensity objective remains
`EXPLORATORY_NOT_MANUSCRIPT_ADMITTED`. Global search is off by default and all
scientifically meaningful fitting must be launched visibly by the user.

## Local Windows workflow

```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e ".[cef]"
.venv\Scripts\python -m pytest tests/cef_fit -q

.venv\Scripts\python -m cef_fit.cli audit-inputs ^
    --config configs/manuscript_fit_v1.yaml

.venv\Scripts\python -m cef_fit.cli fit-pcm ^
    --config configs/manuscript_fit_v1.yaml ^
    --profile smoke

.venv\Scripts\python -m cef_fit.cli fit-cs15 ^
    --config configs/manuscript_fit_v1.yaml ^
    --profile smoke
```

The notebook in `notebooks/` is a frontend only; all scientific logic is in
the importable `cef_fit` package.  The same installation and module calls work
in Colab.

Machine-readable wavefunction coefficients use the explicit ascending
`m_J = -J, ..., +J` basis order employed by the PCF regression backend.

## Input gate

The audit reports one of three objective-readiness classes when all admitted
rows are valid:

- `ENERGY_ONLY`;
- `ENERGY_PLUS_DETECTED_INTENSITY`;
- `ENERGY_PLUS_DETECTED_INTENSITY_PLUS_CENSORING`.

The manuscript intensity gate requires at least the second class. Censored
rows are an optional enhancement, but any censored row presented for admission
is validated fail-closed. Provenance and normalization status vocabularies are
configured under `inputs.admission`; scientific status names do not need to be
renamed to a hard-coded token.

An aggregate energy may omit a single temperature and Q only when its
aggregation status, exact source artifact, and source scan set (directly or by
provenance manifest) are explicit. The former 18.247178-meV scalar row is now
explicitly excluded from the scalar energy likelihood and retained only as
superseded provenance. The reviewed W02 artifact is consumed by the separate
`MODEL_DEPENDENT_ENERGY_CONDITIONAL` workflow in
`configs/model_dependent_energy_conditional_v1.yaml`; its variants are evaluated
independently and are never summed into a likelihood. This conditional workflow
does not enable the existing production configuration and makes no unique
Hamiltonian, intensity, or exchange claim.

## Publication-frame regression gate

The frozen nontrivial R7 regression independently diagonalizes the direct and
rotated canonical Hamiltonians. It covers Hamiltonian covariance, invariant
levels, every ground-state transition tensor, and ground-doublet g principal
values/eigenspaces. Tensor and g-axis comparisons use
`R_CAN_FROM_DIRECT`; signed eigenvectors and degenerate-axis bases are not
treated as physical observables.
