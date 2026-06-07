# Pipeline Mode and Forecast Ledger PRD

Date: 2026-06-06
Repo: `/Users/matthewweigand/Code/opp-intel`
Status: Planning spec

## Summary

`pipeline-read` is doing too much work for the wrong job.

The repo needs three explicit pipeline modes:

- `pipeline-hygiene`: Salesforce-only CRM record quality.
- `pipeline-read`: fast work-the-week triage.
- `pipeline-forecast`: weekly forecast accuracy, built on a saved evidence ledger so it only re-reads what changed after the first baseline.

The goal is not to make the forecast shallow. The goal is to stop re-deriving the full account review every week when most sources have not changed.

## Problem

The current pipeline workflow pushes the same general gather shape across read and forecast. That creates three problems:

1. `pipeline-read` is slow because it behaves like a forecast-read.
2. `pipeline-forecast` is expensive because it repeats baseline account discovery every weekly run.
3. The output language can blur triage confidence and forecast confidence.

That confusion creates inaccurate reads. A fast risk triage should not imply full forecast certainty. A weekly forecast should not skip full-picture evidence, but it should use durable source cursors and prior normalized facts instead of rereading unchanged raw payloads.

## Goals

- Make `pipeline-hygiene`, `pipeline-read`, and `pipeline-forecast` separate jobs with separate source budgets.
- Keep source ownership strict:
  - Salesforce is Salesforce.
  - Gmail is Gmail.
  - Slack is Slack MCP only.
  - Google Calendar is Google Calendar.
  - Zoom is Zoom.
  - Google Drive is Google Drive.
- Make `/pipeline-read` fast enough to run often.
- Make `/pipeline-forecast` accurate enough for weekly forecast calls.
- Add a local forecast ledger so weekly forecast runs use deltas after a baseline.
- Keep all source access read-only.
- Keep source gaps explicit. Missing data is not a negative account claim.
- Keep deterministic scoring. Do not add predictive weights or win-probability scoring.

## Non-Goals

- Do not fold `deal-read` into `pipeline-read`.
- Do not move runtime ledger data into `core`.
- Do not write to Salesforce, Gmail, Slack, Calendar, Zoom, or Drive.
- Do not store raw email bodies, Slack messages, transcripts, or full document text in the repo.
- Do not replace `/deal-read` as the deepest one-deal tool.
- Do not make `pipeline-hygiene` inspect live communication evidence.

## User-Facing Modes

### `pipeline-hygiene`

Question: Is the Salesforce record usable?

This is a CRM data-quality scan. It is not a deal-risk read and not a forecast read.

Default sources:

- Salesforce only.

Reads:

- Opportunity fields.
- Account fields needed for the record.
- Contact roles.
- MEDDPICC fields.
- Notes or next-step fields available in Salesforce.
- Added ARR.
- Forecast category.
- CPQ/legal fields available in Salesforce.
- Close date, stage, owner, activity date.

Does not read:

- Gmail.
- Slack.
- Google Calendar.
- Zoom.
- Google Drive.

Output:

- Dominant CRM gap per opportunity.
- Ordered hygiene list.
- No next-move coaching.
- No forecast confidence.
- No risk claims based on missing non-Salesforce evidence.

### `pipeline-read`

Question: What should I work on this week?

This is fast triage. It ranks risk and gives the next move. It does not claim full forecast certainty.

Default sources:

- Salesforce.
- Gmail.
- Slack MCP.
- Zoom.

Required reads:

- Salesforce opportunity/account/contact truth.
- Gmail company-domain search.
- Gmail full newest matching company-domain thread.
- Slack MCP channel existence and room lookup only.
- Most recent Zoom summary plus metadata.

Default non-reads:

- Google Calendar.
- Google Drive.
- Full Slack message history.
- Zoom transcripts.
- Multiple Gmail threads beyond the newest matching company-domain thread.

Output:

- Triage confidence.
- Ranked deals.
- Dominant risk.
- Next move.
- Blind spots.
- Optional handoff to `pipeline-forecast` or `deal-read`.

Language rules:

