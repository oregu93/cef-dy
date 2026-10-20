# User-executed joint CEF pipeline v1

## Purpose and scientific boundary

This pipeline prepares an ensemble analysis of Dy3+ in DyFeO3. It is intended
to be run visibly by the user from the repository in VS Code or through the
thin Colab notebook. No scientific optimization is performed by importing the
package, running the audit, or running the tests.

The current TAIPAN policy has two simultaneous statuses:

- `MANUSCRIPT_INTENSITY_GATE = FAIL_CLEANLY`: scan-to-scan relative-response
  calibration is not manuscript-qualified.
- `EXPLORATORY_EQ_MAP_USE = AUTHORIZED`: a prepared numerical E-Q table may be
  used for exploratory physical model discovery.

Consequently, E-Q search outputs are
`EXPLORATORY_NOT_MANUSCRIPT_ADMITTED`. They may identify candidate families,
but they may not be presented as a unique experimentally determined
Hamiltonian, a calibrated relative-intensity likelihood, or a formal
confidence interval. `MANUSCRIPT_ADMITTED` remains reserved for a future
provenance-qualified dataset and the manuscript objective is disabled.

Exchange is disabled. Historical 6.447, 18.2257, 27.896, and 44.4 meV values
are context only and are not hidden objective targets.

## Inputs

The fitter consumes numerical linear intensities, never PNG/JPEG pixels,
rendered colours, or logarithmic display values. Stage `01_data_audit`
deterministically materializes the user table from reviewed Stage02R A002/A003
plus the sealed B001 discovery representation; the user does not construct it
manually. The expected CSV schema is
[`schemas/taipan-eq-map-v1.schema.yaml`](../schemas/taipan-eq-map-v1.schema.yaml).
The generated local file is:

```text
local_data/taipan_eq_map_exploratory_v1.csv
```

`local_data/` is intentionally ignored by Git. Record the exact preparation
and normalization in every row. The audit records its SHA-256. If statistical
uncertainties are not calibrated, the reported objective is explicitly an
exploratory weighted loss, not chi-square.

The current temperature audit is fail-closed:

```text
TEN_K_BLOCK_STATUS = NOT_YET_ESTABLISHED
```

A002 does not select a uniquely verified sample-temperature channel, while
the legacy summary does not preserve exact 10-K scan membership. The bridge
therefore materializes 1,796 monitor-controlled discovery points for provenance review with
temperature-unresolved masks, but reports `NOT_READY`. No scan is classified
as 10 K from chronology. Update the reviewed mapping in
[`configs/taipan_prior_artifact_reuse_v1.yaml`](../configs/taipan_prior_artifact_reuse_v1.yaml)
only after deterministic evidence exists.
The exact evidence requirement and the CX-02 priority-scan metadata audit are
recorded in
[`docs/TAIPAN_TEMPERATURE_MAPPING_BLOCKER_V1.md`](TAIPAN_TEMPERATURE_MAPPING_BLOCKER_V1.md).

Before search, explicit feature-to-transition hypotheses must also be added.
B001 windows remain overlapping discovery regions and are not converted into
mandatory levels or assigned by nearest calculated energy.

Review [`configs/taipan_masks_exploratory_v1.yaml`](../configs/taipan_masks_exploratory_v1.yaml)
before search. Only the elastic mask and rows explicitly marked invalid are
active initially. Phonon, collective, detector, edge, and optional candidate
windows are disabled placeholders. The optimizer cannot modify masks.

The M(H) tables come exactly from commit
`2c17955c405ef9698781dfd5364ef7be0245ba15`. Available comparisons are
`H || a` and `H || b` at 10 and 20 K. The two c-axis curves remain
`AMBIGUOUS_CURVE_IDENTITY` and have no fabricated numerical points.
Experimental values retain `TOTAL_BULK_MAGNETIZATION` in emu/g and μB/f.u.;
the calculation is separately labelled `SINGLE_ION_DY_CEF_CONTRIBUTION` in
μB/Dy.

## Objective modes

- `FEATURE_OBJECTIVE`: extracted feature energies/areas, explicit assignment
  branches, and optional reviewed censoring.
- `EQ_MAP_EXPLORATORY_OBJECTIVE`: the prepared linear numerical E-Q table,
  with separate energy, spectral-shape, and exploratory relative-intensity
  residual classes.
- `MANUSCRIPT_OBJECTIVE`: reserved and disabled until provenance review.

The visible E-Q forward model is the sum of all positive-energy transitions
from thermally populated CEF doublets, the explicit TAS `kf/ki` factor, Dy3+
dipole form factor, single-crystal magnetic polarization, the 0.894-meV
empirical elastic-width baseline, a local linear nuisance background, and one
positive nuisance scale per declared A003 block. There is no silent powder
average and no per-scan optimizer rescaling. The elastic width is not a full
TAS resolution function and is not used to infer intrinsic linewidths.

The polarization tensor is explicitly transported and summed over the four
Pbnm Dy(4c) positions using the accepted Stage03R tensor contract. All four
sites share one reference-site CEF Hamiltonian; there are no independently
fitted site parameters. This is the reviewed localized independent-site sum,
not a coherent collective-mode calculation.

## VS Code setup

From the repository root:

```bash
python -m venv .venv
```

Activate the environment (`.venv\Scripts\activate` on Windows or
`source .venv/bin/activate` on Linux/macOS), then run:

