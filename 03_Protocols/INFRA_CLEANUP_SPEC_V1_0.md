# INFRA-CLEANUP-SPEC
```
specification_id: INFRA-CLEANUP-SPEC
specification_version: "1.0"
specification_status: frozen
scientific_design_status: accepted

job_id: WKB-R1-INFRA-CLEANUP-001
execution_status: not_started
execution_authorized: false

execution_role: WKB-R1
recommended_execution_model: GPT-5.6 Sol / Medium

repository: oregu93/cef-dy
branch: main

design_baseline_commit: 83232bfc301859bf93099086768b1d18b163a28b
execution_baseline_policy: canonical_execution_authorization_commit

commit_authorized: false
push_authorized: false
stage_authorized: false
stage03r_authorized: false
```

## JOB\_ID

`WKB-R1-INFRA-CLEANUP-001`

First controlled repository cleanup pass.

This is an infrastructure-maintenance Work job only after separate Project Control authorization.

This frozen specification does **not** authorize execution.

---

# GOAL

Perform a repository-wide **read-only audit** for clearly identifiable human-readable, terminology, navigation, Markdown, LaTeX, Obsidian/GitHub rendering, heading, table, code-fence, link, and anchor defects.

Apply edits only to the explicitly enumerated `EDIT_ALLOWED_FIRST_PASS` files and only when the correction is demonstrably semantic-preserving.

The first pass is intentionally conservative.

Its purpose is to improve readability and rendering without changing:

- scientific knowledge;
- scientific interpretation;
- governance;
- provenance;
- authorization;
- artifact identity;
- numerical content;
- computational behaviour.

The long-term repository-wide cleanup objective remains active. Historical checkpoints, reviewed result/report material, and other provenance-sensitive content may be considered in a separately specified later pass only after explicit provenance/artifact-identity review.

---

# BASELINE

Canonical repository:
```
repository: oregu93/cef-dy
branch: main

design_baseline_commit:
83232bfc301859bf93099086768b1d18b163a28b

execution_baseline_policy:
canonical_execution_authorization_commit
```

This specification was designed and scientifically/infrastructurally reviewed against:
```
83232bfc301859bf93099086768b1d18b163a28b
```

That commit is the `design_baseline_commit`.

It is historical design/review provenance and is not the execution HEAD requirement.

The execution lifecycle is:
```
1. Canonically materialize and commit this frozen specification.
2. Project Control verifies that specification freeze commit.
3. In a separate canonical authorization commit, Project Control records:
   - specification_freeze_commit: <verified freeze commit>
   - execution_authorized: true
   - execution_baseline_policy: canonical_execution_authorization_commit
4. WKB-R1 may execute only while that authorization commit remains
   canonical HEAD.
```

The authorization commit does not store its own SHA.

At WKB-R1 execution preflight, all of the following must hold:
```
branch == main

HEAD == origin/main

canonical execution_authorized == true

canonical specification_freeze_commit matches the reviewed frozen
INFRA-CLEANUP-SPEC

the latest commit modifying:
00_Project/PROJECT_METADATA.yaml

must equal current HEAD
```

Equivalent Git checks may include:
```
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

test "$(git log -1 --format=%H -- 00_Project/PROJECT_METADATA.yaml)" \
     = "$(git rev-parse HEAD)"
```

If `main` advances after authorization without a fresh Project Control authorization/re-baselining decision, STOP without making cleanup edits.

The known local untracked state defined below is permitted.

No pre-existing staged change is permitted.

No pre-existing tracked modification is permitted.

If the local tracked worktree/index differs from canonical HEAD, STOP without making cleanup edits.

---

# RATIONALE

The repository already has a coherent scientific/provenance architecture. The current technical debt is primarily human-facing:

- mixed or awkward Russian/English prose;
- literal translations;
- terminology inconsistency that does not require semantic change;
- Markdown/LaTeX rendering defects;
- heading/table/code-fence inconsistencies;
- navigation and internal-link quality;
- Obsidian/GitHub rendering compatibility.

These issues are worth correcting because they increase reading and handoff cost.

They do **not** justify changing frozen scientific material, historical provenance, machine-readable state, scientific scripts, or reviewed artifacts.

