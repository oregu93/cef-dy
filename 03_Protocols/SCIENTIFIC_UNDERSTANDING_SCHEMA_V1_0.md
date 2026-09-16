---
title: "CEF Dy - Scientific Understanding schema v1.0"
type: protocol
status: frozen
specification_id: SCIENTIFIC-UNDERSTANDING-SCHEMA
specification_version: "1.0"
version: "1.0"
updated: 2026-09-16
---

# Scientific Understanding schema v1.0

## 1. Назначение и границы authority

`Scientific Understanding` - пятая функция существующей Research Knowledge
Base: долговечное концептуальное, объяснительное и выводное научное знание.
Она не заменяет и не дублирует:

- `PROJECT_STATE` - текущее научное состояние;
- `PROJECT_CONTROL` - governance и порядок работ;
- registers - evidence, results, hypotheses, models и decisions;
- `WORK_CHECKPOINTS` - воспроизводимое исполнение;
- `RESEARCH_LOGBOOK` - развитие логики исследования;
- `05_Literature` - source identity, bibliographic authority и extracted evidence.

Канонический corpus после отдельного разрешения располагается в
`06_Scientific_Understanding/`. До pilot этот каталог не создаётся. Схема
остаётся обычным Markdown/YAML, редактируемым через GitHub и локальный Git;
Obsidian syntax и graph database не требуются.

Authority freeze:

```yaml
schema_id: SCIENTIFIC-UNDERSTANDING-SCHEMA
schema_version: "1.0"
schema_status: frozen
parent_design: SCIENTIFIC-UNDERSTANDING-SCHEMA-DESIGN-001
freeze_review: SCIENTIFIC-UNDERSTANDING-SCHEMA-FREEZE-001
specialist_reviews:
  - SCIENTIFIC-UNDERSTANDING-SCHEMA-REVIEW-01-001
  - SCIENTIFIC-UNDERSTANDING-SCHEMA-REVIEW-03-001
  - SCIENTIFIC-UNDERSTANDING-SCHEMA-REVIEW-04-001
```

## 2. Stable identity

Canonical ID:

```text
SU-000001
pattern: ^SU-[0-9]{6}$
```

SU IDs immutable, non-recyclable and independent of filename, title and
`knowledge_kind`. Editing wording or correcting the same scientific object
does not change its ID. Conceptual replacement uses `review_status:
superseded` and `superseded_by`. Human-readable slugs are never foreign keys.
Chat/archive candidates receive no ID before deduplication and scientific and
source review.

Identifiers `SU-900001` ... `SU-900007` used during design review were
illustrative only: they are not allocated, reserved or canonical.

## 3. Canonical front matter

Every canonical note is one Markdown file with YAML front matter:

```yaml
---
id: SU-000001
title: "..."

knowledge_kind: concept
review_status: working

epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []

scope:
  level: GENERAL_PHYSICS

transferability:
  status: GENERAL
  conditions: []
  exclusions: []
  facets:
    kramers_class: NOT_APPLICABLE
    magnetic_order: NOT_APPLICABLE
    exchange_treatment: NOT_APPLICABLE
    temperature_regime: null
    field_regime: null

relations:
  depends_on: []
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples: []
  related_concepts: []

sources:
  background: []
  claim_support: []

convention_refs: []
common_confusions: []
dissertation_roles: []
---
```

Optional blocks/fields when unused:

```text
convention_binding
origin_trail
superseded_by
scope.compounds
scope.rare_earth_ions
scope.method_classes
scope.experiment_classes
```

Do not manually duplicate derived data such as backlinks,
`generalizes_to`, incoming dependencies, graph neighbourhood, resolved
titles, bibliography, evidence categories/review state, chapter ordering or
formula index.

## 4. Knowledge kind and review status

`knowledge_kind` is exactly one of:

```text
concept
method_explanation
derivation
```

- `concept`: physical object, principle, distinction or reusable idea;
- `method_explanation`: why/how a measurement, inference, transformation or
  analysis method works, not an execution specification;
- `derivation`: explanation whose mathematical reasoning or transformation
  and validity assumptions must be reconstructable.

Do not create additional kinds for principle, project reasoning, confusion,
literature note or dissertation note.

`review_status` is exactly:

```text
working
reviewed
superseded
```

`validated` is not an SU v1 status. `superseded` requires a different,
resolvable `superseded_by: SU-xxxxxx`.

## 5. Epistemic basis

