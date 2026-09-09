# FRESH-CLONE-ACCEPTANCE-SPEC

```yaml
specification_id: FRESH-CLONE-ACCEPTANCE-SPEC
specification_version: "1.0"
specification_status: proposed_for_freeze

test_id: FC-PORTABILITY-001

repository: oregu93/cef-dy
branch: main

design_baseline_commit: a106cd10152211ff5bd4a97943113d406e1c5620

execution_status: not_started
execution_authorized: false

fresh_clone_test_passed: false

execution_baseline_policy: canonical_execution_authorization_commit

governance_role: Project Control
technical_review_role: 07 - Research Software & Infrastructure

execution_environment:
  class: local_tier1_linux_sandbox
  platform_family: Linux Mint / Ubuntu-family Linux
  sandbox_isolated_from_working_clone: true

operator: local user/operator

stage03r_authorized: false
commit_authorized: false
push_authorized: false
```

# IDENTITY

This specification defines the first controlled fresh-clone acceptance test for the portable infrastructure layer of the CEF Dy / DyFeO3 project.

The test determines whether a clean Tier-1 Linux environment can reconstruct a usable project infrastructure from canonical GitHub state without hidden dependence on:

- the normal working clone;
- its `.venv`;
- ignored/untracked files;
- its `configs/local_paths.yaml`;
- local patches or generated outputs;
- chat history.

The test is an infrastructure reproducibility test.

It is not:

- scientific analysis;
- Stage03R;
- TAIPAN data reduction;
- repository migration;
- backup execution;
- recovery execution;
- CI;
- repository cleanup.

# GOAL

A valid successful execution must demonstrate:

```text
canonical GitHub main
        ↓
fresh independent clone
        ↓
new sandbox-local Python environment
        ↓
canonical KB validation
        ↓
machine-local configuration reconstructed from tracked example
        ↓
EXP-TAIPAN-001 reconnected by stable identity
        ↓
read-only A-002 inventory verification
        ↓
recovery/backup boundaries understandable from tracked docs
        ↓
clean terminal repository state
```

The execution result may be:

```text
PASS
FAIL
BLOCKED
```

The local executor may not promote canonical project state.

During execution:

```text
canonical_fresh_clone_test_passed: pending_review
```

A canonical:

```text
fresh_clone_test_passed: true
```

requires:

```text
execution PASS
+
07 technical review decision A
+
Project Control acceptance
+
separate canonical capture
```

# BASELINE

Design baseline:

```text
a106cd10152211ff5bd4a97943113d406e1c5620
```

This is not permanently the execution-tested commit.

A separate Project Control execution-authorization transition must establish:

```text
authorized_test_commit: <canonical SHA>
```

Execution requires:

```text
fresh clone HEAD
==
origin/main
==
authorized_test_commit
```

If `main` advances after authorization:

```text
TEST_BLOCKED
STOP_STALE_AUTHORIZATION
```

No automatic rebase, pull-forward, substitution, or reauthorization is permitted.

## Non-self-referential lifecycle

```text
1. design accepted
2. exact specification frozen/materialized
3. specification freeze committed canonically
4. Project Control verifies specification freeze
5. separate execution-authorization commit establishes authorized_test_commit
6. local FC execution tests exactly that commit
7. execution evidence reviewed by 07
8. Project Control accepts/rejects
9. only a separate canonical transition may set fresh_clone_test_passed=true
```

The specification does not contain its own future freeze-commit SHA.

# EXECUTION_ENVIRONMENT

Required environment:

```yaml
class: local_tier1_linux_sandbox
platform_family: Linux Mint / Ubuntu-family Linux
operator: local user/operator
```

The test does not require execution through WKB-R1 or cloud Work.

WKB-R1 may later assist with artifact preparation or canonical capture only if separately authorized.

No new permanent chat role is created.

# SANDBOX_MODEL

Current machine-local operator parameter:

```text
~/CEF_Dy_sandbox/
```

Conceptual layout:

```text
CEF_Dy_sandbox/
├── cef-dy-fresh-clone/
├── logs/
├── artifacts/
└── test-local-data/
```

The absolute sandbox path is:

```text
machine-local execution parameter
```

and is not canonical project identity.

Canonical durable provenance should identify:

```text
test_id
tested_commit
repository
platform family
```

rather than the absolute home-directory path.

# INPUTS

## Canonical inputs

