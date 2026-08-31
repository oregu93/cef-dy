---
title: "Project State v1.x -> Knowledge Base v2 migration"
type: migration_note
status: active
updated: 2026-08-27
---

# Project State v1.x → Knowledge Base v2

## Source hierarchy used

Authoritative migration basis: `01-DyFeO3_PROJECT_STATE.md`, version **1.2**, updated 2026-08-27, available in the CEF Dy project. Earlier `DyFeO3_PROJECT_STATE.md`, version **1.1**, updated 2026-08-21, is retained as an exact local legacy snapshot in `Archive/legacy/`.

> [!important]
> Version 1.2 contains the Stage 03C intensity audit and explicit Stage 03D M0/M1 specification that are absent from v1.1. Therefore v2 current state follows v1.2 wherever the two differ.

## Migration principles

The old monolithic file mixed four different knowledge roles. Migration separates them:

| v1.x content | v2 destination |
|---|---|
| Current physical facts, conventions, current numeric baselines | `PROJECT_STATE.md` |
| Current next stage, decisions, risks, task queue | `PROJECT_CONTROL.md` |
| Chronology / strategic changes | `RESEARCH_LOGBOOK.md` + entries |
| Run-specific execution details | future `WORK_CHECKPOINTS/` |
| Historical detail not required for current re-entry | `Archive/legacy/` |

## Content retained in PROJECT_STATE v2

- Dy$^{3+}$ physical basis and project objective.
- Canonical $C_s$ 15-parameter convention.
- Legacy direct PCF/CFE vs canonical distinction.
- Audited direct/canonical frames.
- PCF↔CFE benchmark status.
- Structural/PCM baseline.
- TAIPAN dataset summary and empirical resolution.
- Status of 18.247 meV CEF candidate, 6.45/27.90 hypotheses, and 44.4 meV unassigned structure.
- Energy-only non-identifiability conclusion.
- Stage 03C intensity audit.
- Stage 03D M0/M1 boundary, detected/censored F002 requirement and shared nuisance normalization.
- Exchange caveat and later model hierarchy.
- Current hypotheses/open questions.

## Content moved primarily to PROJECT_CONTROL

- What should be done next.
- Stage 03D job decomposition.
- Decisions such as no mandatory F004 and no exchange in Stage 03D.
- Work/Codex usage discipline.
- Risks and blocked/deferred tasks.
- Definition of Done.

## Content moved to RESEARCH_LOGBOOK

Historical narrative including:

- 2026-08-13 TAIPAN inventory and preliminary INS analysis;
- structure/PCM and effective-charge exploration;
- broad CFE search and B2 manifold development;
- 2026-08-21 convention/exchange/intensity-identifiability review;
- Stage 03C symmetry-corrected PCM and intensity audit;
- 2026-08-27 project knowledge-system refactor.

## Content intentionally not duplicated into concise v2 state

Large coefficient tables, detailed per-restart optimizer tables, full neighbor-coordinate tables, legacy code snippets, and historical intermediate numerical outputs remain available in legacy/project-source files. They should be promoted into dedicated current reference files only when required for active work.

## Legacy archive note

`Archive/legacy/DyFeO3_PROJECT_STATE_v1.1.md` is a byte-preserving copy of the local v1.1 source available in this session.

The exact v1.2 file was available as a project/File Library source rather than as a local mounted file in this execution environment; therefore this generated bundle does not claim to contain a byte-identical archived v1.2 copy. When initializing the local Git repository, copy the original `01-DyFeO3_PROJECT_STATE.md` v1.2 into `Archive/legacy/` as well.