```yaml
epistemic_basis:
  primary: GENERAL_OR_TEXTBOOK
  additional: []
```

`primary` is mandatory. `primary` and each unique `additional` value must be
one of:

```text
GENERAL_OR_TEXTBOOK
LITERATURE_SUPPORTED
PROJECT_DERIVED
PROJECT_ASSUMPTION
OPEN_OR_CONTESTED
```

### GENERAL_OR_TEXTBOOK

May represent general definitions, standard formalism, mathematical
relationships and established method principles. Alone it cannot carry
compound-specific empirical claims, historical assignments, author
interpretations, project inference or material-specific fitted/numerical
results. A note whose only basis is `GENERAL_OR_TEXTBOOK` cannot declare
`COMPOUND_SPECIFIC` or `EXPERIMENT_SPECIFIC` scope.

### LITERATURE_SUPPORTED

For `review_status: reviewed`, at least one relevant
`sources.claim_support` entry must resolve to an `EV-SRC*` record with
`review_state: reviewed_01`. `preliminary_01A` may support `working` only;
`held` cannot satisfy the reviewed gate.

The literature evidence category remains authoritative. Never strengthen:

```text
DERIVED != MEASURED
FITTED != MEASURED
CALCULATED != MEASURED
ASSUMED != ESTABLISHED
INTERPRETED_BY_AUTHORS != ESTABLISHED_FACT
INFERENCE_FOR_DyFeO3 != SOURCE_MEASUREMENT
```

### PROJECT_DERIVED

Requires non-empty `relations.derived_from`. For a reviewed physical claim,
provenance must include an object that establishes the claim, normally
`EV-*`, `R-*` or equivalent reviewed scientific-result artifact.
`D-*`, protocol, task, checkpoint or authorization alone may establish
reasoning/method/convention/governance provenance, but not a physical claim.
`project_examples` never establishes `PROJECT_DERIVED`.

If substantive reasoning depends on unestablished `H-*` or `MOD-*`, include
`PROJECT_ASSUMPTION` as a primary or additional basis.

### PROJECT_ASSUMPTION

Requires explicit relevant `H-*`, `MOD-*`, `D-*` or frozen-specification
provenance. It marks dependence on an assumption/model/hypothesis rather than
established physical fact.

### OPEN_OR_CONTESTED

States that the reviewed knowledge is the unresolved or contested condition;
it does not establish one competing interpretation.

## 6. Scope

```yaml
scope:
  level: GENERAL_PHYSICS
  compounds: []
  rare_earth_ions: []
  method_classes: []
  experiment_classes: []
```

`scope.level` is exactly:

```text
GENERAL_PHYSICS
METHOD_CLASS
RFEO3_FAMILY
RARE_EARTH_CLASS
COMPOUND_SPECIFIC
EXPERIMENT_SPECIFIC
```

These are categories, not a strict inheritance hierarchy.

Conditional requirements:

```text
METHOD_CLASS        -> method_classes nonempty
COMPOUND_SPECIFIC   -> compounds nonempty
EXPERIMENT_SPECIFIC -> experiment_classes or identifiable experiment/project reference nonempty
```

## 7. Transferability

```yaml
transferability:
  status: CONDITIONAL
  conditions: []
  exclusions: []
  facets:
    kramers_class: ANY
    magnetic_order: ANY
    exchange_treatment: ANY
    temperature_regime: null
    field_regime: null
```

Status is exactly:

```text
GENERAL
CONDITIONAL
BOUND_TO_SCOPE
NOT_ASSESSED
```

Facet vocabularies:

```text
kramers_class:      ANY | KRAMERS | NON_KRAMERS | UNKNOWN | NOT_APPLICABLE
magnetic_order:     ANY | ORDERED | DISORDERED | UNKNOWN | NOT_APPLICABLE
exchange_treatment: ANY | INCLUDED | NEGLECTED | UNKNOWN | NOT_APPLICABLE
```

`UNKNOWN` means the facet matters but is not established.
`NOT_APPLICABLE` means it is irrelevant. They are never normalized into one
another.

For a reviewed `RFEO3_FAMILY + LITERATURE_SUPPORTED` note, one-compound
empirical evidence alone is insufficient unless support includes explicit
general theory or family-wide evidence/analysis. Multiple compounds do not by
count alone prove generality.

Cross-R transfer is fail-closed. Membership in RFeO3 never implies the same:

```text
B_l^m
local axes
CEF level topology
Kramers class
R-Fe exchange state
magnetic structure/state
transition strengths
```

