# PORTABILITY-BASELINE-SPEC

```yaml
specification_id: PORTABILITY-BASELINE-SPEC
specification_version: "1.0"
specification_status: frozen
infrastructure_design_status: accepted

job_id: WKB-R1-PORTABILITY-BASELINE-001
execution_status: not_started
execution_authorized: false

execution_role: WKB-R1
recommended_execution_model: GPT-5.6 Sol / Medium

repository: oregu93/cef-dy
branch: main

design_baseline_commit: fec1d643db70c602290cdc29a1b069f43330b447
execution_baseline_policy: canonical_execution_authorization_commit

commit_authorized: false
push_authorized: false
stage_authorized: false
stage03r_authorized: false
```

# IDENTITY

This specification defines the first controlled implementation of the accepted portable-environment and backup/recovery baseline for the CEF Dy / DyFeO3 project.

It prepares the canonical repository for a later independent fresh-clone acceptance test.

It does not itself perform that test, perform backup, copy external data, configure synchronization, or authorize scientific execution.

Canonical repository:

```text
repository: oregu93/cef-dy
branch: main
design_baseline_commit:
fec1d643db70c602290cdc29a1b069f43330b447
```

Execution role:

```text
WKB-R1
```

# GOAL

Implement the smallest repository-side infrastructure layer that allows a future operator on a clean Linux machine to determine, from canonical tracked sources:

1. how to obtain the canonical Git-tracked project;
2. how to create the minimum KB/infrastructure Python environment;
3. how to reconstruct machine-local path mappings;
4. how to reconnect externally stored datasets without making physical paths part of canonical identity;
5. how to verify `EXP-TAIPAN-001` read-only against existing canonical inventory/provenance;
6. what `work_recovery.py` protects and does not protect;
7. what minimum off-machine backup policy applies;
8. how a later fresh-clone acceptance test must be performed;
9. what Windows compatibility is and is not currently promised.

The implementation must leave the project ready for a later fresh-clone test without claiming that such a test has passed.

Required terminal distinction:

```text
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

# RATIONALE

The Git-tracked repository is already substantially portable.

The remaining infrastructure gap is not a need for a new software platform. It is the absence of one concise canonical operational guide linking existing Git, Python, local-path, external-data, recovery, and backup rules into a fresh-machine reconstruction procedure.

The project already has:

- Git/GitHub as canonical tracked state;
- portable Markdown/YAML;
- a minimal Python dependency declaration;
- ignored machine-local path configuration;
- canonical external-data identities independent of absolute paths;
- reviewed TAIPAN file inventories with relative path, size, and SHA-256;
- a mature Work/session recovery utility.

Therefore this job must prefer documentation and reuse over new infrastructure.

# BASELINE

Design baseline:

```text
fec1d643db70c602290cdc29a1b069f43330b447
```

The specification is designed against that commit.

The design baseline is historical design provenance. It is not the future execution HEAD requirement.

## Authorization lifecycle

The non-self-referential infrastructure authorization lifecycle is mandatory:

```text
1. Freeze this specification against the design baseline.
2. Materialize the frozen specification canonically.
3. Commit and push the specification freeze.
4. Project Control verifies the freeze commit.
5. A separate canonical authorization commit records:
     specification_freeze_commit: <verified freeze commit>
     execution_authorized: true
     execution_baseline_policy: canonical_execution_authorization_commit
6. WKB-R1 executes only while that authorization commit remains canonical HEAD.
```

The specification must not contain the SHA of its own future freeze commit.

At execution preflight:

```text
branch == main
HEAD == origin/main
canonical execution_authorized == true
canonical specification_freeze_commit matches this reviewed frozen specification
latest commit modifying 00_Project/PROJECT_METADATA.yaml == HEAD
```

If `main` advances after authorization without a fresh Project Control authorization/re-baselining decision:

```text
STOP
```

# INPUTS

Mandatory canonical inputs:

```text
00_Project/PROJECT_METADATA.yaml

README.md
requirements.txt
configs/local_paths.example.yaml

03_Protocols/RESEARCH_KB_GUIDE.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/CHAT_BOOTSTRAPS.md

scripts/README.md
scripts/work_recovery.py
scripts/kb_refresh.py
scripts/kb_validate.py

02_Work_Checkpoints/W02-02R-A-002.md
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
04_Results/Stage02R/W02-02R-A-002/provenance_manifest.yaml
```

Repository structural inputs:

```text
.gitignore
.gitattributes
PROJECT_MANIFEST.yaml
```

Known local objects, if present, are protection-only inputs:

```text
00_Project/C001_V1_1_EXECUTION_AUTHORIZATION.yaml
00_Project/C002_EXECUTION_AUTHORIZATION.yaml

04_Results/Stage02R/W02-02R-C-001-v1.1-first-production-diagnostic/
04_Results/Stage02R/W02-02R-C-002-first-production-attempt/
```

They must not be used as canonical portability sources.

# OUTPUTS

The complete write allowlist contains exactly four paths.

## REQUIRED_CREATE

Exactly:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

## REQUIRED_MODIFY

Exactly:

```text
configs/local_paths.example.yaml
```

## OPTIONAL_MODIFY

Only if needed for minimal navigation:

```text
README.md
scripts/README.md
```

`README.md` and `scripts/README.md` are not required to change.

If no navigation change is needed, they must remain unchanged.

No other tracked output is authorized.

Required execution report outputs:

```text
JOB_ID
SPECIFICATION_ID
SPECIFICATION_VERSION