- Say `triage confidence`, not `forecast confidence`.
- Do not say the forecast is clean or defensible.
- Do not make Calendar or Drive claims unless those sources were actually read.
- Do not infer Slack from Salesforce.
- If Zoom is missing, name it as a triage coverage gap.

### `pipeline-forecast`

Question: What changed, and is the forecast real?

This is the weekly forecast workflow. It must gather full-picture evidence, but after a baseline it should read deltas, not re-run the full account review every time.

Default sources:

- Salesforce.
- Gmail.
- Slack MCP.
- Google Calendar.
- Zoom.
- Google Drive.

Required baseline reads:

- Salesforce full opportunity row.
- Salesforce history.
- Salesforce account/contact context.
- Gmail company-domain search.
- Gmail newest matching company-domain thread.
- Bounded relevant Gmail thread coverage.
- Slack MCP deal-room read.
- Google Calendar historical and upcoming meeting evidence.
- Zoom summaries and metadata.
- Linked Google Drive, CPQ, legal, and proposal docs when linked.

Weekly delta reads:

- Salesforce current row every run.
- Salesforce history rows since prior cursor.
- Gmail newest company-domain thread every run, full thread only when changed.
- Slack room messages since prior Slack timestamp.
- Calendar new or changed events since prior cursor, plus upcoming meeting window.
- Zoom summaries and metadata since prior latest meeting date.
- Drive docs only when linked doc modified time changed.

Output:

- Forecast confidence.
- Category rollup.
- Recommendation labels.
- Changed evidence since last run.
- Coverage gaps.
- Deals that need full refresh.
- Deals that need `deal-read`.

## Source Budgets

| Mode | Salesforce | Gmail | Slack MCP | Zoom | Calendar | Drive |
|---|---|---|---|---|---|---|
| `pipeline-hygiene` | Full hygiene fields | Off | Off | Off | Off | Off |
| `pipeline-read` | Opportunity/account/contact | Newest domain thread, full body | Channel lookup only | Most recent summary and metadata | Off | Off |
| `pipeline-forecast` baseline | Full | Newest plus bounded relevant threads | Deal-room read | Summaries and metadata | Historical plus upcoming | Linked docs |
| `pipeline-forecast` delta | Current row plus changes | Changed newest thread and new messages | New messages since cursor | New meetings since cursor | New/changed events plus upcoming | Changed linked docs |

## Forecast Ledger

The forecast ledger is a local, gitignored runtime store. It holds compact source cursors and normalized evidence facts. It does not hold raw source payloads.

### Location

Runtime ledger data:

```text
pipeline-read/state/forecast-ledger/
  README.md
  .gitignore
  deals/
    <opp_id>.json
  accounts/
    <account_id>.json
  runs/
    <run_id>.json
```

Checked into git:

- `pipeline-read/state/forecast-ledger/README.md`
- `pipeline-read/state/forecast-ledger/.gitignore`
- Ledger schemas.
- Ledger scripts.
- Ledger tests.

Ignored:

- `pipeline-read/state/forecast-ledger/deals/*.json`
- `pipeline-read/state/forecast-ledger/accounts/*.json`
- `pipeline-read/state/forecast-ledger/runs/*.json`

### Why It Lives Under `pipeline-read`

`core` owns shared mechanics. `pipeline-read` owns portfolio runtime state.

The ledger is not a shared source contract. It is a pipeline forecast cache and audit trail. It should not live in `core`, and it should not be used by `deal-read` unless a future explicit handoff is designed.

### Core Ledger Schema

Add:

```text
core/schemas/forecast-ledger.schema.json
core/schemas/forecast-delta-plan.schema.json
core/schemas/forecast-run.schema.json
```

Deal ledger shape:

```json
{
  "schema_version": "forecast-ledger.v1",
  "opp_id": "006...",
  "account_id": "001...",
  "account_name": "NW1",
  "opportunity_name": "NW1 - FA + GPX",
  "last_full_refresh_at": "2026-06-06T20:00:00Z",
  "last_forecast_run_at": "2026-06-13T20:00:00Z",
  "source_cursors": {
    "salesforce": {
      "last_history_created_at": "2026-06-06T18:00:00Z",
      "opportunity_fingerprint": "sha256:...",
      "contact_roles_fingerprint": "sha256:..."
    },
    "gmail": {
      "searched_domains": ["nw1.com"],
      "newest_thread_id": "thread-123",
      "newest_message_date": "2026-06-12T15:30:00Z",
      "thread_fingerprint": "sha256:..."
    },
    "slack": {
      "channel_id": "C123",
      "channel_name": "nw1",
      "latest_message_ts": "1780000000.000000",
      "room_fingerprint": "sha256:..."
    },
    "google_calendar": {
      "latest_event_updated_at": "2026-06-10T14:00:00Z",
      "upcoming_window_end": "2026-07-31"
    },
    "zoom": {
      "latest_meeting_id": "987",
      "latest_meeting_date": "2026-06-05T16:00:00Z"
    },
    "google_drive": {
      "linked_doc_ids": ["doc-1"],
      "latest_modified_time": "2026-06-08T12:00:00Z",
      "docs_fingerprint": "sha256:..."
    }
  },
  "normalized_facts": {
    "stage": "Validate",
    "close_date": "2026-06-30",
    "added_arr": 129250,
    "forecast_category": "Commit",
    "latest_next_step": "Vanda to send compliance RFP",
    "latest_customer_email_date": "2026-06-12",
    "latest_rep_email_date": "2026-06-11",
    "latest_zoom_summary_date": "2026-06-05",
    "known_blockers": ["compliance_rfp_pending"],
    "open_coverage_gaps": []
  },
  "coverage": {
    "salesforce": "ok",
    "gmail": "ok",
    "slack": "ok",
    "google_calendar": "ok",
    "zoom": "ok",
    "google_drive": "ok"
  }
}
```

Run ledger shape:

```json
{
  "schema_version": "forecast-run.v1",
  "run_id": "2026-06-13-weekly",
  "run_at": "2026-06-13T20:00:00Z",
  "mode": "forecast",
  "window": "current_quarter",
  "owner_id": "005...",
  "deals": [
    {
      "opp_id": "006...",
      "strategy": "delta",
      "full_refresh_reason": null,
      "changed_sources": ["gmail", "salesforce"],
      "coverage_gaps": []
    }
  ]
}
```

## Config Additions

### `core/config/mode-contracts.json`

Purpose: one durable contract for what each mode is allowed to read and claim.

```json
{
  "pipeline_hygiene": {
    "question": "is the CRM record usable",
    "confidence_label": "hygiene_confidence",
    "expected_sources": ["salesforce"],
    "disallowed_sources": ["gmail", "slack", "google_calendar", "zoom", "google_drive"]
  },
  "pipeline_read": {
    "question": "what should I work this week",
    "confidence_label": "triage_confidence",
    "expected_sources": ["salesforce", "gmail", "slack", "zoom"],
    "limits": {
      "gmail_threads": 1,
      "gmail_thread_read": "full_newest_company_domain_thread",
      "slack": "channel_lookup_only",
      "zoom": "most_recent_summary_metadata",
      "calendar": "off",
      "drive": "off"
    }
  },
  "pipeline_forecast": {
    "question": "what changed and is the forecast real",
    "confidence_label": "forecast_confidence",
    "expected_sources": ["salesforce", "gmail", "slack", "google_calendar", "zoom", "google_drive"],
    "strategy": "baseline_then_delta"
  }
}
```

### `core/config/forecast-ledger-policy.json`

Purpose: deterministic full-refresh and delta rules.

```json
{
  "schema_version": "forecast-ledger-policy.v1",
  "full_refresh_days": 30,
  "force_full_refresh_when": [
    "missing_ledger",
    "schema_version_changed",
    "source_cursor_invalid",
    "prior_connector_degraded",
    "account_domain_changed",
    "owner_or_account_changed",
    "user_requested_full_refresh"
  ],
  "delta_sources": {
    "salesforce": "current_row_plus_history_since_cursor",
    "gmail": "newest_domain_thread_plus_messages_since_cursor",
    "slack": "channel_lookup_plus_messages_since_latest_ts",
    "google_calendar": "changed_events_plus_upcoming_window",
    "zoom": "summaries_since_latest_meeting_date",
    "google_drive": "linked_docs_modified_since_cursor"
  }
}
```