```text
repository: oregu93/cef-dy
branch: main
authorized_test_commit

requirements.txt
configs/local_paths.example.yaml

03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
03_Protocols/PORTABILITY_BASELINE_SPEC_V1_0.md
03_Protocols/RESEARCH_KB_GUIDE.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
03_Protocols/DATA_CONTRACTS.md

scripts/kb_refresh.py
scripts/kb_validate.py
scripts/work_recovery.py

04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
```

## Machine-local inputs

```text
sandbox root
normal working-repository location
physical location of EXP-TAIPAN-001
```

The normal working repository is used only for isolation proof.

The physical dataset path is used only as machine-local resolution of:

```text
EXP-TAIPAN-001
```

# PREFLIGHT

No test phase may begin until execution authorization has been verified.

Required authorization fields:

```text
specification_id == FRESH-CLONE-ACCEPTANCE-SPEC
specification_version == 1.0
execution_authorized == true
authorized_test_commit is defined
execution_baseline_policy == canonical_execution_authorization_commit
```

The local operator must also confirm:

```text
Stage03R remains unauthorized
no GitHub write is authorized
no backup execution is authorized
```

If authorization cannot be verified:

```text
TEST_BLOCKED
STOP_NO_AUTHORIZATION
```

# WRITE_ALLOWLIST

All intentional writes must remain under the sandbox root:

```text
~/CEF_Dy_sandbox/**
```

or the separately recorded machine-local equivalent.

Permitted writes include:

```text
sandbox clone
sandbox clone/.venv/**
sandbox clone/configs/local_paths.yaml
logs/**
artifacts/**
test-local-data/**
```

Tracked files in the fresh clone must remain unchanged by the test.

The following local additions are expected to remain ignored:

```text
.venv/**
configs/local_paths.yaml
```

No external raw-data write is allowed.

# AUDIT_ONLY

## Normal working repository

May be inspected only for:

```text
working repository realpath
working Git toplevel
working .venv realpath, if needed for anti-reuse check
```

It must not be a source of:

```text
tracked files
ignored files
untracked files
local config
.venv
patches
generated artifacts
Git objects
clone alternates
```

## External TAIPAN dataset

`EXP-TAIPAN-001` is audit/read-only.

It may be traversed and read only by the accepted FC-07 identity procedure.

# FORBIDDEN

The local operator must not:

- modify the normal working repository;
- use it as clone source;
- copy from it into the sandbox;
- reuse its `.venv`;
- reuse its `configs/local_paths.yaml`;
- use `git clone --reference` to the working clone;
- use Git alternates pointing to the working clone;
- modify raw TAIPAN data;
- copy the raw TAIPAN archive into the sandbox;
- rename/move/repair/normalize/synchronize raw data;
- run scientific analysis;
- run Stage03R;
- run backup or restore;
- configure synchronization;
- implement CI;
- perform GitHub writes;
- stage/commit/push canonical changes;
- set canonical `fresh_clone_test_passed=true`.

# FC-01 — SANDBOX PREFLIGHT

## PURPOSE

Prove that the future fresh clone executes in an isolated local sandbox and cannot inherit hidden state from the working repository.

## INPUTS

```text
authorized_test_commit
working repository path
sandbox root
fresh clone target
```

Current machine example:

```text
SANDBOX_ROOT=~/CEF_Dy_sandbox
FRESH_CLONE_TARGET=~/CEF_Dy_sandbox/cef-dy-fresh-clone
```

These values remain machine-local.

## COMMANDS_OR_EXACT_PROCEDURE

Record UTC start time and system facts.

Determine:

```bash
realpath <working-repository>
realpath -m <sandbox-root>
realpath -m <fresh-clone-target>
git -C <working-repository> rev-parse --show-toplevel
git --version
python3 --version
uname -a
df -Pk <sandbox-parent>
```

If a working-project `.venv` exists, record only its resolved path for anti-reuse comparison.

Check that:

1. sandbox root is not equal to working-repository realpath;
2. sandbox root is not inside working repository;
3. working repository is not inside sandbox;
4. fresh-clone target is not the working repository;
5. target is absent or an explicitly empty new directory;
6. no existing target `.git` exists;
7. sandbox/root path components do not resolve through symlink aliases into the working repository;
8. system Git, Python 3 and `venv` capability are available;
9. enough disk exists for clone, venv and evidence.

No arbitrary project-wide minimum disk size is canonicalized; actual available bytes are recorded.

## EXPECTED_OUTPUTS

