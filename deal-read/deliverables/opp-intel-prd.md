# PRD: opp-intel Shared Core

Historical note: this PRD records the migration plan that produced the current shared-core repo. The active command surface is `/pipeline-read`, `/pipeline-forecast`, and `/pipeline-hygiene`; old `/pipeline-triage` references are superseded.

## Summary

Build `opp-intel` as the shared parent system for `deal-read` and `pipeline-read`.

The purpose is to keep two different user experiences while removing duplicated source logic, risk-model logic, deterministic metrics, and validation code.

`deal-read` remains the deepest one-opportunity coaching read. `pipeline-read` remains the breadth-oriented multi-opportunity pipeline read. Both use the same `core/` engine underneath.

Target structure:

```text
opp-intel/
├── core/
│   ├── adapters/
│   ├── config/
│   ├── schemas/
│   ├── scripts/
│   ├── validators/
│   └── tests/
├── deal-read/
└── pipeline-read/
```

## Problem

`deal-read` and `pipeline-read` currently duplicate important pieces of the same system:

- Salesforce field mappings
- Gmail freshness and thread handling
- Zoom call planning and call metrics
- Slack internal evidence rules
- linked Google Drive proposal-doc handling
- risk model config
- deterministic per-deal metrics
- validation rules

This creates real maintenance risk. If Zoom is replaced by Gong, or Salesforce fields change, or Slack/Drive rules change, the change has to be made in two repos. That already created drift: `pipeline-read` had deeper linked-doc handling than `deal-read` until `deal-read` was patched.

The current split is useful at the product layer, but wasteful at the engine layer.

## Goals

1. Single-source the shared opportunity evidence engine.
2. Keep `deal-read` and `pipeline-read` as separate entrypoints.
3. Support different analysis depths without duplicating connector or metric code.
4. Make source swaps, for example Zoom to Gong, a `core/` change.
5. Preserve the current read-only safety model.
6. Preserve deterministic gates: no hand-written date math, freshness math, ranking math, call statistics, or validation.
7. Make migration testable in phases, with no big-bang rewrite.

## Non-Goals

- Do not merge `deal-read` into `pipeline-read`.
- Do not make `pipeline-read` do exhaustive deep reads for every opportunity.
- Do not introduce predictive win/loss weights.
- Do not add a database, scheduler, web app, or background job system.
- Do not change connector write rules. `deal-read` may create a Gmail draft only on explicit confirmation. `pipeline-read` writes nothing.
- Do not retarget Salesforce fields or rewrite the risk model during the core extraction.

## Product Model

`opp-intel` has one shared core and two product surfaces.

### `deal-read`

One opportunity. Maximum depth.

Primary question:

> What is really going on in this opportunity, what is at risk, and what should the rep do next?

It reads:

- Salesforce opportunity, fields, history, tasks, contact roles, prior account opportunities
- Gmail threads, including sent freshness
- call summaries and transcripts from the configured call source
- mapped Slack deal-room messages, pins, bookmarks
- linked Google Drive proposal docs

It produces:

- coaching brief
- confidence rating
- top risks
- account history
- call execution read
- next move
- optional Gmail draft offer and draft creation
- computed-inputs footer

### `pipeline-read`

Many opportunities. Bounded depth.

Primary question:

> Which opportunities need attention across the rep's pipeline, and why?

It reads:

- Salesforce portfolio scope
- enough per-deal Salesforce, Gmail, call, Slack, and Drive evidence to rank and explain risk
- Salesforce-only data in hygiene mode

It produces:

- triage ranking
- forecast view
- hygiene view
- dominant risk per deal
- next move per deal in triage and forecast
- evidence gaps
- computed-inputs footer

## Core Principle

The core owns evidence normalization. The surfaces own orchestration and writing.

Raw source data should never leak directly into the skill output contract. Every source goes through a stable internal bundle shape first.

Example:

```text
Zoom or Gong raw call data
        ↓
core call adapter
        ↓
normalized call_evidence
        ↓
deal-read uses it deeply
pipeline-read uses it shallowly
```