EXECUTION_AUTHORIZATION_HEAD
SPECIFICATION_FREEZE_COMMIT

FILES_CREATED
FILES_MODIFIED
FILES_UNCHANGED
UNEXPECTED_FILES

GUIDE_CONTENT_CHECK
LOCAL_PATHS_EXAMPLE_CHECK
EXTERNAL_DATA_VERIFICATION_METHOD
REQUIREMENTS_IDENTITY_CHECK
RECOVERY_BOUNDARY_CHECK
BACKUP_POLICY_CHECK
FRESH_CLONE_CONTRACT_CHECK
CROSS_PLATFORM_SCOPE_CHECK

PROTECTED_FILE_IDENTITY_CHECK
KNOWN_LOCAL_UNTRACKED_CHECK

VALIDATION_RESULTS
TEST_RESULTS
DIFF_REVIEW

implementation_ready_for_fresh_clone_test
fresh_clone_test_passed

STAGED_FILES
COMMIT_PERFORMED
PUSH_PERFORMED

FAILED_OR_AMBIGUOUS_ITEMS
STOP_CONDITION_STATUS
```

Required terminal values for successful implementation:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false

staged_files: []
commit_performed: false
push_performed: false
```

# EDIT_ALLOWED

The complete write allowlist is exactly:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
configs/local_paths.example.yaml
README.md
scripts/README.md
```

No implicit write authority exists.

## FILES_ALLOWED_TO_CREATE

Exactly:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

Creation of any other tracked path is forbidden.

## FILES_ALLOWED_TO_MODIFY

Required:

```text
configs/local_paths.example.yaml
```

Optional, navigation only:

```text
README.md
scripts/README.md
```

## Per-file restrictions

### `03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md`

May be created as a new human-readable infrastructure protocol.

It must reference rather than redefine scientific semantics already governed elsewhere.

It may document:

- Git portability;
- Python environment bootstrap;
- machine-local paths;
- external-data reconnection;
- external-data identity;
- Work recovery boundaries;
- backup/disaster-recovery boundaries;
- fresh-clone procedure;
- cross-platform support tiers;
- links to canonical protocols.

It must not create new scientific, provenance, authorization, or status semantics.

### `configs/local_paths.example.yaml`

Modification is required.

Only neutralization and explanatory cleanup are authorized.

Existing logical keys must remain:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

Personal paths such as:

```text
/home/oleg/...
```

must be replaced with clearly illustrative neutral paths such as:

```text
/path/to/CEF_Dy_Data/TAIPAN_raw
/path/to/CEF_Dy_Data/XRD_raw
/path/to/CEF_Dy_Data/Work_outputs_large
/path/to/CEF_Dy_Data/private
```

or an equally unambiguous neutral equivalent.

No dataset ID may be renamed.

No new machine-local canonical identity semantics may be introduced.

### `README.md`

Modification is optional.

Only a minimal navigation/reference addition to the new infrastructure guide is authorized.

If no such navigation addition is needed, leave the file unchanged.

No generated `AUTO` region may change.

No scientific, repository-policy, external-data, or workflow semantics may be rewritten.

### `scripts/README.md`

Modification is optional.

Only a minimal link/reference to the new infrastructure guide is authorized where useful.

If no such navigation addition is needed, leave the file unchanged.

Existing recovery commands and behavioral descriptions must remain semantically unchanged.

# AUDIT_ONLY

These tracked files may be read for implementation/reference but must remain byte-identical:

```text
requirements.txt
.gitignore
.gitattributes
PROJECT_MANIFEST.yaml

00_Project/PROJECT_METADATA.yaml

03_Protocols/RESEARCH_KB_GUIDE.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/CHAT_BOOTSTRAPS.md

scripts/work_recovery.py
scripts/kb_refresh.py
scripts/kb_validate.py

02_Work_Checkpoints/W02-02R-A-002.md

04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
04_Results/Stage02R/W02-02R-A-002/provenance_manifest.yaml
```

If present locally:

```text
configs/local_paths.yaml
```

is also audit-only for this job and must not be modified.

# FORBIDDEN

The write policy is default-deny.

Any path not listed under `EDIT_ALLOWED` is non-editable.

The following are explicitly protected.

## Scientific state / governance

```text
00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md