The first pass therefore uses a strict default-deny model:

> A tracked file is editable only if it is explicitly listed under `EDIT_ALLOWED_FIRST_PASS`.

---

# EDIT\_ALLOWED\_FIRST\_PASS

Only these tracked files may be modified:
```
README.md

02_Work_Checkpoints/README.md

03_Protocols/MARKDOWN_LATEX_STYLE.md
03_Protocols/RESEARCH_KB_GUIDE.md

04_Results/README.md

Templates/TEMPLATE_LOGBOOK_ENTRY.md
Templates/TEMPLATE_WORK_CHECKPOINT.md

scripts/README.md
```

## Additional sub-file restrictions

### `README.md`

Edits are allowed only in human-maintained regions.

Any region delimited by generated markers such as:
```
<!-- AUTO:...:START -->
...
<!-- AUTO:...:END -->
```

is **not manually editable** by this job.

The job must not change generated scientific/status text indirectly by modifying its source objects.

### `03_Protocols/MARKDOWN_LATEX_STYLE.md`

Allowed changes are restricted to:

- language quality;
- examples whose meaning remains identical;
- Markdown presentation;
- LaTeX rendering;
- links/navigation;
- formatting consistency.

Changing the normative Markdown/LaTeX policy is not authorized.

### `03_Protocols/RESEARCH_KB_GUIDE.md`

Allowed changes are restricted to prose/rendering/navigation corrections.

Changing repository policy, provenance policy, scientific knowledge rules, Git policy, role semantics, status semantics, or workflow authorization semantics is not authorized.

### Templates

Template edits may improve wording or formatting only.

They must not alter required provenance fields, checkpoint semantics, identifiers, review requirements, or execution-control semantics.

---

# AUDIT\_ONLY

These files may be inspected during the repository-wide audit and defects may be reported, but they MUST NOT be modified in this job.

## Repository / environment configuration
```
.gitattributes
.gitignore
.obsidian/app.json
.obsidian/appearance.json
.obsidian/core-plugins.json
PROJECT_MANIFEST.yaml
requirements.txt
configs/local_paths.example.yaml
```

## Central project state and registers
```
00_Project/PROJECT_STATE.md
00_Project/PROJECT_CONTROL.md
00_Project/PROJECT_METADATA.yaml

00_Project/DECISION_REGISTER.yaml
00_Project/EVIDENCE_REGISTER.yaml
00_Project/HYPOTHESIS_REGISTER.yaml
00_Project/MODEL_REGISTER.yaml
00_Project/RESULT_REGISTER.yaml
```

Any apparent language, Markdown, terminology, or rendering issue in these objects must be reported as a candidate follow-up.

It must not be repaired in the first pass.

This deliberately avoids ambiguity over whether apparently stylistic wording carries scientific or governance semantics.

## Semantic general protocols
```
03_Protocols/CHAT_BOOTSTRAPS.md
03_Protocols/DATA_CONTRACTS.md
03_Protocols/KNOWLEDGE_RULES.md
03_Protocols/SCIENTIFIC_TERMINOLOGY.md
03_Protocols/WORK_RECOVERY_PROTOCOL.md
```

These may contain human-readable defects, but their wording directly defines scientific, data, role, recovery, or governance semantics.

Report findings only.

## General executable infrastructure
```
scripts/kb_refresh.py
scripts/kb_validate.py
scripts/project_transition.py
scripts/work_recovery.py
```

No code cleanup, refactor, comment cleanup, formatting, import cleanup, or behavioural modification is authorized.

## Literature layer
```
05_References/bibliography.md
```

Citation identities or literature-derived content must not be altered under a generic infrastructure cleanup.

Report rendering defects only.

---

# FORBIDDEN\_FIRST\_PASS

The following are hard excluded from first-pass editing.

## Frozen Stage02R protocols and specifications
```
03_Protocols/STAGE02R_*.md
```