## Architecture

### Directory Shape

```text
opp-intel/
├── AGENTS.md
├── README.md
├── core/
│   ├── adapters/
│   │   ├── salesforce.py
│   │   ├── gmail.py
│   │   ├── calls_zoom.py
│   │   ├── calls_gong.py
│   │   ├── slack.py
│   │   └── drive.py
│   ├── config/
│   │   ├── risk-model.json
│   │   ├── sf-fields.json
│   │   ├── source-contracts.json
│   │   └── depth-profiles.json
│   ├── schemas/
│   │   ├── evidence-bundle.schema.json
│   │   ├── analyzed-deal.schema.json
│   │   └── rollup.schema.json
│   ├── scripts/
│   │   ├── plan.py
│   │   ├── analyze.py
│   │   ├── compute.py
│   │   ├── callstats.py
│   │   └── rollup.py
│   ├── validators/
│   │   ├── validate_deal_brief.py
│   │   └── validate_pipeline_brief.py
│   └── tests/
├── deal-read/
│   ├── AGENTS.md
│   ├── CONTEXT.md
│   ├── README.md
│   ├── SKILL.md
│   └── tests/
└── pipeline-read/
    ├── AGENTS.md
    ├── CONTEXT.md
    ├── README.md
    ├── SKILL.md
    ├── commands/
    │   ├── pipeline-read/
    │   ├── pipeline-forecast/
    │   └── pipeline-hygiene/
    └── tests/
```

### Why `core/` Exists

`core/` owns facts and mechanics that should not vary by surface:

- source plans
- connector contract definitions
- Salesforce field mapping
- risk model
- deterministic metrics
- call statistics
- internal evidence normalization
- validation gates
- bundle schemas

`deal-read/` and `pipeline-read/` own:

- command routing
- depth profile choice
- connector execution loop
- model judgment over qualitative evidence
- final writing
- product-specific output shape

## Depth Profiles

The key design is not "one core means one level of analysis." The core supports named depth profiles.

### Deal Profile

Used by `deal-read`.

```json
{
  "profile": "deal",
  "scope": "one_opportunity",
  "salesforce": "full_opportunity_history",
  "email": {
    "thread_depth": "full_relevant_threads",
    "max_threads": 10,
    "sent_freshness": true
  },
  "calls": {
    "max_calls": 3,
    "detail": "summary_plus_transcript",
    "call_execution": true
  },
  "slack": {
    "mode": "mapped_room_default",
    "max_messages": 80,
    "read_pins_and_bookmarks": true
  },
  "drive": {
    "linked_docs": "read_content",
    "max_docs": 5
  },
  "output": "coaching_brief"
}
```

### Pipeline Profile

Used by `/pipeline-read` and `/pipeline-forecast`.

```json
{
  "profile": "pipeline",
  "scope": "many_opportunities",
  "salesforce": "portfolio_scope_plus_per_deal_core_fields",
  "email": {
    "thread_depth": "bounded_recent_threads",
    "max_threads": 3,
    "sent_freshness": true
  },
  "calls": {
    "max_calls": 1,
    "detail": "summary_first",
    "call_execution": false
  },
  "slack": {
    "mode": "mapped_room_default",
    "max_messages": 40,
    "read_pins_and_bookmarks": true
  },
  "drive": {
    "linked_docs": "coverage_plus_titles",
    "max_docs": 3
  },
  "output": "rollup"
}
```

### Hygiene Profile

Used by `/pipeline-hygiene`.

```json
{
  "profile": "hygiene",
  "scope": "many_opportunities",
  "salesforce": "portfolio_scope_plus_contact_roles",
  "email": "off",
  "calls": "off",
  "slack": "off",
  "drive": "off",
  "output": "crm_data_quality"
}
```

## Core Data Contracts

### Evidence Bundle

Every analyzed opportunity uses the same top-level bundle.

