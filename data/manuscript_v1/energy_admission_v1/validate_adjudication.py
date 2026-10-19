"""Bounded artifact/admission consistency checks; never imports fit code."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import yaml

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
checks=[]


def check(name, ok):
    if not ok:
        raise AssertionError(name)
    checks.append(name)


def rows(name):
    return list(csv.DictReader((OUT/name).open()))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


decision=json.loads((OUT/"energy_decision_frozen.json").read_text())
summary=yaml.safe_load((OUT/"energy_admission_summary.yaml").read_text())
grid=json.loads((OUT/"model_grid.json").read_text())
models={m["model_id"]:m for k in ["joint_shared_centroid_models","joint_separate_centroid_models","single_block_models"] for m in grid[k]}
check("terminal_state_model_dependent",summary["energy_admission"]==decision["terminal_scientific_state"]=="MODEL_DEPENDENT_ENERGY")
check("no_scalar_admission",all(summary[k] is None for k in ["admitted_energy_meV","stat_sigma_meV","scalar_model_sigma_meV"]))
check("frozen_decision_hash",sha(OUT/"energy_decision_frozen.json")==summary["decision_frozen_sha256"])
check("summary_preserves_frozen_decision",all(summary[k]==v for k,v in decision.items()))
check("comparators_not_in_frozen_decision",all(s not in (OUT/"energy_decision_frozen.json").read_text() for s in ["18.247","18.226"]))
for line in (OUT/"ADJUDICATION_SHA256SUMS").read_text().splitlines():
    digest,name=line.split("  ",1)
    check("hash_"+name,sha(OUT/name)==digest)
integrity=json.loads((OUT/"checkpoint_integrity.json").read_text())
check("checkpoint_integrity_pass",integrity["status"]=="PASS" and integrity["checks_failed"]==0)
judged=rows("model_adjudication.csv")
check("all_45_classified_once",len(judged)==45 and {r["model_id"] for r in judged}==set(models))
check("classification_counts",sum(r["scientific_status"]=="SCIENTIFICALLY_ADMISSIBLE" for r in judged)==18 and sum(r["scientific_status"]=="DIAGNOSTIC_ONLY" for r in judged)==27)
variants=rows("w03_energy_variants.csv")
check("variant_count_roles",len(variants)==36 and sum(v["role"]=="COMMON_CENTROID_CONDITIONAL" for v in variants)==18)
sources=rows("source_scans.csv")
check("45_sources_discovery_only",len(sources)==45 and len({s["scan_record_id"] for s in sources})==45 and all(s["split_role"]=="discovery" for s in sources))
check("variants_match_saved_fits",all(float(v["energy_meV"])==models[v["variant_id"]]["centers_meV"]["shared"] and float(v["conditional_sigma_meV"])==models[v["variant_id"]]["center_sigma_stat_meV"]["shared"] for v in variants))
check("variant_sources_exact",all(set(v["source_scan_ids"].split(';'))=={s["scan_record_id"] for s in sources if s["instrument_block_id"] in models[v["variant_id"]]["blocks"]} for v in variants))
check("stat_dispersion_separated",all(math.isclose(float(v["unscaled_curvature_sigma_meV"])*math.sqrt(float(v["covariance_scale"])),float(v["conditional_sigma_meV"]),rel_tol=1e-12) for v in variants))
shared=grid["joint_shared_centroid_models"]
for label,dim,others in [("background","background_order",["half_window_meV","width_mode"]),("window","half_window_meV",["background_order","width_mode"]),("width","width_mode",["half_window_meV","background_order"])]:
    groups={}
    for m in shared: groups.setdefault(tuple(m[k] for k in others),[]).append(m["centers_meV"]["shared"])
    check(label+"_paired_spread",math.isclose(max(max(g)-min(g) for g in groups.values()),summary["sensitivity_components"][label]["paired_full_range_summary"]["maximum"],abs_tol=1e-12))
covs=np.load(OUT/"covariances.npz",allow_pickle=False)
pars=json.loads((OUT/"parameters.json").read_text())
for r in rows("block_consistency.csv"):
    mid=f"separate_centers_w{r['half_window_meV']}_b{r['background_order']}_per_block"
    par=pars[mid];c=covs[mid.replace('.','p')];i=par["center_indices"][r["block_1"]];j=par["center_indices"][r["block_2"]]
    check(mid+"_difference",math.isclose(float(r["difference_meV"]),par["theta"][i]-par["theta"][j],abs_tol=1e-12) and math.isclose(float(r["difference_sigma_meV"]),math.sqrt(c[i,i]+c[j,j]-2*c[i,j]),abs_tol=1e-12))
for label,c in summary["comparisons_after_decision"].items():
    ds=[m["centers_meV"]["shared"]-c["comparator_meV"] for m in shared]
    check(label+"_postdecision_difference",min(ds)==c["joint_variant_minus_comparator_meV"]["minimum"] and max(ds)==c["joint_variant_minus_comparator_meV"]["maximum"])
for name in ["manuscript_observables.csv","manuscript_observables_provenance.yaml"]:
    p=OUT.parent/name
    check(name+"_unchanged",p.read_bytes()==subprocess.check_output(["git","show",decision["checkpoint_commit"]+":"+str(p.relative_to(ROOT))],cwd=ROOT))
check("boundaries",not summary["observables_updated"] and not summary["holdout_accessed"] and summary["holdout_detector_access_count"]==0 and summary["intensity_rows_admitted"]==summary["censored_rows_admitted"]==0 and not summary["CEF_fitting_executed"] and not summary["numerical_grid_rerun"])
check("temperature_Q_status",summary["temperature_status"]=="UNKNOWN" and summary["Q_status"].startswith("VERIFIED_HKL_AND_Q"))
review=(OUT/"ENERGY_ADMISSION_REVIEW.md").read_text()
check("review_links",all((OUT/p).exists() for p in re.findall(r'\]\(([^)]+)\)',review)))
check("review_decision_hash",summary["decision_frozen_sha256"] in review)
check("git_diff_check",subprocess.run(["git","diff","--check"],cwd=ROOT,check=False).returncode==0)
report=dict(status="PASS",checks_passed=len(checks),checks_failed=0,checks=checks,
    checkpoint=decision["checkpoint_commit"],decision_sha256=summary["decision_frozen_sha256"],
    artifact_hash_manifest_sha256=sha(OUT/"ADJUDICATION_SHA256SUMS"),
    numerical_grid_rerun=False,holdout_detector_access_count=0)
(OUT/"VALIDATION_REPORT.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:v for k,v in report.items() if k!="checks"},indent=2))
