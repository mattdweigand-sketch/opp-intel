# Pipeline Read

Pipeline Read ranks forecast risk across a rep's whole pipeline. It is the pipeline-level sibling of
[Deal Read](../deal-read): it pulls the rep's own Gmail threads, Google Calendar meetings, Zoom recordings, Salesforce data,
mapped Slack deal rooms, and linked Google Drive proposal docs for every open opportunity closing in
JSQ's current fiscal quarter by default. It runs each deal through the same deal-risk model, then rolls
the results into one ranked read: which deals are most at risk, the dominant risk on each with cited
evidence, and the next move. It is read-only across every source and makes no writes, not even a draft.

---

## Modes

Pipeline Read has three views, all over the same engine. The mode is set by the command, never inferred:

- `/pipeline-read`: the work-the-week view. It ranks the rep's open current-quarter deals by
  evidence-backed risk and gives the next move for each one.
- `/pipeline-forecast`: the forecast-call view. It uses the same deal reads, then rolls them into
  forecast posture, category rollup, keep/downgrade/inspect labels, movement from a prior Computed
  inputs artifact when supplied, internal evidence coverage, and evidence gaps.
- `/pipeline-hygiene`: the CRM data-quality view. It asks a different question — not "is this deal at
  risk?" but "is the Salesforce *record* clean?" — and tags each opp with its single dominant data gap
  (no contacts, single-threaded, no champion, missing amount, missing next step, stale activity,
  overdue close). It is deliberately cheap and **Salesforce-only**: no Gmail, Calendar, Zoom, Slack, or Drive, and
  no per-deal fan-out, so it stays fast even on a large pipeline. It names gaps and **proposes no fixes**
  — that is the clean line versus read. (This replaces the standalone `pipeline-health` skill.)

Read and forecast both score deal risk off the same live per-deal evidence; hygiene checks record
completeness off a cheap Salesforce-only scan. Reach for hygiene first to clean the data, read to
decide where the week goes, and forecast when you need to commit a number.

Other options:

- `--next-quarter` runs any view against next fiscal quarter.
- For in-depth single-deal analysis, use `../deal-read` in this repo.

Forecast options:

| Command | Use |
|---|---|
| `/pipeline-forecast --posture conservative` | Treat commit conservatively and surface downgrade risk first. |
| `/pipeline-read --next-quarter` | Run the riskiest-first read on next fiscal quarter instead of the current quarter. |
| `/pipeline-forecast --window next_quarter` | Run the forecast view for next fiscal quarter. |
| `/pipeline-forecast --posture defend-commit` | Focus on whether committed deals have enough evidence to defend. |
| `/pipeline-forecast --posture identify-upside` | Look for credible upside while still naming weak evidence. |
| `/pipeline-forecast --amount-basis acv` | Use ACV as the forecast amount basis. |
| `/pipeline-forecast --compare deliverables/prior-computed-inputs.json` | Compare against a prior Computed inputs artifact for movement. |
| `/pipeline-forecast --internal auto` | Read mapped Slack deal rooms and linked Drive docs only. |
| `/pipeline-forecast --internal off` | Skip Slack and Google Drive internal evidence. |
| `/pipeline-forecast --internal force --internal-window 30d` | Use bounded fallback Slack lookup over the last 30 days when no room is mapped. |

Pipeline Read stays *shallow per deal* so a full run stays practical. It works mostly from meeting
summaries plus Salesforce and email-freshness signals, so it can score every deal without reading
dozens of full transcripts. For single-deal depth, use `../deal-read`.

---

## What you get

A read or forecast brief, short enough to read before a forecast call:

- Confidence rating up front, tied to how much of the pipeline you got a current read on.
- Forecast at a glance: total ACV in the window, ACV at risk, and the headline counts
  (single-threaded, slipped/overdue, stale-data).
- Riskiest first: deals ranked by severity of current evidence, each with cited evidence and a
  specific next action.
- Internal context: mapped Slack deal-room evidence and linked Google Drive proposal docs, unless
  the run passes `--internal off`.
- On-track deals, so the brief is not only risk.
- Blind spots: the deals with stale or thin data, named rather than asserted on.
- Your move this week: the single highest-leverage action across the pipeline.
- A Computed inputs footer: the verbatim output of the roll-up script, showing how the ranking and
  totals were computed.
- In forecast mode: Review scope, Internal evidence, Category rollup, Key movements, Recommendation
  changes, Highest-risk deals, Evidence gaps, and Your move this week.

---

## How it ranks

Deals are ranked by **severity of current evidence**, not by a predicted probability of winning. A deal
carrying a `red` flag (overdue, slipped, single-threaded, stalled, or late-stage with no upcoming
customer meeting) outranks one with only `amber` flags; ties break on flag count, then ACV, then
days-to-close, all observed facts. Calendar flags only count when Calendar coverage is available;
unavailable Calendar is an evidence gap, not a risk flag. There is **no win-
probability model** here by design: grading deals against win/loss outcomes is a central, pooled data
product, never something this local per-rep skill does. The flag-severity tiers live in
`../core/config/risk-model.json`.

Forecast recommendation labels also come from `../core/scripts/rollup.py`: `keep`, `downgrade`, `inspect`, and
`possible_upside`. They are deterministic posture labels, not CRM writebacks and not win-probability
scores.

