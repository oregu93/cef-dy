"""Holdout-clean centroid robustness grid for MANUSCRIPT_CEF_FIT_V1.

This reads only the frozen B001 discovery count representation. Profile
membership comes from the reviewed V2 reconstruction. Per-profile amplitudes
are independent nonnegative nuisance parameters; no relative intensity model
is imposed. Historical/literature energies are not read by this program.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import chi2
import scipy

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
V2 = OUT.parent / "recovery_v2"
B001 = ROOT / "04_Results/Stage02R/W02-02R-B-001"
DONOR = Path.home() / "Загрузки/20_taipan_confirmatory_profiles_colab.py"
DONOR_SHA = "09dd945c036a6f9286fc8c7fdcd905a75e73528f7b0ab54082f58ef82db5d9e1"
SPLIT_SHA = "a7e1fc9979fefa781d393f352acb824dc2da7c205f08961c210afb1a2c0ee670"
POINTS_SHA = "e8f1f0298df74b1948804614ac43ec4580f333d87ad8c68b610acc3933c97b21"
WINDOWS = (5.0, 6.0, 7.0)
BACKGROUND_ORDERS = (0, 1, 2)
WIDTH_MODES = ("shared", "per_block")
STARTS = ((17.5, 2.0), (18.0, 2.5), (18.5, 3.0))
CENTER_BOUNDS = (16.75, 19.25)
WIDTH_BOUNDS = (0.65, 8.0)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


os.environ.setdefault("MPLCONFIGDIR", "/tmp/manuscript-energy-v1-mpl")
spec = importlib.util.spec_from_file_location("energy_v1_donor", DONOR)
donor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = donor
sys.dont_write_bytecode = True
spec.loader.exec_module(donor)


@dataclass
class Layout:
    center_indices: dict[str, int]
    width_indices: dict[str, int]
    background_slices: dict[str, slice]
    area_indices: dict[str, int]
    n_parameters: int


def build_layout(spectra, background_order, width_mode, center_mode):
    blocks = sorted({s.instrument_block_id for s in spectra})
    cursor = 0
    center_keys = ["shared"] if center_mode == "shared" else blocks
    center_indices = {}
    for key in center_keys:
        center_indices[key] = cursor
        cursor += 1
    width_keys = ["shared"] if width_mode == "shared" else blocks
    width_indices = {}
    for key in width_keys:
        width_indices[key] = cursor
        cursor += 1
    background_slices, area_indices = {}, {}
    for spectrum in spectra:
        background_slices[spectrum.group_id] = slice(cursor, cursor + background_order + 1)
        cursor += background_order + 1
        area_indices[spectrum.group_id] = cursor
        cursor += 1
    return Layout(center_indices, width_indices, background_slices, area_indices, cursor)


def key_for(spectrum, mode):
    return "shared" if mode == "shared" else spectrum.instrument_block_id


def expected_counts(theta, spectra, layout, half_window, width_mode, center_mode):
    expected = []
    for spectrum in spectra:
        center = float(theta[layout.center_indices[key_for(spectrum, center_mode)]])
        width = float(theta[layout.width_indices[key_for(spectrum, width_mode)]])
        coefficients = theta[layout.background_slices[spectrum.group_id]]
        x = (spectrum.energy - 18.0) / half_window
        intensity = donor.positive_background(coefficients, x)
        intensity += float(theta[layout.area_indices[spectrum.group_id]]) * donor.gaussian_unit_area(
            spectrum.energy, center, width
        )
        expected.append(np.maximum(spectrum.exposure * intensity, 1e-12))
    return expected


def residuals(theta, spectra, layout, half_window, width_mode, center_mode):
    expected = expected_counts(theta, spectra, layout, half_window, width_mode, center_mode)
    return np.concatenate([
        donor.poisson_deviance_residual(s.counts, mu) for s, mu in zip(spectra, expected)
    ])


def initialize(spectra, layout, half_window, order, center_start, width_start, width_mode, center_mode):
    theta = np.zeros(layout.n_parameters)
    lower = np.full(layout.n_parameters, -np.inf)
    upper = np.full(layout.n_parameters, np.inf)
    for index in layout.center_indices.values():
        theta[index] = center_start
        lower[index], upper[index] = CENTER_BOUNDS
    for index in layout.width_indices.values():
        theta[index] = width_start
        lower[index], upper[index] = WIDTH_BOUNDS
    for spectrum in spectra:
        coefficients, area = donor.initial_background_and_area(
            spectrum, center_start, width_start, half_window, order
        )
        bg = layout.background_slices[spectrum.group_id]
        theta[bg] = coefficients
        lower[bg.start], upper[bg.start] = -30.0, 30.0
        if order:
            lower[bg.start + 1:bg.stop] = -8.0
            upper[bg.start + 1:bg.stop] = 8.0
        ai = layout.area_indices[spectrum.group_id]
        theta[ai] = max(area, 1e-6)
        lower[ai], upper[ai] = 0.0, np.inf
    return theta, lower, upper


def fit_one(spectra, half_window, order, width_mode, center_mode, model_id):
    layout = build_layout(spectra, order, width_mode, center_mode)
    starts = []
    for center_start, width_start in STARTS:
        theta, lower, upper = initialize(
            spectra, layout, half_window, order, center_start, width_start, width_mode, center_mode
        )
        fit = least_squares(
            residuals, theta, bounds=(lower, upper),
            args=(spectra, layout, half_window, width_mode, center_mode), method="trf",
            x_scale="jac", max_nfev=5000, ftol=1e-10, xtol=1e-10, gtol=1e-10
        )
        r = residuals(fit.x, spectra, layout, half_window, width_mode, center_mode)
        starts.append((float(r @ r), fit, center_start, width_start))
    starts.sort(key=lambda item: item[0])
    deviance, fit, best_center_start, best_width_start = starts[0]
    n_points = sum(len(s.energy) for s in spectra)
    dof = max(n_points - layout.n_parameters, 1)
    overdispersion = max(deviance / dof, 1.0)
    covariance = donor.safe_pseudoinverse_covariance(fit.jac, overdispersion)
    errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    singular = np.linalg.svd(fit.jac, compute_uv=False)
    rank = int(np.sum(singular > np.finfo(float).eps * max(fit.jac.shape) * singular[0]))
    centers = {key: float(fit.x[idx]) for key, idx in layout.center_indices.items()}
    center_sigma = {key: float(errors[idx]) for key, idx in layout.center_indices.items()}
    widths = {key: float(fit.x[idx]) for key, idx in layout.width_indices.items()}
    width_sigma = {key: float(errors[idx]) for key, idx in layout.width_indices.items()}
    start_centers = []
    for d, f, cs, ws in starts:
        start_centers.append({
            "center_start_meV": cs, "width_start_meV": ws, "deviance": d,
            "centers_meV": {key: float(f.x[idx]) for key, idx in layout.center_indices.items()},
            "success": bool(f.success), "status": int(f.status)
        })
    expected = expected_counts(fit.x, spectra, layout, half_window, width_mode, center_mode)
    active_areas = sum(int(fit.active_mask[idx] != 0) for idx in layout.area_indices.values())
    summary = {
        "model_id": model_id, "half_window_meV": half_window,
        "window_meV": [18.0-half_window, 18.0+half_window],
        "background_order": order, "width_mode": width_mode, "center_mode": center_mode,
        "blocks": sorted({s.instrument_block_id for s in spectra}),
        "n_profiles": len(spectra), "n_scans": len({i for s in spectra for i in s.source_scan_ids.split(';')}),
        "n_points": n_points, "n_parameters": layout.n_parameters, "dof": dof,
        "deviance": deviance, "reduced_deviance": deviance/dof,
        "aic": deviance + 2*layout.n_parameters,
        "aicc": deviance + 2*layout.n_parameters + 2*layout.n_parameters*(layout.n_parameters+1)/max(n_points-layout.n_parameters-1,1),
        "bic": deviance + math.log(n_points)*layout.n_parameters,
        "success": bool(fit.success), "optimizer_status": int(fit.status),
        "optimizer_message": str(fit.message), "nfev": int(fit.nfev),
        "optimality": float(fit.optimality), "jacobian_rank": rank,
        "covariance_finite": bool(np.isfinite(covariance).all()),
        "centers_meV": centers, "center_sigma_stat_meV": center_sigma,
        "widths_meV": widths, "width_sigma_stat_meV": width_sigma,
        "active_area_bounds": active_areas,
        "best_start": [best_center_start, best_width_start], "starts": start_centers,
        "max_start_center_spread_meV": float(max(
            max(values)-min(values) for values in zip(*[list(x["centers_meV"].values()) for x in start_centers])
        )),
        "valid": bool(fit.success and np.isfinite(covariance).all() and rank == layout.n_parameters and
                      all(CENTER_BOUNDS[0] < v < CENTER_BOUNDS[1] for v in centers.values()) and
                      all(WIDTH_BOUNDS[0] < v < WIDTH_BOUNDS[1] for v in widths.values()) and
                      deviance/dof < 2.0),
        "counts_sum": float(sum(s.counts.sum() for s in spectra)),
        "expected_sum": float(sum(mu.sum() for mu in expected)),
    }
    parameter_record = {
        "theta": fit.x.tolist(), "active_mask": fit.active_mask.tolist(),
        "center_indices": layout.center_indices, "width_indices": layout.width_indices,
        "background_indices": {k:list(range(v.start,v.stop)) for k,v in layout.background_slices.items()},
        "area_indices": layout.area_indices,
    }
    return summary, covariance, parameter_record


def build_spectra(half_window, blocks=None):
    membership = json.loads((V2 / "membership.json").read_text())
    open_members = [m for m in membership if m["reconstruction_source_scans"]]
    if blocks is not None:
        open_members = [m for m in open_members if m["instrument_block_id"] in blocks]
    points = pd.read_csv(B001 / "discovery_point_representation.csv")
    spectra = []
    used = []
    for member in open_members:
        ids = member["reconstruction_source_scans"]
        part = points[points.scan_record_id.isin(ids)].copy()
        assert set(part.scan_record_id) == set(ids)
        part = part[part.energy_transfer_meV.between(18.0-half_window, 18.0+half_window)].sort_values(
            ["energy_transfer_meV", "scan_record_id", "point_index"]
        )
        assert len(part) >= 9
        assert set(part.split_role) == {"discovery"}
        assert (part.exposure_type == "monitor_raw").all()
        used.append(part.assign(observation_id=member["observation_id"]))
        spectra.append(donor.SpectrumSlice(
            group_id=member["observation_id"], instrument_block_id=member["instrument_block_id"],
            temperature_block="UNRESOLVED", q_ainv=np.nan, temperature_K=np.nan,
            h_rlu=np.nan, k_rlu=np.nan, l_rlu=np.nan,
            source_scan_ids=";".join(ids), energy=part.energy_transfer_meV.to_numpy(),
            counts=part.detector_counts.to_numpy(), exposure=part.monitor_counts.to_numpy()/1e6,
            detector_variance=part.detector_counts.to_numpy()
        ))
    return spectra, pd.concat(used, ignore_index=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert digest(DONOR) == DONOR_SHA
    assert digest(B001 / "blind_split.csv") == SPLIT_SHA
    assert digest(B001 / "discovery_point_representation.csv") == POINTS_SHA
    split = pd.read_csv(B001 / "blind_split.csv").set_index("scan_record_id").split_role
    membership = json.loads((V2 / "membership.json").read_text())
    source_scans = sorted({s for m in membership for s in m["reconstruction_source_scans"]})
    assert len(source_scans) == 45 and all(split[s] == "discovery" for s in source_scans)
    blocks = sorted({m["instrument_block_id"] for m in membership if m["reconstruction_source_scans"]})
    records, separate_records, block_records = [], [], []
    covariances, parameters = {}, {}
    for half_window in WINDOWS:
        spectra, used = build_spectra(half_window)
        used.to_csv(OUT / f"fit_points_window_{half_window:.1f}.csv", index=False)
        for order in BACKGROUND_ORDERS:
            for width_mode in WIDTH_MODES:
                model_id = f"joint_w{half_window:.1f}_b{order}_{width_mode}"
                record, cov, par = fit_one(spectra, half_window, order, width_mode, "shared", model_id)
                records.append(record); covariances[model_id]=cov; parameters[model_id]=par
            model_id = f"separate_centers_w{half_window:.1f}_b{order}_per_block"
            record, cov, par = fit_one(spectra, half_window, order, "per_block", "per_block", model_id)
            separate_records.append(record); covariances[model_id]=cov; parameters[model_id]=par
        for block in blocks:
            block_spectra, _ = build_spectra(half_window, {block})
            for order in BACKGROUND_ORDERS:
                model_id = f"block_{block}_w{half_window:.1f}_b{order}"
                record, cov, par = fit_one(block_spectra, half_window, order, "shared", "shared", model_id)
                block_records.append(record); covariances[model_id]=cov; parameters[model_id]=par
        print(f"completed half_window={half_window}", flush=True)
    # Comparable nested pairs: common vs block-specific centroid, both per-block width.
    common_by_key={(r["half_window_meV"],r["background_order"]):r for r in records if r["width_mode"]=="per_block"}
    lrt=[]
    for r in separate_records:
        common=common_by_key[(r["half_window_meV"],r["background_order"])]
        delta=max(common["deviance"]-r["deviance"],0.0)
        lrt.append({"half_window_meV":r["half_window_meV"],"background_order":r["background_order"],
                    "common_model_id":common["model_id"],"separate_model_id":r["model_id"],
                    "delta_deviance":delta,"degrees_of_freedom":1,"p_value":float(chi2.sf(delta,1)),
                    "block_centers_meV":r["centers_meV"],"block_sigma_stat_meV":r["center_sigma_stat_meV"]})
    # Save exact numerical state. npz keys replace punctuation deterministically.
    np.savez_compressed(OUT / "covariances.npz", **{k.replace('.','p'):v for k,v in covariances.items()})
    (OUT / "parameters.json").write_text(json.dumps(parameters, indent=2)+"\n")
    (OUT / "model_grid.json").write_text(json.dumps({
        "task":"HOLDOUT_CLEAN_ENERGY_ADMISSION_V1", "base_commit":"dc339abbc70b0e355c7e27beada8474d1af0ba5a",
        "grid_policy":{"background_orders":BACKGROUND_ORDERS,"half_windows_meV":WINDOWS,
                       "width_modes":WIDTH_MODES,"starts":STARTS,"center_bounds_meV":CENTER_BOUNDS,
                       "width_bounds_meV":WIDTH_BOUNDS,
                       "selection":"No comparator energy enters fitting or model validity. All valid joint models form the sensitivity ensemble."},
        "joint_shared_centroid_models":records,"joint_separate_centroid_models":separate_records,
        "single_block_models":block_records,"common_vs_separate_center_lrt":lrt,
        "source_scan_ids":source_scans,"source_scan_count":len(source_scans),
        "profile_count":30,"holdout_detector_access_count":0,
        "donor_sha256":DONOR_SHA,"split_sha256":SPLIT_SHA,"count_source_sha256":POINTS_SHA,
        "runtime":{"python":sys.version,"numpy":np.__version__,"scipy":scipy.__version__}
    },indent=2)+"\n")
    # Flat reviewer table.
    flat=[]
    for family, items in [("joint_shared_centroid",records),("joint_separate_centroid",separate_records),("single_block",block_records)]:
        for r in items:
            for key,center in r["centers_meV"].items():
                flat.append({"family":family,"model_id":r["model_id"],"center_key":key,
                             "center_meV":center,"stat_sigma_meV":r["center_sigma_stat_meV"][key],
                             "half_window_meV":r["half_window_meV"],"background_order":r["background_order"],
                             "width_mode":r["width_mode"],"n_profiles":r["n_profiles"],
                             "n_scans":r["n_scans"],"n_points":r["n_points"],"deviance":r["deviance"],
                             "reduced_deviance":r["reduced_deviance"],"aicc":r["aicc"],"bic":r["bic"],
                             "valid":r["valid"],"max_start_center_spread_meV":r["max_start_center_spread_meV"]})
    pd.DataFrame(flat).to_csv(OUT / "model_grid.csv", index=False)
    print(json.dumps({"joint_models":len(records),"separate_models":len(separate_records),
                      "single_block_models":len(block_records),
                      "valid_joint_models":sum(r["valid"] for r in records)},indent=2))


if __name__ == "__main__":
    main()
