---
name: pipeline-hygiene
description: Cross-pipeline CRM data-quality scan for a rep - one row per open opportunity, each tagged with its single dominant hygiene flag (no contacts, single-threaded, no champion, missing amount, missing next step, stale activity, overdue close), ordered by a fixed precedence, plus a computed-inputs audit footer. Thin command frontend over the shared pipeline-read engine, run in hygiene mode. Deliberately cheap and Salesforce-only - no Gmail, Calendar, Zoom, Slack, or Drive. Trigger on "/pipeline-hygiene", "is my CRM data clean", "which deals are missing contacts or a champion", "pipeline hygiene", "data-quality scan of my pipeline", "which opps have no next step", "stale or incomplete opportunities". Names data gaps only; it proposes NO fixes or next moves (that is /pipeline-read). For the riskiest-first work-the-week view use /pipeline-read; for the forecast number use /pipeline-forecast. Per-rep, Salesforce read-only, no writes. Do NOT use for a deep read of one named deal (that is deal-read) or another rep's pipeline.
---

# Pipeline Hygiene

Thin command frontend. The engine, shared config, and full pipeline live in this repo. This command runs the **pipeline-read** surface in **hygiene** mode and presents the CRM data-quality view.

**Engine directory:** the repo's `pipeline-read/` surface (call it `$ENGINE`). Scripts are at `$ENGINE/scripts`; shared config is at `../core/config` from the surface.

Hygiene asks a different question than read or forecast: not "is this deal at risk?" but "is the
Salesforce *record* clean?" — contacts logged, a champion role set, `NextStep` and amount filled,
activity recent. It is a deliberately cheap **Salesforce-only** scan: no Gmail, Calendar, Zoom, Slack, or Drive,
and no per-deal subagent fan-out. It names data gaps and **proposes no fixes** — that is the clean line
versus `/pipeline-read`.

## What to do

1. Read `$ENGINE/AGENTS.md` (canonical operating map + hard rules), then `$ENGINE/SKILL.md` (the full
   pipeline). Those bind; this file only fixes the mode and the output.
2. Run the pipeline exactly as `$ENGINE/SKILL.md` describes, hygiene path:
   - §1 resolve scope and list the in-scope opps (`$ENGINE/scripts/plan.py`, `mode:"pipeline"`,
     `hygiene:true`).
   - **§2-3-hygiene** — Salesforce-only gather: run `plan.py` again with `hygiene:true` and the
     `opp_ids` to get the batched `contact_roles_bulk` query and `champion_roles`; group roles by
     `OpportunityId`; run `$ENGINE/scripts/analyze.py` per opp with a light `hygiene:true`
     `compute_input`. **No subagents, no Gmail/Calendar/Zoom/Slack/Drive.**
   - §4 roll up once with `$ENGINE/scripts/rollup.py`. **Set `"mode":"hygiene"` in the rollup bundle.**
3. Present the **§5-hygiene view** (distribution, by-deal dominant flags, clean list). Name the gaps;
   add no fixes or next moves.
4. Validate before presenting: pipe the finished brief into `$ENGINE/scripts/validate_brief.py`. Show
   only `Validation: PASS` (or the failure) in chat; keep the Computed inputs JSON in the brief file.

## Arguments

`/pipeline-hygiene` runs the current fiscal quarter. `--next-quarter` / `--window
current_quarter|next_quarter|30d` choose the window. Hygiene has no `--posture`, `--amount-basis`,
`--compare`, or `--internal` knobs — those belong to `/pipeline-forecast` and `/pipeline-read`; if
asked for risk ranking or a forecast number, route there.

## Hand off

Riskiest-first read with next moves → `/pipeline-read`. Forecast number → `/pipeline-forecast`.
Deep read or a follow-up draft on one deal → `/deal-read <deal>`.