```json
{
  "profile": "deal|pipeline|hygiene",
  "rep": {
    "id": "...",
    "name": "..."
  },
  "opportunity": {
    "id": "...",
    "name": "...",
    "account_id": "...",
    "account_name": "...",
    "stage": "...",
    "amount": 0,
    "close_date": "YYYY-MM-DD",
    "owner_id": "..."
  },
  "salesforce_evidence": {},
  "email_evidence": {},
  "call_evidence": {},
  "internal_evidence": {},
  "source_gaps": []
}
```

### Call Evidence

The call provider can be Zoom, Gong, or another source. The analyzed shape stays stable.

```json
{
  "provider": "zoom|gong",
  "calls": [
    {
      "source_ref": "provider:id",
      "date": "YYYY-MM-DD",
      "title": "...",
      "summary": "...",
      "participants": [],
      "transcript_ref": "...",
      "signals": [],
      "stats_available": true
    }
  ],
  "latest_call_date": "YYYY-MM-DD",
  "source_gaps": []
}
```

### Internal Evidence

Slack and Drive stay soft against Salesforce-owned truth, but they are still real evidence.

```json
{
  "mode": "auto|force|off",
  "deal_room": {
    "source": "slack",
    "coverage": "mapped|deal_room_missing|checked_no_match|unavailable",
    "source_ref": "..."
  },
  "linked_docs": [
    {
      "source": "google_drive",
      "title": "...",
      "coverage": "read|metadata_only|unavailable|skipped",
      "source_ref": "..."
    }
  ],
  "signals": [
    {
      "type": "...",
      "summary": "...",
      "source_ref": "...",
      "confidence": "high|medium|low"
    }
  ],
  "source_gaps": []
}
```

## Source Adapter Requirements

Adapters do not call MCP tools directly. They emit plans and normalize connector results. The model or harness still executes connector calls.

Each adapter must provide:

1. A plan function.
2. A normalize function.
3. Source-gap semantics.
4. Tests against sample raw connector output.

### Call Adapter

The call adapter is the first priority because it is the clearest future swap.

Required behavior:

- `calls_zoom.py` and `calls_gong.py` both output `call_evidence`.
- `callstats.py` consumes normalized transcript turns, not Zoom-specific transcript shape.
- If a provider lacks transcript data, call execution metrics return null and source gaps explain why.
- `deal-read` can request transcript-level detail.
- `pipeline-read` can request summary-first detail.

## Functional Requirements

### FR1: Shared Per-Deal Analysis

`core/scripts/analyze.py` must accept one evidence bundle and return one analyzed deal.

Required output:

- `deal_metrics`
- `call_execution`
- `account_history`
- `internal_evidence`
- `source_gaps`

### FR2: Shared Planning

`core/scripts/plan.py` must emit source plans based on profile.

Required profiles:

- `deal`
- `pipeline`
- `hygiene`

### FR3: Shared Pipeline Rollup

`core/scripts/rollup.py` must aggregate analyzed deals for pipeline modes.

Required modes:

- `triage`
- `forecast`
- `hygiene`

### FR4: Surface-Specific Validation

Core owns validators, but each surface has its own output contract.

Required validators:

- `validate_deal_brief.py`
- `validate_pipeline_brief.py`

### FR5: Surface Routing

`deal-read/SKILL.md` and `pipeline-read/SKILL.md` must be thin orchestration layers.

They must not duplicate:

- risk dimension definitions
- Salesforce field lists
- source adapter rules
- freshness math
- callstats math
- internal evidence normalization
- rollup ranking logic

## Safety Requirements

1. All source reads are read-only.
2. `pipeline-read` makes no writes.
3. `deal-read` may create a Gmail draft only after explicit user confirmation.
4. No email is sent.
5. No Salesforce record is edited.
6. No Slack message is posted.
7. No Drive doc is edited.
8. Confidence must be reduced when source data is stale, missing, or partial.

## Execution Model

Use sequential work first, then wave orchestration.

