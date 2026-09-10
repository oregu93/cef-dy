Ниже — точная schema/authority specification для `LIT-INFRA-01`, без executable implementation details сверх контрактов.

# LITERATURE KNOWLEDGE SCHEMA v1.0

```yaml
specification_id: LIT-INFRA-SCHEMA-SPEC
specification_version: "1.0"
specification_status: proposed_for_freeze

design_id: LIT-KNOWLEDGE-INFRA-V1
design_status: accepted

repository_schema_version: "1.0"

implementation_stage: LIT-INFRA-01
implementation_status: not_started
implementation_authorized: false

zotero_configuration_authorized: false
zotero_write_authorized: false
web_api_implementation_authorized: false
better_bibtex_configuration_authorized: false
references_bib_creation_authorized: false
literature_migration_authorized: false
final_01a_bootstrap_authorized: false
```

# 1. PURPOSE

This specification freezes the canonical schema and authority contracts for the first literature-knowledge infrastructure layer of the CEF Dy / DyFeO3 project.

It governs:

```text
SOURCE identity
registry structure
scientific evidence representation
search provenance
gap tracking
citation/reuse relations
work-family semantics
materialization packets
workflow states
branch taxonomy
offline validation
authority boundaries
```

It does not authorize:

```text
repository modification
Zotero configuration
Zotero API access
Better BibTeX configuration
references.bib creation
literature migration
packet materialization
final 01A bootstrap
scientific promotion
```

# 2. ROLE AND AUTHORITY ARCHITECTURE

Required durable workflow:

```text
01A - Literature Discovery & Provenance
            ↓
structured provenance / materialization packets
            ↓
Git-tracked Literature Knowledge Layer
            ↓
01 - Literature & Physics
            ↓
scientific curation
            ↓
Project Control
```

Chats are producers/reviewers of structured records.

Chats are not the durable database.

# 3. AUTHORITY_MATRIX

## 3.1 Zotero authority

Zotero is the intended later authority for:

```text
full bibliographic metadata
authors
title
journal
volume
issue
pages
publication year
DOI
normal bibliographic identifiers
bibliographic item type
PDF attachments
supplements
collections
controlled Zotero tags
short human reference-manager notes
```

These fields may be mirrored selectively in Git for identity, validation and portability.

Zotero is not the authority for project-specific scientific evidence.

## 3.2 Git authority

Git is canonical for:

```text
SOURCE_ID
source record status
search provenance
SEARCH_PASS records
exact search queries
primary-source verification state
project branch classification
scientific evidence extraction
citation/reuse relations
work-family relations
workflow/review state
gap state
materialization provenance
project-use state
```

## 3.3 Derived authority

Later:

```text
05_Literature/references.bib
```

will be:

```text
derived-but-tracked
```

with generating authority:

```text
Zotero + Better BibTeX
```

It is not created by `LIT-INFRA-01`.

BibTeX is never the scientific evidence database.

# 4. REPOSITORY_STRUCTURE

Canonical target architecture:

```text
05_Literature/
├── SOURCE_REGISTRY.yaml
├── GAPS.yaml
├── SCHEMA_V1.yaml
│
├── SEARCH_LOG/
│   ├── BRANCH_STATUS.yaml
│   └── SP-*.yaml
│
├── EVIDENCE/
│   └── SRC-*.yaml
│
└── PACKETS/
    └── MP-*.yaml
```

Architecturally planned later derived artifact:

```text
05_Literature/references.bib
```

Not part of first schema materialization.

Do not create in v1:

```text
05_Literature/CITATION_GRAPH/
05_Literature/WORK_FAMILIES.yaml
```

Citation relations remain structured source/evidence-level edges.

Work-family membership remains represented through registry fields and relations.

Git does not track empty directories as semantic objects.

Therefore `.gitkeep` files are not part of the required schema foundation.

`EVIDENCE/` and `PACKETS/` become physically present when first real records are materialized.

# 5. SOURCE_ID_POLICY

Canonical source identity format:

```text
SRC-000001
SRC-000002
SRC-000003
...
```

Formal pattern:

```text
^SRC-[0-9]{6}$
```

## 5.1 Immutable identity rules

After canonical materialization:

```text
SOURCE_ID never changes
SOURCE_ID is never recycled
SOURCE_ID is never reassigned to another source
bibliographic correction does not change SOURCE_ID
title correction does not change SOURCE_ID
author correction does not change SOURCE_ID
year correction does not change SOURCE_ID
DOI correction does not change SOURCE_ID
Zotero relinking does not change SOURCE_ID
Zotero item recreation does not change SOURCE_ID
citation-key change does not change SOURCE_ID
work-family reassignment does not change SOURCE_ID
```

`SOURCE_ID` identifies the project bibliographic object independently of external reference-manager identity.

## 5.2 Pending candidate identity

Inside materialization packets only, candidate references may use:

```text
SRC-PENDING-<packet-local-key>
```

Pending IDs:

```text
must never enter SOURCE_REGISTRY.yaml
must never appear in canonical evidence filenames
must never become citation-edge endpoints after materialization
```

They must be resolved during materialization to either:

```text
existing canonical SOURCE_ID
new canonical SOURCE_ID
GAP / unresolved ambiguity
```

## 5.3 Unresolved bibliography

If a distinct durable bibliographic object is known to exist but metadata is incomplete:

```yaml
source_id: SRC-xxxxxx
bibliographic_status: unresolved
```

A normal canonical SOURCE_ID is appropriate.

