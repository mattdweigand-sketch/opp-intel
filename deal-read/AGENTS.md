# Deal Read: Deal-Risk Coaching Skill

Coach one rep on one deal. Pull that rep's own Salesforce, Zoom, Gmail, mapped Slack deal-room evidence, and linked Google Drive proposal docs for a named opportunity, run it through a deal-risk model, and return the top risks with concrete next actions, each tied to evidence from a real call, email, Salesforce field, Slack source, or proposal doc.

`AGENTS.md` is canonical and agent-agnostic. Any agent (Claude, ChatGPT, Codex, Cursor, a raw-API harness) drives this skill the same way: read `AGENTS.md`, then `CONTEXT.md` to route the task, then `SKILL.md` for the full pipeline. Claude Code reaches the same guidance through the thin `CLAUDE.md` wrapper. Update this file, never `CLAUDE.md`, when changing the map or rules; update `CONTEXT.md` when changing task routing; update `SKILL.md` when changing the pipeline itself.

---

## The 60/30/10 architecture

The repo is split by where each piece of judgment belongs, not by file type. This is the durable shape of the system.

- **`config/` is the owned data (the ~60%).** Chosen facts that compound: the risk model's scored dimensions, thresholds, status enum, discovery checklist, and the Salesforce field mapping. These are decisions, not code. To change what the skill believes, edit JSON here, not prose in the prompt.
- **`scripts/` is the deterministic code (the ~30%).** The rails that clear the reliability ceiling: query generation, date arithmetic, talk-ratio and freshness computation, account-history parsing. A model asked to do this in prose tops out around ninety percent compliance. The scripts make it exact every time.
- **`SKILL.md` is the thin steering layer (the ~10%).** What only the model can do: resolve the deal, call the connectors, read transcripts for meaning, score coverage, write the brief in the rep's voice. It points at the data and the code; it does not re-derive them.

When you extend the skill, sort the new piece before you write it. A chosen fact goes in `config/`. A machine-checkable rule gets a check in `scripts/`. Steering stays in `SKILL.md`. The failure mode is writing everything as prose and trapping a load-bearing rule in the layer that decays on the next model upgrade.

---

## Directory Structure

- `AGENTS.md`: canonical operating map (this file). `CLAUDE.md` is a thin wrapper that imports it.
- `CONTEXT.md`: task router; read after this file to pick review, prep, or draft mode.
- `SKILL.md`: the full coaching pipeline: connectors, gather steps, scoring, output templates, draft-email gate.
- `scripts/`: the deterministic core. Stdlib Python, no dependencies.
  - `plan.py`: emits the exact Salesforce/Gmail/Zoom queries to run. You execute them; you never improvise SOQL.
  - `analyze.py`: the single processing entrypoint. Feed it one bundle; it runs `compute.py` + `callstats.py`, parses account history, and normalizes Slack/Drive internal evidence.
  - `compute.py` / `callstats.py`: deterministic deal and call metrics, invoked by `analyze.py`. Not called directly.
  - `validate_brief.py`: output-contract gate. The model pipes its drafted brief in before presenting; it enforces the computed-footer and confidence rules in code instead of by asking.
- `config/`: the owned data.
  - `risk-model.json`: scored dimensions, status enum, thresholds, discovery checklist, and the legal-status not-started set. Canonical on the no-predictive-weights rule (see its `_comment`).
  - `sf-fields.json`: Salesforce field and query mapping, including the contact-role and MEDDPICC fields that ground the champion, economic-buyer, and paper/legal risks. Edit this to retarget another org.
- `tests/`: plain `python3 tests/test_*.py` runners, no pytest. Each pins its script's output against fixtures and exits non-zero on failure.

Every script and test resolves its siblings and config relative to its own location (`HERE = os.path.dirname(os.path.abspath(__file__))`), so the folders move as a unit without breaking paths.

---

## Session Start

1. Read this file
2. Read `CONTEXT.md` to route the task
3. Read `SKILL.md` for the pipeline
4. Confirm the deal name; ask if none is given

---

## Hard Rules

- **Read-only across Salesforce, Zoom, Gmail, Slack, and Google Drive.** The one write this skill can make is creating a Gmail draft, never sending, and only on explicit user confirmation (see `SKILL.md` §6). Never send email, never edit Salesforce, never modify recordings, never post to Slack, and never edit Drive docs.
- **One deal, one rep per run.** Operate only on the running user's own connected accounts. For a whole-pipeline view across deals, redirect to `/pipeline-hygiene` (CRM health), `/pipeline-triage` (risk), or `/pipeline-forecast` (the number).
- **Run the deterministic core, never reinvent it.** Invoke `scripts/plan.py` and `scripts/analyze.py`; do not do date math or talk-ratio counting in your head. The `Computed inputs` footer in the brief is the audit trail that the scripts actually ran, and `scripts/validate_brief.py` gates it: pipe the finished review brief through it before presenting.
- **No predictive weights, no local grading.** Rank risks by severity of current evidence, not by assumed correlation with outcome. Grading dimensions against win/loss outcomes is a central, pooled data product, never something this local per-rep skill does or builds toward. `config/risk-model.json` is canonical on this.
- **Calibrate confidence to evidence.** Name what you could not see rather than writing authoritative risks on thin or stale data.
- **Voice:** no em dashes, no emojis, concrete close. Defer to the writing-style skill for the brief and any draft.
