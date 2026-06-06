---
name: pipeline-read
description: Ranked forecast-risk read across a rep's whole pipeline - riskiest deals first, each with its dominant risk (cited) and the single next move, plus a computed-inputs audit footer. Thin command frontend over the shared pipeline-read engine, run in read mode. Trigger on "/pipeline-read", "/pipeline-read --next-quarter", "read my pipeline", "which of my deals are most at risk", "what should I work this week across my deals". For the forecast-call view (the number, category rollup, keep/downgrade labels, movement vs a prior snapshot) use /pipeline-forecast instead. Per-rep, live connectors (Salesforce, Gmail, Google Calendar, Zoom, mapped Slack deal rooms, linked Google Drive proposal docs), read-only, no writes. Do NOT use for a deep read of one named deal (that is deal-read) or another rep's pipeline.
---

# Pipeline Read

Thin command frontend. The engine, shared config, and full pipeline live in this repo. This command runs the **pipeline-read** surface in **read** mode and presents the ranked-risk brief.

**Engine directory:** the repo's `pipeline-read/` surface (call it `$ENGINE`). Scripts are at `$ENGINE/scripts`; shared config is at `../core/config` from the surface.

## What to do

1. Read `$ENGINE/AGENTS.md` (canonical operating map + hard rules), then `$ENGINE/SKILL.md` (the full
   pipeline). Those bind; this file only fixes the mode and the output.
2. Run the pipeline exactly as `$ENGINE/SKILL.md` describes:
   - §1 resolve scope and list the in-scope opps (`$ENGINE/scripts/plan.py`, `mode:"pipeline"`).
   - §2–3 gather + `analyze.py` per deal (one subagent per deal, metadata only, return contract).
   - §4 roll up once with `$ENGINE/scripts/rollup.py`. **Set `"mode":"read"` in the rollup bundle.**
3. Present the **§5 read brief** (riskiest first, on-track, where-you're-blind, your move this week).
4. Validate before presenting: pipe the finished brief into `$ENGINE/scripts/validate_brief.py`. Show
   only `Validation: PASS` (or the failure) in chat; keep the Computed inputs JSON in the brief file.

## Arguments

`/pipeline-read` runs the current fiscal quarter. `--next-quarter` / `--window current_quarter|next_quarter|30d`
choose the window. `--internal auto|off|force` and `--internal-window 30d` tune internal evidence
(default is `auto`: mapped rooms and linked docs only). The forecast-only knobs (`--posture`,
`--amount-basis`, `--compare`) belong to `/pipeline-forecast`; if asked for those, route there.

## Hand off

Deep read of one deal → `/deal-read <deal>`. Forecast-call view → `/pipeline-forecast`.