If source existence or bibliographic identity itself is uncertain:

```text
create GAP
do not allocate SOURCE_ID
```

## 5.4 Duplicate merge

If canonical records are later proven to represent the same bibliographic object:

```yaml
SRC-000248:
  record_status: merged
  merged_into: SRC-000137
```

Rules:

```text
merged SOURCE_ID remains in registry
merged SOURCE_ID is not deleted
merged SOURCE_ID is not recycled
merged_into must resolve to active canonical SOURCE_ID
new scientific references should target surviving SOURCE_ID
historical provenance may continue to mention merged SOURCE_ID
```

# 6. SOURCE_SLUG_POLICY

`source_slug` is:

```text
human-readable
non-authoritative
mutable
```

Recommended form:

```text
2013-laforge-dyfeo3-ir
```

No canonical relation may depend on slug stability.

Specifically, do not use `source_slug` as:

```text
primary key
citation edge identity
foreign key
evidence filename authority
work-family identity
packet identity
Zotero identity
```

Bibliographic corrections may change it.

# 7. SOURCE_REGISTRY_SCHEMA

Canonical file:

```text
05_Literature/SOURCE_REGISTRY.yaml
```

It is a compact source index, not a scientific evidence store.

Top level maps:

```text
SOURCE_ID → source record
```

Example:

```yaml
SRC-000137:
  record_version: 1
  record_status: active

  source_slug: 2013-laforge-dyfeo3-ir

  bibliographic_identity:
    title_short: "..."
    first_author: "LaForge"
    year: 2013
    doi: "10...."
    other_ids: {}

  bibliographic_status: verified

  citation_key: null

  zotero:
    library_alias: null
    item_key: null
    link_status: unlinked

  work_family_id: null

  primary_source_status: primary_verified
  full_text_status: obtained

  compounds:
    - DyFeO3

  techniques:
    - infrared_spectroscopy

  branches:
    - B01
    - B04

  workflow_state: READY_FOR_01
  hold_scope: null

  search_passes:
    - SP-20260909-DYFEO3-01

  evidence_record: EVIDENCE/SRC-000137.yaml

  last_materialization_packet: MP-20260909-01A-03
```

## 7.1 Required registry fields

Required for every active or merged source:

```text
record_version
record_status
source_slug
bibliographic_identity
bibliographic_status
primary_source_status
full_text_status
compounds
techniques
branches
workflow_state
search_passes
```

Additional required structural fields may be null where not yet linked:

```text
citation_key
zotero
work_family_id
evidence_record
last_materialization_packet
hold_scope
```

## 7.2 `record_version`

Required positive integer:

```text
1, 2, 3, ...
```

Increment when the canonical registry record is materially updated through controlled materialization.

It supports optimistic precondition checking.

## 7.3 `record_status`

Allowed exactly:

```text
active
merged
```

For:

```text
record_status: merged
```

required:

```text
merged_into
```

For active records, `merged_into` must be absent or null.

## 7.4 `bibliographic_identity`

Required keys:

```text
title_short
first_author
year
doi
other_ids
```

Any field may be null when `bibliographic_status` permits unresolved metadata.

`other_ids` is a mapping for identifiers such as:

```text
ISBN
ISSN-derived item references
report number
arXiv
OSTI
JINR report identifier
institutional report identifier
```

Only identifiers actually relevant to the source should be populated.

## 7.5 DOI normalization

Canonical DOI field:

```text
bare DOI string
lowercase where normalization is safe
without https://doi.org/
without doi:
```

Example:

```text
10.1103/physrevb.108.174406
```

A missing DOI is not validation failure if the source legitimately has none or remains unresolved.

## 7.6 `bibliographic_status`

Allowed exactly:

```text
verified
partial
unresolved
```

Semantics:

```text
verified:
bibliographic object sufficiently verified from authoritative/primary metadata

partial:
object identity credible but one or more bibliographic fields remain incomplete

unresolved:
durable source identity exists but bibliographic reconstruction remains unresolved
```

## 7.7 Zotero bridge block

Schema:

```yaml
zotero:
  library_alias:
  item_key:
  link_status:
```

Allowed `link_status` exactly:

```text
unlinked
linked
stale
needs_review
```

Rules:

```text
library_alias + item_key required when link_status = linked
item_key is not SOURCE_ID
title is not Zotero bridge identity
parent_item_key is not a registry field for normal bibliographic items
```

Attachment-specific parent keys may be represented later in attachment metadata.

## 7.8 `work_family_id`

Optional.

When present:

```text
WF-000001
WF-000002
...
```

Formal pattern:

```text
^WF-[0-9]{6}$
```

No standalone work-family registry is required in v1.

## 7.9 `primary_source_status`

Allowed exactly:

```text
primary_verified
primary_found_not_read
secondary_only
citation_only
unresolved
```

Semantics distinguish existence from direct inspection.

## 7.10 `full_text_status`

Allowed exactly:

```text
obtained
accessible_online
abstract_only
metadata_only
unavailable
```

`unavailable` means unavailable to the project at the recorded review point; it does not assert that no copy exists anywhere.

## 7.11 `compounds`, `techniques`, `branches`

All are lists.

Registry uses them for index/filter purposes.

Long applicability reasoning belongs in evidence records.

## 7.12 `workflow_state`

Must follow Section 16.

## 7.13 `hold_scope`

Required non-null only when:

```text
workflow_state: HOLD
```

Allowed exactly:

```text
provenance
scientific
```

## 7.14 `search_passes`

