# opp-intel Instructions

`core/` is the shared opportunity evidence engine. It owns shared config, schemas, source contracts, deterministic mechanics, and shared validators.

`deal-read/` remains the one-opportunity deep read. It owns depth-first orchestration, coaching output, and the explicit-confirmation Gmail draft policy.

`pipeline-read/` remains the many-opportunity pipeline read. It owns portfolio triage, forecast, and hygiene modes. Hygiene remains Salesforce-only.

The shared-core migration is complete through the planned Phase 6 extraction. Preserve behavior first, move one layer at a time, and verify each change before continuing.

Hard constraints:
- Do not edit `/Users/matthewweigand/Code/deal-read` or `/Users/matthewweigand/Code/pipeline-read`.
- Do not fold `deal-read` into `pipeline-read`.
- Do not introduce predictive weights.
- Keep source access read-only.
- `deal-read` may only create Gmail drafts on explicit user confirmation.
- Do not include `/Users/matthewweigand/Code/deal-read/deliverables/forecast-2026-06-05-two-closest.md`.