## Script Additions

### `core/scripts/forecast_ledger.py`

Responsibilities:

- Load deal ledger.
- Validate ledger schema.
- Decide `full_refresh` vs `delta`.
- Merge source deltas into normalized facts.
- Write updated deal/account/run ledger files.
- Refuse to write raw payload fields.

CLI:

```text
python3 core/scripts/forecast_ledger.py decide < input.json
python3 core/scripts/forecast_ledger.py merge < input.json
```

### `core/scripts/forecast_delta.py`

Responsibilities:

- Convert current scope plus prior ledger into source-specific delta plans.
- Emit source cursors and required proofs.
- Emit full-refresh reasons.

Output:

```json
{
  "opp_id": "006...",
  "strategy": "delta",
  "expected_sources": ["salesforce", "gmail", "slack", "google_calendar", "zoom", "google_drive"],
  "source_queries": {
    "salesforce": {"type": "current_row_plus_history_since_cursor"},
    "gmail": {"type": "newest_domain_thread_plus_messages_since_cursor"},
    "slack": {"type": "messages_since_ts"},
    "google_calendar": {"type": "changed_events_plus_upcoming"},
    "zoom": {"type": "summaries_since_date"},
    "google_drive": {"type": "linked_docs_modified_since_cursor"}
  },
  "full_refresh_reason": null
}
```

## Existing Script Changes

### `core/scripts/plan.py`

Add mode-specific planning:

- Hygiene emits Salesforce-only plan.
- Read emits fast triage plan.
- Forecast emits baseline or delta plan.

Inputs:

```json
{
  "mode": "pipeline",
  "view": "read|forecast|hygiene",
  "today": "2026-06-06",
  "owner_id": "005...",
  "force_full_refresh": false,
  "ledger_root": "pipeline-read/state/forecast-ledger"
}
```

For `view=read`, emit:

```json
{
  "view": "read",
  "confidence_label": "triage_confidence",
  "coverage_manifest": {
    "expected_sources": ["salesforce", "gmail", "slack", "zoom"]
  },
  "limits": {
    "gmail_threads": 1,
    "gmail_read": "full_newest_company_domain_thread",
    "slack_messages": 0,
    "zoom_summaries": 1,
    "calendar": false,
    "drive": false
  }
}
```

For `view=forecast`, emit:

```json
{
  "view": "forecast",
  "confidence_label": "forecast_confidence",
  "run_strategy": "baseline|delta",
  "coverage_manifest": {
    "expected_sources": ["salesforce", "gmail", "slack", "google_calendar", "zoom", "google_drive"]
  },
  "ledger": {
    "root": "pipeline-read/state/forecast-ledger",
    "deal_path": "deals/006....json",
    "full_refresh_reason": null
  }
}
```

### `core/scripts/analyze.py`

Add support for:

- `mode_contract`.
- `confidence_label`.
- Ledger-derived normalized facts.
- Source deltas.

Do not let ledger facts override fresh source reads. Fresh reads win, then ledger facts fill unchanged context.

### `core/scripts/rollup.py`

Add mode-aware confidence labels:

- `hygiene_confidence`.
- `triage_confidence`.
- `forecast_confidence`.

Add forecast delta section:

```json
{
  "forecast_delta": {
    "baseline_deals": 1,
    "delta_deals": 6,
    "full_refresh_deals": 1,
    "changed_sources": {
      "salesforce": 3,
      "gmail": 2,
      "slack": 1
    }
  }
}
```

## Validator Changes

### Pipeline brief validator

Rules:

- `pipeline-read` must use `triage confidence`.
- `pipeline-read` must not use `forecast confidence`.
- `pipeline-read` must not claim Calendar or Drive evidence unless those sources are in `source_reads`.
- `pipeline-read` must prove:
  - Gmail company-domain search.
  - Full newest matching company-domain thread read.
  - Slack MCP channel lookup.
  - Most recent Zoom summary or explicit Zoom coverage gap.