List of canonical `SEARCH_PASS_ID` values that materially discovered, verified, or updated the source.

## 7.15 `evidence_record`

For active sources with materialized scientific/provenance evidence:

```text
EVIDENCE/SRC-xxxxxx.yaml
```

May be null temporarily for metadata-only records.

If non-null, target must exist.

## 7.16 Registry exclusions

Do not store long-form:

```text
scientific claims
quotes
CEF parameter tables
level schemes
detailed applicability arguments
citation graph narratives
long provenance histories
```

in the registry.

# 8. EVIDENCE_SCHEMA

One canonical source-level file:

```text
05_Literature/EVIDENCE/SRC-xxxxxx.yaml
```

Filename SOURCE_ID must equal internal `source_id`.

Example:

```yaml
source_id: SRC-000137
evidence_record_version: 1

applicability:
  compounds:
    - DyFeO3
  sample_forms:
    - bulk_single_crystal

evidence:
  - evidence_id: EV-SRC000137-001
    category: MEASURED
    claim: "..."
    quantity:
      value: 18.2
      uncertainty: 0.2
      unit: meV
    conditions:
      temperature_K: 10
    locator:
      page: 4
      figure: 2
    review_state: preliminary_01A

relations: []

cef: null
```

## 8.1 Required top-level fields

```text
source_id
evidence_record_version
evidence
```

Optional:

```text
applicability
relations
cef
```

## 8.2 Evidence category vocabulary

Allowed exactly:

```text
MEASURED
DERIVED
FITTED
ASSUMED
CALCULATED
INTERPRETED_BY_AUTHORS
INFERENCE_FOR_DyFeO3
```

Synonymous substitutes are invalid.

Examples of invalid category names:

```text
OBSERVED
MODELLED
AUTHOR_CLAIM
OUR_INFERENCE
EXTRACTED
ESTIMATED
```

unless later added through explicit schema revision.

## 8.3 Evidence item required fields

Every evidence item requires:

```text
evidence_id
category
claim
```

Recommended evidence ID pattern:

```text
EV-SRC000137-001
```

Formal pattern:

```text
^EV-SRC[0-9]{6}-[0-9]{3,}$
```

Evidence IDs are stable within the source record once canonically materialized.

They are not recycled.

## 8.4 `claim`

Short structured-prose statement describing what the source supports.

It must preserve the semantic category.

Examples:

```text
MEASURED:
"An inelastic feature was observed at ..."

FITTED:
"The authors fitted the spectrum with ..."

ASSUMED:
"The calculation assumed ..."

INFERENCE_FOR_DyFeO3:
"This method could transfer to DyFeO3 because ..."
```

## 8.5 Optional `quantity`

Schema:

```yaml
quantity:
  value:
  uncertainty:
  unit:
```

`uncertainty` may be null if not reported.

Never fabricate missing uncertainty.

## 8.6 Optional `conditions`

Supported fields:

```yaml
conditions:
  temperature_K:
  field_T:
  Q:
  geometry:
  polarization:
```

Only applicable fields should be present/populated.

## 8.7 Optional `locator`

Supported fields:

```yaml
locator:
  page:
  section:
  figure:
  table:
  equation:
  quote_location:
```

A locator is strongly preferred for evidence extracted from accessible full text but is not universally mandatory where source pagination or archival format prevents it.

Do not fabricate page/figure identifiers.

## 8.8 `review_state`

Optional evidence-level state.

Allowed initially:

```text
preliminary_01A
reviewed_01
held
```

This is subordinate to the source-level workflow state.

## 8.9 Applicability block

Optional structured index:

```yaml
applicability:
  compounds: []
  sample_forms: []
```

Detailed scientific transferability reasoning remains evidence items, normally under:

```text
INTERPRETED_BY_AUTHORS
INFERENCE_FOR_DyFeO3
```

as appropriate.

# 9. CEF_SPECIFIC_SCHEMA

Optional:

```yaml
cef:
```

The block must support at least:

```text
ion
J_manifold
site_symmetry
crystallographic_setting
local_axes
formalism
normalization
units
B_lm
levels
degeneracies
eigenstates
g_tensor
R_Fe_exchange
R_R_exchange
INS_intensities
Q_dependence
polarization
temperature_dependence
structure_CEF_model
```

Suggested structure:

```yaml
cef:
  ion:
  J_manifold:
  site_symmetry:

  crystallographic_setting:

  coordinate_convention:
    local_axes:
    formalism:
    normalization:
    parameter_units:

  B_lm: []

  levels: []

  eigenstates: null
  g_tensor: null

  exchange:
    R_Fe:
    R_R:

  ins:
    intensities: []
    Q_dependence:
    polarization:

  temperature_dependence: []

  structure_CEF_model:
```

## 9.1 CEF completeness invariant

Any source-level record containing numerical CEF parameters `B_l^m` must also contain sufficient convention metadata to interpret them.

Required together:

```text
local axes
Stevens/Wybourne or equivalent formalism
normalization
parameter units
```

If one or more are absent:

```text
CEF_PARAMETER_CONTEXT_INCOMPLETE
```

The values may still be preserved as historically reported evidence, but must be marked incomplete and must not be treated as directly comparable/transferrable parameters.

# 10. SEARCH_PASS_SCHEMA

Canonical file:

```text
05_Literature/SEARCH_LOG/SP-*.yaml
```

Canonical ID pattern:

```text
SP-YYYYMMDD-TOPIC-NN
```

Example:

```text
SP-20260910-DYFEO3-01
```

