# Deal Read

Deal-risk coaching for a single sales opportunity. Deal Read synthesizes a rep's own Salesforce data, Zoom recordings, Gmail threads, mapped Slack deal-room evidence, and linked Google Drive proposal docs into a brief that names where one deal is at risk and the specific next actions to de-risk it. The only write it can make is a Gmail draft, never sent, and only on confirmation.

---

## Modes

- **Review (default):** `/deal-read <deal>` returns a risk brief on the deal as it stands.
- **Prep:** `/deal-read <deal> --prep` returns a pre-call plan: where you're blind and the three questions to ask next.
- **Draft:** offered inside a review only when an email is the next move. It writes the follow-up into your Gmail drafts. You review and send.

---

## What you get

A review brief, short enough to read before a call:

- **Confidence** rating up front, tied to how much current evidence backs it.
- **Read:** an honest call on whether the deal is where its stage says it is.
- **Account history:** prior wins and losses on the same account, with the recorded loss reason.
- **Top risks:** the three highest-severity ones, each with cited evidence and a specific next action.
- **What's going well**, so it is not all red.
- **How you ran the call:** talk ratio, question count, and the discovery topics you missed.
- **Internal evidence:** mapped Slack deal-room context and linked proposal-doc coverage, with gaps named when those sources are missing or unavailable.
- **Your next move this week.**
- A **Computed inputs** footer: the verbatim output of the analysis scripts, proof the numbers were computed, not guessed.

The economic-buyer, champion, and paper/legal-status risks are read from structured Salesforce fields when your org maintains them (contact-role picklists, `Legal_Status__c`, the MEDDPICC justification fields), so those calls are grounded in CRM data rather than inferred from job titles. Where a field is blank, the brief names it as a hygiene gap instead of guessing.

---

## Getting Started

1. Point an agent at the repo. Claude Code reads `CLAUDE.md` automatically; any other agent starts at `AGENTS.md`, then `CONTEXT.md`.
2. Connect Salesforce, Zoom, Gmail, Slack, and Google Drive. Slack and Drive are read-only internal evidence sources.
3. Ask: `/deal-read <opportunity or account name>`.
4. For a call you have coming up: `/deal-read <deal> --prep`.

---

## Structure

```
deal-read/
├── AGENTS.md          # Canonical operating map (any agent reads this first)
├── CLAUDE.md          # Thin wrapper that imports AGENTS.md + SKILL.md
├── CONTEXT.md         # Task router: review, prep, or draft mode
├── SKILL.md           # The full coaching pipeline
├── README.md
├── .gitignore
├── scripts/           # Compatibility wrappers into ../core/scripts and ../core/validators
│   ├── plan.py        #   emits the exact connector queries to run
│   ├── analyze.py     #   single processing entrypoint
│   ├── compute.py     #   deal metrics (called by analyze.py)
│   ├── callstats.py   #   call-execution metrics (called by analyze.py)
│   └── validate_brief.py # output-contract gate run on the drafted brief
../core/config/        # Shared owned data
├── risk-model.json    # scored dimensions, thresholds, discovery checklist, legal-status set
└── sf-fields.json     # Salesforce field + query mapping
└── tests/             # python3 tests/test_*.py, no pytest
    ├── test_plan.py
    ├── test_analyze.py
    ├── test_compute.py
    ├── test_callstats.py
    └── test_validate_brief.py
```

Design note: `deal-read/` owns the one-opportunity workflow and output shape. Shared config, deterministic scripts, validators, and source contracts live in `../core/`.