- `pipeline-forecast` must use `forecast confidence`.
- `pipeline-forecast` cannot exceed computed `confidence.max_label`.
- `pipeline-forecast` must include changed evidence since prior run when `run_strategy=delta`.
- `pipeline-forecast` must include full-refresh reasons when any deal used full refresh.

### Deal brief validator

No planned behavior change for this PRD. Keep `deal-read` as the deep one-deal surface.

## Data Retention Rules

Allowed in ledger:

- Source refs.
- Timestamps.
- IDs.
- Hashes/fingerprints.
- Compact normalized facts.
- Coverage status.
- Confidence inputs.
- Short summaries already produced by source systems, such as Zoom summaries.

Not allowed in ledger:

- Raw Gmail thread bodies.
- Raw Slack messages.
- Raw Zoom transcripts.
- Full Google Drive document text.
- Unbounded task/event/message payloads.

If a normalized fact needs evidence, store the source ref and short fact, not the full payload.

## Weekly Forecast Flow

1. Resolve scope from Salesforce.
2. Load deal ledger for each opportunity.
3. Decide full refresh vs delta.
4. Emit per-deal source plans.
5. Gather connector data.
6. Normalize source deltas.
7. Merge with prior ledger facts.
8. Run deterministic analysis.
9. Roll up forecast.
10. Validate output.
11. Write updated ledger.
12. Save run ledger.

## Full Refresh Rules

Full refresh is required when:

- No prior ledger exists.
- Ledger schema version changed.
- Source cursor is missing or invalid.
- Prior connector coverage was degraded.
- Salesforce account domain changed.
- Opportunity account or owner changed.
- User requested full refresh.
- The last full refresh is older than `full_refresh_days`.

Full refresh may be recommended when:

- Forecast category changed into or out of Commit.
- Close date moved by more than configured threshold.
- Added ARR changed materially.
- A new legal/CPQ blocker appears.
- Slack channel mapping changed.

## Delta Merge Rules

Fresh source data wins.

Order:

1. Fresh connector read.
2. Current run normalized delta.
3. Prior ledger normalized fact.
4. Coverage gap.

If a source is degraded in the current run:

- Do not erase prior normalized facts.
- Mark current source as degraded.
- Lower confidence ceiling.
- Do not make new absence claims from that source.

## Repo Structure

Target structure:

```text
opp-intel/
  core/
    config/
      mode-contracts.json
      forecast-ledger-policy.json
      source-contracts.json
      confidence-policy.json
      risk-model.json
      sf-fields.json

    schemas/
      evidence-bundle.schema.json
      analyzed-deal.schema.json
      rollup.schema.json
      forecast-ledger.schema.json
      forecast-delta-plan.schema.json
      forecast-run.schema.json

    scripts/
      plan.py
      analyze.py
      compute.py
      rollup.py
      coverage_manifest.py
      confidence.py
      forecast_ledger.py
      forecast_delta.py

    tests/
      test_mode_contracts.py
      test_forecast_ledger.py
      test_forecast_delta_plan.py
      test_pipeline_read_contract.py
      test_pipeline_forecast_delta_flow.py

  pipeline-read/
    commands/
      pipeline-read/SKILL.md
      pipeline-forecast/SKILL.md
      pipeline-hygiene/SKILL.md

    state/
      forecast-ledger/
        README.md
        .gitignore
        deals/
        accounts/
        runs/

    scripts/
      plan.py
      analyze.py
      rollup.py

    tests/
      test_plan.py
      test_rollup_forecast.py
      test_validate_forecast_brief.py
      test_forecast_ledger_flow.py
```

## Implementation Phases

### Phase 1: Contract Freeze

Add:

- `core/config/mode-contracts.json`
- `core/config/forecast-ledger-policy.json`
- Contract tests.

No behavior change yet.

Acceptance:

- Tests prove each mode has the correct expected sources.
- Tests prove `pipeline-read` uses `triage_confidence`.
- Tests prove `pipeline-forecast` uses `forecast_confidence`.

### Phase 2: Ledger Schema and State Folder

Add:

- Ledger schemas.
- `pipeline-read/state/forecast-ledger/README.md`
- `pipeline-read/state/forecast-ledger/.gitignore`
- Ledger fixture examples under tests only.

Acceptance:

- Runtime ledger JSON files are ignored.
- Schema validates deal, account, and run ledger fixtures.
- Raw payload fields are rejected.

### Phase 3: Ledger Mechanics

Add:

- `core/scripts/forecast_ledger.py`
- Unit tests for load, decide, merge, and write.

Acceptance:

- Missing ledger returns `full_refresh`.
- Fresh valid ledger returns `delta`.
- Degraded prior source returns `full_refresh`.
- Merge preserves prior facts when current source is degraded.

### Phase 4: Delta Planner

Add:

- `core/scripts/forecast_delta.py`
- Plan integration for `view=forecast`.

Acceptance:

- Forecast with no ledger emits baseline plan.
- Forecast with ledger emits delta plan.
- Delta plan includes per-source cursors.
- Slack plan remains Slack MCP only.

### Phase 5: Fast `pipeline-read`

Update `plan.py` and command docs:

- `pipeline-read` expected sources become Salesforce, Gmail, Slack, Zoom.
- Gmail reads full newest company-domain thread.
- Slack checks channel existence through Slack MCP.
- Zoom reads most recent summary and metadata.
- Calendar and Drive are off by default.

Acceptance:

- Planner emits no Calendar or Drive for `pipeline-read`.
- Validator rejects `forecast confidence` in `pipeline-read`.
- Validator rejects Calendar/Drive claims without source proof.

### Phase 6: Weekly `pipeline-forecast`

Update forecast command:

- Uses ledger decide step.
- Runs baseline or delta per deal.
- Updates deal and run ledger after validation.

Acceptance:

- First run creates ledger.
- Second run with no source changes uses deltas and reuses normalized facts.
- Changed Gmail thread triggers Gmail re-read.
- Changed Slack timestamp triggers Slack delta read.
- Changed Drive modified time triggers linked doc re-read.

### Phase 7: Docs and Migration

Update:

- `README.md`
- `AGENTS.md`
- `SETUP.md`
- `pipeline-read/SKILL.md`
- `pipeline-read/commands/pipeline-read/SKILL.md`
- `pipeline-read/commands/pipeline-forecast/SKILL.md`
- `pipeline-read/commands/pipeline-hygiene/SKILL.md`

Acceptance:

- Docs explain the three jobs plainly.
- Docs explain ledger location and gitignore policy.
- Docs state that `pipeline-forecast` is weekly delta-based after baseline.

## Test Plan

Run:

```text
scripts/test.sh
git diff --check
```

Focused tests:

- `python3 core/tests/test_mode_contracts.py`
- `python3 core/tests/test_forecast_ledger.py`
- `python3 core/tests/test_forecast_delta_plan.py`
- `python3 pipeline-read/tests/test_plan.py`
- `python3 pipeline-read/tests/test_validate_forecast_brief.py`
- `python3 pipeline-read/tests/test_forecast_ledger_flow.py`

Required fixtures:

- No prior ledger.
- Valid prior ledger, no changes.
- Changed Gmail newest thread.
- Changed Slack room timestamp.
- Changed Salesforce close date.
- Changed Calendar upcoming meeting.
- Changed Zoom latest meeting.
- Changed Drive linked doc modified time.
- Degraded Gmail connector.
- Degraded Slack connector.
- Forced full refresh.

## Open Decisions

1. Should `pipeline-read` always require Zoom, or should Zoom be required only when a recent meeting exists in Salesforce/Zoom search?
2. How many Gmail threads should `pipeline-forecast` read beyond the newest company-domain thread?
3. Should `pipeline-forecast` read Zoom transcripts, or summaries and metadata only?
4. What is the first full-refresh threshold: 30 days or one fiscal month?
5. Should ledger write happen only after brief validation passes, or should partial ledger state be saved after a failed validation run?

## Recommendation

Build this in phases.

Start with contracts and ledger schema. Do not change runtime gather behavior until the repo can prove the three mode contracts and validate ledger files. Then make `pipeline-read` fast. Finally add forecast deltas.

The important change is architectural: `pipeline-read` becomes triage, `pipeline-forecast` becomes weekly delta forecast, and `pipeline-hygiene` stays Salesforce-only.