ID is immutable after materialization.

## 10.1 Allowed modes

Exactly:

```text
GLOBAL_BASELINE
INCREMENTAL_WATCH
RETROSPECTIVE_MIGRATION
```

## 10.2 Required fields

Every search pass requires:

```text
search_pass_id
mode
objective
scope
executed_at
executed_by_role
sources
queries
seed_sources
sources_found
sources_rejected
duplicates
citation_chains_followed
unresolved_targets
termination_reason
result_state
```

## 10.3 `scope`

Must support:

```yaml
scope:
  branches: []
  compounds: []
  techniques: []
  date_scope:
  language_scope: []
```

Only relevant subfields need be populated.

## 10.4 `sources`

Must support separation of:

```yaml
sources:
  databases: []
  search_engines: []
  repositories: []
  archives: []
  citation_indices: []
```

Only used categories need be populated.

## 10.5 `queries`

Each material query should support:

```yaml
queries:
  - source:
    query:
    language:
    date_filter:
    result:
```

Exact query text must be preserved when recoverable.

## 10.6 Search-result vocabulary

Allowed result state for an individual target/query outcome:

```text
FOUND
SEARCHED_NOT_FOUND
NOT_SEARCHED
INACCESSIBLE
BIBLIOGRAPHY_UNRESOLVED
```

Critical invariant:

```text
SEARCHED_NOT_FOUND
!=
SOURCE_DOES_NOT_EXIST
```

No search-pass state may assert nonexistence merely from failed search.

## 10.7 Retrospective migration

For historical chat/source migration, unrecoverable original query strings must not be invented.

Supported fields:

```yaml
query_recovered: false
provenance_origin: historical_chat
```

When available:

```yaml
original_search_date:
```

may be preserved.

When not known, use null or explicit unknown according to schema representation.

# 11. GAP_SCHEMA

Canonical file:

```text
05_Literature/GAPS.yaml
```

Top-level identity:

```text
GAP-000001
GAP-000002
...
```

Formal pattern:

```text
^GAP-[0-9]{6}$
```

Gap IDs are stable and never recycled.

Example:

```yaml
GAP-000012:
  question: "Recover primary Schuchert 1969 DyFeO3 source"
  importance: high
  status: open
  gap_type: primary_source_recovery

  current_evidence:
    - SRC-000044

  search_passes_attempted:
    - SP-20260910-HISTORICAL-01

  next_search:
    - "Trace exact journal/report bibliography"

  blocked_reason: null

  resolved_by: []
```

## 11.1 Required fields

```text
question
importance
status
gap_type
current_evidence
search_passes_attempted
next_search
blocked_reason
resolved_by
```

Lists may be empty where appropriate.

## 11.2 Gap statuses

Allowed exactly:

```text
open
partially_resolved
resolved
blocked
probably_unrecoverable
```

Critical invariant:

```text
probably_unrecoverable
!=
does_not_exist
```

It means currently unlikely to be recoverable after documented attempts.

## 11.3 `importance`

Recommended controlled values:

```text
low
medium
high
critical
```

## 11.4 Resolution

For:

```text
status: resolved
```

`resolved_by` must contain at least one durable reference, e.g.:

```text
SOURCE_ID
SEARCH_PASS_ID
other canonical evidence identifier
```

# 12. CITATION_RELATION_MODEL

Citation/reuse relationships are structured edges stored in source evidence records.

No independent graph store in v1.

Stable edge IDs:

```text
EDGE-000001
EDGE-000002
...
```

Formal pattern:

```text
^EDGE-[0-9]{6}$
```

Example:

```yaml
relations:
  - edge_id: EDGE-000412
    from_source: SRC-000137
    to_source: SRC-000044
    relation_type: parameter_reuse
    evidence_independence: not_independent

    locator:
      page: 7

    note: "Uses the parameter set attributed to the earlier source."
```

## 12.1 Required edge fields

```text
edge_id
from_source
to_source
relation_type
evidence_independence
```

Optional:

```text
locator
note
supporting_evidence_ids
```

## 12.2 Relation types

Allowed exactly:

```text
cites
independent_confirmation
derivative_citation
historical_reference
parameter_reuse
level_scheme_reuse
method_reference
contradiction
translation
work_version
conference_precursor
expanded_version
```

## 12.3 Evidence independence

Allowed exactly:

```text
independent
partially_independent
not_independent
unknown
```

This field is mandatory for scientific citation/reuse relations.

It prevents repeated citation or reuse from being counted automatically as independent evidence.

## 12.4 Edge integrity

Both:

```text
from_source
to_source
```

must resolve to canonical SOURCE_ID records, including retained merged records where historical provenance genuinely requires them.

New active relations should normally target surviving active records rather than merged aliases.

# 13. WORK_FAMILY_MODEL

Fundamental distinction:

```text
SOURCE_ID = bibliographic object

work_family_id = family of related bibliographic manifestations
```

Examples of one work family:

```text
Russian original
English translation
preprint
publisher version
conference precursor
technical report
thesis chapter
```

## 13.1 Work-family IDs

Format:

```text
WF-000001
WF-000002
...
```

Stable once allocated.

No separate `WORK_FAMILIES.yaml` in v1.

Membership is indexed in source records and relations.

## 13.2 Work-version roles

Allowed initially:

```text
original
translation
preprint
publisher_version
conference_precursor
technical_report
thesis_version
thesis_chapter
expanded_journal_version
later_reanalysis
```

A source record participating in a family may include conceptually:

```yaml
work_family_id: WF-000021
work_version_role: translation
```

`work_version_role` therefore becomes permitted optional registry metadata when `work_family_id` is non-null.

## 13.3 Scientific evidence invariant

```text
multiple SOURCE_IDs
!=
multiple independent scientific evidence units
```

Translation/original and preprint/publisher relationships must be represented explicitly.

Independence is assessed through relations/evidence, not bibliographic count.

# 14. MATERIALIZATION_PACKET_SCHEMA

Canonical packet path:

```text
05_Literature/PACKETS/MP-*.yaml
```

Packet ID format:

```text
MP-YYYYMMDD-01A-NN
```

Example:

```text
MP-20260910-01A-01
```

Packet IDs are immutable.

## 14.1 Required packet fields

```yaml
packet_id:
packet_schema_version:
producer_role:
source_search_passes: []
operations: []
unresolved_ambiguities: []
validation_status:
```

## 14.2 Producer role

For v1 discovery packets:

```text
producer_role: 01A
```

Future schema revisions may support other producers explicitly.

## 14.3 Supported operation types

Allowed v1 operation vocabulary exactly:

```text
SOURCE_CREATE
SOURCE_UPDATE
EVIDENCE_ADD
EVIDENCE_UPDATE
SEARCH_PASS_ADD
ADD_CITATION_EDGE
GAP_CREATE
GAP_UPDATE
WORK_FAMILY_LINK

ZOTERO_CREATE
ZOTERO_LINK_EXISTING
ADD_COLLECTION
ADD_TAG
```

The final four Zotero-facing operations are **requests for future action**.

Their presence does not authorize Zotero mutation.

## 14.4 Required operation fields

Every operation requires:

```yaml
operation_id:
type:
payload:
```

Conditional contextual fields may include:

```text
source_ref
gap_id
search_pass_id
preconditions
temporary_ref
```

## 14.5 Operation IDs

Operation IDs must be unique within packet.

Recommended:

```text
OP-001
OP-002
...
```

Identity is therefore composite:

```text
packet_id + operation_id
```

## 14.6 Preconditions

Update operations should support optimistic preconditions such as:

```yaml
preconditions:
  expected_record_version: 3
```

Other exact identity preconditions may be added later by implementation while preserving schema semantics.

Mismatch:

```text
PACKET_PRECONDITION_FAILURE
```

No silent overwrite.

## 14.7 Idempotency

Packet application must be idempotent where possible.

Previously applied:

```text
packet_id + operation_id
```

must result in either:

```text
NO_OP_ALREADY_APPLIED
```

or a controlled conflict if current canonical state differs from the previously applied result.

It must never silently create a duplicate second record.

## 14.8 Ambiguity

`unresolved_ambiguities` must capture unresolved identity, bibliography, duplicate or provenance questions relevant to materialization.

If ambiguity prevents safe mutation:

```text
validation_status: needs_review
```

and the ambiguous operation must not auto-apply.

# 15. WORKFLOW_STATE_MODEL

Allowed source-level workflow states exactly:

```text
DISCOVERED
PROVENANCE_VERIFIED
READY_FOR_01
01_REVIEWED
CANONICAL_PROJECT_USE
HOLD
REJECTED
```

## 15.1 Authorities

### 01A may assign

```text
DISCOVERED
PROVENANCE_VERIFIED
READY_FOR_01
HOLD
```

where `HOLD` requires:

```text
hold_scope: provenance
```

### 01 may assign

```text
01_REVIEWED
HOLD
REJECTED
```

where scientific hold requires:

```text
hold_scope: scientific
```

### Project Control alone may assign

```text
CANONICAL_PROJECT_USE
```

## 15.2 Promotion invariant

Preliminary 01A classifications do not become final scientific conclusions by schema transition alone.

In particular:

```text
READY_FOR_01
!=
01_REVIEWED

01_REVIEWED
!=
CANONICAL_PROJECT_USE
```

# 16. BRANCH_TAXONOMY

B01–B16 are canonical Git discovery classifications.

Freeze exactly:

```text
B01 DyFeO3 direct
B02 stoichiometric RFeO3
B03 Soviet/Russian historical
B04 optical/Zeeman/FIR/EPR
B05 neutron CEF / INS
B06 CEF inverse problem / identifiability
B07 CEF conventions / transforms
B08 structure → CEF
B09 exchange-aware CEF
B10 magnetoelastic / phonon–CEF
B11 neutron cross section / intensity methodology
B12 software/reproducibility
B13 Fe-only controls
B14 substituted orthoferrites
B15 RCrO3 comparators
B16 RGaO3 / RAlO3 structural comparators
```

They are not required to map one-to-one to:

```text
Zotero collections
Zotero tags
```

Git is authoritative for branch classification.

# 17. BRANCH_SATURATION_MODEL

Canonical file:

```text
05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml
```

Allowed states exactly:

```text
OPEN
DEVELOPING
NEAR_SATURATION
SATURATED_V1
```

A branch assessment must be able to record basis across:

```text
primary_source_coverage
citation_chain_closure
method_coverage
compound_coverage
historical_language_coverage
duplicate_yield
remaining_high_priority_gaps
```

Example:

```yaml
B01:
  status: NEAR_SATURATION

  basis:
    primary_source_coverage: strong
    citation_chain_closure: strong
    method_coverage: moderate
    compound_coverage: strong
    historical_language_coverage: incomplete
    duplicate_yield: high
    remaining_high_priority_gaps: 1

  assessed_from_search_passes:
    - SP-20260910-DYFEO3-04
```

