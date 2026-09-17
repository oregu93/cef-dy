# LIT-INFRA-03 — Zotero integration specification

```yaml
specification_id: LIT-ZOTERO-INTEGRATION-SPEC
specification_version: "1.0"
specification_status: frozen

parent_architecture: LIT-KNOWLEDGE-INFRA-V1
foundation_specification: LIT-INFRA-SCHEMA-SPEC
foundation_specification_version: "1.0"
materializer_specification: LIT-INFRA-MATERIALIZER-SPEC
materializer_specification_version: "1.0"

implementation_stage: LIT-INFRA-03
implementation_status: not_started

schema_reopen_required: false
lit_infra_02_change_required: false

implementation_authorized: false
zotero_connection_authorized: false
zotero_write_authorized: false
better_bibtex_configuration_authorized: false
references_bib_creation_authorized: false
```

# 1. PURPOSE AND FREEZE BOUNDARY

This specification freezes the authority, identity, transport, concurrency,
idempotency, reconciliation, citation-key and bibliography-export contracts for
future Zotero integration.

This freeze does not authorize:

```text
implementation
Zotero connection or access
Zotero reads or writes
Better BibTeX configuration
citation-key allocation
references.bib creation
literature migration or bulk linking
scientific execution
```

The existing literature schema and the offline `LIT-INFRA-02` materializer
remain unchanged.

# 2. AUTHORITY AND IDENTITY MODEL

## 2.1 Git authority

Git is canonical for:

```text
SOURCE_ID
scientific evidence / EV-SRC semantics
evidence category and review_state
project workflow_state
search and project provenance
scientific classification
accepted citation_key mirror
Zotero linkage mapping
materialization provenance
```

## 2.2 Zotero authority

Zotero is canonical for:

```text
full bibliographic metadata
authors, title, journal or report metadata
volume, issue, pages, date and year
DOI and ordinary bibliographic identifiers
bibliographic item type
Zotero item identity
PDFs and supplements
reference-manager collections and organizational tags
native citation-key field
```

Copyrighted PDFs must not be placed in public Git. Absolute local paths are not
canonical identities.

## 2.3 Better BibTeX authority

Better BibTeX owns:

```text
citation-key generation policy
bibliography serialization and export
```

The future `05_Literature/references.bib` artifact is
`derived-but-tracked`; manual edits are not authoritative.

## 2.4 Identity invariants

```text
SOURCE_ID is immutable project source identity.

SOURCE_ID != DOI
SOURCE_ID != Zotero item_key
SOURCE_ID != citation_key

citation_key is not scientific identity.
Zotero item_key is not scientific identity.
```

# 3. TRANSPORT AND LIBRARY ALIAS

```yaml
primary:
  kind: zotero_web_api
  api_version: 3

secondary:
  kind: zotero_local_api
  role:
    - diagnostics
    - interactive_fallback
    - local_verification

manual:
  role: recovery_only
```

Web API and Local API version spaces must never be compared.

External library identity is resolved through the tracked, non-secret
`library_alias` configuration in
`05_Literature/ZOTERO_INTEGRATION_CONFIG.yaml`.

Canonical source linkage remains:

```text
zotero.library_alias
zotero.item_key
zotero.link_status
```

Raw credentials and mutable runtime object or library versions must not be
stored in `SOURCE_REGISTRY.yaml`.

# 4. CREDENTIALS AND AUTHORIZATION STATES

Credentials are forbidden in Git, project metadata, source registry,
materialization packets and the operation ledger, including:

```text
API keys
Authorization headers
local API write credentials
other secrets
```

Preferred runtime-secret order:

```text
OS credential store -> runtime environment
ephemeral environment variable
gitignored local secret configuration only if necessary
```

Keep these states distinct:

```text
access_configured
read_authorized
write_authorized
pilot_execution_authorized
```

None becomes true through this specification freeze.

# 5. ZOTERO_CREATE

## 5.1 Preconditions

`ZOTERO_CREATE` requires all of:

```text
canonical SOURCE_ID resolves
source is active
target library_alias resolves
source is unlinked or explicitly create-eligible
exact-identity duplicate preflight is complete
no unresolved identity ambiguity exists
equivalent operation is not already completed
explicit write authorization is active
```

Exact identity match order:

```text
1. exact normalized DOI
2. exact other stable bibliographic identifier
3. exact already-known Zotero item key
4. explicit human-confirmed bibliographic identity
```

Fuzzy matching may surface candidates. It must not auto-link and must not
automatically suppress create.

## 5.2 Idempotency and create semantics

Every create requires:

```text
canonical external operation identity
persistent non-secret operation ledger
normalized payload fingerprint
```

For ordinary unversioned create:

```text
Zotero-Write-Token: required
mandatory library-wide If-Unmodified-Since-Version: false
server-generated Zotero item key: required
```

## 5.3 Lost-response recovery

Blind repost is forbidden. Recovery proceeds through:

```text
operation ledger
same external operation identity
same write-token semantics where applicable
exact DOI or stable-identifier lookup
identity reconciliation
```

Outcomes:

```text
exactly one recoverable item
  -> recover item_key
  -> record external success
  -> continue Git reconciliation

no item
  -> retry only after idempotency preflight confirms safety

multiple or ambiguous items
  -> NEEDS_REVIEW
  -> no automatic write
```

If Zotero succeeds and Git reconciliation later fails, record
`EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT`. Do not automatically delete the
Zotero item.

# 6. LINKING AND EXISTING-OBJECT MUTATION

`ZOTERO_LINK_EXISTING` may automatically accept only exact normalized DOI,
another stable identifier, or a known `item_key`. A human-confirmed exact
identity is also allowed. A fuzzy-only match is `NEEDS_REVIEW`.

```text
already linked to the same target -> SUCCESS_NOOP
linked to a different target      -> NEEDS_REVIEW
```

A pure link-existing operation does not itself require Zotero mutation.

Existing-object mutations include `ADD_COLLECTION`, `ADD_TAG` and future
bibliographic `UPDATE`. They must use the object version or
`If-Unmodified-Since-Version`. A stale `412` must stop, refetch, recompute and
retry only if the operation is still semantically valid. Blind overwrite is
forbidden. An already-present collection or tag is `SUCCESS_NOOP`.

If changed bibliographic metadata challenges source identity:

```text
zotero.link_status -> needs_review
automatic reconciliation -> STOP
route -> 01A provenance review
```

# 7. OPERATION LEDGER AND CROSS-SYSTEM ATOMICITY

The future canonical ledger path is
`05_Literature/ZOTERO_OPERATION_LOG.yaml`. It is not created by this freeze;
its future owner is the `LIT-INFRA-03` executor.

The ledger must record:

```text
external_operation_identity
SOURCE_ID
library_alias
operation_type
normalized_payload_sha256
write-token identity or fingerprint for unversioned create
external operation state
item_key if known
Zotero object version if known
Zotero library version if known
result fingerprint
Git reconciliation status
```

It must not store credentials. Allowed conceptual states are:

```text
PENDING
DRY_RUN_VALID
EXTERNAL_WRITE_ATTEMPTED
EXTERNAL_WRITE_SUCCEEDED_PENDING_GIT
GIT_RECONCILIATION_PREPARED
GIT_RECONCILED
FAILED_RETRYABLE
FAILED_TERMINAL
NEEDS_REVIEW
```

No distributed transaction across Git and Zotero is assumed.

# 8. GIT RECONCILIATION

The future Zotero executor must not directly modify `SOURCE_REGISTRY.yaml`.
The route is:

```text
Zotero executor result
  -> 01A SOURCE_UPDATE packet
  -> LIT-INFRA-02
  -> canonical SOURCE_REGISTRY
```

Git reconciliation retains the expected Git `HEAD` and expected source
`record_version`.

`LIT-INFRA-02` remains offline, deterministic and network-free. No behavior
change to it is authorized. Existing deferred Zotero operations remain
deferred there.

# 9. CITATION KEYS

```yaml
generator: better-bibtex
storage_authority: Zotero native citation-key field
project_mirror: SOURCE_REGISTRY.citation_key
scientific_identity: false
```

The candidate pilot formula is `auth.lower + shorttitle(3,3) + year`. Its
status is `candidate_for_two_source_pilot`, not permanently accepted.

The actual verified configuration must eventually record:

```text
formula
force_plain_text
regenerate_on_metadata_change
uniqueness_scope
```

Recommended initial policy:

```yaml
force_plain_text: true
regenerate_on_metadata_change: false
```

A generated key becomes project-stable only after:

```text
Zotero item identity is verified
actual BBT configuration identity is recorded
project-wide key uniqueness is verified
controlled SOURCE_UPDATE is accepted in Git
```

After Git acceptance, metadata correction must not silently regenerate the
citation key. Any key change requires controlled explicit revision. Active
project bibliography keys must be unique; collision status is
`CITATION_KEY_COLLISION`.

# 10. BETTER BIBTEX COMPATIBILITY

```text
BBT_COMPATIBILITY_STATUS: NOT_YET_VERIFIED_IN_TARGET_INSTALLATION
```

No Zotero/BBT version combination is frozen as compatible, and there is no
permanent version pin.

A future actual-installation preflight must verify:

```text
installed Zotero version
installed BBT version
plugin loads
native citation-key field is operational
selected formula is operational
force_plain_text is operational
regenerate_on_metadata_change=false is operational
uniqueness scope is operational
Better BibTeX exporter is operational
```

