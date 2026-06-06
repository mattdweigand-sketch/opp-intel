# Task Router

`AGENTS.md` is canonical: it holds the architecture, folder map, and rules. **This file routes a task to the right mode.** All three modes run the same gather-and-score pipeline in `SKILL.md` §1 to §4 and differ only in what they output.

Works with any agent. Claude Code, ChatGPT, Codex, Cursor, or a raw-API harness all use the same path: read `AGENTS.md`, then this file, then the `SKILL.md` section for the task.

---

## Routing

| Task | Mode | Read |
|---|---|---|
| Read a named deal (default) | Review | `SKILL.md` §1 to §5 |
| Prep for an upcoming call (`/deal-read <deal> --prep`) | Prep | `SKILL.md` §1 to §4, then §5-prep |
| Draft the follow-up email | Draft | `SKILL.md` §6 (only after review surfaces email as the next move) |
| Retarget a new Salesforce org | Core config | `../core/config/sf-fields.json` |
| Change the risk model | Core config | `../core/config/risk-model.json` |
| Verify a change broke nothing | Test | `python3 tests/test_*.py` |

The pipeline is identical across review and prep: resolve the opportunity, gather Salesforce, Gmail, Google Calendar, Zoom, Slack, and linked Drive evidence as planned by `scripts/plan.py`, run `scripts/analyze.py` for the metrics, then score `../core/config/risk-model.json`. Only the final output differs. Draft mode is gated on the computed freshness flags, not judgment (see `SKILL.md` §6).