Salesforce owns opportunity truth: amount, stage, close date, owner, and forecast category. Calendar can
affect meeting-cadence flags in read and forecast. Slack deal rooms and linked proposal docs can
affect confidence, evidence gaps, risk notes, internal owner, and next-move wording. They cannot change
deterministic ranking or Salesforce-owned fields. Broad Slack or Drive lookup is allowed only when the
internal mode is `force` (the default); `auto` restricts to mapped deal rooms only.

---

## Getting started

1. Point an agent at the repo. Claude Code reads `CLAUDE.md` automatically; any other agent starts at
   `AGENTS.md`, then `CONTEXT.md`.
2. Connect Salesforce, Gmail, Google Calendar, Zoom, Slack, and Google Drive (all read-only). Gmail,
   Calendar, and Zoom are always part of read and forecast. Slack and Google Drive are the internal
   evidence lane; use `--internal off` only to skip those internal sources.
3. Ask: `/pipeline-read` for the riskiest-first work-the-week read, `/pipeline-forecast` for the
   forecast-call view, and add `--next-quarter` to either for the next fiscal quarter.

Pipeline Read is one surface in this shared repo. Shared deterministic mechanics live in `../core/`;
for single-deal depth, use `../deal-read`.

A full read loops the per-deal connectors `plan.py` reports in `per_deal_connectors`: Salesforce,
Gmail, Google Calendar, and Zoom always, plus Slack and Google Drive whenever internal evidence is on. The default scope
is JSQ's current fiscal quarter. JSQ's fiscal year starts Feb 1, so quarters run Feb-Apr, May-Jul,
Aug-Oct, and Nov-Jan. The skill confirms before running when more than ~15 deals are in scope.

Pipeline Read has no Sales plugin dependency. Broader forecast workflows can consume its output, but
they should consume the Computed inputs artifact rather than re-score its deals.

---

## Handoff artifact

Pipeline Read writes the brief to `deliverables/` when a saved artifact is needed. The chat response
stays short:

```text
Validation: PASS

Saved to deliverables/<file>.md.
```

Include a `computer://` link to the same file when the client supports it. The saved Markdown file
contains the full brief plus a `Computed inputs` JSON block at the bottom. That JSON block is the
handoff artifact.

Use it when another workflow needs the pipeline read:

- Notification workflows can turn it into a message.
- Forecast workflows can cite it as evidence.
- Neither should re-score the deals, change recommendation labels, or rebuild a separate summary
  payload from the prose brief.

Shape:

```json
{
  "schema_version": "pipeline-read.computed-inputs.v1",
  "run": {
    "rep_name": "...",
    "run_date": "...",
    "mode": "read|forecast",
    "posture": "conservative|defend_commit|identify_upside",
    "amount_basis": "acv|crm_primary_amount",
    "internal_evidence": "auto|off|force"
  },
  "portfolio": {},
  "forecast": {},
  "internal_evidence": {},
  "movement": {},
  "ranking": []
}
```

`forecast`, `internal_evidence`, and `movement` appear only when the run needs them.

---

## Relationship to Deal Read

[Deal Read](https://github.com/mattdweigand-sketch/deal-read) is the per-deal sibling. Pipeline Read
reuses its deterministic core verbatim, but runs as a standalone pipeline-level skill.

---

## Structure

```
pipeline-read/
├── AGENTS.md          # Canonical operating map (any agent reads this first)
├── CLAUDE.md          # Thin wrapper that imports AGENTS.md + SKILL.md
├── CONTEXT.md         # Task router: read, forecast, or hygiene mode
├── SKILL.md           # Pipeline surface: full pipeline + all three output views
├── README.md
├── .gitignore
├── commands/          # Thin command frontends (symlinked into ~/.claude/skills)
│   ├── pipeline-read/SKILL.md    #   runs the engine in read mode → §5
│   ├── pipeline-forecast/SKILL.md  #   runs the engine in forecast mode → §5-forecast
│   └── pipeline-hygiene/SKILL.md   #   runs the engine in hygiene mode (SF-only) → §5-hygiene
├── scripts/           # Compatibility wrappers into ../core/scripts and ../core/validators
│   ├── plan.py        #   emits the portfolio query + per-deal queries
│   ├── analyze.py     #   per-deal processing entrypoint (copied from deal-read)
│   ├── rollup.py      #   ranks deals, computes forecast rollups, compares snapshots
│   ├── compute.py     #   deal metrics (called by analyze.py; from deal-read)
│   ├── callstats.py   #   call-execution metrics (called by analyze.py; from deal-read)
│   └── validate_brief.py # output-contract gate run on the drafted brief
../core/config/        # Shared owned data
├── risk-model.json    # dimensions, thresholds, pipeline/forecast/internal/hygiene config
└── sf-fields.json     # Salesforce fields, amount/category mapping, internal + hygiene queries
└── tests/             # python3 tests/test_*.py, no pytest
    ├── test_plan.py
    ├── test_rollup.py
    ├── test_rollup_hygiene.py
    ├── test_rollup_forecast.py
    ├── test_rollup_compare.py
    ├── test_validate_brief.py
    ├── test_validate_forecast_brief.py
    ├── test_forecast_config.py
    ├── test_internal_evidence.py
    ├── test_analyze.py
    ├── test_compute.py
    └── test_callstats.py
```

`pipeline-read/` owns command routing, modes, and output shape. Shared config, deterministic scripts,
validators, and source contracts live in `../core/`.