Percentages may be included diagnostically but are not the principal completion criterion.

`SATURATED_V1` means:

```text
no further high-yield systematic search is currently justified under frozen v1 scope
```

It does not mean future literature cannot appear.

# 18. SCHEMA_V1_CONTRACT

Canonical schema definition file:

```text
05_Literature/SCHEMA_V1.yaml
```

It is the machine-readable vocabulary/constraint source corresponding to this specification.

It must contain or encode at least:

```text
repository_schema_version
ID patterns
allowed enumerations
branch IDs
workflow states
evidence categories
gap statuses
relation types
evidence-independence states
search modes
search-result vocabulary
packet operation types
required field definitions
conditional invariants
```

This Markdown specification remains the human-governance authority.

`SCHEMA_V1.yaml` is its machine-readable implementation.

If the two disagree:

```text
STOP_SCHEMA_DIVERGENCE
```

until corrected through governance.

# 19. VALIDATION_CONTRACT

Future offline validator path:

```text
scripts/literature/literature_validate.py
```

The validator is part of the `LIT-INFRA-01` implementation scope but is not implemented by this specification task.

It must operate without:

```text
Zotero
network
PDF files
external scientific datasets
API credentials
```

## 19.1 Required offline validations

At minimum:

```text
SOURCE_ID uniqueness
SOURCE_ID format
no canonical SRC-PENDING IDs
record_version validity
record_status validity
merged_into target validity

duplicate DOI candidates
DOI normalization/format

registry evidence path resolution
evidence source_id exists
evidence filename/source_id agreement
evidence_id uniqueness
valid evidence categories

valid branch IDs
valid workflow states
HOLD requires valid hold_scope

valid GAP IDs
valid gap statuses
resolved gap has resolution evidence

SEARCH_PASS_ID uniqueness
SEARCH_PASS_ID format
valid search mode
valid search-result vocabulary

EDGE ID uniqueness
EDGE ID format
citation endpoints exist
valid relation type
valid evidence_independence

work-family ID format
work-family references valid
work-version role valid

citation-key uniqueness among non-null keys

packet ID uniqueness
packet operation IDs unique per packet
valid packet operation types
packet references resolvable
no unsafe unresolved pending IDs in canonical stores
```

## 19.2 Duplicate DOI behavior

Exact normalized duplicate DOI across active canonical sources must produce:

```text
DUPLICATE_CANDIDATE
```

and fail closed unless an explicitly represented bibliographic exception is permitted by a future schema revision.

Do not automatically merge.

## 19.3 Live Zotero validation

Live Zotero checking is a separate optional later validation layer.

It may eventually validate:

```text
Zotero availability
Server-ID consistency
library alias
item key existence
DOI agreement
citation-key agreement
attachment identity
```

It must not become mandatory for ordinary Git CI.

# 20. FAILURE_TAXONOMY

Freeze at minimum:

```text
SOURCE_ID_COLLISION
SEARCH_PASS_ID_COLLISION
BIBLIOGRAPHIC_AMBIGUITY
DUPLICATE_CANDIDATE
PRIMARY_SOURCE_UNRESOLVED

MATERIALIZATION_SCHEMA_FAILURE
PACKET_PRECONDITION_FAILURE

CITATION_EDGE_DANGLING
EVIDENCE_REFERENCE_DANGLING
UNKNOWN_BRANCH_ID
INVALID_EVIDENCE_CATEGORY
INVALID_GAP_STATUS

BIBTEX_KEY_COLLISION
BIBTEX_EXPORT_MISMATCH

ZOTERO_UNAVAILABLE
ZOTERO_AUTHORIZATION_REQUIRED
ZOTERO_WRITE_DENIED
ZOTERO_IDENTITY_MISMATCH
ZOTERO_SERVER_ID_CHANGED
ZOTERO_WRITE_CONFLICT

LOCAL_CONFIG_MISSING
```

Additional schema-validation failures frozen here:

```text
INVALID_SOURCE_ID
CANONICAL_PENDING_SOURCE_ID
INVALID_WORKFLOW_STATE
INVALID_SEARCH_PASS_ID
INVALID_EDGE_ID
INVALID_PACKET_ID
INVALID_RELATION_TYPE
INVALID_EVIDENCE_INDEPENDENCE
INVALID_SEARCH_MODE
INVALID_SEARCH_RESULT_STATE
CEF_PARAMETER_CONTEXT_INCOMPLETE
STOP_SCHEMA_DIVERGENCE
```

Core invariant:

```text
ambiguity
→
NEEDS_REVIEW / fail closed
```

Never:

```text
ambiguity
→
automatic create/update/merge
```

# 21. ZOTERO_BOUNDARY

This specification freezes architecture only.

Later architecture:

```text
Zotero
=
bibliographic metadata + PDF/attachment authority

Zotero Desktop Local API
=
preferred first automation backend

Zotero Web API
=
deferred backend

Zotero writes
=
separately authorized future operation
```

This specification does not authorize:

```text
Zotero configuration
Zotero API calls
local read
local write
Web API implementation
credential creation
```

Do not create during `LIT-INFRA-01`:

```text
configs/local_zotero.yaml
scripts/literature/zotero_sync.py
```

# 22. ZOTERO_IDENTITY_BOUNDARY

Future Git bridge uses:

```yaml
zotero:
  library_alias:
  item_key:
  link_status:
```

`item_key` is an external bridge pointer.

It is not canonical project identity.

