No canonical naming conflict was found for the proposed path. The specification below freezes the accepted CI design and current stable official GitHub Action majors.

# INFRA-CI-SPEC

```yaml
specification_id: INFRA-CI-SPEC
specification_version: "1.0"
specification_status: proposed_for_freeze

ci_id: INFRA-CI-001

repository: oregu93/cef-dy
branch: main

design_baseline_commit:
  1c9c1fec22e0a7f598a9d3bd86f599c5751b7414

implementation_status: not_started
implementation_authorized: false

workflow_path:
  .github/workflows/infrastructure-ci.yml

external_data_required: false
secrets_required: false
scientific_execution_allowed: false
stage03r_authorized: false
branch_protection_change_authorized: false

commit_authorized: false
push_authorized: false
```

# IDENTITY

This specification defines the first controlled GitHub Actions CI implementation for the deterministic Git-tracked infrastructure layer of the CEF Dy / DyFeO3 project.

The CI exists only to verify portable repository infrastructure that can run from canonical tracked state without private or external scientific datasets.

`INFRA-CI-001` does not reproduce or replace `FC-PORTABILITY-001`.

The accepted fresh-clone result establishes a broader portability claim involving a clean local Linux sandbox and external-data reconnection. This CI verifies only the narrower Git-tracked portion:

```text
canonical checkout
→ minimal Python bootstrap
→ machine-local leakage guard
→ KB validation
→ recovery selftest
→ clean tracked state
```

The CI does not establish:

```text
TAIPAN raw-data identity
external-data reconstruction
scientific reproducibility
scientific-model correctness
backup correctness
disaster recovery
Stage03R readiness
```

# GOAL

Create exactly one GitHub Actions workflow that automatically checks deterministic repository infrastructure on relevant canonical changes.

A conforming implementation must provide:

```text
small
deterministic
fast
Git-tracked only
no secrets
no private data
no scientific datasets
no scientific execution
no write-back
```

Normal runtime design target:

```text
approximately 1–3 minutes
```

This runtime target is diagnostic only and is not a PASS/FAIL timeout criterion.

# BASELINE

Required design baseline:

```text
1c9c1fec22e0a7f598a9d3bd86f599c5751b7414
```

Accepted portability state at design baseline:

```yaml
execution_result: PASS
technical_review_decision: A
acceptance_status: accepted
fresh_clone_test_passed: true
```

Stage03R remains:

```text
unauthorized
```

The design baseline is design provenance.

A later implementation authorization must be separately established by Project Control against the then-canonical repository state.

No self-authorization is permitted.

# GOVERNANCE_LIFECYCLE

Mandatory lifecycle:

```text
1. CI design accepted
2. this exact specification frozen/materialized
3. specification freeze committed canonically
4. Project Control verifies specification freeze
5. separate implementation authorization
6. implementation creates only the allowlisted workflow
7. GitHub Actions execution
8. technical review by 07 - Research Software & Infrastructure
9. Project Control accepts/rejects CI implementation
10. only later, separately, consider branch-protection enforcement
```

The specification must not contain the SHA-256/SHA of its own future freeze commit.

Branch-protection configuration is not part of `INFRA-CI-001`.

# IMPLEMENTATION_ALLOWLIST

The complete implementation write allowlist is exactly:

```text
CREATE:
.github/workflows/infrastructure-ci.yml

MODIFY:
none

DELETE:
none
```

If implementation determines that any additional tracked file must be created, modified, or deleted:

```text
STOP_SCOPE_EXPANSION
```

No silent expansion is permitted.

# WORKFLOW_IDENTITY

Required workflow path:

```text
.github/workflows/infrastructure-ci.yml
```

Required conceptual workflow name:

```text
Infrastructure CI
```

Required job topology:

```text
one workflow
one job
no matrix
```

Recommended/frozen job identifier:

```text
infrastructure
```

No second job may be introduced in v1.

# TRIGGERS

Freeze exactly these trigger classes:

```yaml
pull_request:
  branches:
    - main

push:
  branches:
    - main

workflow_dispatch:
```

No scheduled trigger.

No `pull_request_target`.

No tag trigger.

No other branch-specific trigger is required.

Minor YAML syntax such as:

```yaml
workflow_dispatch: {}
```

is semantically equivalent and permitted.

# PERMISSIONS

Freeze workflow-level permissions:

```yaml
permissions:
  contents: read
```

No write permission is authorized.

No elevated permission is authorized.

In particular, do not request:

