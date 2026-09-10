# LIT-INFRA-02 — controlled literature packet materializer

```yaml
specification_id: LIT-INFRA-MATERIALIZER-SPEC
specification_version: "1.0"
specification_status: frozen

design_id: LIT-INFRA-02-DESIGN
design_version: "1.0"
design_status: accepted

parent_architecture: LIT-KNOWLEDGE-INFRA-V1
foundation_specification: LIT-INFRA-SCHEMA-SPEC
foundation_specification_version: "1.0"

stage: LIT-INFRA-02
implementation_status: not_started
implementation_authorized: false

zotero_access_authorized: false
zotero_write_authorized: false
better_bibtex_configuration_authorized: false
references_bib_creation_authorized: false
literature_migration_authorized: false
final_01a_bootstrap_authorized: false
automatic_git_publication_authorized: false
Stage03R_authorized: false
```

# 1. PURPOSE

Freeze a local offline controlled transaction layer:

```text
validated MP packet
→ canonical-state validation
→ temporary-reference resolution
→ deterministic ID allocation
→ complete in-memory mutation plan
→ resulting-state validation
→ dry-run
→ explicit apply
→ safe multi-file write
→ post-apply validation
→ WKB-controlled Git publication
```

The materializer:

```text
does not commit
does not push
does not fetch remote data
does not access Zotero
does not migrate literature automatically
```

# 2. AUTHORITY BOUNDARY

Preserve:

```text
Git:
  SOURCE_ID
  search provenance
  scientific evidence
  workflow state
  work-family relations
  gaps
  project-use state
  materialization provenance

Zotero:
  bibliographic metadata authority
  PDFs
  supplements
  reference-manager organization

Materializer:
  deterministic application mechanism only
```

The materializer may materialize Git mirror fields supplied by validated packets.

It must not infer bibliographic identity from Zotero.

# 3. INPUT PACKET

Canonical input:

```text
05_Literature/PACKETS/MP-YYYYMMDD-01A-NN.yaml
```

Required top-level fields:

```text
packet_id
packet_schema_version
producer_role
source_search_passes
operations
unresolved_ambiguities
validation_status
```

v1 producer role:

```text
01A
```

Filename must match `packet_id`.

For canonical apply, packet must be under:

```text
05_Literature/PACKETS/
```

Do not allow arbitrary external absolute packet paths for canonical application.

Dry-run/test fixtures may use disposable repository copies.

# 4. PRECONDITIONS

Before planning:

```text
schema v1 valid
canonical literature state valid
packet valid
packet references structurally valid
no blocking unresolved ambiguity
tracked worktree clean
Git index clean
no unexpected untracked files
```

Allowed untracked exception:

```text
the exact input MP packet only
under 05_Literature/PACKETS/
```

For apply require:

```text
--apply
--expected-head <40-hex SHA>
```

and:

```text
git rev-parse HEAD == expected_head
```

No second acknowledgement token.

The materializer does not fetch remote state.

WKB remains responsible for remote-main verification before execution and fast-forward publication afterwards.

# 5. PROCESSING SEQUENCE

Freeze:

```text
1. resolve repository root
2. validate Git/index/untracked preconditions
3. identify exact packet
4. calculate PACKET_SHA256
5. validate frozen schema identity
6. validate canonical pre-state
7. validate packet structure
8. inspect materialization ledger
9. reject blocking unresolved ambiguities
10. validate operation payload semantics
11. duplicate/identity ambiguity checks
12. expected_record_version checks
13. deterministic ID allocation
14. resolve SRC-PENDING references
15. construct complete resulting state in memory
16. construct canonical shadow tree
17. validate shadow state
18. calculate deterministic mutation plan
19. calculate PLAN_SHA256
20. emit dry-run report
21. stop unless --apply
22. recheck HEAD/pre-state fingerprints
23. safe transactional write
24. post-apply validation
25. emit apply report
```

No canonical mutation before the transactional-write phase.

# 6. OPERATION ORDER

Semantic ordering:

```text
operations YAML list order
```

`operation_id` is audit identity, not sort key.

Forward references to same-packet definitions are allowed only after a complete pre-scan establishes unambiguous definitions.

Allocation order within each namespace follows first semantic occurrence in packet order.

Physical writes occur in repository-relative lexical path order.

# 7. SOURCE_ID ALLOCATION

Materializer owns canonical SOURCE_ID allocation.

`SOURCE_CREATE` uses:

```text
temporary_ref: SRC-PENDING-...
```

Allocation:

```text
max retained canonical SRC numeric suffix + 1
```

Never fill historical gaps.

Merged records count toward maximum.

Multiple creates receive consecutive IDs in packet order.

Never recycle/reassign.

Independent of:

```text
Zotero item key
citation key
source_slug
```

Namespace exhaustion fails closed.

# 8. GAP_ID

Do not introduce `GAP-PENDING-*` in v1.

`GAP_CREATE` proposes a canonical GAP ID.

Materializer grants it only if it exactly matches deterministic monotonic next ID.

Multiple same-packet GAP creates must form the exact consecutive next-ID sequence in packet order.

# 9. EVIDENCE_ID

Materializer owns evidence ID allocation.

For `EVIDENCE_ADD`, packet does not provide authoritative `evidence_id`.

Allocate:

```text
EV-SRCxxxxxx-001
EV-SRCxxxxxx-002
...
```

per source using max existing suffix + 1.

Do not reuse gaps.

`EVIDENCE_UPDATE` must reference an existing evidence ID.

# 10. EDGE_ID

Materializer owns EDGE_ID allocation.

For `ADD_CITATION_EDGE`:

```text
global max EDGE suffix + 1
```

across canonical evidence relations.

Packet-provided new EDGE ID is not authoritative.

# 11. WORK_FAMILY_ID

Do not introduce `WF-PENDING-*`.

`WORK_FAMILY_LINK` references an existing family or proposes exact next monotonic `WF-xxxxxx`.

Several operations may refer to the same newly introduced family.

# 12. SEARCH_PASS_ID

Materializer does not allocate SEARCH_PASS_ID.

Producer owns semantic:

```text
date
topic
sequence
```

identity.

Materializer validates:

```text
format
filename
uniqueness
reference integrity
canonical nonexistence before SEARCH_PASS_ADD
```

unless packet replay is already recognized through materialization ledger.

# 13. SRC-PENDING RESOLUTION

Construct complete packet-local resolution map before mutation.

Example:

```text
SRC-PENDING-a → SRC-000137
SRC-PENDING-b → SRC-000138
```

Every structured pending reference must resolve exactly once.

Reject:

```text
undefined pending ref
duplicate definition
ambiguous definition
```

No pending ID may enter canonical stores other than the immutable retained packet itself.

# 14. SOURCE_CREATE

Required:

```text
temporary_ref
payload
```

System-owned generated fields:

```text
record_version: 1
record_status: active
last_materialization_packet: current packet_id
```

Structurally nullable source fields may be supplied as null by materializer if omitted:

```text
citation_key
zotero
work_family_id
evidence_record
hold_scope
```

Do not synthesize scientific/bibliographic facts.

If same-packet evidence is created:

```text
evidence_record: EVIDENCE/SRC-xxxxxx.yaml
```

may be assigned automatically.

Identity/DOI ambiguity blocks creation.

No automatic merge.

# 15. SOURCE_UPDATE

Requires:

```text
source_ref
preconditions.expected_record_version
payload.patch
```

Expected version is canonical pre-packet version.

System-owned fields cannot be directly patched:

```text
SOURCE_ID
record_version
last_materialization_packet
evidence_record
```

Explicit reviewed merge may be represented only when packet explicitly requests:

```text
record_status: merged
merged_into: SRC-xxxxxx
```

and resulting state satisfies frozen merge invariants.

No inferred merge.

# 16. EVIDENCE_ADD

Targets canonical or same-packet source.

Materializer allocates evidence ID.

Create evidence file if needed:

```text
source_id
evidence_record_version: 1
evidence: [...]
relations: []
cef: null
```

Optional valid applicability fields may be preserved.

Existing evidence record receives append in packet order.

Result must pass category and CEF-context validation.

# 17. EVIDENCE_UPDATE

Requires:

```text
source_ref
existing evidence_id
```

and for existing source:

```text
expected_record_version
```

Allowed modes:

```text
item_patch
record_patch
```

`item_patch` cannot alter evidence ID.

`record_patch` may change only allowed evidence-record metadata such as:

```text
applicability
cef
```

Cannot alter source_id.

No evidence deletion in v1.

# 18. SEARCH_PASS_ADD

Creates:

```text
05_Literature/SEARCH_LOG/<search_pass_id>.yaml
```

Packet must provide complete canonical search-pass record.

Resolve structured packet-local source references before write.

Preserve:

```text
queries
query_recovered
provenance_origin
mode
result_state
termination_reason
```

For retrospective migration:

```text
query_recovered: false
provenance_origin: historical_chat
```

is valid.