```text
FC01_STATUS
start_timestamp_utc
platform
kernel
architecture
git_version
python_version
sandbox_isolation_status
free_space_bytes
```

## PASS

All isolation checks are unambiguous and required host capabilities exist.

## TEST_FAIL

None for ordinary host-precondition problems.

## TEST_BLOCKED

- overlap or path alias cannot be ruled out;
- sandbox target contains unexplained state;
- Git unavailable;
- Python/venv unavailable;
- insufficient disk;
- required isolation facts cannot be determined.

## EVIDENCE_TO_CAPTURE

Local diagnostic:

```text
logs/fc01_preflight.log
```

Sanitized durable:

```text
artifacts/fc01_sandbox_isolation.yaml
```

## STOP_RULE

Any FC-01 BLOCKED condition:

```text
STOP
```

No clone is performed.

# FC-02 — CANONICAL CLONE

## PURPOSE

Prove that the tested repository was obtained directly from canonical GitHub state and is pinned to the separately authorized commit.

## INPUTS

```text
repository: oregu93/cef-dy
authorized_test_commit
fresh clone target
```

## COMMANDS_OR_EXACT_PROCEDURE

Clone only:

```bash
git clone https://github.com/oregu93/cef-dy.git <fresh-clone-target>
cd <fresh-clone-target>
```

Then record:

```bash
git remote get-url origin
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git rev-parse --git-dir
git rev-parse --git-common-dir
```

Do not run:

```text
git pull
git rebase
git merge
git reset
```

to repair a stale authorization.

## EXPECTED_OUTPUTS

```text
origin_url
branch
HEAD
origin_main
git_dir
git_common_dir
authorized_test_commit
```

## PASS

Exactly:

```text
origin == https://github.com/oregu93/cef-dy.git
branch == main
HEAD == origin/main
HEAD == authorized_test_commit
```

and Git metadata is independent of the working repository.

## TEST_FAIL

- clone source is not canonical GitHub;
- clone uses local working-repository Git objects/common-dir;
- canonical tracked clone is structurally abnormal.

## TEST_BLOCKED

If:

```text
origin/main != authorized_test_commit
```

because canonical `main` advanced after authorization:

```text
TEST_BLOCKED
STOP_STALE_AUTHORIZATION
```

Also BLOCKED for network/GitHub failure preventing a valid clone.

## EVIDENCE_TO_CAPTURE

```text
logs/fc02_clone.log
artifacts/fc02_clone_identity.yaml
```

## STOP_RULE

Any FAIL or BLOCKED condition stops execution.

# FC-03 — REPOSITORY CLEANLINESS AND TRACKED-STATE VERIFICATION

## PURPOSE

Establish the pristine state of the fresh clone before local environment/configuration creation.

## INPUTS

Fresh clone from FC-02.

## COMMANDS_OR_EXACT_PROCEDURE

```bash
git status --porcelain=v1 -uall
git diff --check
git diff --name-only
git diff --cached --name-only

git ls-files --error-unmatch requirements.txt
git ls-files --error-unmatch configs/local_paths.example.yaml
```

Verify absent before reconstruction:

```text
.venv
configs/local_paths.yaml
CEF_Dy_Backup
```

## EXPECTED_OUTPUTS

```text
tracked_clean=true|false
staged_count
unstaged_count
unexpected_untracked_count
diff_check
bootstrap_files_present
```

## PASS

- no staged files;
- no tracked modifications;
- no unexplained untracked state;
- `git diff --check` PASS;
- tracked bootstrap files exist;
- no inherited `.venv`;
- no inherited `local_paths.yaml`.

## TEST_FAIL

Fresh canonical clone itself is dirty or missing expected tracked bootstrap material.

## TEST_BLOCKED

Filesystem or permission state prevents trustworthy inspection.

## EVIDENCE_TO_CAPTURE

```text
logs/fc03_git_state.log
artifacts/fc03_repository_state.yaml
```

## STOP_RULE

FAIL or BLOCKED → STOP.

# FC-04 — NEW INFRASTRUCTURE PYTHON ENVIRONMENT

## PURPOSE

Test whether canonical `requirements.txt` is sufficient for the project's KB/infrastructure environment without reuse of the normal working project's Python environment.

## INPUTS

Fresh clean clone.

## COMMANDS_OR_EXACT_PROCEDURE

Before activation record:

```bash
command -v python3
python3 --version
env | grep -E '^(VIRTUAL_ENV|PYTHONPATH)=' || true
```

Create:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then record:

```bash
command -v python
python --version
python -m pip --version
python - <<'PY'
import sys
import yaml
print(sys.prefix)
print(yaml.__version__)
PY
```

Verify resolved `sys.prefix` is inside the fresh-clone sandbox and does not equal the working-project environment.

`PYTHONPATH` must not inject the working repository or another project environment.

## EXPECTED_OUTPUTS

```text
Python version
pip version
PyYAML version
venv path classification
environment_reuse_detected=true|false
requirements_install_status
```

## PASS

- a new sandbox-local `.venv` is created;
- `requirements.txt` installation succeeds;
- PyYAML is available;
- no working-environment reuse;
- no undocumented infrastructure dependency is needed.

## TEST_FAIL

- infrastructure tools require a dependency not declared by canonical baseline;
- successful operation depends on leaked working-project Python state.

## TEST_BLOCKED

- package-index/network outage;
- host Python lacks usable `venv`;
- host-level package installation failure unrelated to repository dependency definition.

## EVIDENCE_TO_CAPTURE

```text
logs/fc04_environment.log
artifacts/fc04_environment.yaml
```

## STOP_RULE

FAIL or BLOCKED → STOP.

# FC-05 — CANONICAL KB VALIDATION

## PURPOSE

Verify that the freshly cloned canonical Knowledge Base validates in the newly reconstructed infrastructure environment.

## INPUTS

Fresh clone + fresh `.venv`.

## COMMANDS_OR_EXACT_PROCEDURE

```bash
python scripts/kb_refresh.py --check
python scripts/kb_validate.py
python scripts/kb_validate.py --strict
git diff --check
git status --porcelain=v1 -uall
```

Capture stdout, stderr and exit status for every command.

## EXPECTED_OUTPUTS

```text
kb_refresh_check
kb_validate
kb_validate_strict
git_diff_check
tracked_state_after_validation
```

## PASS

Required for this first test:

```text
kb_refresh.py --check: exit 0
kb_validate.py: exit 0, errors=0, warnings=0
kb_validate.py --strict: exit 0, errors=0, warnings=0
git diff --check: PASS
```

No tracked file changes.

Expected local ignored `.venv` does not count as dirty tracked state.

## TEST_FAIL

Any required validator fails, warns unexpectedly, or modifies tracked canonical state.

## TEST_BLOCKED

Only a demonstrated host-level execution problem outside the repository/environment contract.

## EVIDENCE_TO_CAPTURE

```text
logs/fc05_kb_refresh_check.log
logs/fc05_kb_validate.log
logs/fc05_kb_validate_strict.log
logs/fc05_git_diff_check.log
artifacts/fc05_validation.yaml
```

## STOP_RULE

FAIL or BLOCKED → STOP.

# FC-06 — MACHINE-LOCAL MAPPING RECONSTRUCTION

## PURPOSE

Verify that a new machine can reconstruct required machine-local configuration from canonical tracked material without copying configuration from the normal working clone.

## INPUTS

```text
configs/local_paths.example.yaml
physical machine-local location of EXP-TAIPAN-001
```

## COMMANDS_OR_EXACT_PROCEDURE

Create only from tracked example:

```bash
cp configs/local_paths.example.yaml configs/local_paths.yaml
```

Populate a real physical path only for:

```text
EXP-TAIPAN-001
```

Mappings not required for the first test:

```text
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

They may remain neutral placeholders and must not be resolved during this test.

Do not consult or copy the working repository's `configs/local_paths.yaml`.

Verify:

```bash
git check-ignore -q configs/local_paths.yaml
git ls-files --error-unmatch configs/local_paths.yaml
git status --porcelain=v1 -uall
```

Expected semantics:

- `git check-ignore` succeeds;
- `git ls-files --error-unmatch configs/local_paths.yaml` fails because the file must not be tracked.

## EXPECTED_OUTPUTS

```text
mapping_source=tracked_example
EXP-TAIPAN-001_mapping_present=true
other_mappings_required=false
local_paths_ignored=true
local_paths_tracked=false
```

## PASS

- mapping reconstructed only from tracked example;
- real physical path added only for `EXP-TAIPAN-001`;
- logical ID unchanged;
- local file is ignored and untracked;
- no old-machine config used.

## TEST_FAIL

- tracked example is insufficient;
- mapping requires canonical-ID modification;
- local config becomes tracked/unignored;
- working clone config is necessary.

## TEST_BLOCKED

Actual physical TAIPAN dataset location cannot be identified or accessed on the host.

## EVIDENCE_TO_CAPTURE

Private local diagnostics may record absolute path.

Canonical-review evidence must record only:

```text
dataset_id: EXP-TAIPAN-001
mapping_status: configured
physical_path: machine_local_redacted
```

Files:

```text
logs/fc06_local_paths.log
artifacts/fc06_local_paths.yaml
```

## STOP_RULE

FAIL or BLOCKED → STOP.

# FC-07 — EXP-TAIPAN-001 READ-ONLY IDENTITY VERIFICATION

## PURPOSE

Verify that the externally stored TAIPAN raw archive connected through the fresh sandbox mapping is byte-identical to the canonical reviewed A-002 inventory.

## INPUTS

```text
sandbox configs/local_paths.yaml
EXP-TAIPAN-001 mapped root
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
```

## COMMANDS_OR_EXACT_PROCEDURE

Use the accepted canonical FC-07 procedure exactly as documented in:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

Do not redesign, simplify, filter or substitute the verifier during test execution.

Canonical universe:

```text
CANONICAL_FILES =
complete A-002 inventory for dataset_id == EXP-TAIPAN-001
```

Actual universe:

```text
ACTUAL_FILES =
all regular files recursively under the mapped EXP-TAIPAN-001 dataset root,
represented by dataset-root-relative POSIX paths
```

Required semantics:

```text
MISSING = canonical - actual
EXTRA = actual - canonical
```

For common paths:

```text
file_size_bytes
SHA-256
```

must match.

No extension-only filter is allowed.

Symlink/junction ambiguity, unsupported filesystem object or path escape is fail-closed.

Raw files are read-only.

Do not alter permissions or remount the dataset as part of the test.

## EXPECTED_OUTPUTS

At minimum:

```text
DATASET_ID
EXPECTED_FILES
ACTUAL_FILES
MISSING
EXTRA
SIZE_MISMATCH
SHA256_MISMATCH
STATUS
exit_code
```

Mismatch paths, if any, must be sorted and dataset-root-relative.

## PASS

Exactly:

```text
MISSING=0
EXTRA=0
SIZE_MISMATCH=0
SHA256_MISMATCH=0
STATUS=PASS
exit_code=0
```

and no link/path safety error.

## TEST_FAIL

Any of:

```text
MISSING > 0
EXTRA > 0
SIZE_MISMATCH > 0
SHA256_MISMATCH > 0
symlink/junction ambiguity
path escape
unsupported object
readable regular file cannot reproduce expected identity
evidence of raw-data mutation caused by test
```

## TEST_BLOCKED

- dataset unavailable/unmounted;
- storage device unavailable;
- whole-dataset permission/I/O condition prevents valid census before identity comparison can be completed.

## EVIDENCE_TO_CAPTURE

Full local log:

```text
logs/fc07_verification.log
```

Sanitized summary:

```text
artifacts/fc07_summary.yaml
```

Required schema:

```yaml
dataset_id: EXP-TAIPAN-001
canonical_inventory: 04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
expected_files: <int>
actual_files: <int>
missing: <int>
extra: <int>
size_mismatch: <int>
sha256_mismatch: <int>
status: PASS|FAIL
exit_code: <int>
dataset_physical_path: machine_local_redacted
```

If mismatches occur, preserve dataset-relative mismatch paths.

## STOP_RULE

FAIL or BLOCKED → STOP.

No repair/rerun within the same test identity unless separately reviewed.

# FC-08 — PORTABILITY / RECOVERY BOUNDARY CHECKS

## PURPOSE

Verify that a clean clone contains enough canonical documentation and functioning infrastructure utilities to distinguish:

```text
Git clone != external data restoration
Work recovery != disaster recovery
synchronization != backup
```

without prior chat or working-clone knowledge.

## INPUTS

Fresh clone only.

## COMMANDS_OR_EXACT_PROCEDURE

Inspect canonical:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
03_Protocols/RESEARCH_KB_GUIDE.md
scripts/README.md
```

Record binary PASS/FAIL answers for:

```text
tracked-vs-external architecture understood
local_paths reconstruction understood
external identity understood
Work recovery boundary understood
disaster recovery boundary understood
sync-vs-backup distinction understood
minimum backup principle understood
Tier-1/Tier-2 scope understood
```