```text
contents: write
actions: write
checks: write
pull-requests: write
issues: write
id-token: write
packages: write
```

unless separately redesigned and authorized in the future.

# ACTIONS_POLICY

Only official GitHub actions are authorized:

```text
actions/checkout@v7
actions/setup-python@v7
```

No third-party action.

No artifact-upload action.

No cache action.

No coverage/reporting action.

No external service integration.

For checkout, implementation must disable retained Git credentials:

```yaml
persist-credentials: false
```

This reinforces the no-write-back boundary.

No local repository alternates, Git-LFS retrieval, submodule initialization, or scientific-data checkout is required.

# RUNNER

Freeze:

```yaml
runs-on: ubuntu-24.04
```

Do not use:

```text
ubuntu-latest
```

`ubuntu-24.04` is a GitHub-hosted Ubuntu-family Tier-1 CI proxy.

It does not imply exact equivalence to the physical Linux Mint workstation used for `FC-PORTABILITY-001`.

# PYTHON_POLICY

Freeze:

```text
Python 3.12
```

Use one Python version only.

Required setup semantic:

```yaml
python-version: "3.12"
```

No Python matrix.

No PyPy.

No experimental/free-threaded Python.

No scientific-environment bootstrap.

A future expansion to multiple Python versions requires separate design review.

# DEPENDENCY_POLICY

Canonical dependency source:

```text
requirements.txt
```

Freeze bootstrap command:

```bash
python -m pip install -r requirements.txt
```

Record:

```bash
python --version
python -m pip --version
python -c "import yaml; print(yaml.__version__)"
```

Do not install:

```text
NumPy
SciPy
pandas
Matplotlib
PyCrystalField
McPhase
Mantid
scientific fitting/modeling dependencies
```

unless they are already part of canonical infrastructure requirements through a separately governed future decision.

`requirements.txt` must not be modified by this implementation.

# DEPENDENCY_CACHE_POLICY

Freeze:

```text
pip_cache_enabled: false
```

Do not configure `actions/setup-python` caching.

Do not add `actions/cache`.

Reason:

```text
current dependency layer is minimal;
cache adds state/key/failure complexity without demonstrated need.
```

# EXTERNAL_DATA_BOUNDARY

CI must not require or resolve:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

CI must not:

```text
construct real configs/local_paths.yaml
read an existing local_paths.yaml
run FC-07
mount raw data
download raw data
download scientific result datasets
fabricate dummy TAIPAN data
access private project material
access machine-local external storage
```

Explicit invariant:

```text
INFRA-CI-001 does not reproduce or replace FC-PORTABILITY-001.
```

FC-07 remains a controlled local external-data identity test.

It is outside GitHub Actions CI.

# SCIENTIFIC_BOUNDARY

CI must not:

```text
run Stage02R scientific analysis
run Stage03R
perform CEF fitting
perform INS fitting
calculate new scientific results
modify reviewed scientific artifacts
change experimental assignments
change scientific/provenance semantics
change scientific authorization state
```

Required state:

```yaml
scientific_execution_allowed: false
stage03r_authorized: false
```

# SECRETS_POLICY

Required:

```yaml
secrets_required: false
```

Workflow must not reference project, repository, environment, organization, or user secrets.

The standard GitHub workflow token may exist as part of GitHub Actions runtime, but workflow permissions remain:

```yaml
contents: read
```

and checkout credentials must not be persisted.

No additional token or credential may be required.

# MACHINE_LOCAL_LEAKAGE_CONTRACT

Canonical leakage contract is the repository's existing `.gitignore`.

Freeze the generic check:

```bash
git ls-files -ci --exclude-standard
```

Required output:

```text
empty
```

Implementation must fail if one or more paths are returned.

The implementation must not duplicate a large independent path blacklist inside workflow YAML.

The generic check covers whatever machine-local/private/generated categories are already declared by the canonical ignore contract.

This includes current categories such as:

```text
.venv/
venv/
env/
configs/local_paths.yaml
CEF_Dy_Data/
data/
local_data/
private/
secrets/
credentials/
CEF_Dy_Backup/
backup/
backups/
ignored raw/intermediate/cache output areas
ignored archive/binary-output extensions
```

The canonical source of truth for the exact patterns is `.gitignore`, not this explanatory list.

# LARGE_ARTIFACT_POLICY

Do not implement an arbitrary size threshold.

Do not fail merely because:

```text
file_size > N MiB
```

for any newly invented N.

For v1:

```text
UNEXPECTED_LARGE_ARTIFACT
```

means a tracked object belonging to an already-canonical ignored large/generated category.

Such a case will normally also appear in:

```bash
git ls-files -ci --exclude-standard
```

Classification as `UNEXPECTED_LARGE_ARTIFACT` is diagnostic refinement of `MACHINE_LOCAL_LEAKAGE`, not an independent size scanner.

# KB_VALIDATION_POLICY

Freeze exactly:

```bash
python scripts/kb_refresh.py --check
python scripts/kb_validate.py
python scripts/kb_validate.py --strict
```

Required policy:

```text
errors = 0
warnings = 0
```

No accepted-warning baseline is introduced by this CI specification.

A future nonzero-warning policy requires separate governance.

# RECOVERY_SELFTEST_POLICY

Freeze:

```bash
python scripts/work_recovery.py selftest
```

Required:

```text
PASS
```

This is only the built-in disposable selftest.

It is not:

```text
actual Work recovery
panic snapshot execution on project state
backup
restore
disaster recovery
```

The selftest must not produce persistent repository mutation.

# CHECKOUT_IDENTITY

Immediately after checkout, record at minimum:

```bash
git rev-parse HEAD
git branch --show-current || true
git status --porcelain=v1 -uall
```

The branch-name command may be empty/detached in some GitHub Actions event contexts; detached HEAD by itself is not failure.

The authoritative tested revision is:

```text
git rev-parse HEAD
```

CI need not reconstruct local fresh-clone authorization semantics.

# REQUIRED_ORDER_OF_CHECKS

Freeze this logical order:

```text
1. checkout
2. record checkout identity
3. machine-local leakage guard
4. setup Python 3.12
5. dependency bootstrap
6. kb_refresh --check
7. kb_validate
8. kb_validate --strict
9. work_recovery selftest
10. git diff --check
11. tracked/index cleanliness
12. final repository cleanliness
```

Minor grouping inside shell steps is allowed only when this logical dependency/order is preserved.

# C-01 — CHECKOUT

Required:

```text
actions/checkout@v7
```

Required security input:

```yaml
persist-credentials: false
```

No LFS.

No submodules.

No alternate repository source.

PASS:

```text
canonical event revision is successfully checked out.
```

Failure classification:

```text
CI_CONFIG_FAILURE
or
CI_RUNNER_BLOCKED
```

depending on cause.

# C-02 — CHECKOUT IDENTITY RECORD

Run:

```bash
git rev-parse HEAD
git status --porcelain=v1 -uall
```

The initial checkout must not contain unexplained generated local state.

Expected at this point:

```text
clean
```

If checkout itself is dirty:

```text
TRACKED_STATE_MUTATION
or
MACHINE_LOCAL_LEAKAGE
```

depending on observed object.

# C-03 — MACHINE-LOCAL LEAKAGE GUARD

Run:

```bash
git ls-files -ci --exclude-standard
```

Implementation must explicitly test that stdout is empty.

A semantically conforming shell form is:

```bash
leakage="$(git ls-files -ci --exclude-standard)"
if [ -n "$leakage" ]; then
  printf '%s\n' "$leakage"
  exit 1
fi
```

Equivalent fail-closed implementation is allowed.

PASS:

```text
tracked ignored leakage set is empty
```

Failure:

```text
MACHINE_LOCAL_LEAKAGE
```

If returned path belongs specifically to an existing ignored large/generated category, diagnostic subtype may additionally be:

```text
UNEXPECTED_LARGE_ARTIFACT
```

# C-04 — PYTHON SETUP

Required:

```text
actions/setup-python@v7
```

with:

```yaml
python-version: "3.12"
```

No cache.

Record:

```bash
python --version
python -m pip --version
```

PASS:

```text
Python 3.12 environment available
```

# C-05 — DEPENDENCY BOOTSTRAP

Run:

```bash
python -m pip install -r requirements.txt
python -c "import yaml; print(yaml.__version__)"
```

PASS:

```text
requirements installation succeeds
PyYAML imports successfully
```

No hidden package installation is allowed.

# C-06 — KB REFRESH CHECK

Run:

```bash
python scripts/kb_refresh.py --check
```

Required exit:

```text
0
```

Failure:

```text
KB_VALIDATION_FAILURE
```

# C-07 — KB VALIDATION

Run:

```bash
python scripts/kb_validate.py
```

Required:

```text
exit 0
errors = 0
warnings = 0
```

Failure:

```text
KB_VALIDATION_FAILURE
```

# C-08 — STRICT KB VALIDATION

Run:

```bash
python scripts/kb_validate.py --strict
```

Required:

```text
exit 0
errors = 0
warnings = 0
```

Failure:

```text
KB_VALIDATION_FAILURE
```

# C-09 — WORK RECOVERY SELFTEST

Run:

```bash
python scripts/work_recovery.py selftest
```

Required:

```text
PASS
exit 0
```

Failure:

```text
RECOVERY_SELFTEST_FAILURE
```

unless evidence clearly establishes a hosted-runner/external-service defect.

# C-10 — DIFF FORMAT CHECK

Run:

```bash
git diff --check
```

Required exit:

```text
0
```

Failure:

```text
TRACKED_STATE_MUTATION
```

if produced by validation/selftest state.

# C-11 — TRACKED / INDEX CLEANLINESS

Run:

```bash
git diff --exit-code
git diff --cached --exit-code
```

Required:

```text
both exit 0
```

Failure:

```text
TRACKED_STATE_MUTATION
```

# C-12 — FINAL REPOSITORY CLEANLINESS

Run:

```bash
git status --porcelain=v1 -uall
```

Required output:

```text
empty
```

No persistent untracked files are expected from the CI operations.

Failure must be classified according to cause:

```text
TRACKED_STATE_MUTATION
MACHINE_LOCAL_LEAKAGE
or other implementation defect
```

No cleanup command may be used merely to force PASS.

In particular, do not use:

```text
git clean
git reset --hard
git checkout -- .
git restore .
```

to hide mutation caused by CI checks.

# WRITE_BOUNDARY

Allowed ephemeral state:

```text
GitHub-hosted runner filesystem
GitHub Actions tool/runtime state
Python installation/environment created by setup-python
pip installation state outside persistent canonical Git history
temporary fixture state created by work_recovery.py selftest
```

Repository-side terminal expectation:

```text
no tracked modifications
no staged modifications
no untracked persistent files
```

Workflow must not:

```text
git add
git commit
git push
create canonical result artifacts
modify metadata
write back to repository
open pull requests
create releases
create tags
```

# FORBIDDEN

The workflow must not contain or invoke:

```text
git commit
git push
git tag
git merge
git rebase
git reset --hard as cleanup
GitHub API write operations
repository mutation actions
artifact upload
cache upload
coverage upload
external reporting
secret retrieval
private-data download
scientific-data mount
scientific execution
FC-07
backup
restore
synchronization
```

# FAILURE_TAXONOMY

## CI_CONFIG_FAILURE

Definition:

```text
workflow configuration prevents valid CI execution.
```

Examples:

```text
invalid YAML
invalid action configuration
invalid step syntax
unsupported workflow key
```

Repository/CI implementation failure.

## CI_RUNNER_BLOCKED

Definition:

```text
GitHub-hosted runner cannot be provisioned or otherwise cannot begin meaningful execution for a platform/service reason.
```

Not by itself repository nonconformance.

## CI_EXTERNAL_SERVICE_FAILURE

Definition:

```text
external service required for otherwise valid CI is unavailable.
```

Examples:

```text
PyPI network outage
GitHub service/network outage
```

Must be distinguished from an invalid `requirements.txt`.

## DEPENDENCY_BOOTSTRAP_FAILURE

Definition:

```text
canonical requirements cannot construct the required infrastructure environment on the supported runner.
```

Repository nonconformance unless the evidence establishes `CI_EXTERNAL_SERVICE_FAILURE`.

## MACHINE_LOCAL_LEAKAGE

Definition:

```text
one or more tracked paths are classified as ignored by canonical .gitignore.
```

Repository nonconformance.

## KB_VALIDATION_FAILURE

Any required KB command:

```text
fails
returns nonzero
reports errors
reports warnings
```

Repository nonconformance.

## RECOVERY_SELFTEST_FAILURE

`work_recovery.py selftest` does not complete successfully.

Repository infrastructure nonconformance unless a host defect is independently established.

## TRACKED_STATE_MUTATION

Validation/selftest creates:

```text
tracked diff
staged change
persistent repository mutation
```

Repository infrastructure nonconformance.

## UNEXPECTED_LARGE_ARTIFACT

A tracked object belongs to an existing canonical ignored large/generated category.

No arbitrary file-size threshold is introduced.

This may be reported together with:

```text
MACHINE_LOCAL_LEAKAGE
```

# PASS_CRITERIA

