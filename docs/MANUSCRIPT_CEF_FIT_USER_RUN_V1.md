# Manuscript CEF fit: user run v1

Run commands from the repository root in a clean checkout of
`work/manuscript-cef-fit-v1`. Install once with `python -m pip install -e ".[cef]"`.
The canonical configuration is
`configs/manuscript_cef_fit_10k_exploratory_v1.yaml`; the CLI uses it by default.

## What is fitted

Stage 00 deterministically creates
`local_data/taipan_eq_map_exploratory_10K_v1.csv`: 520 ungridded B001 discovery
points from 20 accepted scans (raw scans 104215–104240 with gaps), combined with
A002 geometry, A003 acquisition/normalization metadata, and the accepted
temperature mapping. The operational selection is scan mean 9.95–10.05 K and
within-scan range at most 0.05 K. Exact scan temperatures remain in the table;
the block forward model uses 9.998965 K. Holdout detector access is zero.

The reviewed feature table is
`configs/manuscript_cef_fit_feature_table_v1.yaml`. BF-005 is the sole first-run
active CEF feature and BF-004 constrains shape in the same overlapping approximately
18-meV region; they are not two independent excitations. BF-001–BF-003 are preserved
diagnostically but excluded from every primary objective component because the
2.5–7 meV weight may be collective. BF-006–BF-008 remain diagnostic only.

## Physics and varied parameters

The forward model is single-ion Dy3+ (`J=15/2`, `gJ=4/3`) with 15 direct Cs
parameters in the internal `(b,c,a)` frame. It uses reviewed per-point Pbnm Q
geometry, the independent localized four-Dy-site tensor sum, Dy3+ form factor,
explicit polarization and `kf/ki`, all-state Boltzmann populations, a fixed
0.894 meV Gaussian resolution baseline, and a profiled local-linear background.

The search varies the 15 normalized coordinates `h_i = kappa_i B_i` within
[-8,+8] meV. Those bounds are an exploratory search domain, not physical priors.
Competitive near-bound solutions are retained and flagged for domain-sensitivity
review.

Exchange, powder averaging, CEF–phonon coupling, a full TAS resolution kernel,
absolute-cross-section claims, and a joint M(H) likelihood are deliberately absent.
Historical R3/R5/R7, PCM/formal, and M0 values initialize restarts only. Values
6.45, 18.2257, 18.247178, 27.90, and approximately 44.4 meV are not silently
inserted as mandatory targets.

## Objective and assignment branches

The exploratory loss is
`L_total = w_E L_energy + w_S L_shape + w_I L_relative_intensity` with first-run
neutral weights 1,1,1. These weights are not physically calibrated and the loss is
not a statistical chi-square. The BF-005 energy term is zero anywhere inside its
frozen B001 discovery window [17.4983, 20.49835] meV and rises continuously outside
the nearest edge, normalized by the half-window only as a penalty scale. There is no
midpoint/centroid preference. Shape losses are normalized within admitted features
and then averaged; relative-intensity losses are normalized within accepted
normalization blocks. One signal scale and local background parameters are profiled
per block, never per scan. Nuisance values and boundary flags are saved.

An assignment branch fixes BF-005 to one particular `D0->Dj` transition for the
entire optimization. Exactly seven branches, D0→D1 through D0→D7, are generated
deterministically. There is no nearest-level matching or hidden reassignment.

A restart is one independently seeded CMA-ES trajectory for one fixed assignment.
Every candidate is rescored by the repository's own forward model and objective.

## Stages 00–03: required review run

```bash
python -m cef_fit.user_pipeline 00_materialize_10k
python -m cef_fit.user_pipeline 01_data_audit
python -m cef_fit.user_pipeline 02_forward_review
python -m cef_fit.user_pipeline 03_objective_review
```

These stages materialize, audit, and review a frozen historical seed. They do not
optimize or generate a new Blm result. Send the JSON reports and diagnostic figures
under `results/manuscript_cef_fit_10k_exploratory_v1/00_materialize_10k` through
`03_objective_review` to Project Control before enabling stage 04.

## Stage 04: user-executed search

The checked-in safety switches are off. After review, make a recorded config copy
or reviewed config commit and set both `switches.RUN_EXPLORATORY_SEARCH` and
`search.run_exploratory_search` to `true`. Then run, for example:

```bash
python -m cef_fit.user_pipeline 04_global_search \
  --search-profile FIRST_EXPLORATORY_SEARCH \
  --workers 4 \
  --enable-exploratory-search
```

The checked-in default is `workers: 1`, which preserves the serial execution path.
On a six-core local machine, `--workers 4` is the recommended production setting.
Parallelism is only across complete independent `(assignment, restart)` trajectories;
population size, CMA-ES generations, deterministic restart seeds, bounds, objective,
and retained-candidate scientific fields are unchanged. Each worker owns a separate
atomic restart checkpoint under `04_global_search/restart_checkpoints`, while one
coordinator alone writes the merged checkpoint and candidate list.

Profiles are qualitative compute choices:

- `SMOKE_SEARCH`: seconds/minutes; wiring and debugging only; output is `SMOKE_ONLY`.
- `FIRST_EXPLORATORY_SEARCH`: recommended first real run; 32 population, 8 restarts
  per assignment, up to 20,000 evaluations per restart; expect hours to potentially
  much longer depending on machine and branch count.
- `EXTENDED_SEARCH`: later convergence study; 16 restarts per assignment and up to
  50,000 evaluations; potentially days.

Stop with Ctrl-C. Checkpoints are written during generations. Resume the identical
run with the same command plus `--resume` (the worker count may be changed). Resume
fails closed if the commit, config,
dataset, feature table, assignment set, parameter convention, resolution/background
variant, or search profile differs. An interrupted restart repeats from its recorded
deterministic seed.

## Post-search stages

```bash
python -m cef_fit.user_pipeline 05_ensemble_summary
python -m cef_fit.user_pipeline 06_frozen_mh_screen
python -m cef_fit.user_pipeline 07_cluster
python -m cef_fit.user_pipeline 08_wavefunctions
python -m cef_fit.user_pipeline 09_mcphase_export
```

Stage 05 retains at least the best candidate from every restart; it does not select
a unique solution. Stage 06 compares frozen candidates with the digitized Ke et al.
H||a/b data at 10/20 K, keeping total bulk experiment and single-ion Dy calculation
explicitly distinct; it never refits Blm. Stage 07 writes parameter and physical-
observable distance components, hierarchical families, and review-only medoids.
Stage 08 exports projectors as the primary wavefunction objects plus gauge-fixed
representatives, g tensors/axes, and transition tensors. Stage 09 only exports
representatives to McPhase; a later mismatch is a validation blocker, never an
automatic refit.

All outputs are under `results/manuscript_cef_fit_10k_exploratory_v1`. After stage
04, return `search_summary.json`, `search_checkpoint.json`, and
`retained_candidates.jsonl` to Project Control. After downstream stages, also return
the ensemble, M(H), clustering, wavefunction, and McPhase manifests.

None of the retained candidates, clusters, M(H) comparisons, or McPhase exports are
manuscript claims until separately reviewed and admitted.

## Colab

Open `notebooks/DyFeO3_joint_cef_fit_user_run.ipynb` after cloning/checking out the
same commit. Its first cell installs this repository and displays the commit; every
stage calls `cef_fit.user_pipeline`, so there is no notebook-only physics. For
persistent output, mount Google Drive before running and change `outputs.root` in a
config copy to the mounted path, or download the results directory after the run.
