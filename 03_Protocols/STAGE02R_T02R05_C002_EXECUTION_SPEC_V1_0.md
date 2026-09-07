# W02-02R-C-002 execution specification v1.0

```yaml
stage_id: M02R
task_id: T-02R-05
job_id: W02-02R-C-002
specification_version: "1.0"

document_status: frozen
scientific_design_status: accepted
execution_status: not_started
implementation_status: not_started
implementation_preparation_authorized: true
execution_authorized: false
holdout_detector_access_authorized: false

design_freeze_main: 122691ae7e69e40458509feec0dd2135aeb4108f
c001_execution_baseline: a8f5605177470d55de982227d9a9f36a7c801562
```

C002 v1.0 является спецификацией внутренней проверки трёх заранее
зарегистрированных presence hypotheses на замороженной отложенной выборке
TAIPAN. Она не является физическим назначением спектральных особенностей и не
авторизует доступ к detector fields или исполнение C002.

---

# FROZEN_FAMILY_IDENTITY

```yaml
future_C002_spec:
  path: 04_Results/Stage02R/W02-02R-C-001-v1.1/future_C002_spec.yaml
  sha256: 38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b

family_size: 3
family_frozen_before_detector_access: true

hypotheses:
  - hypothesis_id: C002-CX-01-K0-K1
    complex_id: CX-01
    hypothesis_type: presence
    parent_K: 0
    child_K: 1
    eligible_holdout_scan_count: 13
    eligible_holdout_scan_ids:
      - SCAN-02R-26cdfd757f62fb5b
      - SCAN-02R-41d12941c2dac178
      - SCAN-02R-42d0a4d8bd2d58cc
      - SCAN-02R-4650765ebe11f415
      - SCAN-02R-48f6ae0dc1c99d07
      - SCAN-02R-54bfea84553b4c65
      - SCAN-02R-58a76874c3967085
      - SCAN-02R-5e02dde1da14be55
      - SCAN-02R-79960ffd3b8a968b
      - SCAN-02R-87edbdf74d1e5fb1
      - SCAN-02R-a1d82bdc331e2df4
      - SCAN-02R-b14e49e20117cb08
      - SCAN-02R-c74434b3ed5fc9b8

  - hypothesis_id: C002-CX-02-K0-K1
    complex_id: CX-02
    hypothesis_type: presence
    parent_K: 0
    child_K: 1
    eligible_holdout_scan_count: 12
    eligible_holdout_scan_ids:
      - SCAN-02R-42d0a4d8bd2d58cc
      - SCAN-02R-48f6ae0dc1c99d07
      - SCAN-02R-54bfea84553b4c65
      - SCAN-02R-58a76874c3967085
      - SCAN-02R-5e02dde1da14be55
      - SCAN-02R-5f553db9674e6d45
      - SCAN-02R-79960ffd3b8a968b
      - SCAN-02R-87edbdf74d1e5fb1
      - SCAN-02R-a1d82bdc331e2df4
      - SCAN-02R-b14e49e20117cb08
      - SCAN-02R-baae22000a534323
      - SCAN-02R-c74434b3ed5fc9b8

  - hypothesis_id: C002-CX-03-K0-K1
    complex_id: CX-03
    hypothesis_type: presence
    parent_K: 0
    child_K: 1
    eligible_holdout_scan_count: 5
    eligible_holdout_scan_ids:
      - SCAN-02R-42d0a4d8bd2d58cc
      - SCAN-02R-5f553db9674e6d45
      - SCAN-02R-a1d82bdc331e2df4
      - SCAN-02R-a88a59b9d2315a05
      - SCAN-02R-baae22000a534323
```

Family membership, hypothesis order and eligible scan membership are immutable
during implementation and execution. No hypothesis or scan may be added,
removed or substituted after detector access.

---

# HOLDOUT_ACCESS_POLICY

До отдельной Project Control execution authorization разрешена только работа с
уже materialized metadata-only family specification.

```yaml
implementation_preparation:
  holdout_metadata_access: allowed_from_canonical_C001_artifacts
  holdout_detector_access: forbidden
  detector_derived_rate_access: forbidden

C002_execution_without_separate_authorization: forbidden
```

