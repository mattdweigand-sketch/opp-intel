# Pipeline Read: Forecast-Risk Triage Skill

Coach one rep across their whole forecast. Pull that rep's own Salesforce, Zoom, and Gmail data for
every open opportunity closing inside the current fiscal quarter by default, add mapped Slack deal-room and linked
proposal-doc evidence by default in every mode (turn it off with `--internal off`), run each through the same deal-risk model
`deal-read` uses, and roll the results up into one ranked triage: which deals are most at risk, the
dominant risk on each (tied to real evidence), and the single next move. Read-only across all sources.

`pipeline-read` is the pipeline-level sibling of `deal-read`. Where `deal-read` does the deep read of
one named deal, `pipeline-read` runs the same gather-and-score pipeline across the forecast and ranks
the results. It is portable and self-contained: copy the folder, point an agent at it, connect the
read-only connectors.

`AGENTS.md` is canonical and agent-agnostic. Any agent (Claude, ChatGPT, Codex, Cursor, a raw-API
harness) drives this skill the same way: read `AGENTS.md`, then `CONTEXT.md` to route the task, then
`SKILL.md` for the full pipeline. Claude Code reaches the same guidance through the thin `CLAUDE.md`
wrapper. Update this file, never `CLAUDE.md`, when changing the map or rules; update `CONTEXT.md` when
changing task routing; update `SKILL.md` when changing the pipeline itself.

## Three commands, one engine

The pipeline runs in one of three views, chosen by the **command**, never inferred:

- **`/pipeline-triage`** — ranked forecast-risk brief (riskiest first, next move each). Roll-up
  `mode:"triage"`.
- **`/pipeline-forecast`** — forecast-call read (the number, category rollup, keep/downgrade labels,
  movement, evidence gaps). Roll-up `mode:"forecast"`; owns `--posture`, `--amount-basis`, `--compare`,
  `--internal-window`.
- **`/pipeline-hygiene`** — CRM data-quality scan (one dominant data gap per opp: no contacts,
  single-threaded, no champion, missing amount, missing next step, stale activity, overdue close).
  Roll-up `mode:"hygiene"`. It asks a different question than the other two — record completeness, not
  deal risk — so it has its own flags and ranking, runs a deliberately cheap **Salesforce-only** gather
  (no Zoom/Gmail/Slack/Drive, no per-deal subagent fan-out), and **proposes no fixes or next moves**.

The three commands are thin frontends in `commands/pipeline-triage/`, `commands/pipeline-forecast/`, and
`commands/pipeline-hygiene/`, each a `SKILL.md` that reads this engine and only fixes the mode + the
output section. The deterministic core (`scripts/`, `config/`) and the pipeline (`SKILL.md` steps 1–4,
plus §2-3-hygiene for the Salesforce-only path) are single-sourced here — the frontends never copy them.
`rollup.py` obeys the bundle's explicit `mode`; it does not infer the view from `amount_basis` or
`posture`.

---

## Relationship to deal-read

- **`deal-read`** — the per-deal sibling. `pipeline-read` reuses its deterministic core verbatim
  (`compute.py`, `callstats.py`, `analyze.py`) and its per-deal query plan. When a single deal in the
  triage needs the full call/email coaching read, hand off to `/deal-read <deal>`. The two stay in
  lockstep: if you change the per-deal metrics in `deal-read`, copy the change here.

---

## The 60/30/10 architecture

The repo is split by where each piece of judgment belongs, not by file type. This is the durable shape
of the system, inherited from `deal-read`.

- **`config/` is the owned data (the ~60%).** Chosen facts that compound: the risk model's scored
  dimensions, thresholds, status enum, discovery checklist, the Salesforce field mapping, the pipeline
  roll-up controls, JSQ's Feb 1 fiscal-year start and quarter window options, forecast posture and
  label options, amount basis, category convention, internal evidence caps, and the hygiene flag set,
  precedence, stale threshold, and champion roles. These are decisions, not code. To change what the
  skill believes, edit JSON here, not prose in the prompt.