Never fabricate queries.

# 19. GAP_CREATE / GAP_UPDATE

`GAP_CREATE` uses exact proposed deterministic next GAP ID.

`GAP_UPDATE` targets existing GAP.

Preserve frozen statuses:

```text
open
partially_resolved
resolved
blocked
probably_unrecoverable
```

`probably_unrecoverable` never means nonexistence.

`resolved` requires valid `resolved_by`.

# 20. ADD_CITATION_EDGE

Required:

```text
from_source
to_source
relation_type
evidence_independence
```

Materializer allocates EDGE_ID.

Both endpoints must resolve.

Canonical storage location:

```text
EVIDENCE/<from_source>.yaml
```

and:

```text
edge.from_source
==
owning evidence record source_id
```

This storage convention is frozen by LIT-INFRA-02.

Work-family membership does not imply evidence independence.

# 21. WORK_FAMILY_LINK

Required:

```text
source_ref
work_family_id
work_version_role
```

Existing source requires expected_record_version.

Family may already exist or be exact next monotonic family ID.

Grouping must never automatically alter `evidence_independence`.

# 22. SOURCE RECORD VERSIONING

New source:

```text
record_version = 1
```

For an existing source changed by one or more source-associated operations in one successfully applied packet:

```text
record_version += 1
```

exactly once per packet.

Source-associated mutations include:

```text
SOURCE_UPDATE
EVIDENCE_ADD
EVIDENCE_UPDATE
ADD_CITATION_EDGE
WORK_FAMILY_LINK
```

Also update:

```text
last_materialization_packet = packet_id
```

All operations targeting the same pre-existing source must use the same pre-packet expected version.

Conflicting values:

```text
PACKET_PRECONDITION_FAILURE
```

# 23. EVIDENCE RECORD VERSIONING

New record:

```text
evidence_record_version = 1
```

Existing evidence record changed one or more times within one packet:

```text
evidence_record_version += 1
```

exactly once per successfully applied packet.

# 24. OPTIMISTIC CONCURRENCY

Two layers:

```text
repository-wide:
--expected-head

per-existing-source:
expected_record_version
```

Mismatch:

```text
PACKET_PRECONDITION_FAILURE
```

No reconciliation/rebase in materializer.

# 25. MATERIALIZATION LEDGER

Freeze canonical ledger path:

```text
05_Literature/MATERIALIZATION_LOG.yaml
```

Purpose:

```text
durable packet application provenance
replay detection
allocation provenance
deferred Zotero request status
```

Initial form:

```yaml
schema_version: "1.0"
applications: {}
```

Per application record at minimum:

```text
packet_sha256
base_head
plan_sha256
result

allocated_source_ids
allocated_gap_ids
allocated_evidence_ids
allocated_edge_ids
allocated_work_family_ids

files_created
files_modified

deferred_zotero_requests
```

No wall-clock timestamp required.

No absolute paths.

No secrets.

The materializer is sole mutating authority for this ledger.

01A/01/Zotero do not manually edit application entries.

WKB may commit the generated ledger changes but must not rewrite application facts.

# 26. REPLAY / IDEMPOTENCY

If ledger contains:

```text
same packet_id
same packet_sha256
result: applied
```

return:

```text
STATUS=ALREADY_APPLIED
```

with zero mutation.

If same packet ID exists with different SHA:

```text
MATERIALIZATION_SCHEMA_FAILURE
```

No semantic replay/reconciliation.

Required determinism:

```text
same packet bytes
+
same canonical pre-state
→
same IDs
same output bytes
same PLAN_SHA256
```

# 27. APPLIED PACKET VALIDATION COMPATIBILITY

Future implementation must narrowly modify:

```text
scripts/literature/literature_validate.py
```

to distinguish:

```text
unapplied retained packet
applied packet recorded in MATERIALIZATION_LOG
```

Applied status must be established only by the ledger.

Do not infer it from canonical effects.

For applied packets:

```text
packet structure remains validated
packet SHA must match ledger
SRC-PENDING remains permitted only within packet
CREATE operations are not rejected merely because their canonical effects now exist
```

This is a compatibility adaptation to the validator.

It is not authorization to weaken canonical-state checks.

# 28. DEFERRED ZOTERO OPERATIONS

These packet types:

```text
ZOTERO_CREATE
ZOTERO_LINK_EXISTING
ADD_COLLECTION
ADD_TAG
```

are:

```text
validated
not executed
reported as deferred
```

Ledger state:

```text
deferred_not_executed
```

Never mark them:

```text
completed
applied
synced
```

within LIT-INFRA-02.

A mixed Git+Zotero packet may apply its Git mutations while preserving deferred Zotero requests.

A Zotero-only packet may receive a ledger application entry indicating Git-side packet processing complete while all Zotero actions remain deferred.

# 29. DUPLICATE / AMBIGUITY HANDLING

Before source creation or DOI-changing update compare normalized DOI against:

```text
canonical active sources
same-packet proposed sources
```

Duplicate DOI:

```text
DUPLICATE_CANDIDATE
```

Other unresolved identity ambiguity:

```text
BIBLIOGRAPHIC_AMBIGUITY
```

No allocation/application.

No fuzzy title/author auto-merge.

No Zotero matching.

# 30. VALIDATION RESPONSIBILITIES

`literature_validate.py` owns canonical structural validation.

`materialize_packet.py` owns transaction/application semantics.

Do not duplicate the complete validator implementation.

Materializer should reuse/call/import the accepted validator where practical.

Both participate in fail-closed reference integrity and resulting-state validation.

# 31. DRY RUN

Default command is non-mutating.

Conceptual interface:

```text
python scripts/literature/materialize_packet.py \
  05_Literature/PACKETS/MP-....yaml
```

Required:

```text
MODE=DRY_RUN
```

It performs complete planning including deterministic IDs and plan digest.

Repository state after dry-run must be byte-for-byte unchanged.

No persistent temp file.

# 32. APPLY

Conceptual interface:

```text
python scripts/literature/materialize_packet.py \
  05_Literature/PACKETS/MP-....yaml \
  --apply \
  --expected-head <sha>
```

Application requires all dry-run checks plus HEAD/pre-state recheck.

No second confirmation token.

# 33. TRANSACTION MODEL

Before writing:

```text
all target post-state bytes exist in memory
all target paths known
shadow-state validator PASS
pre-state fingerprints captured
```

Safe write:

```text
temporary sibling files
complete UTF-8 writes
flush/fsync where practical
rollback state retained
pre-state fingerprints rechecked
deterministic path-order replacement
ledger included in same logical transaction
post-apply validation
```

On caught write/post-validation failure:

```text
restore previous files
remove newly created files
verify restored state
stop
```

No canonical delete operation in v1.

Power/process interruption cannot be made physically atomic across arbitrary filesystem files without disproportionate machinery; recovery remains possible from clean Git HEAD because materializer never commits.

# 34. NEW FAILURE CODE

Freeze one new LIT-INFRA-02-specific failure:

```text
MATERIALIZATION_ROLLBACK_FAILURE
```

Meaning:

```text
an apply failed
and automatic restoration of canonical pre-state
could not be verified
```

Required consequence:

```text
stop all literature materialization
require manual WKB/Git recovery
```

Do not add unrelated new failure codes.

This code belongs to the LIT-INFRA-02 specification.

Do not modify `SCHEMA_V1.yaml` during this freeze.

# 35. GIT STATE

Before materialization:

```text
no staged changes
no tracked modifications
```

Allowed untracked state:

```text
none
```

or exactly the input packet under canonical PACKETS directory.

Materializer must not execute:

```text
git add
git commit
git push
git pull
git fetch
git merge
git rebase
git reset
git restore
```

WKB/governance performs publication separately.

# 36. RUNTIME WRITE ALLOWLIST

Materializer may create/modify only:

```text
05_Literature/SOURCE_REGISTRY.yaml
05_Literature/GAPS.yaml
05_Literature/MATERIALIZATION_LOG.yaml
05_Literature/EVIDENCE/SRC-xxxxxx.yaml
05_Literature/SEARCH_LOG/SP-*.yaml
```

Read-only:

```text
05_Literature/SCHEMA_V1.yaml
05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml
05_Literature/PACKETS/MP-*.yaml
```

No delete operation in v1.

All other writes fail closed.

# 37. DETERMINISTIC SERIALIZATION

Freeze:

```text
UTF-8
LF
two-space YAML indentation
stable/canonical field ordering
semantic list order preserved
single trailing newline
safe YAML types only
no Python object tags
no generated timestamps
no machine-local paths
```

Registries should serialize canonical IDs in ascending order.

Ledger ordering must be deterministic.

# 38. PLAN_SHA256

PLAN_SHA256 is SHA-256 over deterministic canonical representation of:

```text
packet_id
packet_sha256
base_head
allocated IDs
files to create
files to modify
exact post-state bytes
record-version changes
deferred Zotero request identities
```

No timestamp.