Then run:

```bash
python scripts/work_recovery.py selftest
```

The selftest operates only on its disposable fixture and must not modify canonical project state.

## EXPECTED_OUTPUTS

```text
boundary check matrix
work_recovery selftest exit status
tracked-state-after-selftest
```

## PASS

All documentation checks are understandable from fresh clone alone, selftest succeeds, and no tracked project state changes.

## TEST_FAIL

- a required boundary depends on hidden knowledge;
- selftest fails in supported Tier-1 environment;
- canonical project state is unexpectedly modified.

## TEST_BLOCKED

Host restriction prevents disposable selftest fixture operation.

## EVIDENCE_TO_CAPTURE

```text
logs/fc08_boundary_review.log
logs/fc08_work_recovery_selftest.log
artifacts/fc08_boundary_checks.yaml
```

## STOP_RULE

FAIL or BLOCKED → STOP.

# FC-09 — TERMINAL ACCEPTANCE AND EVIDENCE SEAL

## PURPOSE

Establish the final execution result and seal reproducible evidence without promoting canonical project state.

## INPUTS

All prior phase evidence.

## COMMANDS_OR_EXACT_PROCEDURE

Final repository checks:

```bash
git rev-parse HEAD
git rev-parse origin/main
git status --porcelain=v1 -uall
git diff --check
git diff --name-only
git diff --cached --name-only
```

Confirm:

```text
HEAD == authorized_test_commit
origin/main == authorized_test_commit
```

Expected local ignored state may include:

```text
.venv/
configs/local_paths.yaml
```

No tracked changes or staged files are permitted.

Create:

```text
artifacts/phase_matrix.yaml
artifacts/test_manifest.yaml
artifacts/checksums.sha256
```

Compute SHA-256 for all durable evidence files excluding the checksum file itself until the final checksum step.

## EXPECTED_OUTPUTS

Phase matrix:

```yaml
FC-01: PASS
FC-02: PASS
FC-03: PASS
FC-04: PASS
FC-05: PASS
FC-06: PASS
FC-07: PASS
FC-08: PASS
FC-09: PASS
```

Execution result:

```text
PASS | FAIL | BLOCKED
```

Canonical state during local execution:

```text
canonical_fresh_clone_test_passed: pending_review
```

## PASS

All mandatory phases PASS, evidence bundle complete and internally consistent, final tracked repository clean, tested commit unchanged.

## TEST_FAIL

Any mandatory phase FAIL or unexpected tracked mutation exists.

## TEST_BLOCKED

No FAIL exists but one or more mandatory phases is BLOCKED.

## EVIDENCE_TO_CAPTURE

```text
logs/fc09_final_state.log
artifacts/fc09_final_state.yaml
artifacts/phase_matrix.yaml
artifacts/test_manifest.yaml
artifacts/checksums.sha256
```

## STOP_RULE

After evidence seal and execution report:

```text
STOP
```

Do not promote canonical state.

# EVIDENCE_BUNDLE

Required durable review bundle:

```text
artifacts/
├── test_manifest.yaml
├── phase_matrix.yaml
├── fc01_sandbox_isolation.yaml
├── fc02_clone_identity.yaml
├── fc03_repository_state.yaml
├── fc04_environment.yaml
├── fc05_validation.yaml
├── fc06_local_paths.yaml
├── fc07_summary.yaml
├── fc08_boundary_checks.yaml
├── fc09_final_state.yaml
└── checksums.sha256
```

Required local logs:

```text
logs/
├── fc01_preflight.log
├── fc02_clone.log
├── fc03_git_state.log
├── fc04_environment.log
├── fc05_kb_refresh_check.log
├── fc05_kb_validate.log
├── fc05_kb_validate_strict.log
├── fc05_git_diff_check.log
├── fc06_local_paths.log
├── fc07_verification.log
├── fc08_boundary_review.log
├── fc08_work_recovery_selftest.log
└── fc09_final_state.log
```

# TEST_MANIFEST_SCHEMA

`artifacts/test_manifest.yaml` must contain at least:

```yaml
test_id: FC-PORTABILITY-001
specification_id: FRESH-CLONE-ACCEPTANCE-SPEC
specification_version: "1.0"

repository: oregu93/cef-dy
branch: main
authorized_test_commit: "<sha>"

execution_environment:
  class: local_tier1_linux_sandbox
  platform_family: "<recorded Linux distribution family>"

start_timestamp_utc: "<ISO-8601>"
end_timestamp_utc: "<ISO-8601>"

git_version: "<version>"
python_version: "<version>"
pip_version: "<version>"
pyyaml_version: "<version>"

sandbox_isolation_status: PASS|FAIL|BLOCKED
clone_identity_status: PASS|FAIL|BLOCKED
repository_cleanliness_status: PASS|FAIL|BLOCKED
environment_bootstrap_status: PASS|FAIL|BLOCKED
kb_validation_status: PASS|FAIL|BLOCKED
local_mapping_status: PASS|FAIL|BLOCKED
fc07_status: PASS|FAIL|BLOCKED
boundary_status: PASS|FAIL|BLOCKED
terminal_status: PASS|FAIL|BLOCKED

execution_result: PASS|FAIL|BLOCKED
canonical_fresh_clone_test_passed: pending_review

evidence_manifest_status: sealed
```

# LOCAL_DIAGNOSTIC_EVIDENCE

Local diagnostic logs may contain where needed:

```text
absolute sandbox root
absolute working repository path
absolute raw dataset path
local username
hostname
mount information
```

This information is permitted only when useful to prove isolation or diagnose a failure.

Local diagnostic evidence is not automatically canonicalizable.

# CANONICAL_DURABLE_EVIDENCE

The review/capture candidate should retain:

```text
test ID
authorized tested commit
repository/branch
platform family
kernel/architecture if useful
Git/Python/pip/PyYAML versions
phase statuses
validator statuses
FC-07 summary counts
execution result
evidence checksums
technical review result
Project Control disposition
```

Absolute machine paths should not be required.

# PRIVACY_NORMALIZATION

Normalize or omit:

```text
/home/<username>/...
hostname
raw dataset absolute path
sandbox absolute path
credentials
mount credentials
cloud-provider private paths
```

Preferred normalized forms:

```yaml
sandbox_path: machine_local_redacted
working_repository_path: machine_local_redacted
dataset_physical_path: machine_local_redacted
dataset_id: EXP-TAIPAN-001
```

Dataset-relative paths from the canonical inventory are not private machine paths and may be preserved when required for mismatch evidence.

# TEST_FAIL_RULES

`TEST_FAIL` means the tested portability contract was validly exercised and failed.

Examples:

- fresh canonical clone unexpectedly dirty;
- tracked bootstrap files missing;
- hidden infrastructure dependency required;
- KB validators fail;
- fresh-machine mapping cannot be reconstructed from canonical example;
- FC-07 content mismatch;
- hidden working-clone state proves necessary;
- recovery selftest fails on supported platform;
- documentation is insufficient for required portability/recovery boundary;
- tracked repository changes unexpectedly.

Any mandatory phase FAIL yields:

```text
execution_result: FAIL
fresh_clone_test_passed: false
```

# TEST_BLOCKED_RULES

`TEST_BLOCKED` means a valid acceptance determination could not be made due to prerequisite/environment/authorization conditions.

Examples:

- authorization missing;
- canonical `main` advanced after authorization;
- GitHub/network unavailable;
- package index unavailable;
- sandbox isolation ambiguous;
- insufficient disk;
- system Python lacks required `venv` support;
- external dataset unavailable;
- storage device unavailable;
- host permissions prevent valid test.

If no phase FAIL exists but any mandatory phase is BLOCKED:

```text
execution_result: BLOCKED
fresh_clone_test_passed: false
```

A BLOCKED result may never be interpreted as PASS.

# PASS_CRITERIA

Local execution may report:

```text
execution_result: PASS
```

if and only if all mandatory conditions hold:

1. valid execution authorization exists;
2. test uses exactly the authorized commit;
3. FC-01 PASS;
4. sandbox is isolated from normal working clone;
5. FC-02 PASS;
6. clone comes directly from canonical GitHub;
7. Git metadata is independent;
8. `HEAD == origin/main == authorized_test_commit`;
9. FC-03 PASS;
10. fresh tracked repository is clean;
11. FC-04 PASS;
12. new sandbox-local venv is used;
13. tracked `requirements.txt` is sufficient;
14. FC-05 PASS;
15. all canonical KB checks pass with zero errors/warnings;
16. FC-06 PASS;
17. only `EXP-TAIPAN-001` requires real physical mapping;
18. sandbox `local_paths.yaml` is reconstructed from tracked example;
19. mapping remains ignored/untracked;
20. FC-07 PASS;
21. no MISSING;
22. no EXTRA;
23. no size mismatch;
24. no SHA mismatch;
25. no link/junction/path-escape ambiguity;
26. no raw-data write;
27. FC-08 PASS;
28. recovery selftest passes;
29. portability/recovery distinctions are reconstructable from canonical docs;
30. FC-09 PASS;
31. final tracked clone is clean;
32. all phase evidence is complete;
33. evidence checksums are sealed;
34. no normal-working-repository state was used as test input.