Configuration drift blocks acceptance of new citation keys but does not
invalidate existing `SOURCE_ID` or scientific evidence.

# 11. BIBLIOGRAPHY EXPORT

The future canonical path is `05_Literature/references.bib`. This freeze does
not create it.

```yaml
status: derived-but-tracked
manual_edits_authoritative: false
initial_translator: Better BibTeX
initial_policy_status: pilot_only_unverified
permanent_dissertation_authority: false
activation_status: blocked_pending_real_compile_test
```

Activation requires at least:

```text
SRC-000001 linked
SRC-000002 linked
pilot citation keys accepted in Git
BBT compatibility verified
BBT configuration identity recorded
real dissertation/Overleaf stack available
compilation test PASS
```

The real pilot compile must exercise both:

```text
SRC-000001 — Klement'ev 1994
  Russian/Cyrillic metadata
  historical technical report
  no DOI
  difficult citation-key case

SRC-000002 — Scheie 2022
  modern journal
  DOI/arXiv
  ordinary Latin-script case
```

Initial export scope:

```yaml
library_alias: project-main
collection: "CEF Dy"
sort: citation_key
automatic_mode: Paused
```

Do not export the whole personal Zotero library.

Better BibTeX is only the initial pilot export policy, not permanent
dissertation-format authority. If the later dissertation stack establishes
`biblatex + biber`, a controlled switch to Better BibLaTeX is permitted. This
changes serialization only, not `SOURCE_ID`, evidence or workflow state.

# 12. COLLECTIONS, TAGS AND ATTACHMENTS

The required project collection is `CEF Dy`. Git scientific branch taxonomy
must not be mirrored into Zotero. Collections and tags are organizational and
do not become scientific-classification authority.

Zotero is the authority for PDFs, supplements and scanned reports. The first
two-source pilot performs no attachment writes.

# 13. PORTABILITY

```text
loss of Zotero access does not destroy Git scientific evidence
Git does not replace Zotero bibliography and PDF functions
```

Workstation migration sequence:

```text
clone Git
sync or install Zotero
resolve library alias
install BBT
verify compatibility
compare actual BBT configuration with tracked configuration
perform read-only identity reconciliation
resume writes only after a clean preflight
```

# 14. PILOT SOURCES

`SRC-000001` — Klement'ev 1994:

```text
historical Russian/Cyrillic metadata
technical report
no DOI
matching priority:
  report identifier
  cover identifier
  explicit identity confirmation
no fuzzy auto-link
```

`SRC-000002` — Scheie 2022:

```text
modern journal metadata
DOI
arXiv
matching priority:
  DOI
  arXiv identifier
  title/author/year consistency
multiple DOI matches -> NEEDS_REVIEW
```

This specification freeze does not modify either source record.

# 15. FUTURE TOOLING

The existing `scripts/literature/materialize_packet.py` remains network-free
and unchanged. A future executor candidate is
`scripts/literature/zotero_executor.py`; it is not created by this freeze.

Future responsibilities include:

```text
resolve deferred Zotero operations
read-only preflight
external operation identity and idempotency
versioned existing-object mutation
write-token create semantics
result capture and operation ledger
Git reconciliation payload
```

The future executor is forbidden from:

```text
direct SOURCE_REGISTRY mutation
scientific adjudication
SOURCE_ID allocation
secret persistence
silent BBT configuration
silent references.bib activation
```

# 16. PHASE PLAN AND AUTHORIZATION BOUNDARIES

```text
Phase 0 — design
  completed

Phase 1 — specification freeze
  completed by this materialization

Phase 2 — offline implementation + synthetic tests
  not authorized

Phase 3 — read-only Zotero connection test
  separate authorization required

Phase 4 — BBT installation/compatibility/configuration preflight
  separate user action and authorization required

Phase 5 — two-source read-only dry run
  not authorized

Phase 6 — two-source Zotero write pilot
  separate Project Control authorization required

Phase 7 — Git reconciliation through 01A -> LIT-INFRA-02

Phase 8 — references.bib activation + real compile test
  separate authorization required

Phase 9 — broader linking
  only after pilot acceptance
  no automatic bulk migration
```

# 17. TERMINAL ASSERTIONS

```text
SCHEMA_REOPEN_REQUIRED: false
LIT_INFRA_02_CHANGE_REQUIRED: false

IMPLEMENTATION_AUTHORIZED: false
ZOTERO_CONNECTION_AUTHORIZED: false
ZOTERO_WRITE_AUTHORIZED: false
BETTER_BIBTEX_CONFIGURATION_AUTHORIZED: false
REFERENCES_BIB_CREATION_AUTHORIZED: false
```
