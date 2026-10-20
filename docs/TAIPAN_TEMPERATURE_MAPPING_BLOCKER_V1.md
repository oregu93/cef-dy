# TAIPAN temperature-mapping blocker v1

## Decision

The Stage02R bridge is deterministically materialized, but it is **not ready
for a real experimental CEF forward/objective/search run**. No reviewed input
maps exact scans to a verified sample temperature. In particular, the five
CX-02 priority scans cannot currently be labelled 10 K.

The blocker is deliberately narrow:

```text
TEN_K_BLOCK_STATUS = NOT_YET_ESTABLISHED
TEN_K_SCAN_COUNT = 0
TEMPERATURE_SUMMARY_K = null
NEXT_REAL_EXPERIMENTAL_STAGE = BLOCKED
```

A002 preserves `ptsamp`, `tfloat`, `temp`, four `T1_Sensor*` channels and four
`T1_Setpoint*` channels for these scans. Their units and physical meanings are
unresolved, so the semantic report records
`selection_status = no_unique_sensor_or_unit_selected`. Acquisition chronology
is provenance only and is not used to infer temperature.

## CX-02 priority-scan preflight

The full machine-readable audit is
[`configs/taipan_cx02_priority_scan_preflight_v1.yaml`](../configs/taipan_cx02_priority_scan_preflight_v1.yaml).
It uses metadata and already reviewed B001 results only; no detector
reanalysis, feature refit, or CEF fit was performed.

| raw scan | scan record | role | E range (meV) | computed Q range (Å⁻¹) | frozen B001 relation |
|---:|---|---|---:|---:|---|
| 104095 | `SCAN-02R-8dcd5041a8a4e044` | discovery | 0.9986–24.9983 | 3.034236–3.034515 | BF-004 tier-1 support |
| 104098 | `SCAN-02R-731f452fb62a55bd` | discovery | 0.9984–24.9983 | 3.359770–3.360008 | BF-004 tier-1 support |
| 104099 | `SCAN-02R-8641a638f4880175` | discovery | 0.9986–24.9983 | 2.980200–2.980439 | BF-004 tier-1 support |
| 104215 | `SCAN-02R-75faa4a614a8f130` | discovery | −0.0014–24.9982 | 3.243713–3.243976 | BF-005 tier-1 support |
| 104225 | `SCAN-02R-f56f915bc229d6aa` | discovery | −0.0007–24.9983 | 3.625701–3.625957 | BF-005 tier-1 support |

All five are monitor-controlled, B001 `discovery_usable`, and members of
`NORMCOMP-02R-26ed32e42105dda7`. The Q trajectories are recalculated from each
A002 per-point Pbnm HKL and its assigned lattice state; raw `q` is not treated
as an authoritative magnitude. BF-004 and BF-005 jointly define frozen CX-02
over 17.49800–20.49835 meV, but neither is a mandatory CEF level.

## Exact evidence needed to unblock

Supply one reviewed, version-controlled temperature mapping whose rows contain:

- exact `scan_record_id` and `raw_scan_id` membership;
- sample temperature in kelvin and an allowed tolerance/range;
- the selected raw sensor field, its verified unit and its physical binding to
  sample temperature;
- source artifact path and immutable checksum;
- review status and limitation statement.

For the five priority scans, the next evidence source is the original
`TAIPAN_exp1296_scan*.dat` environment metadata identified by the checksums in
the preflight YAML, interpreted against instrument/sample-environment records
that can identify the physical sensor and unit. A chronology-only mapping or a
remembered block boundary is insufficient.

Once that evidence is reviewed, update only the `temperature_mapping` section
of `configs/taipan_prior_artifact_reuse_v1.yaml` with the exact
`scan_record_id` list and verified temperature. The materializer will then
emit explicit values and the audit can independently decide readiness.

## Safe commands while blocked

- Stage `01_data_audit` materialization/audit and its dataset-only diagnostic
  figure are safe.
- Unit tests and synthetic forward-model tests are safe.
- Frozen historical-seed calculations that do not use the unresolved
  experimental temperature mapping are safe.
- Real experimental stages `02_cef_forward`, `03_ins_objective`, and
  `04_global_search` remain blocked. Production fitting remains forbidden.

The dataset diagnostic deliberately says “temperature unresolved”, contains
no calculated CEF overlay, and does not label the dataset 10 K.
