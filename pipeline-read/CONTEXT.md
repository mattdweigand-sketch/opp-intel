# Task Router

`AGENTS.md` is canonical: it holds the architecture, folder map, and rules. **This file routes a task
to the right mode.** The mode is set by the command: `/pipeline-read` for read, `/pipeline-forecast`
for forecast, or `/pipeline-hygiene` for the CRM data-quality scan. Read and forecast default to the
same fast bulk-first scope-gather-roll-up pipeline in `SKILL.md` §1 to §4 and differ only in what they
emphasize in the output. `--deep-search` opts into the slower per-deal search-agent path. Hygiene runs
a cheaper Salesforce-only path (§1, §2-3-hygiene, §4) and asks a different question — record
completeness, not deal risk.

Works with any agent. Claude Code, ChatGPT, Codex, Cursor, or a raw-API harness all use the same path:
read `AGENTS.md`, then this file, then the `SKILL.md` section for the task.

---

## Routing

| Task | Mode | Read |
|---|---|---|
| Read my pipeline (`/pipeline-read`, default current fiscal quarter) | Read | `SKILL.md` §1 to §5 |
| Deep search my pipeline (`--deep-search`) | Read or Forecast | `SKILL.md` §1, §2-3-deep-search, §4, then §5 or §5-forecast |
| Next-quarter pipeline read (`--next-quarter` or `--window next_quarter`) | Read or Forecast | `SKILL.md` §1 to §5 or §5-forecast |
| Forecast realism for the current fiscal quarter (`/pipeline-forecast`) | Forecast | `SKILL.md` §1 to §4, then §5-forecast |
| Is my CRM data clean? Missing contacts/champion/next-step, stale opps (`/pipeline-hygiene`) | Hygiene | `SKILL.md` §1, §2-3-hygiene, §4, §5-hygiene |
| Change hygiene flags, precedence, stale threshold, or champion roles | Core config | `../core/config/risk-model.json` (`hygiene` block) |
| Change the hygiene contact-roles query fields | Core config | `../core/config/sf-fields.json` (`hygiene_scope`) |
| Forecast posture (`--posture conservative|defend-commit|identify-upside`) | Forecast | `SKILL.md` §1 to §4, then §5-forecast; config in `../core/config/risk-model.json` |
| Prior snapshot comparison (`--compare <computed-inputs.json>`) | Forecast | Load the prior Computed inputs JSON and pass it to `rollup.py` |
| Internal evidence (`--internal auto|off|force`) | Forecast/Internal | `SKILL.md` §2-3-fast or §2-3-deep-search and `../core/config/risk-model.json` `internal_evidence` |
| Deep-read one deal from the read | Hand off | run `/deal-read <deal>` (the per-deal sibling) |
| Change the fiscal close calendar, close window, or flag-severity tiers | Core config | `../core/config/risk-model.json` (`pipeline` block) |
| Change forecast posture labels or internal-evidence caps | Core config | `../core/config/risk-model.json` (`forecast`, `internal_evidence`) |
| Retarget a new Salesforce org | Core config | `../core/config/sf-fields.json` |
| Change amount basis, forecast category convention, or Slack room mapping fields | Core config | `../core/config/sf-fields.json` |
| Change the risk model | Core config | `../core/config/risk-model.json` |
| Verify a change broke nothing | Test | `python3 tests/test_*.py` |

The pipeline is identical across read and forecast: resolve the rep's in-scope opps for JSQ's current
fiscal quarter by default, or next fiscal quarter when requested, run `scripts/plan.py`, and follow the
returned `execution_strategy`. Standard mode is `bulk_first`: bulk Salesforce, `pipeline_bulk_reduce.py`,
`analyze.py` per deal, then `rollup.py`, with bounded connector escalation only for material/risky/blind
deals. Deep search is explicit: `run_depth:"deep_search"` uses bounded per-deal search agents, then
`pipeline_reduce.py`, `analyze.py`, and `rollup.py`. Read leads with the riskiest deals overall.
Forecast leads with posture, category rollup, recommendation labels, movement from a prior Computed
inputs artifact when supplied, and evidence gaps.

Hygiene is the cheap exception: it skips the per-deal Gmail/Calendar/Zoom/Slack loop. It resolves the same
in-scope opps, runs one batched `OpportunityContactRole` query, computes CRM data-quality flags per opp
with `compute.py` (`hygiene:true`), and rolls up with `rollup.py` `mode:"hygiene"`. It leads with a flag
distribution and a by-deal list of the single dominant data gap on each opp, and proposes no fixes.