- **`scripts/` is the deterministic code (the ~30%).** The rails that clear the reliability ceiling:
  the portfolio-list and contact-roles queries, per-deal query generation, date arithmetic, talk-ratio
  and freshness computation, account-history parsing, pipeline ranking, forecast category rollup,
  recommendation labels, hygiene flag classification and distribution, internal evidence summaries,
  snapshot comparison, and output validation. A model asked to do this in prose tops out around ninety
  percent compliance. The scripts make it exact every time.
- **`SKILL.md` is the thin steering layer (the ~10%).** What only the model can do: resolve the rep's
  pipeline, loop the connectors per deal, read transcripts for meaning, score coverage, and write the
  triage brief in the rep's voice. It points at the data and the code; it does not re-derive them.

When you extend the skill, sort the new piece before you write it. A chosen fact goes in `config/`. A
machine-checkable rule gets a check in `scripts/`. Steering stays in `SKILL.md`. The failure mode is
writing everything as prose and trapping a load-bearing rule in the layer that decays on the next model
upgrade.

---

## Directory Structure

- `AGENTS.md`: canonical operating map (this file). `CLAUDE.md` is a thin wrapper that imports it.
- `CONTEXT.md`: task router; read after this file to pick triage, forecast, or hygiene mode.
- `SKILL.md`: the shared engine: scope resolution, per-deal gather + analyze loop, roll-up, all three outputs.
- `commands/`: the three thin command frontends. `pipeline-triage/SKILL.md`, `pipeline-forecast/SKILL.md`,
  and `pipeline-hygiene/SKILL.md` each read this engine and only fix the mode + the presented section;
  they are symlinked into `~/.claude/skills/` so `/pipeline-triage`, `/pipeline-forecast`, and
  `/pipeline-hygiene` are invocable. They carry no engine logic of their own.
- `scripts/`: the deterministic core. Stdlib Python, no dependencies.
  - `plan.py`: two phases. The pipeline phase emits the scoped portfolio-list query plus forecast
    amount/category fields and internal-evidence mapping fields when enabled (or, with `hygiene:true`,
    forces those off and — given `opp_ids` — emits the batched `OpportunityContactRole` query); the
    per-deal phase emits the exact Salesforce/Gmail/Zoom queries and bounded Slack/linked-doc
    instructions for one deal. You execute them; you never improvise SOQL or broad Slack/Drive search.
  - `analyze.py`: the per-deal processing entrypoint. Feed it one deal's bundle; it runs `compute.py` +
    `callstats.py`, parses account history, and preserves source-backed internal evidence. Run it once
    per in-scope deal.
  - `rollup.py`: the pipeline aggregator. Feed it every per-deal `analyze.py` output; it ranks the
    deals by severity of current evidence (or, in `mode:"hygiene"`, by hygiene-flag precedence),
    computes portfolio and forecast/hygiene aggregates, emits deterministic recommendation or hygiene
    flags, summarizes internal evidence, and compares against a prior Computed inputs artifact when
    supplied.
  - `compute.py` / `callstats.py`: deterministic deal and call metrics, invoked by `analyze.py`. Not
    called directly. Copied from `deal-read`; `compute.py` also emits the hygiene flags on a
    `hygiene:true` run.
  - `validate_brief.py`: output-contract gate. The model pipes its drafted brief in before presenting;
    it enforces the computed-footer, schema, forecast/hygiene sections, source refs, evidence gaps, and
    confidence rules in code instead of by asking.
- `config/`: the owned data.
  - `risk-model.json`: scored dimensions, status enum, thresholds, discovery checklist, JSQ's Feb 1
    fiscal-year start, current-quarter default, next-quarter option, and the `pipeline`, `forecast`,
    `internal_evidence`, and `hygiene` blocks. Canonical on the no-predictive-weights rule (see its
    `_comment`).
  - `sf-fields.json`: Salesforce field and query mapping, including the `pipeline_scope` list query,
    `hygiene_scope` contact-roles query, amount basis, forecast category convention, and Slack
    deal-room mapping fields. Edit this to retarget another org.
- `tests/`: plain `python3 tests/test_*.py` runners, no pytest. Each pins its script's output against
  fixtures and exits non-zero on failure.