Canonical:

```text
fresh_clone_test_passed: true
```

is necessary and sufficient only after:

```text
execution_result == PASS
AND
07 technical review == A
AND
Project Control acceptance
AND
separate canonical capture
```

# STOP_CONDITIONS

Immediate stop on:

```text
STOP_NO_AUTHORIZATION
STOP_STALE_AUTHORIZATION
STOP_SANDBOX_ISOLATION_FAILURE
STOP_CLONE_IDENTITY_FAILURE
STOP_ENVIRONMENT_REUSE
STOP_VALIDATION_FAILURE
STOP_MAPPING_FAILURE
STOP_DATASET_UNAVAILABLE
STOP_FC07_MISMATCH
STOP_RAW_MUTATION_RISK
STOP_RECOVERY_SELFTEST_FAILURE
STOP_UNEXPECTED_TRACKED_CHANGE
```

Do not repair-and-continue across a STOP condition under the same test identity unless Project Control explicitly authorizes a controlled rerun.

# SANDBOX_RETENTION_POLICY

Canonical principle:

```text
execution sandbox is disposable;
execution evidence is not.
```

The sandbox must not be deleted before:

```text
execution complete
evidence sealed
07 technical review complete
Project Control disposition
```

unless Project Control explicitly releases it earlier.

On PASS:

- retain until technical review and governance disposition;
- then deletion is allowed.

On FAIL or BLOCKED:

- retain until root cause and disposition are reviewed;
- do not delete evidence needed to understand failure.

After sandbox disposal, retain at minimum:

```text
durable evidence bundle
relevant execution logs
evidence checksums
07 technical review
Project Control disposition
```

No indefinite sandbox retention is required.

# TECHNICAL_REVIEW_CONTRACT

Return execution evidence to:

```text
07 - Research Software & Infrastructure
```

The review must independently verify:

1. specification/test identity;
2. authorized test commit;
3. sandbox isolation;
4. canonical clone source;
5. Git independence from working clone;
6. fresh tracked-state cleanliness;
7. environment isolation;
8. requirements-only bootstrap;
9. KB validation outputs;
10. local mapping reconstruction provenance;
11. FC-07 exact procedure identity;
12. FC-07 census semantics;
13. FC-07 counts and exit code;
14. read-only raw-data boundary;
15. recovery selftest;
16. portability/recovery documentation boundary;
17. final repository cleanliness;
18. evidence checksums;
19. PASS/FAIL/BLOCKED classification;
20. privacy normalization.

Technical-review decisions:

```text
A — ACCEPT
B — ACCEPT_WITH_LIMITATIONS
C — REJECT_EXECUTION_RESULT
```

For promotion to canonical:

```text
fresh_clone_test_passed: true
```

technical review must be:

```text
A
```

# CANONICAL_CAPTURE_CONTRACT

The local executor must never alter canonical project state.

After:

```text
execution_result: PASS
+
07 technical review: A
+
Project Control acceptance
```

Project Control may authorize a separate canonical transition.

A future capture may record fields equivalent to:

```yaml
fresh_clone_test:
  test_id: FC-PORTABILITY-001
  specification_id: FRESH-CLONE-ACCEPTANCE-SPEC
  specification_version: "1.0"
  tested_commit: "<authorized_test_commit>"
  execution_status: completed
  execution_result: PASS
  technical_review_status: completed
  technical_review_decision: A
  acceptance_status: accepted
  fresh_clone_test_passed: true
```

The exact canonical metadata location remains a Project Control decision.

The execution sandbox itself is not canonical project state.

# LIFECYCLE TERMINAL STATE BEFORE EXECUTION AUTHORIZATION

This proposed specification ends with:

```yaml
specification_status: proposed_for_freeze
execution_status: not_started
execution_authorized: false
fresh_clone_test_passed: false
stage03r_authorized: false
```

No test execution is authorized by this specification draft.

