"""Bounded diagnostic reconstruction; never reads a holdout count source.

Run from the repository root. Requires the hash-pinned legacy Stage03A donor
in ~/Загрузки and NumPy/SciPy/pandas/PyYAML/matplotlib. Does not execute its main.
The V1 commit supplies group identities only; no V1 fitted parameter is reused.
"""
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import scipy

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
V1 = "415dd1751b7bf232476674af4e7e2571dd89a113"
B001 = ROOT / "04_Results/Stage02R/W02-02R-B-001"
DONOR = Path.home() / "Загрузки/20_taipan_confirmatory_profiles_colab.py"
DONOR_SHA = "09dd945c036a6f9286fc8c7fdcd905a75e73528f7b0ab54082f58ef82db5d9e1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(DONOR) == DONOR_SHA
    assert digest(B001 / "blind_split.csv") == "a7e1fc9979fefa781d393f352acb824dc2da7c205f08961c210afb1a2c0ee670"
    original = subprocess.check_output(
        ["git", "show", V1 + ":data/manuscript_v1/manuscript_observables.csv"], cwd=ROOT
    )
    assert hashlib.sha256(original).hexdigest() == "729814555eb250bc89b839ee5f89a9c94679d2e0b6518f7a4c7fa1fa07d9f9ce"
    rows = list(csv.DictReader(io.StringIO(original.decode())))
    rows = [r for r in rows if r["observable_type"] == "integrated_peak_area"]
    assert len(rows) == 46
    split = pd.read_csv(B001 / "blind_split.csv").set_index("scan_record_id")["split_role"].to_dict()
    # This input is already physically separated from holdout detector data.
    points = pd.read_csv(B001 / "discovery_point_representation.csv")
    assert set(points.split_role) == {"discovery"}
    assert all(split[s] == "discovery" for s in points.scan_record_id.unique())
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/manuscript-v2-mpl")
    spec = importlib.util.spec_from_file_location("legacy_stage03a_v2_donor", DONOR)
    donor = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = donor
    sys.dont_write_bytecode = True
    spec.loader.exec_module(donor)
    config = donor.Stage03AConfig(auto_mount_google_drive=False, make_figures=False, show_figures=False)
    spectra, membership, used_points = [], [], []
    for row in rows:
        ids = row["source_scan_id"].split(";")
        holdout = [s for s in ids if split[s] == "holdout"]
        unavailable = [s for s in ids if split[s] != "discovery" and s not in holdout]
        selected = [s for s in ids if split[s] == "discovery"] if not holdout else []
        record = dict(observation_id=row["observation_id"], original_source_scans=ids,
                      excluded_holdout_scans=holdout, excluded_non_discovery_scans=unavailable,
                      reconstruction_source_scans=selected,
                      instrument_block_id=row["instrument_block_id"],
                      original_detection_status=row["detection_status"],
                      recomputation_uses_only_open_scans=bool(selected),
                      new_area_independent_of_holdout_content=bool(selected),
                      legacy_area_independent_of_holdout_content=False)
        membership.append(record)
        if not selected:
            record["status"] = "EXCLUDE_HOLDOUT_CONTAMINATED" if holdout else "NO_OPEN_INPUT"
            continue
        part = points[points.scan_record_id.isin(selected)].copy()
        assert set(part.scan_record_id) == set(selected)
        # Rounded target and window set before the V2 fit; no archived fitted
        # centroid, width, background, area, or model-choice score enters.
        part = part[part.energy_transfer_meV.between(12.0, 24.0)].sort_values(
            ["energy_transfer_meV", "scan_record_id", "point_index"])
        assert len(part) >= config.min_points_per_profile
        assert np.isfinite(part[["energy_transfer_meV", "detector_counts", "monitor_counts"]]).all().all()
        assert (part.monitor_counts > 0).all() and (part.detector_counts >= 0).all()
        assert (part.exposure_type == "monitor_raw").all()
        part.insert(0, "observation_id", row["observation_id"])
        used_points.append(part)
        record["status"] = "RECONSTRUCTED_DISCOVERY_ONLY"
        record["fit_points"] = len(part)
        spectra.append(donor.SpectrumSlice(
            group_id=row["observation_id"], instrument_block_id=row["instrument_block_id"],
            temperature_block="UNRESOLVED", q_ainv=np.nan, temperature_K=np.nan,
            h_rlu=np.nan, k_rlu=np.nan, l_rlu=np.nan, source_scan_ids=";".join(selected),
            energy=part.energy_transfer_meV.to_numpy(), counts=part.detector_counts.to_numpy(),
            exposure=part.monitor_counts.to_numpy()/1e6,
            detector_variance=part.detector_counts.to_numpy()))
    assert len(spectra) == 30
    assert sum(bool(r["excluded_holdout_scans"]) for r in membership) == 16
    pd.concat(used_points).to_csv(OUT / "discovery_fit_points.csv", index=False)
    (OUT / "membership.json").write_text(json.dumps(membership, indent=2)+"\n")
    captures = {}
    original_ls = donor.least_squares
    original_cov = donor.safe_pseudoinverse_covariance
    def capture_ls(*args, **kwargs):
        fit = original_ls(*args, **kwargs)
        captures["fit"] = fit
        return fit
    def capture_cov(*args, **kwargs):
        covariance = original_cov(*args, **kwargs)
        captures["covariance"] = covariance
        return covariance
    donor.least_squares, donor.safe_pseudoinverse_covariance = capture_ls, capture_cov
    summaries, measurements = [], []
    for order in (0, 1, 2):
        summary, measurement, _ = donor.fit_simultaneous_feature_background(
            "F002_V2_DIAGNOSTIC", "targeted_reconstruction_not_blind_detection", 18.0, 2.5,
            spectra, order, config)
        fit, cov = captures["fit"], captures["covariance"]
        layout = donor.build_simultaneous_layout(spectra, order)
        sv = np.linalg.svd(fit.jac, compute_uv=False)
        summary["jacobian_rank"] = int(np.sum(sv > np.finfo(float).eps*max(fit.jac.shape)*sv[0]))
        summary["covariance_finite"] = bool(np.isfinite(cov).all())
        summary["optimality"] = float(fit.optimality)
        for i, row in measurement.iterrows():
            idx = layout.area_indices[row.spectrum_group_id]
            bg = list(range(layout.background_slices[row.spectrum_group_id].start,
                            layout.background_slices[row.spectrum_group_id].stop))
            corr = cov[idx,bg]/np.sqrt(cov[idx,idx]*np.diag(cov)[bg])
            measurement.loc[i,"area_background_max_abs_correlation"] = np.max(np.abs(corr))
            measurement.loc[i,"area_active_bound"] = int(fit.active_mask[idx])
            measurement.loc[i,"area_sigma_from_covariance"] = np.sqrt(max(cov[idx,idx],0))
            measurement.loc[i,"center_active_bound"] = int(fit.active_mask[layout.center_index])
            measurement.loc[i,"width_active_bound"] = int(fit.active_mask[layout.width_indices[row.instrument_block_id]])
        np.save(OUT / f"covariance_order{order}.npy", cov, allow_pickle=False)
        (OUT / f"parameters_order{order}.json").write_text(json.dumps({
            "theta":fit.x.tolist(),"active_mask":fit.active_mask.tolist(),
            "center_index":layout.center_index,"width_indices":layout.width_indices,
            "area_indices":layout.area_indices,
            "background_indices":{k:list(range(v.start,v.stop)) for k,v in layout.background_slices.items()}
        },indent=2)+"\n")
        summaries.append(summary)
        measurements.append(measurement)
        print(json.dumps(summary),flush=True)
    valid = [s for s in summaries if s["success"] and s["covariance_finite"]]
    assert valid
    selected = min(valid,key=lambda r:r["bic"])["background_order"]
    pd.concat(measurements).to_csv(OUT / "all_background_measurements.csv",index=False)
    (OUT / "fit_summary.json").write_text(json.dumps({
        "status":"DIAGNOSTIC_ONLY", "selected_background_order":selected,
        "background_fits":summaries,"center_initial_meV":18.0,"window_meV":[12.0,24.0],
        "fwhm_initial_meV":2.5,"energy_systematic_meV":None,
        "native_energy_points_used":True,"coaddition":False,
        "scipy_version":scipy.__version__,"numpy_version":np.__version__,
        "python_version":sys.version,"donor_sha256":DONOR_SHA,
        "count_source_sha256":digest(B001 / "discovery_point_representation.csv"),
        "holdout_detector_access_count":0,
        "selection_caveat":"Legacy group identities and target choice retained; this is not a new blind discovery or independent validation."
    },indent=2)+"\n")


if __name__ == "__main__":
    main()