This includes the Stage02R analysis contract and all Stage02R A/B/C specifications, including but not limited to:
```
03_Protocols/STAGE02R_TAIPAN_ANALYSIS_CONTRACT.md
03_Protocols/STAGE02R_T02R03_INVENTORY_SPEC.md
03_Protocols/STAGE02R_T02R03_A002_PARSER_SPEC.md
03_Protocols/STAGE02R_T02R03_A003_CLASSIFICATION_SPEC.md
03_Protocols/STAGE02R_T02R04_B001_BLIND_FEATURE_DISCOVERY_SPEC.md
03_Protocols/STAGE02R_T02R05_C001_CONFIRMATORY_MODEL_PREPARATION_SPEC.md
03_Protocols/STAGE02R_T02R05_C001_V1_1_CONFIRMATORY_MODEL_PREPARATION_SPEC.md
```

and any other tracked path matching the exact pattern above.

## Scientific Stage02R implementations/configurations
```
scripts/stage02r/**
```

No source, configuration, embedded metadata, comments, formatting, newline normalization, or byte-level modification is authorized.

## Legacy archive
```
Archive/legacy/**
```

No audit-driven rewrite, rename, relocation, normalization, or deletion.

## Raw/private data

No raw TAIPAN data may be modified, moved, renamed, deleted, normalized, or staged.

In particular, do not modify or traverse for cleanup purposes:
```
CEF_Dy_Data/**
data/**
local_data/**
private/**
```

and do not modify the filesystem object resolved as dataset `EXP-TAIPAN-001` through machine-local path mapping.

Private manuscript material is completely outside cleanup scope.

## Default-deny rule

Any tracked path not explicitly present in `EDIT_ALLOWED_FIRST_PASS` is non-editable in this job.

The classifications in this specification explain how known relevant non-editable paths should be treated; they do not create implicit write authority.

---

# REQUIRES\_SEPARATE\_PROVENANCE\_REVIEW

The following material is part of the longer-term cleanup objective but is excluded from first-pass edits because wording/rendering changes can alter historical record identity, provenance interpretation, or reviewed-artifact byte identity.

## Migration/history material
```
00_Project/MIGRATION_NOTES.md

01_Logbook/RESEARCH_LOGBOOK.md
01_Logbook/entries/**
```

## Historical Work checkpoints
```
02_Work_Checkpoints/W02-*.md
```

`02_Work_Checkpoints/README.md` is explicitly excepted and is allowed in the first pass.

## Reviewed / historical Stage02R result layer
```
04_Results/Stage02R/**
```

This includes:

- scientific review reports;
- provenance manifests;
- numerical tables;
- YAML/CSV/JSON artifacts;
- figures or other generated artifacts;
- historical diagnostic result packages;
- reviewed result text;
- any artifact with recorded SHA-256 or other identity semantics.

A later cleanup pass may inspect this material for language/rendering improvements only after an explicit review determines, per artifact or artifact class:

1. whether byte identity is scientific provenance;
2. whether editing would invalidate a recorded checksum;
3. whether the correct action is modification, superseding documentation, or no change;
4. whether the object is an immutable historical record.

No such review is authorized by this specification.

---

# ALLOWED\_CHANGE\_TYPES

Within `EDIT_ALLOWED_FIRST_PASS`, the executor may make only the following types of changes.

## Language

- replace awkward literal translations with natural professional Russian;
- improve grammar, punctuation, syntax, and readability;
- remove unnecessary language mixing where the English term is not itself a project term;
- preserve established English machine labels and technical terms where intentional.

## Terminology

- normalize spelling/capitalization of an already-established term;
- make two prose usages consistent when they are demonstrably synonymous in current canonical terminology;
- preserve all machine-readable terms exactly.

If terminology normalization could alter conceptual meaning, STOP on that item and report it instead of editing.

## Markdown

- heading syntax and hierarchy where section meaning/order is unchanged;
- malformed or inconsistent lists;
- table rendering;
- code fences;
- accidental code formatting;
- blank-line/layout defects;
- internal links;
- anchors;
- relative navigation links;
- Obsidian/GitHub-compatible Markdown.

## LaTeX

- malformed delimiters;
- rendering-safe placement of inline/display mathematics;
- broken `aligned`, matrix, or related environments;
- escaping that affects rendering only;
- accidental code formatting around mathematical notation;
- formatting required for compatibility with the current Markdown/LaTeX style protocol.

No mathematical expression may be numerically or physically changed.

## Navigation/documentation

