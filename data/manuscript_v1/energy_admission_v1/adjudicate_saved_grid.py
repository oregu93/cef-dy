"""Read-only numerical adjudication of the frozen grid; no optimizer imports.

Writes only new adjudication artifacts beside the unchanged checkpoint files.
Does not promote an observation or execute W03. Run with numpy and PyYAML.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import yaml

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CHECKPOINT = "45a0c7964b12f23806e2a3c128263d0614a7914d"
CHECKPOINT_TREE = "d469861a685bedb8811fa877a78da61af80895fc"
BASE = "dc339abbc70b0e355c7e27beada8474d1af0ba5a"
INPUTS = ["RECOVERY_HANDOFF.md", "covariances.npz", "fit_energy_grid.py",
          "fit_points_window_5.0.csv", "fit_points_window_6.0.csv",
          "fit_points_window_7.0.csv", "model_grid.csv", "model_grid.json", "parameters.json"]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_json(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def write_csv(name, rows):
    with (OUT/name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def stats(values):
    a = np.asarray(values, dtype=float)
    return dict(n=len(a), minimum=float(a.min()), maximum=float(a.max()),
                median=float(np.median(a)), mean=float(a.mean()),
                full_range=float(np.ptp(a)), descriptive_sample_sd=float(np.std(a, ddof=1)) if len(a)>1 else 0.,
                max_absolute_excursion_from_median=float(max(abs(a-np.median(a)))))


def main():
    checks = []
    def require(name, condition):
        if not condition:
            raise RuntimeError("CHECKPOINT_INTEGRITY_FAILURE: "+name)
        checks.append(name)

    require("checkpoint_tree", subprocess.check_output(
        ["git","rev-parse",CHECKPOINT+"^{tree}"],cwd=ROOT).decode().strip()==CHECKPOINT_TREE)
    for name in INPUTS:
        p=OUT/name
        require("committed_bytes_"+name,p.read_bytes()==subprocess.check_output(
            ["git","show",CHECKPOINT+":"+str(p.relative_to(ROOT))],cwd=ROOT))
    grid=json.loads((OUT/"model_grid.json").read_text())
    parameters=json.loads((OUT/"parameters.json").read_text())
    covariances=np.load(OUT/"covariances.npz",allow_pickle=False)
    table=list(csv.DictReader((OUT/"model_grid.csv").open()))
    shared=grid["joint_shared_centroid_models"]
    separate=grid["joint_separate_centroid_models"]
    single=grid["single_block_models"]
    models=shared+separate+single
    require("model_counts",[len(shared),len(separate),len(single),len(table),len(parameters),len(covariances.files)]==[18,9,18,54,45,45])
    require("unique_model_ids",len({m["model_id"] for m in models})==45)
    split_path=ROOT/"04_Results/Stage02R/W02-02R-B-001/blind_split.csv"
    count_path=split_path.with_name("discovery_point_representation.csv")
    require("split_hash",digest(split_path)==grid["split_sha256"])
    require("discovery_count_hash",digest(count_path)==grid["count_source_sha256"])
    donor=Path.home()/"Загрузки/20_taipan_confirmatory_profiles_colab.py"
    require("donor_hash_no_import",digest(donor)==grid["donor_sha256"])
    split={r["scan_record_id"]:r["split_role"] for r in csv.DictReader(split_path.open())}
    source_ids=set(grid["source_scan_ids"])
    require("45_discovery_scans",len(source_ids)==grid["source_scan_count"]==45 and all(split[s]=="discovery" for s in source_ids))
    require("recorded_holdout_boundary",grid["holdout_detector_access_count"]==0)
    membership=json.loads((OUT.parent/"recovery_v2/membership.json").read_text())
    member={m["observation_id"]:m for m in membership if m["reconstruction_source_scans"]}
    require("V2_membership",len(member)==30 and {s for m in member.values() for s in m["reconstruction_source_scans"]}==source_ids)
    raw_points={(r["scan_record_id"],r["point_index"]):r for r in csv.DictReader(count_path.open())}
    for w,n in [(5,400),(6,480),(7,560)]:
        pts=list(csv.DictReader((OUT/f"fit_points_window_{w}.0.csv").open()))
        require(f"window_{w}_population",len(pts)==n and {p["scan_record_id"] for p in pts}==source_ids and {p["observation_id"] for p in pts}==set(member))
        require(f"window_{w}_count_provenance",all(
            p["scan_record_id"] in member[p["observation_id"]]["reconstruction_source_scans"] and
            p["split_role"]=="discovery" and 18-w<=float(p["energy_transfer_meV"])<=18+w and
            all(float(p[k])==float(raw_points[(p["scan_record_id"],p["point_index"])][k]) for k in
                ["energy_transfer_meV","detector_counts","monitor_counts"])
            for p in pts))
    for m in models:
        mid=m["model_id"]; par=parameters[mid]; cov=covariances[mid.replace('.','p')]; n=m["n_parameters"]
        require(mid+"_state",cov.shape==(n,n) and len(par["theta"])==n and np.isfinite(cov).all() and np.allclose(cov,cov.T))
        require(mid+"_numeric",m["valid"] and m["success"] and m["jacobian_rank"]==n and m["reduced_deviance"]<2)
        for key,i in par["center_indices"].items():
            rows=[r for r in table if r["model_id"]==mid and r["center_key"]==key]
            require(mid+"_"+key+"_csv_covariance",len(rows)==1 and
                abs(par["theta"][i]-m["centers_meV"][key])<1e-12 and
                abs(math.sqrt(cov[i,i])-m["center_sigma_stat_meV"][key])<1e-12 and
                abs(float(rows[0]["center_meV"])-m["centers_meV"][key])<1e-12 and
                abs(float(rows[0]["stat_sigma_meV"])-m["center_sigma_stat_meV"][key])<1e-12)
    fit_source=(OUT/"fit_energy_grid.py").read_text()
    require("no_comparator_fit_input",all(token not in fit_source for token in ["18.247","18.226","manuscript_observables.csv"]))
    for name in ["manuscript_observables.csv","manuscript_observables_provenance.yaml"]:
        p=OUT.parent/name
        require(name+"_unchanged",p.read_bytes()==subprocess.check_output(["git","show",CHECKPOINT+":"+str(p.relative_to(ROOT))],cwd=ROOT))
    obs=list(csv.DictReader((OUT.parent/"manuscript_observables.csv").open()))
    require("no_intensity_censor_promotion",not any(r["likelihood_role"] in ["DETECTED_INTENSITY","CENSORED_NONDETECTION"] for r in obs))
    require("old_aggregate_excluded",next(r for r in obs if r["observation_id"]=="TAIPAN-F002-ENERGY-AGGREGATE")["likelihood_role"]=="EXCLUDED_FROM_BASELINE_LIKELIHOOD")
    # All assertions above precede artifact mutation. Failure stops without regenerating fits.
    write_json("checkpoint_integrity.json",dict(status="PASS",checkpoint=CHECKPOINT,
        checks_passed=len(checks),checks_failed=0,checks=checks,input_sha256={n:digest(OUT/n) for n in INPUTS},
        numerical_grid_rerun=False,holdout_detector_access_count=0))

    classifications=[]
    for m in models:
        joint=m in shared
        classifications.append(dict(model_id=m["model_id"],numerical_status="NUMERICALLY_VALID",
            scientific_status="SCIENTIFICALLY_ADMISSIBLE" if joint else "DIAGNOSTIC_ONLY",
            scope="conditional common-centroid sensitivity variant; not an independently admitted observation" if joint else "block-consistency diagnostic; not an additional independent observation",
            reason=(f"Frozen validity conditions pass; background {m['background_order']}, window +/-{m['half_window_meV']}, width {m['width_mode']}; independent profile amplitudes. No rejection based on comparator proximity." if joint else
                    "Frozen validity conditions pass; retained to assess the common-centroid assumption. Separate and single-block fits reuse the joint inputs.")))
    write_csv("model_adjudication.csv",classifications)

    sensitivity={}
    for label,dim,other in [("background","background_order",["half_window_meV","width_mode"]),
                            ("window","half_window_meV",["background_order","width_mode"]),
                            ("width","width_mode",["half_window_meV","background_order"])]:
        strata=[]
        for key in sorted({tuple(m[k] for k in other) for m in shared}):
            group=[m for m in shared if tuple(m[k] for k in other)==key]
            strata.append(dict(fixed_dimensions=dict(zip(other,key)),**stats([m["centers_meV"]["shared"] for m in group])))
        sensitivity[label]={"paired_full_range_summary":stats([s["full_range"] for s in strata]),
            "paired_strata":strata,"by_level":{str(v):stats([m["centers_meV"]["shared"] for m in shared if m[dim]==v]) for v in sorted({m[dim] for m in shared})}}

    differences=[]
    for r in grid["common_vs_separate_center_lrt"]:
        par=parameters[r["separate_model_id"]]; cov=covariances[r["separate_model_id"].replace('.','p')]
        b1,b2=sorted(par["center_indices"]);i,j=par["center_indices"][b1],par["center_indices"][b2]
        d=float(par["theta"][i]-par["theta"][j]);s=float(np.sqrt(cov[i,i]+cov[j,j]-2*cov[i,j]))
        differences.append(dict(half_window_meV=r["half_window_meV"],background_order=r["background_order"],
            block_1=b1,block_2=b2,block_1_centroid_meV=par["theta"][i],block_2_centroid_meV=par["theta"][j],
            block_1_sigma_meV=math.sqrt(cov[i,i]),block_2_sigma_meV=math.sqrt(cov[j,j]),
            difference_meV=d,difference_sigma_meV=s,difference_approx95_low=d-1.96*s,difference_approx95_high=d+1.96*s,
            delta_deviance=r["delta_deviance"],lrt_df=1,lrt_p_value=r["p_value"]))
    write_csv("block_consistency.csv",differences)
    block_stats={b:dict(centroid_meV=stats([m["centers_meV"]["shared"] for m in single if m["blocks"]==[b]]),
        sigma_meV=stats([m["center_sigma_stat_meV"]["shared"] for m in single if m["blocks"]==[b]])) for b in sorted({b for m in single for b in m["blocks"]})}

    source_inventory={r["scan_record_id"]:r for r in csv.DictReader((ROOT/"04_Results/Stage02R/W02-02R-A-002/scan_inventory.csv").open())}
    source_rows=[]
    for sid in sorted(source_ids):
        memberships=[m for m in member.values() if sid in m["reconstruction_source_scans"]]
        assert len(memberships)==1
        m=memberships[0];meta=source_inventory[sid]
        source_rows.append(dict(scan_record_id=sid,raw_scan_id=meta["raw_scan_id"],source_checksum=meta["source_checksum"],
            observation_id=m["observation_id"],instrument_block_id=m["instrument_block_id"],split_role="discovery"))
    write_csv("source_scans.csv",source_rows)
    variants=[]
    for family,mm in [("COMMON_CENTROID_CONDITIONAL",shared),("BLOCK_STRESS_TEST_ONLY",single)]:
        for m in mm:
            scans=sorted({s for v in member.values() if v["instrument_block_id"] in m["blocks"] for s in v["reconstruction_source_scans"]})
            variants.append(dict(variant_id=m["model_id"],role=family,energy_meV=m["centers_meV"]["shared"],
                conditional_sigma_meV=m["center_sigma_stat_meV"]["shared"],
                unscaled_curvature_sigma_meV=m["center_sigma_stat_meV"]["shared"]/math.sqrt(max(m["reduced_deviance"],1)),
                covariance_scale=max(m["reduced_deviance"],1),background_order=m["background_order"],
                half_window_meV=m["half_window_meV"],width_mode=m["width_mode"],source_scan_ids=";".join(scans)))
    write_csv("w03_energy_variants.csv",variants)
    centers=[m["centers_meV"]["shared"] for m in shared]
    sigmas=[m["center_sigma_stat_meV"]["shared"] for m in shared]
    # Scientific decision is frozen BEFORE accessing historical comparators below.
    decision=dict(task="HOLDOUT_CLEAN_ENERGY_ADMISSION_V1",mode="ADJUDICATION_ONLY",
        checkpoint_commit=CHECKPOINT,checkpoint_tree=CHECKPOINT_TREE,base_commit=BASE,
        terminal_scientific_state="MODEL_DEPENDENT_ENERGY",energy_admission="MODEL_DEPENDENT_ENERGY",
        admitted_energy_meV=None,stat_sigma_meV=None,scalar_model_sigma_meV=None,
        scientifically_admissible_models=18,scientifically_admissible_scope="conditional common-centroid sensitivity ensemble only",
        numerically_valid_models=45,diagnostic_only_models=27,rejected_models=0,
        rationale="Between-model centroid span is about twice a conditional covariance sigma and follows background choice. Block offset changes with background; equality is not established. Do not promote a single precise centroid.",
        common_centroid_ensemble_meV=stats(centers),conditional_stat_sigma_meV=stats(sigmas),
        sigma_definition="Saved sqrt(diag(pseudoinverse(J.T@J))*max(deviance/dof,1)); local covariance approximation, not calibrated coverage. Contains residual-dispersion scaling, but NOT between-model sensitivity. Raw curvature sigmas are in w03_energy_variants.csv.",
        sensitivity_components=sensitivity,
        multimodality="Order-0 centroids form a lower band separated from orders 1/2. This reflects discrete analysis choices, not evidence for multiple physical peaks or a posterior mode probability.",
        block_assessment="BLOCK_DEPENDENCE_UNRESOLVED",block_summaries=block_stats,
        block_difference_meV=stats([r["difference_meV"] for r in differences]),
        block_difference_sigma_meV=stats([r["difference_sigma_meV"] for r in differences]),
        block_difference_approx95_envelope=[min(r["difference_approx95_low"] for r in differences),max(r["difference_approx95_high"] for r in differences)],
        block_lrt_p_range=[min(r["lrt_p_value"] for r in differences),max(r["lrt_p_value"] for r in differences)],
        block_caveat="LRT chi-square calibration is approximate with active nonnegative areas and excess deviance; failure to reject is not equivalence. The fits cannot identify calibration offsets separately from background/geometry/physical shifts.",
        absolute_energy_calibration_systematic_meV=None,absolute_energy_calibration_status="UNAVAILABLE_NOT_ZERO",
        recommended_W03_energy_likelihood={
            "representation":"FINITE_VARIANTS_NO_SINGLE_CENTROID_ADMISSION",
            "joint_variant_count":18,"single_block_stress_variant_count":18,
            "per_variant_term":"q_m(theta)=(DeltaE_CEF(theta)-E_m)^2/s_m^2, approximate conditional Gaussian; keep m fixed for the complete run",
            "rule":"Use all 18 common-centroid variants as separately labelled ENERGY_ONLY sensitivity runs with the same frozen CEF settings, assignment policy and budgets. Run all 18 single-block variants as labelled stress tests of the unresolved block assumption. Do not sum them as independent observations, choose a comparator-favoured variant, or minimize over m to select one final Hamiltonian.",
            "propagation":"Report distributions/supports separately by m; publish both union (compatibility with at least one variant) and intersection (compatibility with all variants) using identical per-variant thresholds. Only claims stable across the variants and block stress tests may be called robust. Empty intersection is reported, not repaired by dropping variants. No posterior model weights inferred from grid frequency.",
            "scope":"Diagnostic ENERGY_ONLY PCM/Cs15 model-sensitivity propagation; does not authorize a production run or manuscript-grade scalar likelihood. Recorded energy scale remains conditional on unavailable absolute calibration.",
            "systematic_treatment":"Keep background/window/width/block effects explicit; they interact and are not independent Gaussian errors. No quadrature total is assigned."},
        temperature_status="UNKNOWN",temperature_centroid_blocker=False,
        temperature_reason="The fitted positional model has no temperature term and every profile amplitude is free. Unknown sensor binding does not invalidate this conditional position fit, but absence of physical temperature shifts/blends is not proven. No claim about general Cs15 ground population.",
        Q_status="VERIFIED_HKL_AND_Q (inherited V2 checks for these 45 scans)",
        observables_updated=False,source_scan_count=45,profile_count=30,source_scan_ids=sorted(source_ids),
        holdout_accessed=False,holdout_detector_access_count=0,intensity_rows_admitted=0,censored_rows_admitted=0,
        CEF_fitting_executed=False,numerical_grid_rerun=False,
        feature_existence_scope="A finite fitted near-18-meV component persists across the saved grid; no new null-model test, significance, or separate-excitation claim is made.")
    write_json("energy_decision_frozen.json",decision)
    decision_sha=digest(OUT/"energy_decision_frozen.json")
    # Comparisons only; never inputs to the decision or any saved fit.
    comparisons={}
    for label,value in [("old_TAIPAN_holdout_mixed",18.24717836149484),("literature_external",18.226)]:
        comparisons[label]={"comparator_meV":value,"role":"COMPARISON_ONLY",
            "joint_variant_minus_comparator_meV":stats([c-value for c in centers]),
            "combined_significance":None,"note":"No independent comparison error model or cross-covariance established; old aggregate overlaps these scans. No independent z-test or reweighting; literature value is approximate."}
    summary={**decision,"decision_frozen_sha256":decision_sha,"comparisons_after_decision":comparisons,
        "checkpoint_integrity":"PASS","main_remote_at_start":"c65cfb1daa8edf4ce85684b5093869c0f287d269",
        "observables_sha256_unchanged":digest(OUT.parent/"manuscript_observables.csv"),
        "provenance_manifest_sha256_unchanged":digest(OUT.parent/"manuscript_observables_provenance.yaml"),
        "next_exact_action":"Independent review of the model-dependent variant representation and unresolved block dependence before any W03 execution authorization.",
        "stop":"READY_FOR_ENERGY_ADMISSION_REVIEW"}
    (OUT/"energy_admission_summary.yaml").write_text(yaml.safe_dump(summary,sort_keys=False,allow_unicode=True))
    tracked=[OUT/n for n in INPUTS]+[OUT/n for n in ["adjudicate_saved_grid.py","checkpoint_integrity.json",
        "model_adjudication.csv","block_consistency.csv","source_scans.csv","w03_energy_variants.csv",
        "energy_decision_frozen.json","energy_admission_summary.yaml","ENERGY_ADMISSION_REVIEW.md"]]
    if (OUT/"validate_adjudication.py").exists(): tracked.append(OUT/"validate_adjudication.py")
    (OUT/"ADJUDICATION_SHA256SUMS").write_text("".join(digest(p)+"  "+p.name+"\n" for p in tracked if p.exists()))
    print(json.dumps({"integrity":"PASS","checks":len(checks),"decision":decision["terminal_scientific_state"],
        "decision_sha256":decision_sha,"centroid_stats":decision["common_centroid_ensemble_meV"],
        "block_assessment":decision["block_assessment"],"comparisons":comparisons},indent=2))


if __name__=="__main__":
    main()