`INFRA-CI-001` PASS requires all of the following:

1. workflow configuration is valid;
2. checkout succeeds;
3. canonical event revision is available;
4. initial repository state is clean;
5. `git ls-files -ci --exclude-standard` returns empty;
6. `ubuntu-24.04` runner is used;
7. Python 3.12 setup succeeds;
8. canonical `requirements.txt` installs successfully;
9. PyYAML imports successfully;
10. `kb_refresh.py --check` succeeds;
11. `kb_validate.py` succeeds;
12. `kb_validate.py --strict` succeeds;
13. KB errors equal zero;
14. KB warnings equal zero;
15. `work_recovery.py selftest` succeeds;
16. `git diff --check` succeeds;
17. `git diff --exit-code` succeeds;
18. `git diff --cached --exit-code` succeeds;
19. final `git status --porcelain=v1 -uall` is empty;
20. no external scientific dataset is accessed;
21. no private data is accessed;
22. no secrets are required;
23. no scientific execution occurs;
24. no repository write-back occurs.

# BRANCH_PROTECTION_POLICY

Recommendation only:

```text
INFRA-CI-001 should eventually become a required merge check for main.
```

Frozen authorization state:

```yaml
branch_protection_change_authorized: false
```

Do not configure required status checks during implementation.

A later branch-protection decision requires:

```text
CI implementation
→ successful operational runs
→ technical review
→ Project Control acceptance
→ separate governance action
```

# SECURITY_PRIVACY

Required properties:

```text
permissions: contents: read
no secrets
no third-party actions
no private datasets
no local absolute paths
no usernames
no hostnames supplied by project
no external scientific-data paths
```

GitHub-hosted runner-generated machine identifiers may appear in standard GitHub logs as platform runtime metadata, but the workflow must not intentionally inject private project-machine information.

No private manuscript path or content may enter CI.

No real TAIPAN path may enter CI.

# IMPLEMENTATION_TEST_PLAN

## T-CI-01 — workflow recognized / syntactically usable

Verify GitHub Actions recognizes:

```text
.github/workflows/infrastructure-ci.yml
```

and can instantiate the single `infrastructure` job.

PASS:

```text
workflow starts successfully
```

## T-CI-02 — pull_request trigger

Verify a controlled PR targeting:

```text
main
```

runs the workflow.

PASS:

```text
INFRA-CI-001 job starts from pull_request event
```

No private data may be introduced for this test.

## T-CI-03 — workflow_dispatch trigger

Manually dispatch workflow.

PASS:

```text
same infrastructure job executes without special inputs
```

No workflow inputs are required.

## T-CI-04 — push-to-main run

After accepted implementation is canonically merged/committed through governance, verify push to `main` produces a passing run.

This is an operational acceptance test, not authorization for implementation by this specification.

## T-CI-05 — dependency bootstrap

Verify:

```text
Python == 3.12.x
requirements installation PASS
PyYAML import PASS
```

## T-CI-06 — leakage negative baseline

On canonical clean repository:

```bash
git ls-files -ci --exclude-standard
```

must return empty.

## T-CI-07 — KB validation

Verify:

```text
kb_refresh --check PASS
kb_validate PASS
kb_validate --strict PASS
errors=0
warnings=0
```

## T-CI-08 — recovery selftest

Verify:

```text
work_recovery.py selftest PASS
```

## T-CI-09 — final clean Git state

Verify:

```text
git diff --check PASS
git diff --exit-code PASS
git diff --cached --exit-code PASS
git status --porcelain=v1 -uall empty
```

## T-CI-10 — no external-data dependency

Static workflow review must confirm absence of:

```text
configs/local_paths.yaml reconstruction
EXP-TAIPAN-001 access
EXP-XRD-001 access
WORK-OUTPUTS access
PRIVATE-DATA access
FC-07
raw-data download/mount
scientific-data fixtures
```

## T-CI-11 — no write-back / commit / push path

Static workflow review must confirm:

```text
permissions == contents: read
checkout persist-credentials == false
no git add
no git commit
no git push
no repository-write action
```

## T-CI-12 — leakage guard positive synthetic test

During implementation review, test the leakage guard against a disposable environment only.

Allowed approaches:

```text
temporary local synthetic Git repository
temporary Git fixture
disposable noncanonical branch/fixture
```

Preferred:

```text
temporary synthetic Git repository outside canonical repository
```

Test concept:

1. initialize temporary Git repository;
2. create `.gitignore` entry for a synthetic machine-local path;
3. force-add that ignored path;
4. run:

```bash
git ls-files -ci --exclude-standard
```

5. verify nonempty result;
6. verify the workflow-equivalent guard returns failure.

Forbidden:

```text
committing private data to canonical main
using actual TAIPAN data
using real secrets
```

T-CI-12 need not be permanently embedded in the production CI workflow.

It is an implementation-review test of guard behavior.

# IMPLEMENTATION_VALIDATION

Before technical acceptance, review must confirm:

```text
exact changed paths == workflow allowlist
workflow YAML valid
triggers exact
permissions read-only
official actions only
checkout@v7
setup-python@v7
ubuntu-24.04
Python 3.12
one job
no matrix
no cache
no external datasets
no secrets
no scientific execution
commands/order conform
leakage guard fail-closed
KB zero-warning policy preserved
selftest included
terminal cleanliness fail-closed
no write-back path
no branch protection change
```

# OPERATIONAL_ACCEPTANCE

Creating the workflow file is not by itself sufficient for final CI acceptance.

Required sequence after implementation authorization:

```text
implementation
→ static technical review
→ GitHub Actions execution
→ trigger tests as authorized
→ technical review of workflow and run evidence
→ Project Control acceptance
```

CI acceptance should distinguish:

```text
implementation_status
operational_run_status
technical_review_status
acceptance_status
```

Do not infer branch-protection authorization from CI acceptance.

# ROLLBACK_PLAN

If implementation is defective before canonical capture:

```text
do not stage/commit/push
preserve diagnostics
remove only job-owned new workflow if rollback is authorized and safe
STOP
```

If the workflow is already canonical and later found defective:

1. classify whether failure is workflow-specific or repository-specific;
2. do not weaken KB/scientific governance to make CI green;
3. do not alter scientific outputs;
4. separately authorize correction or removal of:

```text
.github/workflows/infrastructure-ci.yml
```

No broad reset or unrelated repository rollback is implied.

Because branch protection is not part of v1 implementation, a defective workflow must not be made a required merge gate before operational acceptance.

# STOP_CONDITIONS

Immediate implementation STOP on:

```text
STOP_SCOPE_EXPANSION
STOP_BASELINE_MISMATCH
STOP_AUTHORIZATION_MISSING
STOP_UNAUTHORIZED_ACTION
STOP_EXTERNAL_DATA_REQUIREMENT
STOP_SECRET_REQUIREMENT
STOP_SCIENTIFIC_EXECUTION_REQUIREMENT
STOP_BRANCH_PROTECTION_EXPANSION
STOP_DEPENDENCY_CHANGE_REQUIRED
STOP_THIRD_PARTY_ACTION_REQUIRED
STOP_WRITE_PERMISSION_REQUIRED
```

If implementation requires anything outside:

```text
CREATE .github/workflows/infrastructure-ci.yml
```

STOP rather than expanding scope.

# FORBIDDEN_CONTINUATION

This specification does not authorize:

```text
workflow creation
git add
git commit
git push
GitHub Actions execution
branch protection modification
requirements.txt changes
new Python dependencies
scientific testing
FC-07
Stage03R
```

# TERMINAL SPECIFICATION STATE

Before canonical materialization:

```yaml
specification_id: INFRA-CI-SPEC
specification_version: "1.0"
specification_status: proposed_for_freeze

ci_id: INFRA-CI-001

implementation_status: not_started
implementation_authorized: false

external_data_required: false
secrets_required: false
scientific_execution_allowed: false
stage03r_authorized: false
branch_protection_change_authorized: false
```

```text
SPECIFICATION_ID:
INFRA-CI-SPEC

SPECIFICATION_VERSION:
1.0

SPECIFICATION_PATH:
03_Protocols/INFRA_CI_SPEC_V1_0.md

DESIGN_BASELINE_COMMIT:
1c9c1fec22e0a7f598a9d3bd86f599c5751b7414

IMPLEMENTATION_ALLOWLIST:
CREATE:
  .github/workflows/infrastructure-ci.yml
MODIFY:
  none
DELETE:
  none

EXTERNAL_DATA_REQUIRED:
false

SECRETS_REQUIRED:
false

SCIENTIFIC_EXECUTION_ALLOWED:
false

STAGE03R_AUTHORIZED:
false

BRANCH_PROTECTION_CHANGE_AUTHORIZED:
false

READY_FOR_SPEC_FREEZE:
true
```

**A — SPEC_READY_FOR_FREEZE**