## 8. Relations

Canonical relation block and complete v1 vocabulary:

```yaml
relations:
  depends_on: []
  specializes: []
  contrasts_with: []
  derived_from: []
  project_examples: []
  related_concepts: []
```

- `depends_on`: directional prerequisite, targets `SU-*`;
- `specializes`: this object is narrower than target `SU-*`, directional;
- `contrasts_with`: explicit distinction, targets `SU-*`, semantically
  symmetric; one stored edge is sufficient;
- `related_concepts`: weak association, targets `SU-*`, symmetric;
- `derived_from`: targets `SU-*`, `EV-*`, `R-*`, `H-*`, `MOD-*`, `D-*`,
  recognized protocols/specifications/checkpoints/tasks/result packages;
- `project_examples`: project objects illustrating/applying a concept;
  targets `EV-*`, `R-*`, `H-*`, `MOD-*`, `D-*` and recognized
  checkpoint/task/specification/result-package IDs.

The epistemic class of a relation target is never strengthened by the edge.
Do not store inverse `generalizes_to` or generic `evidence_for` relations.
No self dependency/specialization, duplicate relation entry, dependency cycle
or specialization cycle is allowed.

## 9. Literature bridge

```yaml
sources:
  background:
    - SRC-000123
  claim_support:
    - EV-SRC000123-004
```

`background` targets canonical `SRC-*`; `claim_support` targets canonical
`EV-SRC*`. Notes do not duplicate DOI, authors, journal metadata, Zotero item
key, BibTeX key, PDF path, evidence category or evidence review state. Those
remain owned by `05_Literature`.

## 10. Convention authority and active binding

`convention_refs` gives authority/provenance, preferably repository-relative
paths. `convention_binding` states which convention is actively assumed:

```yaml
convention_refs:
  - 03_Protocols/SCIENTIFIC_TERMINOLOGY.md

convention_binding:
  status: EXPLICIT
  crystallographic_setting: null
  origin_choice: null
  global_frame: null
  local_frame: null
  site:
    species: null
    wyckoff: null
    site_symmetry: null
```

Status is exactly `EXPLICIT`, `UNRESOLVED` or `NOT_APPLICABLE`.

- `EXPLICIT`: non-empty `convention_refs` and at least one relevant non-null
  active binding field;
- `UNRESOLVED`: convention is relevant but incomplete and
  `transferability.status` must not be `GENERAL`;
- `NOT_APPLICABLE`: binding detail fields are absent or null.

Reviewed claims about `B_l^m`, tensor components, coordinate transforms,
site-specific quantities or crystallographic mapping cannot leave convention
relevance implicit.

## 11. Common confusions and dissertation roles

Local recurring errors are strings:

```yaml
common_confusions:
  - "transition matrix element != static moment"
```

Do not create a second `CONFUSION-*` namespace. Use `contrasts_with` only if
both sides deserve durable SU identities.

`dissertation_roles` is required (an empty list is valid) and contains only:

```text
theoretical_background
literature_review
experimental_methods
analysis_methodology
results_interpretation
defense_preparation
```

It is retrieval metadata only, never final chapter structure or a reason to
duplicate explanations.

## 12. Origin trail and chat promotion

Optional origin trail:

```yaml
origin_trail:
  - source_type: chat
    role: "03 - CEF Modelling & Fit Design"
    date: 2026-09-16
    locator: "bounded conversation/message reference"
  - source_type: archive
    locator: "Archive/legacy/...md#section"
```

Allowed `source_type`: `chat`, `archive`. Origin answers where an idea was
encountered, never what scientifically supports it. It cannot satisfy
literature, evidence or derivation provenance.

Promotion lifecycle:

```text
CHAT_CANDIDATE
  -> DEDUPLICATED_CANDIDATE
  -> SCIENTIFIC_REVIEWED
  -> SOURCED_OR_LINKED
  -> CANONICAL_CONCEPT
```

Terminal alternatives: `MERGED_INTO_EXISTING`, `REJECTED`, `HOLD`. Candidate
and deduplicated states have no SU ID. Before allocation, compare with existing
SU objects, terminology, knowledge rules, protocols, registers, literature
evidence and `PROJECT_STATE`. A chat locator never satisfies scientific
provenance.

## 13. Formula contract

Equations remain portable Markdown/LaTeX in the note body. Explain meaning,
symbols, assumptions, validity domain, convention dependencies and relation
to experiment/project. No equation database is introduced.