Every script and test resolves its siblings and config relative to its own location
(`HERE = os.path.dirname(os.path.abspath(__file__))`), so the folders move as a unit without breaking
paths.

---

## Handoff Artifact

The portable handoff artifact is the verbatim `Computed inputs` JSON from `rollup.py`. Pass this same
object to notification workflows; do not hand-build a separate summary payload. Broader forecast
workflows may cite it, but they should not re-score the deals or rewrite deterministic labels. The
schema is:

```json
{
  "schema_version": "pipeline-read.computed-inputs.v1",
  "run": {
    "rep_name": "...",
    "run_date": "...",
    "mode": "triage|forecast",
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

`forecast`, `internal_evidence`, and `movement` appear when forecast mode or comparison inputs require
them. The artifact is read-only evidence for notification and downstream forecast workflows, not an
instruction to write CRM, send messages, or create tasks.

---

## Session Start

1. Read this file
2. Read `CONTEXT.md` to route the task
3. Read `SKILL.md` for the pipeline
4. Confirm scope: the running rep's open opps closing in the current fiscal quarter by default. JSQ's
   fiscal year starts Feb 1, so quarters run Feb-Apr, May-Jul, Aug-Oct, and Nov-Jan. Use the
   next-quarter option only when the user asks for it.

---

## Hard Rules

- **Read-only across all connectors.** `pipeline-read` makes no writes at all — not even a draft.
  Drafting a follow-up is a per-deal action; it lives in `deal-read`. Never send email, never edit
  Salesforce, never modify recordings, never post to Slack, and never edit Drive docs.
- **One rep per run.** Operate only on the running user's own connected accounts. Do not access another
  rep's mailbox or recordings.
- **Confirm before a large run.** A full read loops the per-deal connectors that `plan.py` reports in
  `per_deal_connectors` (Salesforce, Gmail, and Zoom always; Slack and Google Drive when internal
  evidence is on). If the in-scope set exceeds `pipeline.large_run_threshold` in `risk-model.json`, list
  the deals and the connector set from `per_deal_connectors`, and confirm before looping — do not
  silently fan out into dozens of connector calls.
- **Run the deterministic core, never reinvent it.** Invoke `scripts/plan.py`, `scripts/analyze.py`
  (once per deal), and `scripts/rollup.py` (once over all deals); do not do date math, ranking, or ACV
  summing in your head. The `Computed inputs` footer is the audit trail that the scripts ran, and
  `scripts/validate_brief.py` gates it: pipe the finished brief through it before presenting.
- **Recommendation labels come from `rollup.py`.** Forecast labels are exactly `keep`, `downgrade`,
  `inspect`, or `possible_upside`. Do not hand-write a stronger category call than the script emitted.
- **Use comparison only from a prior Computed inputs artifact.** `--compare` movement must come from
  prior `pipeline-read.computed-inputs.v1` JSON. Do not infer movement from current Salesforce history.
- **Bound internal evidence.** `internal=auto` uses mapped Slack deal rooms only and records
  `deal_room_missing` when no mapping exists. Broad Slack or Drive lookup is allowed only under
  `internal=force`. Linked Google Drive proposal docs are read only when linked from the mapped room or
  explicit deal context.
- **Preserve source ownership.** Salesforce owns amount, stage, close date, owner, and forecast
  category. Slack and Drive can affect confidence, evidence gaps, risk notes, internal owner, and
  next-move wording, but they cannot override Salesforce-owned opportunity truth or deterministic
  ranking.
- **No predictive weights, no local grading.** Rank deals by severity of current evidence (the
  flag-severity tiers), not by an assumed probability of winning or losing. There is no per-deal
  win-probability score here, and there is no plan to add one: grading deals or dimensions against
  win/loss outcomes is a central, pooled data product, never something this local per-rep skill does or
  builds toward. `config/risk-model.json` is canonical on this.
- **Calibrate confidence to evidence.** Name the deals you could not see clearly (stale or thin data)
  rather than asserting authoritative risks across the whole pipeline on a lagging view.
- **Voice:** no em dashes, no emojis, concrete close. Defer to the writing-style skill for the brief.
