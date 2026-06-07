# opp-intel Instructions

`core/` is the shared opportunity evidence engine. It owns shared config, schemas, source contracts, deterministic mechanics, and shared validators.

`deal-read/` remains the one-opportunity deep read. It owns depth-first orchestration, coaching output, and the explicit-confirmation Gmail draft policy.

`pipeline-read/` remains the many-opportunity pipeline read. It owns portfolio read, forecast, and hygiene modes. Hygiene remains Salesforce-only.

The shared-core migration is complete through the planned Phase 6 extraction. Preserve behavior first, move one layer at a time, and verify each change before continuing.

Source ownership:
- Salesforce owns Salesforce opportunity/account/contact truth only.
- Gmail owns Gmail thread, participant, timestamp, inbound/outbound, unanswered-thread, and email-recency truth.
- Slack owns Slack channel/message/deal-room/internal-activity truth through Slack MCP only. Salesforce is never Slack evidence.
- Google Calendar owns Calendar event truth.
- Zoom owns Zoom meeting/call truth.
- Google Drive owns linked-doc and proposal-doc truth.

Coverage proof rules:
- Missing or incomplete connector reads are coverage gaps, not negative account claims.
- Active bundles must carry `coverage_manifest` / `source_reads` for the expected profile sources emitted by `plan.py`.
- Missing expected source-read proof hard-fails before analysis; degraded source statuses become coverage gaps.
- Gmail absence/recency claims require company-domain search proof and either the newest matching company-domain thread id or `domain_thread_search_status=no_match`.
- Slack absence/activity claims require Slack MCP proof: `slack_mcp_checked`, searched channels, channel matches, and a Slack-source deal-room reference when found.
- Do not cite Salesforce as evidence for Slack room existence, Slack activity, or Slack absence.
- Deal and pipeline outputs must include computed-inputs evidence and pass their validator before presentation.

Hard constraints:
- Do not edit `/Users/matthewweigand/Code/deal-read` or `/Users/matthewweigand/Code/pipeline-read`.
- Do not fold `deal-read` into `pipeline-read`.
- Do not introduce predictive weights.
- Keep source access read-only.
- `deal-read` may only create Gmail drafts on explicit user confirmation.
- Do not include `/Users/matthewweigand/Code/deal-read/deliverables/forecast-2026-06-05-two-closest.md`.
