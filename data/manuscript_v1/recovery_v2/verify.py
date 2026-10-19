"""Validate reconstruction provenance/admission boundaries without refitting."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import yaml

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
checks=[]


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


membership=json.loads((OUT/"membership.json").read_text())
points=pd.read_csv(OUT/"discovery_fit_points.csv")
split=pd.read_csv(ROOT/"04_Results/Stage02R/W02-02R-B-001/blind_split.csv").set_index("scan_record_id").split_role
check("counts_are_discovery_only", all(split[s]=="discovery" for s in points.scan_record_id.unique()))
check("population_30_profiles_45_scans_480_points", (points.observation_id.nunique(),points.scan_record_id.nunique(),len(points))==(30,45,480))
check("16_groups_17_holdout_scans_excluded",sum(bool(m["excluded_holdout_scans"]) for m in membership)==16 and
      len({s for m in membership for s in m["excluded_holdout_scans"]})==17 and
      not any(m["excluded_holdout_scans"] and m["reconstruction_source_scans"] for m in membership))
for m in membership:
    if m["reconstruction_source_scans"]:
        check("membership_"+m["observation_id"],set(points[points.observation_id==m["observation_id"]].scan_record_id)==set(m["reconstruction_source_scans"]))
q=pd.read_csv(OUT/"q_semantics_checks.csv")
check("Q_45_scans_1516_points_no_rounding_failure",len(q)==45 and q.n_points.sum()==1516 and q.rounding_interval_failures.sum()==0)
for order in range(3):
    cov=np.load(OUT/f"covariance_order{order}.npy",allow_pickle=False)
    params=json.loads((OUT/f"parameters_order{order}.json").read_text())
    check(f"covariance_order{order}",cov.shape==(len(params["theta"]),)*2 and np.isfinite(cov).all() and np.allclose(cov,cov.T))
rows=list(csv.DictReader((OUT.parent/"manuscript_observables.csv").open()))
old=list(csv.DictReader(io.StringIO(subprocess.check_output(["git","show",
    "415dd1751b7bf232476674af4e7e2571dd89a113:data/manuscript_v1/manuscript_observables.csv"],cwd=ROOT).decode())))
check("row_ids_preserved",[r["observation_id"] for r in rows]==[r["observation_id"] for r in old])
preserved=["source_scan_id","intensity_value","intensity_sigma","energy_meV","energy_sigma_meV","source_artifact","provenance_status"]
check("original_values_preserved",all(all(a[k]==b[k] for k in preserved) for a,b in zip(rows,old)))
check("no_intensity_or_censor_admission",not any(r["likelihood_role"] in ["DETECTED_INTENSITY","CENSORED_NONDETECTION"] for r in rows))
check("mixed_energy_demoted",rows[0]["likelihood_role"]=="EXCLUDED_FROM_BASELINE_LIKELIHOOD")
check("no_invented_temperature",all(r["temperature_K"]=="" for r in rows if r["observable_type"]=="integrated_peak_area"))
dec=pd.read_csv(OUT/"row_admission.csv")
check("46_single_primary_decisions",len(dec)==46 and dec.observation_id.nunique()==46 and dec.v2_admission_decision.notna().all())
check("exact_decision_partition",dec.v2_admission_decision.value_counts().to_dict()=={
    "OTHER_EXCLUSION":26,"HOLDOUT_CONTAMINATED":16,"NORMALIZATION_AMBIGUOUS":3,"FIT_COLLAPSE":1})
manifest=yaml.safe_load((OUT.parent/"manuscript_observables_provenance.yaml").read_text())
check("observables_hash",manifest["observables_sha256"]==hashlib.sha256((OUT.parent/"manuscript_observables.csv").read_bytes()).hexdigest())
check("artifact_hashes",all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest["V2_artifacts"].items()))
check("gate_fail_closed",manifest["V2"]["manuscript_intensity_gate"]=="FAIL_CLEANLY" and manifest["V2"]["holdout_detector_access_count"]==0)
print(json.dumps({"status":"PASS","checks_passed":len(checks),"checks_failed":0,"checks":checks},indent=2))