00_Project/DECISION_REGISTER.yaml
00_Project/EVIDENCE_REGISTER.yaml
00_Project/HYPOTHESIS_REGISTER.yaml
00_Project/MODEL_REGISTER.yaml
00_Project/RESULT_REGISTER.yaml
```

`00_Project/PROJECT_METADATA.yaml` is audit-only and byte-protected during WKB-R1 execution.

## Frozen scientific protocols

```text
03_Protocols/STAGE02R_*.md
```

## Scientific implementations/configurations

```text
scripts/stage02r/**
```

## Provenance-sensitive Stage02R result layer

```text
04_Results/Stage02R/**
```

except these exact audit-only references:

```text
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
04_Results/Stage02R/W02-02R-A-002/provenance_manifest.yaml
```

The exceptions are read-only, not editable.

## Historical Work checkpoints

```text
02_Work_Checkpoints/W02-*.md
```

except:

```text
02_Work_Checkpoints/W02-02R-A-002.md
```

which is audit-only.

## Legacy

```text
Archive/legacy/**
```

## External/local/private data

Do not modify, copy, move, synchronize, restore, or back up as part of this job:

```text
CEF_Dy_Data/**
data/**
local_data/**
private/**
secrets/**
credentials/**
```

and any filesystem object resolved through local mappings such as:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

External data may only be discussed in documentation.

## Known local untracked historical objects

The following remain completely outside implementation scope:

```text
00_Project/C001_V1_1_EXECUTION_AUTHORIZATION.yaml
00_Project/C002_EXECUTION_AUTHORIZATION.yaml

04_Results/Stage02R/W02-02R-C-001-v1.1-first-production-diagnostic/
04_Results/Stage02R/W02-02R-C-002-first-production-attempt/
```

They must not be:

```text
modified
deleted
moved
renamed
reconstructed
staged
committed
incorporated into canonical DR policy as resolved objects
```

Their later provenance/disposition review is separate.

# ENVIRONMENT_BOUNDARY

The infrastructure environment remains deliberately minimal.

Canonical dependency declaration:

```text
requirements.txt
```

must remain byte-identical.

Current infrastructure model:

```text
Git
Python 3
python venv
pip
requirements.txt
```

`requirements.txt` is the KB/infrastructure dependency baseline.

This job must not add:

```text
NumPy
SciPy
pandas
Matplotlib
PyCrystalField
McPhase
Mantid
scientific-fitting dependencies
```

merely for future scientific use.

Scientific/fitting/modeling environments are a separate future concern and require stage/job-specific scientific design.

The new guide must document a Linux bootstrap equivalent to:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The job must not claim a tested Python minor-version compatibility range.

The later fresh-clone test must record the actual Python and PyYAML versions used.

No Docker, Conda, Poetry, virtual-machine framework, environment lock platform, or container system is introduced.

# MACHINE_LOCAL_CONFIG_MODEL

`configs/local_paths.yaml` remains:

```text
machine-local
Git-ignored
non-canonical as physical path mapping
reconstructed per machine
```

A fresh machine reconstructs it from:

```text
configs/local_paths.example.yaml
```

Expected documented procedure:

```bash
cp configs/local_paths.example.yaml configs/local_paths.yaml
```

Then the operator replaces neutral illustrative paths with real local paths.

Required logical identities remain stable:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

The guide must explicitly distinguish:

```text
dataset ID
    canonical logical identity

local_paths.yaml path
    machine-local physical resolution
```

Required safety check:

```bash
git check-ignore -q configs/local_paths.yaml
```

A machine-local absolute path must never become scientific provenance or dataset identity.

# EXTERNAL_DATA_IDENTITY_MODEL

Canonical external-data identity is independent of physical storage provider and absolute path.

Where available, identity is based on:

```text
dataset_id / artifact_id
dataset-relative source path
byte size
SHA-256 checksum
canonical provenance records
```

For `EXP-TAIPAN-001`, the canonical read-only verification reference is:

```text
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
```

The required fields are:

```text
dataset_id
source_file
file_size_bytes
source_checksum
```

The new guide must state that:

```text
local absolute path
cloud-provider path
mount point
sync folder name
```

are physical storage details and not canonical dataset identity.

## External verification decision

No new tracked verifier utility is authorized.

The implementation must reuse the existing canonical inventory.

The guide must contain a small documented read-only procedure or command capable of:

1. reading `configs/local_paths.yaml`;
2. resolving `EXP-TAIPAN-001`;
3. reading the canonical A-002 `file_inventory.csv`;
4. restricting reference rows to `dataset_id == EXP-TAIPAN-001`;
5. defining the canonical comparison universe as the complete A-002 inventory for `EXP-TAIPAN-001`;
6. defining `ACTUAL_FILES` as all regular files recursively under the mapped `EXP-TAIPAN-001` dataset root, represented by dataset-root-relative POSIX paths;
7. resolving each canonical `source_file` relative to the mapped dataset root;
8. checking regular-file existence;
9. checking byte size;
10. computing SHA-256;
11. reporting missing, extra, size-mismatched, and checksum-mismatched files deterministically;
12. returning nonzero on mismatch;
13. never modifying raw data.

The actual-file universe is defined exactly as:

```text
ACTUAL_FILES =
all regular files recursively under the mapped EXP-TAIPAN-001 dataset root,
represented by dataset-root-relative POSIX paths
```

The canonical-file universe is:

```text
CANONICAL_FILES =
the complete A-002 file inventory for dataset_id == EXP-TAIPAN-001
```

`MISSING` means:

```text
a canonical inventory source_file absent from ACTUAL_FILES
```

`EXTRA` means:

```text
a regular file present in the actual recursive census
but absent from the canonical A-002 inventory
```

`SIZE_MISMATCH` means:

```text
a path present in both universes whose actual byte size differs
from canonical file_size_bytes
```

`SHA256_MISMATCH` means:

```text
a path present in both universes whose actual SHA-256 differs
from canonical source_checksum
```

No extension-only filter may redefine the actual or canonical census.

In particular, a filter such as:

```text
*.dat
```

must not be used to limit `ACTUAL_FILES` unless the canonical A-002 inventory itself defines the complete comparison universe that way.

The A-002 inventory, not a guessed filename extension, defines the canonical comparison set.

Symlinks and junctions must not be silently treated as regular dataset files.

If the recursive census encounters:

- a symlink;
- a junction;
- an unresolved link-like filesystem object;
- a path that would escape outside the mapped dataset root;
- an ambiguity about whether traversal remains inside the dataset root;

the verification must fail closed.

No symlink/junction target outside the mapped dataset root may be followed as if it were canonical dataset content.

The documented procedure may use:

```text
Python standard library
+
PyYAML already present in requirements.txt
```

It must not require a new dependency.

It must reject or report path traversal or path escape rather than normalizing it silently.

Expected deterministic summary format should contain at least:

```text
DATASET_ID
EXPECTED_FILES
ACTUAL_FILES
MISSING
EXTRA
SIZE_MISMATCH
SHA256_MISMATCH
STATUS
```

Sorted mismatch path lists must be emitted when non-empty.

Success requires:

```text
MISSING=0
EXTRA=0
SIZE_MISMATCH=0
SHA256_MISMATCH=0
STATUS=PASS
```

The procedure is documentation prepared for later FC-07.

This implementation job must not run it against raw TAIPAN data.

# WORK_RECOVERY_BOUNDARY

The existing behavior of:

```text
scripts/work_recovery.py
```

must remain unchanged.

The guide must state:

```text
work_recovery.py
=
interrupted Work/session state preservation and resume diagnosis
```

It may protect, subject to its existing protocol:

- staged state;
- unstaged state;
- non-ignored untracked Work state;
- index state;
- diffs;
- hashes;
- control context;
- recovery diagnostics.

It must explicitly not be represented as guaranteeing:

- workstation-loss recovery;
- disk-loss recovery;
- off-machine backup;
- raw-data backup;
- ignored external-data backup;
- private-material backup;
- Git hosting;
- scientific validation;
- scientific authorization;
- automatic restoration.

The authoritative behavioral contract remains:

```text
03_Protocols/WORK_RECOVERY_PROTOCOL.md
```

The new guide must link to it rather than duplicate detailed snapshot semantics.

# BACKUP_POLICY_BOUNDARY

This job documents backup policy only.

It performs no backup.

Minimum required principle:

```text
irreplaceable non-Git data
=
primary working copy
+
independent off-machine copy
```

The two copies must not depend on the same physical disk/device.

The guide must distinguish:

```text
synchronization
backup
canonical identity
physical storage
provenance
```

Synchronization must not be described as equivalent to backup.

A synchronization provider may be one off-machine layer, but a synchronized folder alone is not sufficient evidence of independent backup safety.

The guide may state as `useful`, not mandatory:

```text
third independent copy of especially valuable data
```

and:

```text
periodic git bundle stored outside GitHub
```

The guide must state that GitHub remains canonical for the tracked repository even if a Git bundle or archive exists elsewhere.

No provider-specific setup is performed.

No Yandex.Disk configuration is performed.

No files are copied to or from any backup provider.

No backup application, NAS, DVC, Git-LFS, database, or backup orchestration platform is introduced.

# CROSS_PLATFORM_SCOPE

Formal portability tiers:

```text
Tier 1:
Linux Mint / Ubuntu-family Linux

Tier 2:
Windows reasonable compatibility only
```

Tier 1 receives the later formal fresh-clone acceptance test.

Tier 2 means:

- tracked Markdown/YAML/Git architecture should remain portable;
- existing Python utilities should not be unnecessarily made Linux-only;
- existing Windows-compatible recovery behavior is preserved;
- Windows fresh-clone acceptance is not required by this job;
- no Windows CI matrix is required;
- future scientific execution environments may define their own platform support.

The guide must not imply full Windows scientific-workflow equivalence.

# FRESH_CLONE_CONTRACT

The fresh-clone acceptance test is a separate future execution operation.

This implementation job prepares the instructions and prerequisites only.

It must never report:

```text
fresh_clone_test_passed: true
```

## FC-01 — CLEAN LINUX CONTEXT

Purpose:

Verify that the test does not depend on the original workstation.

Starting context must not reuse:

```text
existing repository clone
existing .venv
existing configs/local_paths.yaml
existing CEF_Dy_Backup
original machine's project directory
```

### PASS

A clean Tier-1 Linux context is documented and identified.

No original repository clone or local environment is reused.

### FAIL

Any required project state is implicitly inherited from the original workstation.

## FC-02 — CANONICAL CLONE

Procedure:

```bash
git clone <canonical repository>
cd cef-dy
git switch main
git pull --ff-only

git rev-parse HEAD
git rev-parse origin/main
git status --short
```

The exact repository URL may be documented using the canonical GitHub repository.

### PASS

```text
HEAD == origin/main
branch == main
tracked worktree clean
```

The tested commit is recorded.

### FAIL

- clone fails;
- wrong branch;
- HEAD differs from origin/main;
- unexpected tracked modification exists.

## FC-03 — VENV + REQUIREMENTS BOOTSTRAP

Procedure:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Record:

```text
Python version
PyYAML version
```

### PASS

- venv creation succeeds;
- installation succeeds from tracked `requirements.txt`;
- no undocumented Python dependency is required for KB/infrastructure validation.

### FAIL

Any KB/infrastructure bootstrap requires a package absent from the tracked baseline or undocumented manual environment repair.

## FC-04 — KB VALIDATION

Procedure:

```bash
python scripts/kb_refresh.py --check
python scripts/kb_validate.py
python scripts/kb_validate.py --strict
git diff --check
git status --short
```

### PASS

- refresh check passes;
- normal validation passes;
- strict validation passes, or matches an explicitly frozen accepted-warning policy if one exists at test time;
- diff check passes;
- validation does not alter tracked canonical files.

### FAIL

Any new validation failure, undocumented generated change, or dirty tracked repository caused by bootstrap.

## FC-05 — WORK_RECOVERY SELFTEST

Procedure:

```bash
python scripts/work_recovery.py selftest
```

### PASS

- exit success;
- disposable fixture selftest passes;
- canonical project files remain unchanged.

### FAIL

- selftest failure;
- unexpected modification to project files/index;
- undocumented platform dependency.

## FC-06 — LOCAL_PATHS RECONSTRUCTION

Starting only from tracked repository material:

```bash
cp configs/local_paths.example.yaml configs/local_paths.yaml
```

Populate the new machine's actual physical mappings.

Check:

```bash
git check-ignore -q configs/local_paths.yaml
git status --short
```

### PASS

- reconstruction instructions are sufficient;
- logical IDs are preserved;
- local file is ignored;
- no machine-specific absolute path becomes a tracked change.

### FAIL

- original-machine path knowledge is required;
- local mapping is not ignored;
- reconstruction requires modifying a canonical dataset identity.

## FC-07 — EXTERNAL DATA RECONNECTION / IDENTITY VERIFICATION

For `EXP-TAIPAN-001`:

1. independently restore, mount, or make available the intended physical dataset;
2. map its root through `configs/local_paths.yaml`;
3. run the documented read-only verification against:

```text
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
```

The canonical comparison universe is:

```text
all rows of the A-002 canonical inventory with:
dataset_id == EXP-TAIPAN-001
```

The actual comparison universe is:

```text
ACTUAL_FILES =
all regular files recursively under the mapped EXP-TAIPAN-001 dataset root,
represented by dataset-root-relative POSIX paths
```

`EXTRA` means:

```text
a regular file present in that actual recursive census
but absent from the canonical A-002 inventory
```

No extension-only filter such as:

```text
*.dat
```

may redefine the canonical or actual census unless the canonical A-002 inventory itself defines the complete universe that way.

Symlinks/junctions are not silently treated as regular dataset files.

Any symlink/junction ambiguity, unresolved link traversal, or path escape outside the mapped dataset root is fail-closed.

### PASS

```text
dataset_id == EXP-TAIPAN-001
missing files == 0
extra files == 0
size mismatches == 0
SHA-256 mismatches == 0
verification status == PASS
```

No raw file is modified.

### FAIL

Any:

- missing canonical file;
- extra regular file;
- size mismatch;
- SHA-256 mismatch;
- symlink/junction ambiguity;
- path escape outside the mapped dataset root;
- undocumented narrowing of the canonical census;
- write to raw data.

FC-07 confirms byte-level reconnection to the reviewed inventory.

It does not re-run Stage02R scientific analysis.

## FC-08 — NO-HIDDEN-KNOWLEDGE DOCUMENTATION TEST

A competent operator should be able to determine from tracked canonical documentation alone:

```text
what repository/branch is canonical
how to bootstrap Python
what requirements.txt means
how to reconstruct local_paths.yaml
where external data belong
how external-data identity is verified
what work_recovery does
what work_recovery does not do
what minimum backup policy applies
how to perform FC-01 through FC-09
```

Access credentials or the physical location of a private/off-machine backup may remain private non-Git information.

No original-workstation absolute path or prior chat transcript may be required to understand the procedure.

### PASS

All procedural/project-semantic information required for reconstruction is present in tracked docs, except provider credentials/secret storage access.

### FAIL

A required reconstruction step depends on undocumented chat history, a personal path copied from the old machine, or implicit operator knowledge.

## FC-09 — FINAL REPOSITORY CLEANLINESS

Procedure:

```bash
git status --short
git diff --check
```

### PASS

- no unexpected tracked modifications;
- machine-local config/environment remain ignored;
- test-created noncanonical state is clearly local;
- canonical HEAD remains the recorded tested commit.

### FAIL

Unexpected tracked changes or repository mutation caused by the reconstruction procedure.

## Fresh-clone state semantics

After this implementation job:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

Only a later separately authorized FC execution may change the second field.

# ALLOWED_CHANGE_TYPES

Allowed changes are limited to:

1. creation of the infrastructure guide;
2. documentation of accepted infrastructure architecture;
3. neutralization of personal absolute paths in the example local-path mapping;
4. optional minimal navigation links;
5. documentation of exact later FC procedure;
6. documentation of the existing canonical TAIPAN identity-verification mechanism;
7. documentation of backup principles;
8. documentation of Linux/Windows portability tiers.

Changes must be semantic-preserving relative to existing canonical protocols where those protocols already define behavior.

# FORBIDDEN_CHANGE_TYPES

The executor must not:

- modify `requirements.txt`;
- add scientific dependencies;
- change Python infrastructure code;
- create a new verifier utility;
- modify `work_recovery.py`;
- alter recovery behavior;
- perform a fresh clone;
- run FC-01 through FC-09 as an acceptance operation;
- claim fresh-clone PASS;
- copy, hash-scan, move, restore, or modify raw data during this implementation job;
- configure Yandex.Disk;
- perform backup;
- create Git bundles;
- implement CI;
- create GitHub Actions;
- introduce Docker;
- introduce Conda;
- introduce Poetry;
- introduce DVC;
- introduce Git-LFS;
- introduce NAS infrastructure;
- introduce a database;
- create general sync/backup software;
- implement `W00-HANDOFF-001`;
- resolve historical untracked provenance;
- change scientific state;
- change scientific conclusions;
- alter frozen scientific specifications;
- alter reviewed result artifacts;
- alter hashes/IDs/statuses/provenance;
- change authorization semantics;
- start Stage03R;
- stage files;
- commit;
- push.

# PREFLIGHT

WKB-R1 must perform preflight before any edit.

## P-01 — canonical authorization identity

Verify:

```text
repository == oregu93/cef-dy
branch == main
HEAD == origin/main
```

Read canonical metadata and verify:

```text
PORTABILITY-BASELINE-SPEC is frozen
specification_freeze_commit matches reviewed frozen specification
execution_authorized == true
execution_baseline_policy == canonical_execution_authorization_commit
latest commit modifying 00_Project/PROJECT_METADATA.yaml == HEAD
```

Equivalent Git checks may include:

```bash
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

test "$(git log -1 --format=%H -- 00_Project/PROJECT_METADATA.yaml)" \
     = "$(git rev-parse HEAD)"
```

If any condition fails:

```text
STOP
```

Do not repair by pull/rebase/reset.

## P-02 — tracked worktree/index

Record:

```bash
git status --porcelain=v1 -uall
git diff --name-only
git diff --cached --name-only
```

Required:

```text
pre-existing tracked modifications == 0
pre-existing staged files == 0
```

Known protected local untracked objects are permitted but must remain untouched.

Unexpected untracked files may be reported.

If an unexpected object conflicts with an intended output path:

```text
STOP
```

## P-03 — protection manifests

Before editing, record byte identity for:

```text
all AUDIT_ONLY tracked files
all explicitly protected scientific/governance files
all frozen Stage02R specifications
all scripts/stage02r tracked files
all tracked 04_Results/Stage02R files
all tracked historical W02 checkpoints
Archive/legacy/**
```

For known local untracked objects, record a deterministic local manifest where feasible:

```text
relative path
object type
regular-file list
byte sizes
SHA-256
```

No protected object may be modified.

## P-04 — baseline validation

Run:

```bash
python3 scripts/kb_refresh.py --check
python3 scripts/kb_validate.py
python3 scripts/kb_validate.py --strict
git diff --check
```

Record exact exit codes/warnings.

A legitimate pre-existing warning must not cause scope expansion.

A substantive baseline failure requiring non-authorized changes causes:

```text
STOP
```

# IMPLEMENTATION_STEPS

## I-01 — create infrastructure guide

Create:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

The guide must contain concise sections covering:

```text
Purpose / scope

Canonical tracked layer
What git clone recovers
What git clone does not recover

Tier-1 Linux bootstrap
Python venv bootstrap
Infrastructure dependency boundary

Machine-local configuration
local_paths.yaml reconstruction

External data architecture
Canonical external-data identity
EXP-TAIPAN-001 reconnection verification

Work recovery boundary

Backup vs synchronization
Minimum off-machine backup policy
Optional third copy
Optional Git bundle

Disaster-recovery reconstruction model

Fresh-clone FC-01..FC-09 procedure

Windows Tier-2 scope

Canonical protocol links
```

The guide must link to, not duplicate in full:

```text
03_Protocols/RESEARCH_KB_GUIDE.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/CHAT_BOOTSTRAPS.md
scripts/README.md
```

## I-02 — neutralize local-path example

Modify:

```text
configs/local_paths.example.yaml
```

Required IDs remain identical:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

Remove personal machine assumptions from example absolute paths.

Do not modify actual local:

```text
configs/local_paths.yaml
```

## I-03 — document TAIPAN identity verification

Reuse:

```text
04_Results/Stage02R/W02-02R-A-002/file_inventory.csv
```

Do not create a new tracked utility.

Document one deterministic read-only procedure satisfying `EXTERNAL_DATA_IDENTITY_MODEL`, including the exact complete actual-file universe defined there.

The procedure must not execute automatically during this Work job.

## I-04 — optional README navigation

If needed, add one concise link from root `README.md` to:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

If no such link is needed, leave `README.md` unchanged.

Do not rewrite surrounding scientific/repository content.

Do not modify AUTO regions.

## I-05 — optional scripts navigation

If useful, add one concise reference from:

```text
scripts/README.md
```

to the infrastructure guide.

If no such link is needed, leave `scripts/README.md` unchanged.

Do not alter commands or recovery behavior descriptions.

## I-06 — self-review

Review the complete diff.

Every hunk must map to:

```text
guide creation
neutral example path
optional navigation link
```

No other rationale is valid.

# VALIDATION

## V-01 — exact changed-path validation

The complete permissible changed-path universe is exactly:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
configs/local_paths.example.yaml
README.md
scripts/README.md
```

Required changed paths:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
configs/local_paths.example.yaml
```

Optional changed paths:

```text
README.md
scripts/README.md
```

Required new file:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
```

No other new tracked file is permitted.

No rename/deletion is permitted.

## V-02 — requirements identity

`requirements.txt` must be byte-identical to pre-job state.

## V-03 — recovery implementation identity

These must be byte-identical:

```text
scripts/work_recovery.py
03_Protocols/WORK_RECOVERY_PROTOCOL.md
```

## V-04 — canonical scientific/provenance identity

All protected scientific/frozen/provenance-sensitive material recorded in preflight must be byte-identical.

## V-05 — known local untracked identity

Known local protected objects must remain:

```text
untracked
unstaged
unmodified
not moved
not renamed
not deleted
```

Their before/after manifests must match.

## V-06 — generated-region identity

All existing `AUTO` regions, including root README generated regions, must remain byte-identical.

## V-07 — KB refresh check

Run:

```bash
python3 scripts/kb_refresh.py --check
```

Required: PASS.

Do not run write-mode refresh merely because new documentation was added unless the canonical tools themselves explicitly require it and doing so would not modify non-allowed files.

If `--check` requires a non-allowed generated update:

```text
STOP
```

## V-08 — KB validation

Run:

```bash
python3 scripts/kb_validate.py
python3 scripts/kb_validate.py --strict
```

Required:

```text
no new errors
no new warnings
```

Any accepted pre-existing warning must remain no worse than baseline.

## V-09 — patch integrity

Run:

```bash
git diff --check
```

Required: PASS.

## V-10 — navigation/link validation

If navigation changes are made, verify that links added to:

```text
README.md
scripts/README.md
```

resolve to the new guide.

Verify links in the new guide resolve to existing canonical paths.

## V-11 — configuration-example validation

Verify:

```text
configs/local_paths.example.yaml
```

remains valid YAML.

Verify required logical keys are exactly preserved.

Verify no personal `/home/oleg/...` example remains.

Verify no real secret/private credential is added.

## V-12 — external-verification documentation review

Inspect the documented FC-07 procedure.

Required:

- canonical inventory path is exact;
- identity fields are exact;
- canonical universe is the complete A-002 inventory for `EXP-TAIPAN-001`;
- `ACTUAL_FILES` is all regular files recursively under the mapped dataset root represented by dataset-root-relative POSIX paths;
- `EXTRA` means a regular file in that complete actual recursive census but absent from the canonical inventory;
- no extension-only filter silently narrows the census;
- symlinks/junctions are not silently treated as regular dataset files;
- path escape or symlink/junction ambiguity is fail-closed;
- procedure is read-only;
- mismatch output deterministic;
- no new dependency;
- no raw write;
- no scientific re-analysis;
- no provider path used as identity.

Do not run the procedure against the actual dataset.

## V-13 — fresh-clone semantics

Verify guide states exactly the semantic distinction:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

It must not claim any FC stage actually passed.

## V-14 — backup-policy semantics

Verify guide contains:

```text
primary working copy
+
independent off-machine copy
```

for irreplaceable non-Git data.

Verify:

```text
synchronization != backup
```

is explicit.

Third copy must be non-mandatory.

Git bundle outside GitHub must be non-mandatory.

No provider is designated as sole canonical source.

## V-15 — Git state

Record:

```bash
git status --porcelain=v1 -uall
git diff --name-only
git diff --cached --name-only
```

Required:

```text
no staged files
no commit
no push
```

# TESTS

The implementation job must run only repository-side implementation tests.

It must not run the fresh-clone acceptance test.

## T-01

Exact allowed changed-path check.

Required:

```text
03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md
configs/local_paths.example.yaml
```

Optional:

```text
README.md
scripts/README.md
```

No other changed path permitted.

## T-02

New infrastructure guide exists and is valid UTF-8 Markdown.

## T-03

Guide contains all mandatory subject sections.

## T-04

`requirements.txt` byte identity unchanged.

## T-05

`work_recovery.py` byte identity unchanged.

## T-06

`WORK_RECOVERY_PROTOCOL.md` byte identity unchanged.

## T-07

Required `local_paths.example.yaml` logical IDs unchanged.

## T-08

Personal example `/home/oleg/` paths absent from final example file.

## T-09

Actual `configs/local_paths.yaml`, if present, unchanged and ignored.

## T-10

External verification method references the canonical A-002 file inventory.

## T-11

External verification method checks relative path, size, and SHA-256.

## T-12

External verification method has read-only/fail-closed semantics.

## T-13

No new verifier source file exists.

## T-14

Fresh-clone contract contains FC-01 through FC-09.

## T-15

Every FC stage contains explicit PASS and FAIL criteria.

## T-16

Guide states Tier 1 Linux Mint/Ubuntu-family and Tier 2 Windows reasonable compatibility.

## T-17

Guide does not claim Windows full scientific-workflow equivalence.

## T-18

Guide distinguishes synchronization from backup.

## T-19

Minimum two-location policy is documented.

## T-20

Third copy and Git bundle are described only as useful/non-mandatory.

## T-21

No Docker/Conda/Poetry/DVC/Git-LFS/NAS/database/CI implementation introduced.

## T-22

`W00-HANDOFF-001` remains deferred.

## T-23

Known local historical objects are untouched.

## T-24

Protected scientific/provenance files are byte-identical.

## T-25

Generated AUTO regions are byte-identical.

## T-26

`kb_refresh.py --check` PASS.

## T-27

`kb_validate.py` PASS.

## T-28

`kb_validate.py --strict` PASS or exact accepted pre-existing-warning parity.

## T-29

`git diff --check` PASS.

## T-30

Final fresh-clone state flags are:

```text
implementation_ready_for_fresh_clone_test=true
fresh_clone_test_passed=false
```

## T-31

FC-07 defines:

```text
ACTUAL_FILES =
all regular files recursively under the mapped EXP-TAIPAN-001 dataset root,
represented by dataset-root-relative POSIX paths
```

and compares them against the complete A-002 canonical inventory for `EXP-TAIPAN-001`.

## T-32

FC-07 defines `EXTRA` as any regular file in the complete actual recursive census absent from the canonical A-002 inventory.

## T-33

FC-07 does not use an extension-only filter to redefine the census unless such a restriction is itself defined by the canonical inventory.

## T-34

FC-07 treats symlink/junction ambiguity or dataset-root path escape as fail-closed.

# PASS_CRITERIA

The job passes only if all of the following are true:

1. Execution began from a valid canonical authorization HEAD.
2. Only the exact four-path write allowlist was available.
3. `03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md` was created.
4. `configs/local_paths.example.yaml` was modified as required.
5. `README.md` and `scripts/README.md`, if modified, contain navigation-only changes.
6. The infrastructure guide is sufficient to define the later Linux fresh-clone procedure.
7. `requirements.txt` is unchanged.
8. No scientific/fitting dependency was added.
9. No Python implementation code changed.
10. No verifier utility was added.
11. `local_paths.example.yaml` preserves logical IDs and uses neutral example paths.
12. Existing `configs/local_paths.yaml`, if present, is untouched.
13. External-data identity remains independent of physical/cloud paths.
14. TAIPAN reconnection verification reuses the canonical A-002 inventory.
15. The canonical FC-07 universe is the complete A-002 inventory for `EXP-TAIPAN-001`.
16. `ACTUAL_FILES` is the complete recursive set of regular files below the mapped dataset root using root-relative POSIX paths.
17. `EXTRA` is defined against that complete actual recursive census.
18. No extension-only filter silently narrows the census.
19. Symlink/junction ambiguity and path escape are fail-closed.
20. Verification is documented as read-only and deterministic.
21. No raw data were accessed for execution of FC-07.
22. `work_recovery.py` behavior is unchanged.
23. Work recovery is explicitly distinguished from disaster recovery.
24. Minimum off-machine backup policy is documented.
25. Synchronization is explicitly not equated with backup.
26. Third-copy and Git-bundle options remain non-mandatory.
27. Tier-1/Tier-2 platform scope is documented correctly.
28. FC-01 through FC-09 each have explicit PASS/FAIL criteria.
29. The implementation does not claim fresh-clone PASS.
30. All scientific/frozen/provenance-sensitive protected material is byte-identical.
31. Known protected local untracked objects are unchanged and unstaged.
32. AUTO regions are unchanged.
33. KB refresh check passes.
34. KB validators pass according to baseline warning policy.
35. `git diff --check` passes.
36. No CI is created.
37. No backup is performed.
38. No Yandex.Disk/provider setup is performed.
39. No external data are copied or moved.
40. `W00-HANDOFF-001` is not implemented.
41. No historical provenance disposition occurs.
42. No Stage03R work or authorization occurs.
43. Nothing is staged, committed, or pushed.
44. Final execution report records:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

# ROLLBACK

The job is fail-closed.

## Before edits

If authorization, baseline, worktree, index, or mandatory prevalidation fails:

```text
make no edits
STOP
report failure
```

Do not repair via:

```text
pull
reset
checkout
restore
clean
stash
rebase
merge
```

## After job-owned edits

If validation fails:

1. preserve diagnostics;
2. do not stage, commit, or push;
3. revert only files changed/created by this job;
4. restore modified allowed files to exact pre-job bytes;
5. remove the newly created guide only if it was created by this job and no unrelated concurrent modification occurred;
6. never use `git clean`;
7. never use broad `git reset --hard`;
8. never touch known protected local untracked objects;
9. recompute protected identity checks;
10. if narrow rollback cannot be proven safe:

```text
STOP
manual_recovery_required
```

A failure must not trigger broader infrastructure repair.

# STOP_CONDITION

STOP immediately after:

1. the allowed guide/config/navigation implementation is complete;
2. repository-side tests are complete;
3. validation is complete;
4. protected identity review is complete;
5. exact diff review is complete;
6. WKB-R1 execution report is produced.

Do not proceed to:

```text
fresh-clone execution
backup execution
Yandex.Disk configuration
raw-data copying
disaster-recovery drill
CI
W00-HANDOFF-001
historical provenance disposition
scientific environment design
Stage03R
git add
git commit
git push
```

Successful STOP state:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

# HANDOFF_REQUIREMENTS

Return the completed execution report and exact diff to:

```text
07 - Research Software & Infrastructure
```

for focused technical review.

The technical review must verify at minimum:

```text
exact changed paths
required vs optional output compliance
guide completeness
requirements identity
local-path semantics
external-data identity semantics
complete FC-07 actual-file universe
FC-01..FC-09 contract
recovery boundary
backup boundary
platform tiers
protected-file identity
known-untracked identity
validation results
no fresh-clone execution
no backup execution
no CI
no Stage03R
```

Consequential acceptance/canonical capture remains a Project Control decision.

Return accepted consequential results to:

```text
00 - Project Control r1
```

This specification does not authorize Git staging, commit, push, fresh-clone execution, backup execution, CI, W00-HANDOFF-001, or Stage03R.

**Specification state:** frozen v1.0 candidate with Project Control corrections incorporated. It has not been materialized or executed.