If Zotero item is:

```text
deleted
recreated
merged
moved between libraries
restored with changed item keys
```

`SOURCE_ID` remains unchanged.

Bridge state becomes:

```text
stale
or
needs_review
```

until relinked.

# 23. BETTER_BIBTEX_BOUNDARY

Freeze:

```text
Better BibTeX recommended: true
```

Identity invariant:

```text
SOURCE_ID
!=
Zotero item key
!=
BibTeX citation key
```

No identifier derives authority from another.

Later:

```text
Zotero + Better BibTeX
→
05_Literature/references.bib
```

But `LIT-INFRA-01` does not authorize:

```text
Better BibTeX installation/configuration
citation-key formula freeze
auto-export configuration
references.bib creation
```

# 24. REFERENCES_BIB_BOUNDARY

Planned later artifact:

```text
05_Literature/references.bib
```

Policy:

```text
derived-but-tracked
```

Generating authority:

```text
Zotero + Better BibTeX
```

Git records history/diffs.

Normal manual bibliographic editing of generated BibTeX is not authoritative.

The artifact is introduced only after its own Zotero/Better BibTeX bootstrap and acceptance.

# 25. PDF_ATTACHMENT_POLICY

Canonical boundary:

```text
Zotero / external personal literature storage:
  PDFs
  scans
  supplements
  archival copies

Git:
  metadata
  hashes
  provenance
  identity
  evidence
```

Git source/evidence metadata may later record:

```text
attachment_status
attachment_type
sha256
retrieval_source
retrieval_date
redistribution_status
```

No absolute attachment filesystem path is canonical.

PDF SHA-256 is recommended especially for:

```text
important primary sources
historical scans
hard-to-recover archival documents
conflicting versions/scans
quantitatively used supplements
```

It is optional for routine recoverable attachments.

# 26. COPYRIGHT_BOUNDARY

Public Git repository must not become a bulk copyrighted-document archive.

Distinguish:

```text
bibliographic/provenance metadata
open-access attachment
personal-use attachment
public-domain/archive material
```

Possession/access does not imply redistribution authorization.

Default:

```text
PDF bytes outside Git
metadata/hash inside Git
```

No literature-infrastructure schema field may imply redistribution rights merely from:

```text
full_text_status: obtained
```

# 27. MIGRATION_BOUNDARY

Existing `01A` history will later be migrated from actual historical records.

Required process:

```text
historical chat/source record
→ retrospective structured extraction
→ provenance verification
→ materialization packet
→ controlled Git/Zotero integration
```

Do not regenerate historical baseline from model memory alone.

Mode:

```text
RETROSPECTIVE_MIGRATION
```

If original query cannot be recovered:

```yaml
query_recovered: false
provenance_origin: historical_chat
```

No invented historical query.

No migration is authorized by this specification.

# 28. BASELINE_AND_WATCH_COMPATIBILITY

Both:

```text
GLOBAL_BASELINE
INCREMENTAL_WATCH
```

use the same:

```text
SOURCE_REGISTRY
SOURCE_ID namespace
EVIDENCE store
GAPS
citation relation model
```

Rediscovery by watch must resolve against existing source identity before any `SOURCE_CREATE`.

A known source produces:

```text
SOURCE_UPDATE
duplicate/no-op
```

not a new SOURCE_ID.

# 29. MATERIALIZATION_BOUNDARY

This specification defines materialization packet semantics but does not authorize packet application.

Actual packet materialization belongs to:

```text
LIT-INFRA-02
```

after:

```text
LIT-INFRA-01 schema foundation accepted
```

The schema foundation may validate packet syntax/reference integrity but must not perform project literature migration.

# 30. 01A_BOOTSTRAP_BOUNDARY

Final durable-output instructions for `01A` must not be issued until at least:

```text
LIT-INFRA-01 accepted
LIT-INFRA-02 packet materializer accepted
```

Therefore:

```yaml
final_01a_bootstrap_authorized: false
```

The intended future output after each meaningful search pass remains:

```text
SEARCH_PASS record
source create/update operations
evidence additions/updates
citation relations
work-family relations
gap updates
requested future Zotero operations
explicit unresolved ambiguities
```

But no final 01A bootstrap is frozen here.

# 31. LIT-INFRA-01_IMPLEMENTATION_SCOPE

After this specification is canonically frozen and Project Control later issues separate implementation authorization, `LIT-INFRA-01` may create only the Git schema foundation and its offline validator.

Exact proposed allowlist:

```text
CREATE:
05_Literature/SOURCE_REGISTRY.yaml
05_Literature/GAPS.yaml
05_Literature/SCHEMA_V1.yaml
05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml
scripts/literature/literature_validate.py

MODIFY:
none

DELETE:
none
```

## 31.1 `.gitkeep`

Not included.

Reason:

```text
Git does not track directories as canonical semantic entities.
Empty EVIDENCE/ and PACKETS/ directories provide no durable information.
```

They become materialized automatically when real evidence or packet records are introduced in later authorized stages.

## 31.2 Validator inclusion

The validator **is included** in `LIT-INFRA-01`.

Reason:

```text
schema + authority definitions without offline enforcement
would not constitute a complete reproducible Git schema foundation.
```

However, this specification freezes only the validator contract.

Exact implementation logic remains subject to later implementation review.

## 31.3 Initial file semantics

`SOURCE_REGISTRY.yaml`:

```text
valid empty registry
```

`GAPS.yaml`:

```text
valid empty gap registry
```

`BRANCH_STATUS.yaml`:

must represent B01–B16 with initial status chosen only according to separately reviewed current literature state.

Because assigning saturation states is a substantive literature-state action, `LIT-INFRA-01` implementation should preferably initialize structure without making unsupported branch-saturation claims.

A conforming neutral representation is:

```yaml
schema_version: "1.0"
branches:
  B01:
    status: OPEN
    assessment_status: not_assessed
```

or an equivalent schema-approved neutral initialization.

`OPEN` at initialization means:

```text
not canonically declared saturated
```

not:

```text
no literature work has occurred
```

Historical baseline migration will later establish richer assessment evidence.

# 32. IMPLEMENTATION_SCOPE_EXPANSION

If later implementation discovers a need to create/modify another tracked file:

```text
STOP_SCOPE_EXPANSION
```

Examples requiring stop:

```text
README modification
PROJECT_METADATA modification
requirements.txt modification
.gitignore modification
new Zotero config
packet materializer
references.bib
migration artifacts
```

Such additions require separate governance authorization.

# 33. SCHEMA_VERSIONING

Repository schema version:

```text
1.0
```

Changes that modify allowed semantics require explicit schema version review.

Examples:

```text
new evidence category
new workflow state
new relation type
changed SOURCE_ID semantics
changed authority matrix
changed gap-status vocabulary
changed packet operation semantics
```

Do not silently mutate `SCHEMA_V1.yaml` while retaining the same governance meaning if the change is substantive.

Minor clarifications that do not change accepted semantics may remain within v1 only through controlled review.

# 34. GOVERNANCE_SEQUENCE

Required lifecycle:

```text
accepted LIT-KNOWLEDGE-INFRA-V1 design
→
freeze LIT-INFRA-SCHEMA-SPEC v1.0
→
canonical specification materialization
→
Project Control verifies freeze
→
separate LIT-INFRA-01 implementation authorization
→
schema foundation + offline validator implementation
→
07 technical review
→
Project Control acceptance
→
LIT-INFRA-02 design/authorization
→
packet materializer
→
final 01A durable-output bootstrap
→
Zotero integration stages
```

No self-authorization.

# 35. STOP_CONDITIONS

Immediate stop on:

```text
STOP_SCOPE_EXPANSION
STOP_SCHEMA_DIVERGENCE
STOP_AUTHORIZATION_MISSING
STOP_SOURCE_ID_POLICY_CHANGE
STOP_AUTHORITY_CONFLICT
STOP_ZOTERO_SCOPE_ENTRY
STOP_BIBTEX_SCOPE_ENTRY
STOP_MIGRATION_SCOPE_ENTRY
STOP_01A_BOOTSTRAP_SCOPE_ENTRY
```

# 36. TERMINAL_STATE

Before canonical specification materialization:

```yaml
specification_id: LIT-INFRA-SCHEMA-SPEC
specification_version: "1.0"
specification_status: proposed_for_freeze

design_id: LIT-KNOWLEDGE-INFRA-V1

repository_schema_version: "1.0"

implementation_stage: LIT-INFRA-01
implementation_status: not_started
implementation_authorized: false

zotero_configuration_authorized: false
zotero_write_authorized: false
web_api_implementation_authorized: false
better_bibtex_configuration_authorized: false
references_bib_creation_authorized: false
literature_migration_authorized: false
final_01a_bootstrap_authorized: false
```

## Specification summary

```text
SPECIFICATION_ID:
LIT-INFRA-SCHEMA-SPEC

SPECIFICATION_VERSION:
1.0

SPECIFICATION_PATH:
03_Protocols/LITERATURE_KNOWLEDGE_SCHEMA_V1_0.md

DESIGN_ID:
LIT-KNOWLEDGE-INFRA-V1

SOURCE_ID_POLICY:
immutable sequential project IDs:
SRC-000001, SRC-000002, ...
never renamed
never recycled
independent of Zotero item key, citation key, slug and corrected bibliography

REPOSITORY_SCHEMA_VERSION:
1.0
```

### PROPOSED_LIT_INFRA_01_IMPLEMENTATION_ALLOWLIST

```text
CREATE:
05_Literature/SOURCE_REGISTRY.yaml
05_Literature/GAPS.yaml
05_Literature/SCHEMA_V1.yaml
05_Literature/SEARCH_LOG/BRANCH_STATUS.yaml
scripts/literature/literature_validate.py

MODIFY:
none

DELETE:
none
```

`.gitkeep` files are deliberately excluded. `EVIDENCE/` and `PACKETS/` are logical schema paths that will materialize with real records.

```text
ZOTERO_CONFIGURATION_AUTHORIZED:
false

ZOTERO_WRITE_AUTHORIZED:
false

WEB_API_IMPLEMENTATION_AUTHORIZED:
false

BETTER_BIBTEX_CONFIGURATION_AUTHORIZED:
false

REFERENCES_BIB_CREATION_AUTHORIZED:
false

LITERATURE_MIGRATION_AUTHORIZED:
false

01A_FINAL_BOOTSTRAP_AUTHORIZED:
false

READY_FOR_SCHEMA_FREEZE:
true
```

The proposed path `03_Protocols/LITERATURE_KNOWLEDGE_SCHEMA_V1_0.md` has no current canonical naming conflict. Current `main` is `be0906d78bc1a168c9e1658cb472bbce89589e3d`; this repository advance is from the separate infrastructure-CI freeze and does not alter the accepted literature schema design. 

**A — SCHEMA_READY_FOR_FREEZE**
