# Model-dependent conditional-energy analysis v1

Required labels: `MODEL_DEPENDENT_ENERGY|NO_UNIQUE_HAMILTONIAN_CLAIM|NO_INTENSITY_CONSTRAINT|NO_EXCHANGE`.

## A. What TAIPAN currently establishes

W02 supports an excitation feature near 18 meV only through 18 alternative
primary conditional reductions of the same scans. There is no admitted scalar
TAIPAN energy and no likelihood is formed by summing variants.

## B. Centroid model dependence

The primary joint-centroid variants span `17.922223` to `18.130905`
meV (full span `0.208682` meV). Single-block stress variants
span `17.802472` to `18.235117` meV. These ranges describe analysis
model dependence, not a statistical confidence interval.

## C. One-parameter PCM M0

Assignments robustly inside the scale box across all primary variants:
`D0->D1, D0->D2, D0->D3, D0->D4, D0->D5`. Assignments that also
remain inside the scale box across all single-block stress variants:
`D0->D1, D0->D2, D0->D3, D0->D4, D0->D5`. PCM M0 is quantitatively
interpretable as a one-scale conditional baseline; it does not identify a
general CEF Hamiltonian. Because M0 is a uniform positive scale, its projectors,
transition strengths, and g tensors are invariant; the predicted level-energy
scale changes with the W02 variant and assignment.

## D. Fifteen-parameter Cs15 model

The bounded representative CMA-ES campaign found `196` accepted
conditional solutions in `196` operational parameter
families. Compatible assignments were `D0->D1, D0->D2, D0->D3, D0->D4, D0->D5, D0->D6, D0->D7`. One
energy condition cannot identify 15 coefficients, rank a unique solution, or
define a confidence region. `69/196` solutions touch
the operational search-boundary margin. The family labels are descriptive
search outcomes, not confidence regions or optimizer probabilities.

## Historical R3/R5/R7 continuity check

The frozen historical solutions were evaluated without refitting. Only their
D2 energies are near the W02 conditional ensemble:

- `CS15-HIST-B2-R3`: D2 q range `0.667`–`7.055`; `2/18` primary variants within q <= 1.
- `CS15-HIST-B2-R5`: D2 q range `0.650`–`7.009`; `2/18` primary variants within q <= 1.
- `CS15-HIST-B2-R7`: D2 q range `0.642`–`6.987`; `2/18` primary variants within q <= 1.

This does not promote any historical solution or make its prior ~18.2-meV
lineage an independent confirmation.

## E. Wavefunctions and g tensor

The minimum pairwise ground-doublet projector overlap across accepted Cs15
solutions is `0.000002`. Principal-g ranges are `[[8.302000988996838,19.71644963179794],[0.010393007084236607,9.925569678181782],[0.004471660777399952,5.1332899782331785]]`.
Accordingly, wavefunctions and g tensors are
`not experimentally determined by the conditional energy alone`.

## F. Viable level assignments

PCM M0 retains `D0->D1, D0->D2, D0->D3, D0->D4, D0->D5`
across every primary variant without a scale-boundary conflict. The diagnostic
Cs15 search can satisfy `D0->D1, D0->D2, D0->D3, D0->D4, D0->D5, D0->D6, D0->D7`, illustrating rather
than resolving assignment ambiguity.

## G. Most informative next observable

Reviewed, Q-resolved relative transition intensities for at least two distinct
CEF excitations would most directly constrain eigenvectors and assignments.
Additional independently resolved transition energies would constrain the
level scheme; polarization information would further constrain wavefunctions.

## Magnetization

`SKIPPED__NO_REVIEWED_TEMPERATURE_LIST`. Literature M(H) was not used for selection.