После отдельной будущей авторизации реализация должна открывать detector fields
только для перечисленных выше eligible holdout scans и только в пределах
соответствующей hypothesis. Каждый запрос поля должен записываться в append-only
field-access log. Forbidden request должен завершаться до decode/materialization.

До этой будущей авторизации запрещены:

```text
detector
det_err
detector / monitor
detector / time
любая detector-derived rate
holdout residual
holdout fit
```

Discovery detector data не могут использоваться для повторного выбора модели,
family membership, fit window, threshold или seed после freeze.

---

# MODEL_SPECIFICATION

Для каждого hypothesis применяется замороженная пара вложенных моделей:

```yaml
parent_model:
  K: 0
  background_family: B1_log_linear

child_model:
  K: 1
  background_family: B1_log_linear
  component_family: observed_unit_area_Gaussian

likelihood: raw_count_exposure_conditioned_Poisson
```

Для scan `s` и native point `i`:

```math
D_{si}\sim\operatorname{Poisson}(\mu_{si}),
```

```math
\mu_{si}=E_{si}\left[B_s(x_i)+\sum_{k=1}^{K}A_{sk}G(E_i;c_{sk},w_{sk})\right],
```

```math
\log B_s(x)=b_{0s}+b_{1s}x,\qquad x\in[-1,1].
```

`G` — unit-area Gaussian observed-profile component. Все параметры остаются
scan-specific; shared cross-scan intensity normalization отсутствует.

```yaml
parameter_domains:
  b0: unbounded
  b1: unbounded
  area: nonnegative_unbounded
  observed_fwhm: strictly_positive_unbounded
  centroid: strictly_inside_frozen_complex_union

arbitrary_per_scan_scale: forbidden
physical_minimum_separation_rule: none
```

Exposure semantics и fit windows берутся только из замороженного
`future_C002_spec.yaml` и связанных metadata eligibility artifacts. Global
fixed-`Ef` assumption запрещён.

---

# JOINT_TEST_STATISTIC

Для каждого hypothesis parent и child fit выполняются по всем и только его
eligible holdout scans. Совместный log likelihood является суммой независимых
scan-specific contributions:

```math
\ell_K=\sum_{s\in S_h}\ell_{s,K}.
```

Observed statistic:

```math
T_{\mathrm{obs}}=2\left(\ell_1-\ell_0\right).
```

Один hypothesis даёт один joint statistic. Запрещены post-access изменение
множества `S_h`, выбор наиболее благоприятного scan или объединение hypotheses.

---

# OBSERVED_OPTIMIZER_POLICY

```yaml
optimizer:
  implementation: scipy.optimize.minimize
  method: L-BFGS-B
  parameter_coordinates: physical_model_coordinates

deterministic_multistarts:
  initial: 8
  escalate_to: 16
  escalation_trigger: best_optimum_not_reproduced

post_optimizer_polishing: forbidden
secondary_optimizer: forbidden
KKT_role: final_observed_fit_diagnostic_only
```

Best optimum считается reproduced, если как минимум два различных start дают:

```math
|\ell_j-\ell_{\mathrm{best}}|\le
10^{-6}\max(1,|\ell_{\mathrm{best}}|).
```

Если reproduction отсутствует после 16 starts, observed fit получает
`optimizer_stability_status: unresolved`. KKT не модифицирует parameters, не
является polishing step и не заменяет likelihood comparison.

---

# BOOTSTRAP_POLICY

Для каждого hypothesis выполняется fixed null parametric bootstrap:

```yaml
bootstrap_replicates: 4096
rng: numpy.random.PCG64
bootstrap_design: fixed
adaptive_extension: forbidden
model_local_starts: 4
```

Каждый bootstrap dataset генерируется из fitted K0 parent model для того же
frozen eligible scan set. Parent и child fit используют ровно четыре
deterministic model-local starts:

1. same-model observed-data MLE;
2. bootstrap-dataset deterministic baseline;
3. deterministic positive perturbation of baseline;
4. deterministic negative perturbation of baseline.

Parent→child embedding, child→parent projection и adaptive start escalation
запрещены.

Если parent или child bootstrap fit numerical-invalid:

```math
T_b=+\infty.
```

---

# SEED_POLICY

Canonical serialization:

```yaml
encoding: UTF-8
key_order: lexical_sorted
separators: [",", ":"]
whitespace: none
ensure_ascii: true
```

Payload fields:

```yaml
job_id: W02-02R-C-002
c002_execution_spec_version: "1.0"
c002_execution_spec_freeze_main: 122691ae7e69e40458509feec0dd2135aeb4108f
c001_execution_baseline: a8f5605177470d55de982227d9a9f36a7c801562
future_C002_spec_sha256: 38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b
hypothesis_id: <exact_hypothesis_id>
bootstrap_replicates: 4096
rng: numpy.random.PCG64
```

Derivation:

```python
payload_bytes = canonical_json.encode("utf-8")
seed_sha256 = sha256(payload_bytes).hexdigest()
seed_integer = int(seed_sha256, 16)
rng = numpy.random.Generator(numpy.random.PCG64(seed_integer))
```

Frozen canonical JSON and hashes:

```text
C002-CX-01-K0-K1
{"bootstrap_replicates":4096,"c001_execution_baseline":"a8f5605177470d55de982227d9a9f36a7c801562","c002_execution_spec_freeze_main":"122691ae7e69e40458509feec0dd2135aeb4108f","c002_execution_spec_version":"1.0","future_C002_spec_sha256":"38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b","hypothesis_id":"C002-CX-01-K0-K1","job_id":"W02-02R-C-002","rng":"numpy.random.PCG64"}
seed_sha256: abde54d98da2396b269daf9d0f26effabc79ba6e90ff96e4edc9ec0c3e860712

C002-CX-02-K0-K1
{"bootstrap_replicates":4096,"c001_execution_baseline":"a8f5605177470d55de982227d9a9f36a7c801562","c002_execution_spec_freeze_main":"122691ae7e69e40458509feec0dd2135aeb4108f","c002_execution_spec_version":"1.0","future_C002_spec_sha256":"38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b","hypothesis_id":"C002-CX-02-K0-K1","job_id":"W02-02R-C-002","rng":"numpy.random.PCG64"}
seed_sha256: afeed89848a6527dbbff1efa9bb00127aa22e59e778c2bcf441ece63f066a0da

C002-CX-03-K0-K1
{"bootstrap_replicates":4096,"c001_execution_baseline":"a8f5605177470d55de982227d9a9f36a7c801562","c002_execution_spec_freeze_main":"122691ae7e69e40458509feec0dd2135aeb4108f","c002_execution_spec_version":"1.0","future_C002_spec_sha256":"38fd01e53d539bc877a36f7cd8152faf372905ddf9ce68b1c3779874654f555b","hypothesis_id":"C002-CX-03-K0-K1","job_id":"W02-02R-C-002","rng":"numpy.random.PCG64"}
seed_sha256: 6fe2650a2d8dcca2081d63497512d3fb7df1a47a732849b755402913202269b1
```

---

# RAW_P_VALUE_POLICY

Для каждого hypothesis:

```math
p_{\mathrm{raw}}=
\frac{1+\#\{b:T_b\ge T_{\mathrm{obs}}\}}{4097}.
```

```yaml
p_value_convention: plus_one
denominator: 4097
tail: T_b_greater_than_or_equal_to_T_observed
```

Adaptive continuation после просмотра result запрещена.

---

# HOLM_POLICY

Полная family из трёх hypotheses участвует в едином Holm correction:

```yaml
procedure: Holm
global_alpha: 0.05
family_size: 3
ordering:
  primary: raw_p_value_ascending
  tie_break: hypothesis_id_lexical_ascending
family_shrinkage_after_detector_access: forbidden
```

Для rank `i=1,...,3` rejection допускается при:

```math
p_{(i)}\le\frac{0.05}{3-i+1}.
```

Rejection sequence останавливается при первом failure. Все последующие
hypotheses не rejected независимо от их individual raw p-values.

---

# NUMERICAL_FAILURE_POLICY

Observed parent/child numerical failure не удаляет hypothesis из family:

```yaml
test_status: numerical_failure
raw_p_value: 1.0
Holm_family_membership: retained
scientific_result_semantics: numerical_failure
```

Bootstrap replicate failure сохраняется как `T_b=+infinity`. Failure records
должны включать hypothesis, model, replicate, fit status, reason и start count.
Частичный numerical output не может быть представлен как confirmed presence.

---

# SCIENTIFIC_RESULT_SEMANTICS

Разрешены только три итоговых значения:

```yaml
presence_confirmed_internal_holdout:
  condition: Holm_rejected_and_numerically_valid

presence_not_confirmed:
  condition: numerically_valid_and_not_Holm_rejected

numerical_failure:
  condition: required_observed_test_not_numerically_valid
```

`presence_not_confirmed` не означает физического отсутствия excitation.
`presence_confirmed_internal_holdout` означает только внутреннее подтверждение
на заранее отложенной части того же targeted TAIPAN dataset; это не независимая
beamtime replication и не доказательство CEF/magnon/phonon origin.

```yaml
physical_assignment: forbidden
spectral_completeness_claim: forbidden
absence_outside_measured_regions: not_inferable
```

---

# RESOLUTION_BOUNDARY

```yaml
resolution_status: resolution_not_established
```

C002 проверяет presence hypotheses в observed phenomenological model. Он не
устанавливает intrinsic linewidth, resolution-limited character, close-level
resolution или physical line count. Неустановленное разрешение не отменяет
presence test, но блокирует эти дополнительные физические утверждения.

---

# OUTPUT_CONTRACT

Минимальный canonical output должен содержать:

```yaml
per_hypothesis:
  - hypothesis_id
  - exact_eligible_holdout_scan_ids
  - observed_parent_fit_status
  - observed_child_fit_status
  - T_observed
  - bootstrap_replicates
  - seed_payload_canonical_json
  - seed_sha256
  - bootstrap_failed_replicates
  - raw_p_value
  - Holm_rank
  - Holm_threshold
  - Holm_rejected
  - test_status
  - scientific_result_semantics

global:
  - family_size
  - family_members
  - Holm_global_alpha
  - holdout_detector_access_count
  - C002_executed
  - resolution_status
  - physical_assignment_performed
  - spectral_completeness_claim
```

Required provenance:

```yaml
design_freeze_main:
c001_execution_baseline:
future_C002_spec_path:
future_C002_spec_sha256:
source_sha256:
config_sha256:
input_artifact_identities:
output_artifact_identities:
field_access_log:
test_report:
```

No output may contain a CEF, magnon or phonon assignment.

---

# MANDATORY_TESTS

## C002-T01 — Frozen identities

Verify design freeze main, C001 execution baseline, future C002 spec path/SHA,
implementation source/config and all required input identities.

## C002-T02 — Exact family

Verify exactly three hypotheses in frozen lexical IDs, with no additions,
deletions or substitutions.

## C002-T03 — Exact eligible membership

Verify exact scan IDs and counts 13/12/5 against canonical
`future_C002_spec.yaml` before detector access.

## C002-T04 — Holdout access guard

Verify zero detector materialization before authorization, allowlisted fields
only, hard failure before decode for forbidden requests, and complete access log.

## C002-T05 — Model contract

Verify K0/K1, B1 log-linear background, unit-area Gaussian child component,
raw-count/exposure Poisson likelihood, scan-specific parameters and frozen
domains/windows.

## C002-T06 — Observed optimizer

Verify deterministic 8 starts, 16 only when optimum reproduction fails,
L-BFGS-B, no polishing, no secondary optimizer and KKT diagnostic-only role.

## C002-T07 — Bootstrap contract

Verify B=4096, exactly four model-local starts, null generation from fitted K0,
no adaptive extension and failed replicate `T_b=+infinity`.

## C002-T08 — Seed reproducibility

Verify canonical JSON bytes and all three frozen SHA-256 seed hashes exactly.

## C002-T09 — Raw p-values

Verify plus-one tail convention, `>=` comparison and denominator 4097.

## C002-T10 — Holm family control

Verify global alpha 0.05, full family size three, raw-p ascending order,
lexical hypothesis-ID tie-break and stop at first failure.

## C002-T11 — Numerical failure

