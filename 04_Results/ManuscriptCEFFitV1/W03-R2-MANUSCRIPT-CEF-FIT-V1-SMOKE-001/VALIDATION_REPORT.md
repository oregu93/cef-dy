# W03 r2 manuscript CEF fit v1 — validation report

Status: `PASS_READY_FOR_IMPLEMENTATION_REVIEW`

The first implementation checkpoint stops at smoke scope. No production fit,
profile scan, accepted-solution ensemble, exchange model, or scientific result
promotion was performed.

The project-owned NumPy Hamiltonian exactly reproduces the frozen historical
R7 levels and transition strengths and agrees at matrix level with the locally
installed PyCrystalField and CrysFieldExplorer backends. Tests cover operator
conventions, Kramers pairing, transition tensors, objectives, censored
likelihoods, nuisance profiling, PCM scaling, Cs15 coordinates, doublet
projectors, gauge fixing, g tensors, frozen-CEF magnetization, the input gate,
and optional backend cross-checks.

The current manuscript table intentionally contains only one admitted energy
candidate. Missing scan-level provenance and the absence of reviewed detected
and censored intensity rows produce `DRAFT_PROVENANCE_INCOMPLETE`. This blocks
joint intensity production fitting while leaving implementation and diagnostic
smoke calculations available.

The PCM smoke enumerates all seven assignments. Uniform scaling can match the
candidate for D1 through D5 inside the declared search box; D6 and D7 occupy a
scale boundary. This is a code/constraint diagnostic, not evidence for any
assignment.

The Cs15 smoke runs one fixed-seed bounded restart for every assignment. All
branches terminate, while D1 through D4 occupy the numerical search boundary.
The result demonstrates the expected energy-only non-identifiability and must
not be ranked as a preferred Hamiltonian family.

Terminal marker: `READY_FOR_IMPLEMENTATION_REVIEW`