- clearer link labels;
- navigation wording;
- fixing a demonstrably broken internal link to the intended existing canonical object;
- headings or local document organization where content meaning and object identity remain unchanged.

## Minimality rule

Do not rewrite a passage merely because another wording is possible.

A change requires an identifiable defect or a clear consistency/rendering benefit.

---

# FORBIDDEN\_CHANGE\_TYPES

The executor MUST NOT:

- alter a scientific conclusion;
- strengthen or weaken epistemic status;
- change `candidate`, `working`, `reviewed`, `validated`, `rejected`, `superseded`, or analogous status semantics;
- alter machine-readable status values;
- change Stage02R, C001, C002, C003, Stage03R, Stage03D or other authorization state;
- change a capability envelope;
- authorize anything;
- change an ID;
- rename an evidence/result/hypothesis/model/decision/job/feature identifier;
- change a SHA-256 value;
- regenerate an artifact merely for formatting;
- change artifact identity;
- change numerical values, uncertainties, units, dataset counts, energies, fit results, or scientific parameters;
- change physical assignments;
- change provenance semantics;
- change source/citation identity;
- change frozen contracts;
- change scientific code/configuration;
- refactor Python;
- modify dependency declarations;
- change `.gitignore`, `.gitattributes`, Obsidian configuration, or environment configuration;
- edit generated `AUTO` blocks manually;
- alter Project State, Project Control, Project Metadata, or scientific registers;
- modify historical checkpoints or result packages;
- rename, move, delete, stage, commit, or push any file;
- introduce new infrastructure architecture;
- start or prepare Stage03R execution;
- broaden scope to fix validation warnings outside the approved files.

No new tracked repository file may be created by this job.

---

# KNOWN\_LOCAL\_UNTRACKED\_STATE

At specification freeze, the Linux worktree is known to contain:
```
00_Project/C001_V1_1_EXECUTION_AUTHORIZATION.yaml
00_Project/C002_EXECUTION_AUTHORIZATION.yaml

04_Results/Stage02R/W02-02R-C-001-v1.1-first-production-diagnostic/
04_Results/Stage02R/W02-02R-C-002-first-production-attempt/
```

For this job all four objects are:
```
classification: audit_only
modify: false
delete: false
move: false
rename: false
stage: false
commit: false
provenance_disposition_review: outside_scope
```

Before any cleanup edit, create a deterministic inventory of each object containing, as applicable:
```
relative path
object type
recursive file list
file sizes
SHA-256 of every regular file
```

After editing, reproduce the inventory.

The before/after manifests must be identical.

Also verify with Git that these objects remain untracked and unstaged.

If any listed object is absent, unexpectedly tracked, staged, modified during the job, or has an unresolved filesystem state, STOP and report the discrepancy.

No attempt to repair, relocate, capture, stage, delete, or canonicalize these objects is permitted.

---

# EXECUTION\_METHOD

After Project Control authorization through a separate canonical execution-authorization commit, WKB-R1 shall execute in the following order.

## 1. Canonical preflight

Verify:
```
repository: oregu93/cef-dy
branch: main

HEAD == origin/main

canonical execution_authorized == true

canonical execution_baseline_policy ==
canonical_execution_authorization_commit

canonical specification_freeze_commit matches the reviewed frozen
INFRA-CLEANUP-SPEC

latest commit modifying:
00_Project/PROJECT_METADATA.yaml

equals current HEAD
```

Equivalent Git checks may include:
```
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

test "$(git log -1 --format=%H -- 00_Project/PROJECT_METADATA.yaml)" \
     = "$(git rev-parse HEAD)"
```

The specification design baseline:
```
83232bfc301859bf93099086768b1d18b163a28b
```

is historical design/review provenance and must not be substituted for the execution authorization commit.

Do not run `git pull` to repair a mismatch.

If canonical `execution_authorized` is not `true`, STOP.

If `specification_freeze_commit` is absent or does not match the reviewed frozen specification, STOP.

If `HEAD != origin/main`, STOP.

If the latest commit modifying `00_Project/PROJECT_METADATA.yaml` is not current `HEAD`, STOP.

If `main` has advanced after authorization without a fresh authorization/re-baselining decision, STOP.