Verify failed observed hypothesis remains in family with raw p-value 1.0 and
`scientific_result_semantics: numerical_failure`.

## C002-T12 — Scientific/resolution boundary

Verify only the three frozen scientific result semantics, resolution status
`resolution_not_established`, no physical assignment and no spectral
completeness claim.

## C002-T13 — Provenance and STOP

Verify complete provenance, immutable family, B001 and C001 inputs unchanged,
private material absent, C002 access audit complete and STOP reached before
combined re-estimation, physical interpretation or Stage03 inference.

---

# PASS_CRITERIA

C002 passes only if:

1. all frozen identities match;
2. family contains exactly the three frozen hypotheses;
3. exact eligible scan memberships and counts 13/12/5 match;
4. detector access occurs only after separate authorization and only through the allowlist;
5. no detector value changes family membership, scan eligibility or seed;
6. K0/K1 model and joint statistic follow this specification;
7. observed optimization follows deterministic 8→16 policy;
8. every bootstrap uses exactly four model-local starts;
9. B=4096 fixed bootstrap is completed or the hypothesis is retained as numerical failure;
10. all frozen seed hashes reproduce exactly;
11. raw p-values use plus-one denominator 4097;
12. Holm correction uses the complete frozen family and global alpha 0.05;
13. numerical failures remain in family with raw p-value 1.0;
14. result semantics use only the three allowed values;
15. resolution remains `resolution_not_established`;
16. no physical assignment or spectral completeness claim is made;
17. B001, C001 artifacts and the frozen family remain unchanged;
18. private/unpublished material is absent;
19. C002-T01...C002-T13 all PASS;
20. STOP condition is satisfied.

An outcome `presence_not_confirmed` or `numerical_failure` is a valid C002
outcome and does not itself violate the execution specification.

---

# STOP_CONDITION

C002 STOP is reached after writing and freezing:

```yaml
all_three_hypothesis_results:
raw_p_values:
Holm_decisions:
scientific_result_semantics:
numerical_failure_records:
holdout_field_access_log:
holdout_detector_access_count:
resolution_status: resolution_not_established
provenance_manifest:
test_report:
```

Then return to:

```text
W02-02R-C-002
        ↓
STOP
        ↓
02 - TAIPAN Data Reduction
artifact-level scientific review
        ↓
00 - Project Control
```

C002 MUST NOT continue into:

```text
family modification
discovery + holdout combined re-estimation
physical CEF/magnon/phonon assignment
historical target comparison
Stage03R inference
Stage03D execution
```

---

# IMPLEMENTATION_REQUIREMENTS

Implementation preparation is authorized, but implementation execution is not.

Required implementation properties:

```yaml
fail_closed_identity_checks: true
metadata_only_preparation: true
detector_decode_before_execution_authorization: forbidden
exact_family_embedded_or_verified: true
exact_seed_hashes_verified_before_execution: true
deterministic_resume_without_family_mutation: required
append_only_field_access_log: required
partial_output_promotion_on_failure: forbidden
```

Implementation source/config require separate static conformance review. Any
change to this scientific contract requires a new specification version and
Project Control decision.

---

# NONBLOCKING_LIMITATIONS

The following are accepted nonblocking limitations:

- holdout is internal to the same purpose-driven TAIPAN beamtime and is not an independent replication;
- acquired scans are not an exhaustive continuous energy survey;
- `resolution_not_established` blocks intrinsic-linewidth and close-level-resolution claims;
- no shared absolute or cross-mode intensity scale is established;
- numerical failure may remain a valid hypothesis outcome;
- a non-confirmed presence hypothesis does not establish physical absence;
- C002 cannot assign CEF, magnon or phonon origin;
- C002 cannot establish completeness of the Dy3+ CEF scheme.

---

# SPECIFICATION_STATUS

```yaml
C002:
  execution_specification_version: "1.0"
  execution_specification_status: frozen
  scientific_design_status: accepted
  implementation_status: not_started
  implementation_preparation_authorized: true
  execution_authorized: false
  holdout_detector_access_authorized: false

next_governance_action: W02_C002_implementation_preparation
```

**Return to:** `00 - Project Control`