For an initial density matrix and final-state projector:

$$
M_{\alpha\beta}^{(i\to f)} = \operatorname{Tr}\left(\rho_i J_\alpha P_f J_\beta\right).
$$

For equal population of $g_i$ initial states:

$$
\rho_i=\frac{P_i}{g_i},\qquad
M_{\alpha\beta}^{(i\to f)}=\frac{1}{g_i}\operatorname{Tr}\left(P_iJ_\alpha P_fJ_\beta\right).
$$

This definition does not require a Kramers doublet. For the Dy3+ ground
doublet specialization:

$$
g_0=2,\qquad \rho_0=\frac{P_0}{2},\qquad
M_{\alpha\beta}^{(0i)}=\frac12\operatorname{Tr}\left(P_0J_\alpha P_iJ_\beta\right).
$$

Reserve isotropic intrinsic strength:

$$
S_{if}=\operatorname{Tr}M^{(i\to f)}=\sum_\alpha M_{\alpha\alpha}^{(i\to f)}.
$$

Use a distinct polarization-contracted quantity:

$$
S^\perp_{if}(\hat{\mathbf Q})=
\sum_{\alpha\beta}\left(\delta_{\alpha\beta}-\hat Q_\alpha\hat Q_\beta\right)
M_{\alpha\beta}^{(i\to f)}.
$$

Preserve the hierarchy:

```text
static moment
!= transition matrix element
!= transition tensor
!= intrinsic S_if
!= polarization-contracted S_if^perp(Qhat)
!= magnetic neutron cross section
!= measured TAS observable
```

The measured TAS observable additionally depends on populations, magnetic
form factor, scan geometry, instrument resolution/acceptance, normalization
and detector/monitor response.

## 14. Validation contract

Validation is structural and semantic-contract validation, not automated
scientific-truth adjudication.

Required structural invariants:

```text
SU_ID_VALID
SU_ID_UNIQUE
SU_ID_IMMUTABLE
SU_ID_NOT_RECYCLED
SUPERSEDED_REQUIRES_TARGET
SUPERSEDED_TARGET_RESOLVES

KNOWLEDGE_KIND_VALID
REVIEW_STATUS_VALID
EPISTEMIC_BASIS_VALID
SCOPE_LEVEL_VALID
TRANSFERABILITY_STATUS_VALID
KRAMERS_FACET_VALID
MAGNETIC_ORDER_FACET_VALID
EXCHANGE_TREATMENT_FACET_VALID
DISSERTATION_ROLE_VALID
CONVENTION_BINDING_STATUS_VALID

RELATION_TARGET_RESOLVES
NO_SELF_DEPENDENCY
NO_SELF_SPECIALIZATION
NO_DEPENDENCY_CYCLE
NO_SPECIALIZATION_CYCLE
NO_DUPLICATE_RELATION_ENTRY
NO_MANUAL_GENERALIZES_TO
RELATION_TARGET_CLASS_VALID

SOURCE_REFERENCE_VALID
SOURCE_REFERENCE_RESOLVES
LITERATURE_REVIEWED_GATE
LITERATURE_CATEGORY_INTEGRITY
GENERAL_TEXTBOOK_SCOPE_GATE
PROJECT_DERIVED_REQUIRES_PROVENANCE
PROJECT_ASSUMPTION_PRESERVED
SCOPE_CONDITIONAL_FIELDS_VALID
RFEO3_FAMILY_REVIEW_GATE
CONVENTION_BINDING_VALID
UNKNOWN_NOT_APPLICABLE_DISTINCT
ORIGIN_TRAIL_NOT_PROVENANCE
```

Identity immutability/non-recycling across history is a governance/history
check. Family generality, body-prose evidence strengthening and whether a
project artifact physically establishes a claim remain scientific-review
checks where structure alone is insufficient.

Canonical validation command:

```text
python scripts/scientific_understanding_validate.py
python scripts/scientific_understanding_validate.py --selftest
```

An absent `06_Scientific_Understanding/` is valid before pilot and reports
zero notes. Once created, every Markdown file in it is canonical SU corpus and
must validate.

## 15. Freeze boundary

This v1.0 materialization allocates no real SU ID, creates no concept corpus,
ingests no chat or literature content, changes no register and configures no
Zotero/BibTeX/graph workflow. A separate Project Control decision is required
for a small reviewed pilot before any broad ingestion or migration.