## 2. Worktree preflight

Record:
```
git status --porcelain=v1 -uall
git diff --name-only
git diff --cached --name-only
```

Requirements:
```
tracked_worktree_changes: none
staged_changes: none
known_untracked_objects: allowed
```

Unexpected untracked objects may be reported but must not be deleted or modified. If they overlap an intended edit path or make safe execution ambiguous, STOP.

## 3. Recovery snapshot

Run the existing recovery preflight for this job:
```
python3 scripts/work_recovery.py start --job WKB-R1-INFRA-CLEANUP-001
```

This does not authorize other actions and must not modify tracked repository content.

If the recovery snapshot fails integrity checks, STOP before editing.

## 4. Pre-edit validation baseline

Run and record:
```
python3 scripts/kb_refresh.py --check
python3 scripts/kb_validate.py
python3 scripts/kb_validate.py --strict
git diff --check
```

Record exact exit codes, errors, and warnings.

A pre-existing legitimate strict-mode warning is not permission to change unrelated files.

If normal validation or refresh checking reveals a substantive canonical inconsistency requiring non-approved edits, STOP and report rather than broaden scope.

## 5. Protection manifests

Before edits, record byte identity for:

- all paths in `FORBIDDEN_FIRST_PASS`;
- all paths in `REQUIRES_SEPARATE_PROVENANCE_REVIEW`;
- all `AUDIT_ONLY` tracked files;
- all known local untracked objects.

For tracked files, repository blob identity plus local preflight byte hash may be used.

For directories, use a deterministic recursive manifest.

## 6. Repository-wide audit

Audit tracked human-readable material across the repository for:
```
language
literal translations
terminology consistency
Markdown
LaTeX
headings
tables
code fences
links
anchors
Obsidian rendering
GitHub rendering
navigation
documentation wording
```

For every finding assign:
```
edit_now
audit_only_finding
separate_review_required
no_change
```

Only findings whose path is in `EDIT_ALLOWED_FIRST_PASS` may receive `edit_now`.

## 7. Conservative editing

Modify only the explicitly allowed files.

For any questionable change:
```
skip the edit
record the finding
```

Do not solve scientific or governance ambiguity through wording.

Do not perform global search-and-replace unless each resulting hunk is individually reviewed and within the allowed file list.

Do not run automatic repository-wide formatters.

## 8. Diff review

After editing, inspect the complete diff.

For every changed hunk verify that it is exclusively:
```
language
rendering
formatting
navigation
```

and not:
```
science
governance
provenance
authorization
machine-readable semantics
numerical content
```

Any semantic-risk hunk must be removed from the job-owned diff or the job fails.

## 9. Validation

Run the complete validation contract below.

## 10. Handoff

Return results to:

`07 - Research Software & Infrastructure`

for technical review and then to:

`00 - Project Control r1`

for consequential acceptance/capture decision.

Do not stage, commit, or push.

---

# VALIDATION

## V-01 — execution authorization identity

PASS only if:
```
branch == main

HEAD == origin/main

canonical execution_authorized == true

canonical execution_baseline_policy ==
canonical_execution_authorization_commit

canonical specification_freeze_commit matches the reviewed frozen
INFRA-CLEANUP-SPEC

latest commit modifying:
00_Project/PROJECT_METADATA.yaml

equals current HEAD
```

Equivalent Git checks may include:
```
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

test "$(git log -1 --format=%H -- 00_Project/PROJECT_METADATA.yaml)" \
     = "$(git rev-parse HEAD)"
```

The design baseline:
```
83232bfc301859bf93099086768b1d18b163a28b
```

records the commit against which this specification was designed and reviewed; it is not the execution HEAD requirement.

If `main` has advanced after authorization without a fresh authorization/re-baselining decision, V-01 FAILS and the job must STOP.

## V-02 — exact changed-file audit

Record:
```
git status --porcelain=v1 -uall
git diff --name-only
git diff --stat
git diff
git diff --cached --name-only
```

Requirements:

- every tracked changed path belongs to `EDIT_ALLOWED_FIRST_PASS`;
- no new tracked path exists;
- no deletion exists;
- no rename exists;
- index remains unchanged;
- no file is staged.