```bash
python -m pip install -e ".[cef]"
python -m pytest -q
```

The canonical entrypoint is:

```bash
python -m cef_fit.user_pipeline STAGE --config configs/user_executed_joint_cef_pipeline_v1.yaml
```

## Copyable stage sequence

1. Materialize and audit the Stage02R bridge. It currently returns `NOT_READY`
   with the exact 10-K mapping blocker; after that provenance is reviewed it
   will return `READY_FOR_EXPLORATORY_SANITY_RUN`. The current command also
   writes a dataset-only diagnostic figure labelled temperature-unresolved,
   with no CEF overlay and no optimization:

   ```bash
   python -m cef_fit.user_pipeline 01_data_audit --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

2. Run a frozen historical-seed forward sanity check (no fitting):

   ```bash
   python -m cef_fit.user_pipeline 02_cef_forward --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

   This real experimental stage is intentionally blocked until the reviewed
   temperature mapping is present. Synthetic forward-model tests remain safe.

3. Inspect the objective decomposition (no optimization):

   ```bash
   python -m cef_fit.user_pipeline 03_ins_objective --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

4. This step is blocked now. Only after the temperature mapping is reviewed,
   and after inspecting the dataset, masks, forward model, objective, and
   explicit feature assignments,
   explicitly set both `switches.RUN_EXPLORATORY_SEARCH` and
   `search.run_exploratory_search` to `true` in the configuration. Then start
   the user-executed search:

   ```bash
   python -m cef_fit.user_pipeline 04_global_search --config configs/user_executed_joint_cef_pipeline_v1.yaml --enable-exploratory-search
   ```

5. Resume after interruption. Identity checks fail closed if the config,
   dataset, mask, objective mode, or code commit changed. A partially completed
   restart is repeated from its deterministic seed; completed restarts are not
   repeated:

   ```bash
   python -m cef_fit.user_pipeline 04_global_search --config configs/user_executed_joint_cef_pipeline_v1.yaml --enable-exploratory-search --resume
   ```

6. Retain the compatible ensemble without selecting one optimum:

   ```bash
   python -m cef_fit.user_pipeline 05_build_ins_ensemble --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

7. Calculate frozen single-ion M(H) at the exact literature field points:

   ```bash
   python -m cef_fit.user_pipeline 06_calculate_mh --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

8. Produce non-ranking M(H) shape/high-field diagnostics:

   ```bash
   python -m cef_fit.user_pipeline 07_compare_mh --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

9. Inspect the disabled future joint interface:

   ```bash
   python -m cef_fit.user_pipeline 08_joint_objective --config configs/user_executed_joint_cef_pipeline_v1.yaml
   ```

10. Cluster in parameter, energy, projector, neutron, g-tensor, and M(H)
    spaces using explicit weights:

    ```bash
    python -m cef_fit.user_pipeline 09_cluster_solutions --config configs/user_executed_joint_cef_pipeline_v1.yaml
    ```

11. Export all doublets, projectors, gauge-fixed coefficients, transition
    tensors/strengths, and g tensors for preliminary cluster medoids:

    ```bash
    python -m cef_fit.user_pipeline 10_export_wavefunctions --config configs/user_executed_joint_cef_pipeline_v1.yaml
    ```

12. Export canonical-Cs15 McPhase parameter files without running McPhase:

    ```bash
    python -m cef_fit.user_pipeline 11_export_mcphase --config configs/user_executed_joint_cef_pipeline_v1.yaml
    ```

13. After a separate visible McPhase run, provide a JSON mapping candidate IDs
    to objects containing `levels_meV` and, where exported by that run,
    `frame_axes`, canonical Hamiltonian real/imaginary matrices,
    `g_principal_values`, and `mh_muB_per_Dy`:

    ```bash
    python -m cef_fit.user_pipeline 12_validate_mcphase --config configs/user_executed_joint_cef_pipeline_v1.yaml --mcphase-levels path/to/user_mcphase_levels.json
    ```

McPhase disagreement never triggers automatic refitting. Check Stevens
convention, units, axes, normalization, and operator definitions first.

## Checkpoints and outputs

Local outputs go under `results/user_executed_joint_cef_pipeline_v1/`, which
is ignored by Git until the user deliberately reviews/materializes a result.
The search checkpoint records config, dataset and mask hashes; objective mode;
assignment; seed/restart; evaluations; retained candidates; Git commit; and
package versions. All external CMA-ES proposals are re-evaluated by the
project-owned forward model and objective.

The pipeline retains secondary minima. Clustering is based primarily on
observable equivalence, not only raw Blm distance. Preliminary medoids require
user scientific review before being called physical families.

## What may enter a paper now

The imported M(H) digitization and its explicit provenance/status may be cited
subject to normal review. The exploratory TAIPAN intensity search, its family
labels, and its loss values are not manuscript-admitted. No output becomes
manuscript-admitted merely by completing this pipeline; that requires a later
Project-Control provenance decision.

## Colab

Use [`notebooks/DyFeO3_joint_cef_fit_user_run.ipynb`](../notebooks/DyFeO3_joint_cef_fit_user_run.ipynb).
It is a thin frontend that invokes the same importable modules and stage
entrypoint. `RUN_EXPLORATORY_SEARCH = False` and
`ENABLE_JOINT_MH_FIT = False` are visible defaults.
