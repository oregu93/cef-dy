"""Materialize V2 admission decisions from discovery-only reconstruction.

Metadata from mixed tables is read with an explicit column whitelist excluding
detector/monitor counts. The original table and manifest remain in the V1 commit.
Run after reconstruct.py from any working directory.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = OUT.parent
V1 = "415dd1751b7bf232476674af4e7e2571dd89a113"
A002 = ROOT / "04_Results/Stage02R/W02-02R-A-002"
CHECKPOINT = ROOT / "04_Results/Stage03R/STAGE03R-R2-SCIENTIFIC-CHECKPOINT-MATERIALIZATION-001/CHECKPOINT.yaml"


def old_bytes(name):
    return subprocess.check_output(["git", "show", f"{V1}:data/manuscript_v1/{name}"], cwd=ROOT)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    membership = json.loads((OUT / "membership.json").read_text())
    by_id = {r["observation_id"]:r for r in membership}
    ids = {s for r in membership for s in r["reconstruction_source_scans"]}
    headers = {j["scan_record_id"]:j["canonical_header_mappings"] for j in
               map(json.loads,(A002 / "parsed_header_metadata.jsonl").open())}
    # Explicit metadata-only reads: detector fields are never selected.
    cols = ["scan_record_id","point_index","q_raw","h_raw","k_raw","l_raw","ei_raw","ef_raw","S2_raw"]
    geometry = pd.read_csv(A002 / "scan_points.csv", usecols=cols)
    geometry = geometry[geometry.scan_record_id.isin(ids)].copy()
    q_checks = []
    for sid, g in geometry.groupby("scan_record_id"):
        h = headers[sid]
        cell = np.array(list(map(float,h["latticeconstants"]["values"][0].split())))
        assert np.array_equal(cell[3:], [90.,90.,90.])
        lat = cell[:3]
        ub = np.array(list(map(float,h["ubmatrix"]["values"][0].split()))).reshape(3,3)
        v = g[["h_raw","k_raw","l_raw"]].to_numpy()
        q = 2*np.pi*np.linalg.norm(v/lat,axis=1)
        q_ub = 2*np.pi*np.linalg.norm(v@ub.T,axis=1)
        q_kin = np.sqrt((g.ei_raw+g.ef_raw-2*np.sqrt(g.ei_raw*g.ef_raw)*
                         np.cos(np.deg2rad(g.S2_raw)))/2.072124855)
        # Source precision: four decimal h,k,l,q; six decimal cell parameters.
        lo = 2*np.pi*np.linalg.norm(np.maximum(abs(v)-.00005,0)/(lat+.0000005),axis=1)
        hi = 2*np.pi*np.linalg.norm((abs(v)+.00005)/(lat-.0000005),axis=1)
        failures = int(((g.q_raw+.00005<lo)|(g.q_raw-.00005>hi)).sum())
        geometry.loc[g.index,"Q_from_hkl_Ainv"] = q
        geometry.loc[g.index,"Q_from_UB_Ainv"] = q_ub
        geometry.loc[g.index,"Q_from_geometry_Ainv"] = q_kin
        for axis,values in zip("XYZ",(2*np.pi*v[:,1]/lat[1],2*np.pi*v[:,2]/lat[2],2*np.pi*v[:,0]/lat[0])):
            geometry.loc[g.index,f"Q_CEF_{axis}_Ainv"] = values
        q_checks.append(dict(scan_record_id=sid,n_points=len(g),rounding_interval_failures=failures,
                             max_abs_raw_q_minus_hkl=float(max(abs(g.q_raw-q))),
                             max_abs_raw_q_minus_UB=float(max(abs(g.q_raw-q_ub))),
                             max_abs_raw_q_minus_geometry=float(max(abs(g.q_raw-q_kin))),
                             status="VERIFIED_HKL_AND_Q" if failures==0 else "AMBIGUOUS"))
    assert all(r["rounding_interval_failures"]==0 for r in q_checks)
    geometry.to_csv(OUT / "open_scan_geometry.csv",index=False)
    pd.DataFrame(q_checks).to_csv(OUT / "q_semantics_checks.csv",index=False)
    inventory = pd.read_csv(A002 / "scan_inventory.csv",usecols=["scan_record_id","raw_scan_id","source_checksum"])
    raw_ids = inventory.set_index("scan_record_id").raw_scan_id.astype(str).to_dict()
    legacy_cols = ["scan_id","source_sha256","temperature_min_K","temperature_max_K",
                   "temperature_median_K","temperature_source_column","instrument_block_id",
                   "monochromator","analyzer","collimation","preset_type","preset_channel",
                   "preset_value","latticeconstants_raw","ubmatrix_raw"]
    legacy_path = Path.home()/"Загрузки/DyFeO3_TAIPAN_scan_inventory.csv"
    assert sha(legacy_path)=="e23b01ee3c51ffe79fd287be59fd5b3ae85ea44427b4498fa3fed7d25d403853"
    legacy = pd.read_csv(legacy_path, usecols=legacy_cols,
                         dtype={"scan_id":str}).set_index("scan_id")
    for sid in ids:
        assert inventory.set_index("scan_record_id").loc[sid,"source_checksum"] == legacy.loc[raw_ids[sid],"source_sha256"]
    summary = json.loads((OUT / "fit_summary.json").read_text())
    fits = pd.read_csv(OUT / "all_background_measurements.csv")
    selected = fits[fits.background_order==summary["selected_background_order"]].set_index("spectrum_group_id")
    fit_global = summary["background_fits"][summary["selected_background_order"]]
    rows = list(csv.DictReader(io.StringIO(old_bytes("manuscript_observables.csv").decode())))
    fields = list(rows[0])+["original_recovery_status","original_likelihood_role","original_detection_status",
                           "v2_admission_decision","v2_reason","holdout_clean_status","q_status",
                           "temperature_status","legacy_temp_channel_value","excluded_holdout_scans",
                           "reconstruction_source_scans","v2_diagnostic_area","v2_diagnostic_sigma",
                           "v2_diagnostic_z","v2_peak_quality_pass"]
    decisions=[]
    for row in rows:
        row.update(original_recovery_status=row["provenance_status"],original_likelihood_role=row["likelihood_role"],
                   original_detection_status=row["detection_status"],v2_admission_decision="UNCHANGED_CONTEXT_ONLY",
                   v2_reason="Outside intensity recovery population; no new scientific admission.",
                   holdout_clean_status="NOT_APPLICABLE")
        oid=row["observation_id"]
        if oid=="TAIPAN-F002-ENERGY-AGGREGATE":
            row.update(likelihood_role="EXCLUDED_FROM_BASELINE_LIKELIHOOD",
                       v2_admission_decision="HISTORICAL_AGGREGATE_ONLY",
                       v2_reason="V1 shared centroid contains holdout contribution; retained as history, not used by V2.",
                       holdout_clean_status="HOLDOUT_CONTAMINATED")
        if oid not in by_id:
            continue
        m=by_id[oid]
        row.update(likelihood_role="EXCLUDED_FROM_BASELINE_LIKELIHOOD",temperature_status="UNKNOWN",
                   legacy_temp_channel_value=re.search(r"legacy_temp_channel=([^;]+)",row["notes"])[1],
                   excluded_holdout_scans=";".join(m["excluded_holdout_scans"]),
                   reconstruction_source_scans=";".join(m["reconstruction_source_scans"]))
        # Historical fields are kept byte-value-equivalent; all new estimates
        # have explicit V2 names, never silently replace old fitted areas.
        if m["excluded_holdout_scans"]:
            row.update(v2_admission_decision="HOLDOUT_CONTAMINATED",v2_reason="EXCLUDE_HOLDOUT_CONTAMINATED; whole group excluded; no subtraction or backfill.",
                       holdout_clean_status="HOLDOUT_CONTAMINATED",q_status="AMBIGUOUS")
        else:
            f=selected.loc[oid]
            good=bool(fit_global["success"] and fit_global["covariance_finite"] and
                      fit_global["jacobian_rank"]==fit_global["n_parameters"] and
                      fit_global["reduced_deviance"]<2 and np.isfinite(f.area_sigma_from_covariance) and
                      f.area_sigma_from_covariance>0 and f.area_per_1e6_monitor_meV>0 and
                      f.area_z>=3 and f.area_active_bound==0 and f.center_active_bound==0 and
                      f.width_active_bound==0 and .65<f.fwhm_observed_meV<8 and
                      12<f.center_meV<24 and f.area_background_max_abs_correlation<.95)
            collapse=bool(f.area_active_bound!=0 or f.area_per_1e6_monitor_meV<=1e-8)
            decision="FIT_COLLAPSE" if collapse else "NORMALIZATION_AMBIGUOUS" if good else "OTHER_EXCLUSION"
            reason=("Area is on the nonnegative bound or <=1e-8; no Gaussian detected-area likelihood." if collapse else
                    "Peak-quality checks pass, but one scale per block cannot be established from instrument-response provenance." if good else
                    "Does not meet independent detected-peak quality rule; no intensity admission.")
            g=geometry[geometry.scan_record_id.isin(m["reconstruction_source_scans"])]
            row.update(v2_admission_decision=decision,v2_reason=reason,
                       holdout_clean_status="V2_RECONSTRUCTION_CLEAN_LEGACY_FIT_NOT_CLEAN",q_status="VERIFIED_HKL_AND_Q",
                       v2_diagnostic_area=str(f.area_per_1e6_monitor_meV),v2_diagnostic_sigma=str(f.area_sigma_stat_per_1e6_monitor_meV),
                       v2_diagnostic_z=str(f.area_z),v2_peak_quality_pass=str(good).lower(),
                       h_pbnm=str(g.h_raw.median()),k_pbnm=str(g.k_raw.median()),l_pbnm=str(g.l_raw.median()),
                       Q_Ainv=str(g.Q_from_hkl_Ainv.median()))
        row["notes"] += "; V2 supersedes V1 admission labels; original numeric areas remain historical; see recovery_v2/ADMISSION_REVIEW.md."
        decisions.append({k:row.get(k,"") for k in ["observation_id","instrument_block_id","source_scan_id",
                          "original_detection_status","v2_admission_decision","v2_reason","holdout_clean_status",
                          "q_status","temperature_status","excluded_holdout_scans","reconstruction_source_scans",
                          "v2_diagnostic_area","v2_diagnostic_sigma","v2_diagnostic_z","v2_peak_quality_pass"]})
    with (DATA/"manuscript_observables.csv").open("w",newline="") as out:
        w=csv.DictWriter(out,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
    pd.DataFrame(decisions).to_csv(OUT/"row_admission.csv",index=False)
    blocks={}
    for block in sorted({m["instrument_block_id"] for m in membership}):
        bm=[m for m in membership if m["instrument_block_id"]==block]
        bs={s for m in bm for s in m["reconstruction_source_scans"]}
        g=geometry[geometry.scan_record_id.isin(bs)]
        l=legacy.loc[[raw_ids[s] for s in sorted(bs)]]
        blocks[block]={"status":"NOT_ADMISSIBLE","admitted_rows":0,"original_profiles":len(bm),
                       "reconstructed_profiles":sum(bool(m["reconstruction_source_scans"]) for m in bm),
                       "open_scans":len(bs),"quality_passing_rows":[r["observation_id"] for r in decisions if
                         r["instrument_block_id"]==block and r.get("v2_peak_quality_pass")=="true"],
                       "raw_temp_channel_range":[float(l.temperature_min_K.min()),float(l.temperature_max_K.max())],
                       "Ef_meV_range":[float(g.ef_raw.min()),float(g.ef_raw.max())],
                       "kf_Ainv_range":[float(math.sqrt(g.ef_raw.min()/2.072124855)),float(math.sqrt(g.ef_raw.max()/2.072124855))],
                       "recorded_invariants":{k:sorted(map(str,l[k].unique())) for k in
                           ["monochromator","analyzer","collimation","preset_type","preset_channel","latticeconstants_raw","ubmatrix_raw"]},
                       "preset_values":sorted(map(float,l.preset_value.unique())),
                       "missing_field_classification":{
                         "absolute_cross_section_scale":"NOT_APPLICABLE",
                         "overall_block_scale_A_b":"CONSTANT_BUT_VALUE_UNKNOWN",
                         "detector_monitor_hardware_gain_invariance":"UNRESOLVED",
                         "filter_higher_order_suppression_invariance":"UNRESOLVED",
                         "attenuator_invariance":"UNRESOLVED",
                         "focusing_aperture_state":"UNRESOLVED",
                         "Q_dependent_resolution_acceptance":"MATERIAL_FOR_RELATIVE_INTENSITY"},
                       "reason":"Unknown constant calibration is absorbable by A_b; scan invariance of response/acceptance is not demonstrated. Missing state is not evidence of a constant state."}
    thermal={}
    for gap in [18.24717836149484,6.447,1.0]:
        z=[math.exp(-gap/(.08617333262*t)) for t in [3.4,10.0]]
        p=[1/(1+x) for x in z]
        thermal[str(gap)]={"gap_meV":gap,"T_K_sensitivity_values":[3.4,10.0],
                            "excited_to_ground_equal_doublet_population":z,"two_doublet_ground_population":p,
                            "relative_ground_population_change":1-p[1]/p[0]}
    result={"task":"MANUSCRIPT_INTENSITY_ADMISSION_RECOVERY_V2","mode":"BOUNDED_SALVAGE_ONLY",
            "manuscript_intensity_gate":"FAIL_CLEANLY","W03_allowed_objective_ceiling":"ENERGY_ONLY",
            "energy_only_caveat":"Not execution authorization. V1 holdout-mixed aggregate remains historical; an independently authorized energy input is required.",
            "previous_remote_branch":"work/manuscript-taipan-input-recovery-v1","previous_remote_commit":V1,
            "previous_remote_tree":"f85afbf06db5daf6f5ae8e1e60b0edc512709420",
            "canonical_main_verified":"c65cfb1daa8edf4ce85684b5093869c0f287d269",
            "nonholdout_profiles_reconstructed":30,"holdout_contaminated_profiles_excluded":16,
            "excluded_holdout_scan_count":len({s for m in membership for s in m["excluded_holdout_scans"]}),
            "non_discovery_scans_not_used":sorted({s for m in membership for s in m["excluded_non_discovery_scans"]}),
            "discovery_scans_used":len(ids),"fit_points":480,
            "Q_semantics":"VERIFIED_HKL_AND_Q for 30 reconstructed profiles / 45 scans; excluded groups not newly admitted",
            "Q_formula":"Q_Pbnm=2*pi*(h/a,k/b,l/c); Q_CEF=2*pi*(k/b,l/c,h/a)",
            "Q_point_checks":len(geometry),"Q_rounding_interval_failures":0,
            "mixed_point_table_access":{"path":"04_Results/Stage02R/W02-02R-A-002/scan_points.csv",
                                        "selected_columns":cols,"detector_or_monitor_columns_selected":False},
            "legacy_metadata_inventory_sha256":sha(legacy_path),
            "W03_Q_requirement":"Full vector in the transition-tensor frame for polarization contraction; magnitude alone supplies only the form factor. No powder averaging substituted.",
            "temperature_semantics":"UNKNOWN","temperature_calculations":thermal,
            "temperature_assessment":"18.247-meV thermal occupation is negligible over hypothetical 3.4-10 K. This does not bound ground population if D0->D2..D7 assignments allow lower levels. The 1-meV illustrative gap is not an assignment. For a single transition at a common temperature, the population factor can be absorbed by A_b, even if T is unknown. SG042/SG044 have raw channels near 10, so temperature is not an independent demonstrated blocker for that pair; channel-to-sample binding and common sample condition remain unverified. Do not combine 3.4/10 regimes for an unrestricted model without checking this. No sample T invented.",
            "blocks":blocks,"detected_rows_reviewed_V1":8,"detected_rows_admitted":0,
            "V1_detected_clean_diagnostic_only":5,"V1_detected_holdout_exclusions":3,
            "V2_detected_quality_pass":sum(r.get("v2_peak_quality_pass")=="true" for r in decisions),
            "fit_collapses_V2":sum(r["v2_admission_decision"]=="FIT_COLLAPSE" for r in decisions),
            "primary_decision_counts":dict(pd.Series([r["v2_admission_decision"] for r in decisions]).value_counts().items()),
            "censored_rows_admitted":0,"original_nondetections_diagnostic_only":38,
            "censoring":"Legacy A+1.64485*sigma is a Wald upper limit, not the z=3 detection threshold. The selected bounded shared fit supplies no calibrated censoring likelihood; V1 CENSOR_ADMISSIBLE label superseded.",
            "energy_systematic_status":"ENERGY_SYSTEMATIC_UNAVAILABLE",
            "energy_systematic_reason":"No traceable absolute reference uncertainty/zero-offset calibration in the reviewed inputs; empirical elastic width is not an energy calibration uncertainty.",
            "holdout_detector_access_count":0,"raw_detector_files_opened":False,"CEF_fitting_performed":False,
            "stage_transition":False,"remaining_material_blockers":[
                "Within-block response/acceptance invariance not established; A_b cannot absorb unknown scan-dependent factors.",
                "Block inst_f4703b6bd8 has only one quality-passing fresh detection under the chosen diagnostic extraction."],
            "conditional_temperature_limitation":"General D0->Dn models can have lower levels: thermal negligibility is not guaranteed across differing sample temperatures. Not treated as a separate decisive blocker for the near-10-channel detected pair.",
            "quality_rule":{"area_z_min":3,"area_collapse_floor":1e-8,"maximum_background_abs_correlation":.95,
                            "global_reduced_deviance_max":2,"require_full_rank_finite_covariance":True,
                            "require_optimizer_success_and_interior_center_width_area":True,
                            "selection_uses_CEF_agreement":False},
            "source_hashes":{str(p.relative_to(ROOT)):sha(p) for p in [CHECKPOINT,A002/"scan_inventory.csv",
                           A002/"parsed_header_metadata.jsonl",ROOT/"06_Scientific_Understanding/neutron-polarization-intrinsic-strength.md",
                           ROOT/"06_Scientific_Understanding/dyfeo3-pbnm-pnma-cef-frame-binding.md"]}}
    # Convert numpy scalar counts to ordinary integers for portable YAML.
    result["primary_decision_counts"]={k:int(v) for k,v in result["primary_decision_counts"].items()}
    (OUT/"admission_summary.yaml").write_text(yaml.safe_dump(result,sort_keys=False,allow_unicode=True))
    old_manifest=yaml.safe_load(old_bytes("manuscript_observables_provenance.yaml"))
    manifest={"schema_version":"manuscript_taipan_observables_provenance_v2",
              "task":result["task"],"manuscript_input_gate":"DRAFT_PROVENANCE_INCOMPLETE",
              "manuscript_intensity_gate":"FAIL_CLEANLY","V2_admission_is_authoritative":True,
              "V1_history":{"commit":V1,"tree":"f85afbf06db5daf6f5ae8e1e60b0edc512709420",
                            "original_manifest_sha256":hashlib.sha256(old_bytes("manuscript_observables_provenance.yaml")).hexdigest(),
                            "superseded_fields":["dataset-wide Q ambiguity for reconstructed subset","CENSOR_ADMISSIBLE diagnostic label","ENERGY role for holdout-mixed aggregate"],
                            "original_manifest":old_manifest},
              "V2":result,"observables_sha256":sha(DATA/"manuscript_observables.csv"),
              "review_path":"data/manuscript_v1/recovery_v2/ADMISSION_REVIEW.md",
              "V2_artifacts":{str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.iterdir()) if p.is_file()}}
    (DATA/"manuscript_observables_provenance.yaml").write_text(yaml.safe_dump(manifest,sort_keys=False,allow_unicode=True))
    print(json.dumps({k:result[k] for k in ["manuscript_intensity_gate","primary_decision_counts","blocks"]},indent=2))


if __name__=="__main__":
    main()