No machine path.

# 39. OUTPUT REPORT

At minimum:

```text
PACKET_ID
MODE
BASE_HEAD
PACKET_SHA256
PLAN_SHA256

PRECONDITION_STATUS
VALIDATION_STATUS

ALLOCATED_SOURCE_IDS
ALLOCATED_GAP_IDS
ALLOCATED_EVIDENCE_IDS
ALLOCATED_EDGE_IDS
ALLOCATED_WORK_FAMILY_IDS

FILES_TO_CREATE
FILES_TO_MODIFY
FILES_TO_DELETE

RECORD_VERSION_CHANGES
EVIDENCE_RECORD_VERSION_CHANGES

DEFERRED_ZOTERO_REQUESTS

POST_VALIDATION_STATUS
STATUS
```

Deterministic ordering.

# 40. TEST MATRIX

Freeze the accepted test matrix covering at minimum:

```text
SOURCE_CREATE
multiple SOURCE_CREATE
historical source-ID gaps
SOURCE_UPDATE valid/stale version
conflicting expected versions

defined/undefined/duplicate pending refs
canonical pending leakage

EVIDENCE_ADD
multiple evidence additions
EVIDENCE_UPDATE
wrong evidence owner
invalid evidence category
CEF context
zero B_lm

ADD_CITATION_EDGE
dangling endpoint
wrong edge owning source

GAP_CREATE monotonic
skipped/recycled GAP
GAP_UPDATE
resolved gap semantics
probably_unrecoverable

SEARCH_PASS_ADD
duplicate search pass
retrospective query_recovered:false
no fabricated-query requirement

WORK_FAMILY_LINK existing/new
skipped/recycled WF
no independence mutation

duplicate DOI canonical/same-packet
unresolved ambiguity

replay
packet-ID/hash conflict

dry-run no mutation
apply exact writes
partial write rollback
post-validation rollback
rollback failure

post-apply validator
applied-packet validator compatibility

deferred Zotero
Zotero-only packet

dirty/staged/unexpected-untracked state
permitted input packet
expected HEAD mismatch

deterministic report
network disabled
different CWD
no absolute/user path leakage
```

Tests must use temporary/synthetic fixtures only.

# 41. PASS CRITERIA

Freeze acceptance criteria exactly around:

```text
default non-mutating
explicit --apply
HEAD-bound apply
deterministic reference resolution
monotonic/non-recycling IDs
no canonical SRC-PENDING
record-version concurrency
idempotent replay
packet ID/hash protection
resulting-state validator PASS
applied packet remains valid provenance
runtime write allowlist
no delete
rollback on ordinary failure
rollback on post-validation failure
deferred Zotero remains unexecuted
offline operation
no PDF/secrets requirements
no Git publication by materializer
no scientific authorization changes
all fixture tests pass
```

# 42. STOP CONDITIONS

Before mutation stop on:

```text
STOP_SCHEMA_DIVERGENCE
PACKET_PRECONDITION_FAILURE
BIBLIOGRAPHIC_AMBIGUITY
DUPLICATE_CANDIDATE
undefined/ambiguous packet reference
ID collision/nonmonotonic allocation
unexpected Git state
HEAD mismatch
unsupported operation semantics
write outside allowlist
attempted Zotero execution
attempted references.bib change
attempted branch-status change
attempted scientific authorization change
shadow-state validator failure
```

After mutation starts:

```text
failure
→ rollback
→ verify
→ stop
```

Rollback verification failure:

```text
MATERIALIZATION_ROLLBACK_FAILURE
```

# 43. FUTURE IMPLEMENTATION SCOPE

A future separately authorized implementation is expected to use:

```text
CREATE:
scripts/literature/materialize_packet.py
05_Literature/MATERIALIZATION_LOG.yaml

MODIFY:
scripts/literature/literature_validate.py

DELETE:
none
```

This is a specification of future scope.

It is not current implementation authorization.

# 44. AUTHORIZATION STATE

Explicitly unauthorized:

```text
LIT-INFRA-02 implementation
Zotero access
Zotero writes
Better BibTeX
references.bib
literature migration
final 01A bootstrap
automatic Git publication
Stage03R
```

Canonical terminal state of this specification freeze:

```yaml
specification_id: LIT-INFRA-MATERIALIZER-SPEC
specification_version: "1.0"
specification_status: frozen

design_id: LIT-INFRA-02-DESIGN
design_version: "1.0"
design_status: accepted

stage: LIT-INFRA-02
implementation_status: not_started
implementation_authorized: false
```
