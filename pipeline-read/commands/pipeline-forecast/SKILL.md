---
name: pipeline-forecast
description: Forecast-call read across a rep's whole pipeline - leads with the number, forecast posture, category rollup (commit/upside/pipeline), deterministic keep/downgrade/inspect/possible_upside labels, movement vs a prior snapshot, internal-evidence coverage, and named evidence gaps, plus a computed-inputs audit footer. Thin command frontend over the shared pipeline-read engine, run in forecast mode. Standard mode is fast and bulk-first; --deep-search opts into per-deal search agents across Salesforce, Gmail, Google Calendar, Zoom, Slack, and Google Drive within profile caps. Trigger on "/pipeline-forecast", "/pipeline-forecast --posture conservative", "/pipeline-forecast --compare <prior>", "/pipeline-forecast --deep-search", "is my forecast real", "what would I actually bank this quarter", "review my forecast". For the quick riskiest-first work-the-week view use /pipeline-read instead. Per-rep, live connectors, read-only, no writes. Do NOT use for a deep read of one named deal (that is deal-read) or another rep's pipeline.
---

# Pipeline Forecast

Thin command frontend. The engine, shared config, and full pipeline live in this repo. This command runs the **pipeline-read** surface in **forecast** mode and presents the forecast-read view.

**Engine directory:** the repo's `pipeline-read/` surface (call it `$ENGINE`). Scripts are at `$ENGINE/scripts`; shared config is at `../core/config` from the surface.

## What to do

1. Read `$ENGINE/AGENTS.md` (canonical operating map + hard rules), then `$ENGINE/SKILL.md` (the full
   pipeline). Those bind; this file only fixes the mode and the output.
2. Run the pipeline exactly as `$ENGINE/SKILL.md` describes:
   - §1 resolve scope (`$ENGINE/scripts/plan.py`, `mode:"pipeline"`, with `forecast:true` and the
     posture / amount-basis / internal options the user passed; include `run_depth:"deep_search"` only
     when `--deep-search` is passed).
   - In standard fast mode, use §2-3-fast: bulk Salesforce, `pipeline_bulk_reduce.py`, then
     `analyze.py` per deal. In `--deep-search`, use §2-3-deep-search with bounded per-deal agents,
     including `internal_evidence` with source refs.
   - §4 roll up once with `$ENGINE/scripts/rollup.py`. **Set `"mode":"forecast"` in the rollup bundle**,
     plus `posture`, `amount_basis`, `internal`, and `prior_rollup`/`compare_file` when supplied.
3. Present the **§5-forecast view** (confidence, review scope, internal evidence, the number + realistic
   call, category rollup, key movements, recommendation changes, highest-risk deals, evidence gaps,
   your move this week). Use `forecast.category_rollup` and `forecast.recommendations` verbatim; use
   `movement` only when it came from a prior Computed inputs artifact.
4. Validate before presenting: pipe the finished brief into `$ENGINE/scripts/validate_brief.py`. Show
   only `Validation: PASS` (or the failure) in chat; keep the Computed inputs JSON in the brief file.

## Arguments

`--next-quarter` / `--window current_quarter|next_quarter|30d`; `--posture conservative|defend-commit|identify-upside`;
`--amount-basis acv`; `--compare <prior-computed-inputs.json>`;
`--deep-search`; `--internal auto|off|force`; `--internal-window 30d`. Movement requires `--compare` with a prior
`pipeline-read.computed-inputs.v1` artifact, never inferred from current CRM history.

## Hand off

Deep read of one deal → `/deal-read <deal>`. Quick work-the-week read → `/pipeline-read`.