Phases 0-2 must be single-threaded. One agent owns the baseline, repo shape, shared config, depth profiles, schemas, and parity fixtures. This prevents workers from inventing incompatible definitions of the evidence bundle, source contracts, or profile boundaries.

Do not use wave orchestration until the contracts and fixtures are committed.

Phases 3-6 may use wave orchestration because the work can split cleanly against frozen contracts:

- per-deal core extraction
- source planning and adapter extraction
- pipeline rollup extraction
- validator extraction
- `deal-read` surface thinning
- `pipeline-read` surface thinning
- reviewer pass against parity fixtures

The supervisor must treat the committed schemas, depth profiles, and parity fixtures as the source of truth. Workers may not change those contracts unless the supervisor explicitly pauses the wave, updates the contract centrally, and reruns the affected parity tests.

## Migration Plan

### Phase 0: Freeze Current Behavior

Purpose: prevent regressions before moving files.

Actions:

- Run all tests in `deal-read`.
- Run all tests in `pipeline-read`.
- Save current generated plan outputs for representative deal and pipeline fixtures.
- Save current analyze outputs for representative bundles.

Exit criteria:

- Both repos pass their test suites.
- Baseline fixtures exist.
- No behavior changes yet.

### Phase 1: Create `opp-intel` Skeleton

Purpose: create the repo shape without moving behavior.

Actions:

- Create `opp-intel/`.
- Add `core/`, `deal-read/`, and `pipeline-read/`.
- Copy current `deal-read` and `pipeline-read` surfaces into their folders.
- Add top-level `AGENTS.md` explaining the shared-core boundary.

Exit criteria:

- Repo structure exists.
- Skill surfaces still read clearly.
- No duplicated logic has been edited yet.

### Phase 2: Extract Shared Config

Purpose: single-source stable facts first.

Actions:

- Move common risk-model fields into `core/config/risk-model.json`.
- Move common Salesforce fields into `core/config/sf-fields.json`.
- Add `core/config/depth-profiles.json`.
- Add tests proving both surfaces resolve config from `core/config`.

Exit criteria:

- Changing a shared threshold changes both surfaces.
- No copied Salesforce field mapping remains in surface folders.

### Phase 3: Extract Per-Deal Core Scripts

Purpose: single-source deterministic per-deal analysis.

Actions:

- Move `compute.py`, `callstats.py`, and shared portions of `analyze.py` into `core/scripts/`.
- Keep surface wrappers only if needed for command compatibility.
- Add tests for `deal` and `pipeline` profile inputs.

Exit criteria:

- `deal-read` and `pipeline-read` call the same `core/scripts/analyze.py`.
- Per-deal fixture output matches baseline, except for intentional path changes.

### Phase 4: Extract Source Planning and Adapters

Purpose: make source swaps a core change.

Actions:

- Refactor `plan.py` into core profile-aware planning.
- Add adapter modules for Salesforce, Gmail, calls, Slack, and Drive.
- Add `calls_zoom.py` as the current call provider.
- Define `calls_gong.py` as the future provider interface, even if not fully implemented.

Exit criteria:

- `deal` profile emits deep plans.
- `pipeline` profile emits bounded plans.
- `hygiene` profile emits Salesforce-only plans.
- Swapping call provider changes call planning in one place.

### Phase 5: Extract Rollup and Validators

Purpose: keep output gates single-sourced.

Actions:

- Move `rollup.py` into `core/scripts/`.
- Move validation logic into `core/validators/`.
- Keep separate deal and pipeline validators.

Exit criteria:

- Pipeline rollup tests pass from `core`.
- Deal brief validation passes from `core`.
- Pipeline brief validation passes from `core`.

### Phase 6: Thin the Skill Surfaces

Purpose: make the final architecture obvious.

Actions:

- Rewrite `deal-read/SKILL.md` to reference `core/` for all shared mechanics.
- Rewrite `pipeline-read/SKILL.md` to reference `core/` for all shared mechanics.
- Keep only orchestration, mode routing, output shape, and write policy in surface files.

Exit criteria:

- No surface file contains copied risk-model definitions.
- No surface file contains copied source adapter rules.
- The depth difference is explicit and profile-based.

## Acceptance Criteria

### Architecture Acceptance

- `opp-intel/core/` contains shared config, schemas, scripts, validators, and adapter contracts.
- `deal-read/` contains only the one-opportunity skill surface and tests specific to that surface.
- `pipeline-read/` contains only the multi-opportunity skill surface, commands, and tests specific to that surface.

### Behavior Acceptance

- `deal-read` still performs the deepest one-opportunity read.
- `pipeline-read` still performs bounded multi-opportunity triage, forecast, and hygiene.
- Hygiene remains Salesforce-only.
- Slack and Drive evidence can affect confidence, gaps, risk notes, and next-move wording, but not Salesforce-owned fields.
- No predictive weights are introduced.

### Swap Acceptance

Given the call provider changes from Zoom to Gong:

- only `core/adapters/calls_*`, `core/config/source-contracts.json`, and provider-specific tests need changes;
- `deal-read/SKILL.md` does not need call-source rewrites;
- `pipeline-read/SKILL.md` does not need call-source rewrites;
- both surfaces still consume `call_evidence`.

### Test Acceptance

Required tests:

- `core/tests/test_plan_profiles.py`
- `core/tests/test_analyze_deal.py`
- `core/tests/test_internal_evidence.py`
- `core/tests/test_call_adapter_zoom.py`
- `core/tests/test_call_adapter_contract.py`
- `core/tests/test_rollup_triage.py`
- `core/tests/test_rollup_forecast.py`
- `core/tests/test_rollup_hygiene.py`
- `core/tests/test_validate_deal_brief.py`
- `core/tests/test_validate_pipeline_brief.py`
- `deal-read/tests/test_skill_contract.py`
- `pipeline-read/tests/test_command_contracts.py`

All tests must run with plain Python, no pytest required, unless the repo explicitly changes its test runner.

## Key Tradeoffs

### Monorepo vs Shared Package

Recommendation: monorepo.

Reason: these are local skills with shared scripts, not a published library. A monorepo keeps source, skills, tests, and docs in one place and avoids package install friction.

### Adapter Abstraction vs Direct Script Calls

Recommendation: small adapter contracts, not a heavy framework.

Reason: the actual need is source normalization, not a general connector platform.

### Depth Profiles vs Separate Scripts

Recommendation: depth profiles.

Reason: `deal-read` and `pipeline-read` need different levels of analysis, but the difference should be explicit config passed into shared code, not duplicated code.

## Open Questions

1. Should the first `opp-intel` repo be created from `deal-read`, from `pipeline-read`, or from a fresh folder?
2. Should the old repos become archived, symlinked wrappers, or remain active until migration is complete?
3. Should `pipeline-read` commands remain under `pipeline-read/commands/`, or be registered from top-level repo metadata?
4. Should `source-contracts.json` name MCP tools directly, or describe source capabilities independent of the MCP implementation?
5. Should `Gong` be stubbed in Phase 4, or left as an explicit future adapter after Zoom is fully extracted?

## Recommended First Build Slice

Do not start by moving everything.

Start with this narrow slice:

1. Create `opp-intel/core/config/`.
2. Move shared `risk-model.json` and `sf-fields.json`.
3. Add `depth-profiles.json`.
4. Add a core `plan.py` that can emit the same plans currently emitted by both repos.
5. Prove parity with fixtures from current `deal-read` and `pipeline-read`.

This gives immediate maintenance leverage without risking the entire workflow.

## Done Definition

The migration is done when:

- `deal-read` and `pipeline-read` live under `opp-intel`.
- both surfaces use `core/` for shared source plans, metrics, config, evidence schemas, and validators.
- both surfaces pass their old behavior tests.
- core tests prove profile differences are intentional.
- changing the call provider contract can be tested in core without editing both skill surfaces.
- docs clearly state: `deal-read` is depth, `pipeline-read` is breadth, `core` is the shared evidence engine.
