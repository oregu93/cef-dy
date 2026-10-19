# DyFeO3 manuscript CEF fit v1

This package is the local, user-visible implementation of the reviewed
`DyFeO3 MANUSCRIPT_CEF_FIT_V1` design.  It implements the single-ion
Dy3+ (`J=15/2`) kernel, explicit transition-assignment branches, objective
components, nuisance scales, PCM and Cs15 smoke workflows, doublet projectors,
g tensors, and frozen-CEF magnetization.

Scientific boundaries are enforced in code and configuration:

- exchange is off;
- 18.247178 +/- 0.119021 meV is the current TAIPAN candidate;
- 6.447 and 27.896 meV are historical context only;
- about 44.4 meV is an ambiguous diagnostic only;
- Stage03R sensitivity near 38 meV is not a physical transition-strength limit;
- energy-only Cs15 calculations map a non-identifiable landscape and do not
  establish a unique Hamiltonian;
- production fitting is disabled until the provenance gate and independent
  review are both satisfied.

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

`audit-inputs` currently returns `DRAFT_PROVENANCE_INCOMPLETE`.  This blocks a
manuscript-grade joint intensity fit but deliberately does not block code
tests, PCM smoke, energy-only Cs15 diagnostics, wavefunction/g calculations,
or magnetization code.