## V-03 — KB generated-state check

Run:
```
python3 scripts/kb_refresh.py --check
```

Required result: PASS.

The cleanup job must not regenerate re-entry blocks.

## V-04 — normal KB validation

Run:
```
python3 scripts/kb_validate.py
```

Required result: no new error and no cleanup-induced warning.

## V-05 — strict KB validation

Run:
```
python3 scripts/kb_validate.py --strict
```

Compare against the pre-edit strict-validation baseline.

Preferred result:
```
PASS
```

If strict validation has a legitimate warning already present before cleanup:

- preserve it;
- report it verbatim enough to identify the warning;
- do not modify unrelated files to eliminate it;
- PASS is permitted only if the post-edit warning/error set is not worsened and the warning is demonstrably pre-existing.

Any new warning or error caused by cleanup is FAIL.

## V-06 — whitespace / patch integrity

Run:
```
git diff --check
```

Required result: PASS.

## V-07 — forbidden-byte identity

Recompute the protection manifests.

Required:
```
FORBIDDEN_FIRST_PASS:
  byte_identical: true

REQUIRES_SEPARATE_PROVENANCE_REVIEW:
  byte_identical: true

AUDIT_ONLY:
  byte_identical: true
```

No protected tracked file may differ from its pre-edit bytes.

## V-08 — known untracked-state preservation

For:
```
00_Project/C001_V1_1_EXECUTION_AUTHORIZATION.yaml
00_Project/C002_EXECUTION_AUTHORIZATION.yaml
04_Results/Stage02R/W02-02R-C-001-v1.1-first-production-diagnostic/
04_Results/Stage02R/W02-02R-C-002-first-production-attempt/
```

verify:
```
present_as_expected
untracked
unstaged
not_modified
not_deleted
not_moved
recursive_manifest_identical
```

Any failure is job FAIL.

## V-09 — semantic-risk diff review

Review every changed hunk explicitly for accidental changes to:
```
numbers
units
scientific assertions
epistemic qualifiers
IDs
hashes
status words
authorization words
capability statements
provenance statements
model meanings
experimental meanings
```

PASS only if no such semantic change is present.

Changes that merely move the same scientific string as part of safe Markdown restructuring should be avoided in the first pass unless strictly necessary for rendering; if unavoidable, they require explicit hunk-level confirmation of textual identity.

## V-10 — generated-region integrity

Verify that no manually generated or `AUTO`-delimited region has changed.

Required result: PASS.

---

# OUTPUTS

WKB-R1 must return, without creating a new tracked repository artifact:
```
JOB_ID
DESIGN_BASELINE_COMMIT
SPECIFICATION_FREEZE_COMMIT
EXECUTION_AUTHORIZATION_HEAD

AUDIT_SUMMARY
  files_audited
  edit_now_findings
  audit_only_findings
  separate_review_findings
  no_change_count

FILES_CHANGED
  exact path list

CHANGE_SUMMARY_BY_FILE

FILES_EXAMINED_BUT_NOT_CHANGED

SEPARATE_REVIEW_CANDIDATES

PREVALIDATION_RESULTS
POSTVALIDATION_RESULTS

STRICT_VALIDATION_PREEXISTING_WARNINGS

FORBIDDEN_IDENTITY_CHECK
AUDIT_ONLY_IDENTITY_CHECK
PROVENANCE_SENSITIVE_IDENTITY_CHECK

KNOWN_UNTRACKED_STATE_CHECK

SEMANTIC_RISK_DIFF_REVIEW

GIT_INDEX_STATUS
COMMIT_STATUS
PUSH_STATUS

DIAGNOSTICS
FAILED_OR_AMBIGUOUS_ITEMS

STOP_CONDITION_STATUS
MANUAL_USER_ACTIONS
```

Expected Git statuses:
```
staged_files: []
commit_performed: false
push_performed: false
```

The executor must return the exact local diff for review or an exact summary sufficient for the reviewing context to inspect every changed hunk.

---

# PASS\_CRITERIA

The job passes only if all of the following hold:

1. Execution begins while the canonical execution-authorization commit remains current canonical HEAD.
2. Repository-wide audit was completed without scope expansion.
3. Only explicitly allowed tracked files changed.
4. Every actual change is demonstrably language/rendering/navigation-only.
5. No scientific conclusion changed.
6. No governance or authorization meaning changed.
7. No machine-readable status, ID, hash, artifact identity, or provenance meaning changed.
8. No frozen Stage02R specification changed.
9. No Stage02R scientific source/configuration changed.
10. No historical checkpoint changed.
11. No reviewed Stage02R result/report/artifact changed.
12. `Archive/legacy/**` is unchanged.
13. Central Project State/Control/Metadata/registers are unchanged.
14. Audit-only semantic protocols are unchanged.
15. Known local untracked objects are byte-identical, untracked, and unstaged.
16. `python3 scripts/kb_refresh.py --check` passes.
17. `python3 scripts/kb_validate.py` introduces no failure or warning.
18. `python3 scripts/kb_validate.py --strict` is no worse than its pre-edit baseline; any legitimate pre-existing warning is preserved and explicitly reported.
19. `git diff --check` passes.
20. Semantic-risk diff review passes.
21. Git index is unchanged.
22. Nothing is committed or pushed.
23. Stage03R is not started, prepared, or authorized.

A job with zero file edits may still PASS if the repository-wide audit finds no clearly safe defects in the allowed scope.

---

# STOP\_CONDITION

STOP immediately after:

1. repository-wide audit;
2. permitted first-pass edits;
3. complete validation;
4. exact diff/identity review;
5. production of the WKB-R1 execution report.

Do not:

- stage;
- commit;
- push;
- update Project Control;
- update Project State;
- update Project Metadata;
- capture the job canonically;
- begin a second cleanup pass;
- repair audit-only findings;
- repair historical/provenance-sensitive findings;
- begin portability/recovery implementation;
- begin W00-HANDOFF-001;
- begin CI work;
- begin Stage03R.

Return the result for review.

---

# ROLLBACK / FAILURE RULE

The job is fail-closed.

## Pre-edit failure

If execution-authorization identity, tracked-worktree, index, recovery, or required prevalidation checks fail before editing:
```
make no cleanup edits
STOP
report the failure
```

Do not attempt to repair canonical state.

## Failure after edits

If any validation or semantic-safety condition fails after job-owned edits:

1. Do not stage, commit, push, clean, reset, pull, merge, rebase, or stash.
2. Preserve the failure diagnostics.
3. Revert **only the files modified by this cleanup job**, and only to their exact pre-job bytes captured by the recovery/preflight state.
4. Before replacing a file, verify that it has not acquired an unrelated concurrent modification.
5. Never touch the known untracked objects during rollback.
6. Never use directory-wide deletion or `git clean`.
7. Never use a broad `git reset --hard`.
8. Re-run protection-manifest checks after narrow rollback.
9. If safe narrow rollback cannot be proven, leave the worktree untouched, STOP, and report `manual_recovery_required`.

A validation failure must never trigger broader cleanup or semantic repair.

## Scope ambiguity

When there is doubt whether a proposed edit is semantic-preserving:
```
DO NOT EDIT
```

Record it under:
```
AUDIT_ONLY_FINDING
```

or:
```
SEPARATE_REVIEW_REQUIRED
```

as appropriate.

---

# AUTHORIZATION STATE
```
specification_version: "1.0"
specification_status: frozen
scientific_design_status: accepted

design_baseline_commit: 83232bfc301859bf93099086768b1d18b163a28b
execution_baseline_policy: canonical_execution_authorization_commit

execution_authorized: false
WKB_R1_execution_authorized: false

git_add_authorized: false
git_commit_authorized: false
git_push_authorized: false

stage03r_authorized_by_this_specification: false
scientific_state_change_authorized: false
```

Canonical lifecycle:
```
materialize frozen specification
        ↓
commit + push freeze materialization
        ↓
Project Control verifies freeze commit
        ↓
separate canonical authorization commit records:
  specification_freeze_commit: <verified freeze commit>
  execution_authorized: true
  execution_baseline_policy: canonical_execution_authorization_commit
        ↓
WKB-R1 may execute only while that authorization commit remains
canonical HEAD
```

This specification does not authorize WKB-R1 execution.

---
