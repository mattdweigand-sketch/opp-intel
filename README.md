# opp-intel

`opp-intel` is the shared home for opportunity intelligence work.

It has one shared core and two agent-facing surfaces:

- `deal-read/` gives one opportunity the deepest read.
- `pipeline-read/` gives a rep's pipeline a breadth-oriented read.
- `core/` holds the shared evidence mechanics both surfaces use.

The repo exists so the two surfaces can share source planning, config, deterministic analysis, schemas, and validators without collapsing into one tool.

## What each surface does

### deal-read

`deal-read` is the single-opportunity coaching workflow.

It reads Salesforce, Gmail, Google Calendar, Zoom, Slack channels through Slack, and linked Google Drive proposal docs for one deal. It returns a short risk brief with confidence, account history, top risks, what is going well, call-execution signals, internal evidence, and the next move.

Use it when the question is about one deal:

```text
/deal-read <opportunity or account name>
/deal-read <opportunity or account name> --prep
```

The default mode reviews the deal as it stands. Prep mode produces the pre-call plan: where the evidence is thin and what to ask next.

`deal-read` is the only surface that can create a Gmail draft. It never sends mail, and it may only write a draft after explicit confirmation.

### pipeline-read

`pipeline-read` is the portfolio workflow.

It reads the rep's open opportunities in the selected window, runs the shared deal-risk mechanics across them, and rolls the result into a ranked pipeline view. It is read-only across every source and makes no writes.

Use it when the question is about many deals:

```text
/pipeline-read
/pipeline-forecast
/pipeline-hygiene
```

`/pipeline-read` is the work-the-week view. It ranks open deals by evidence-backed risk and gives the next move for each one.

`/pipeline-forecast` is the forecast-call view. It rolls the same per-deal reads into forecast posture, category rollup, recommendation labels, movement from a prior computed-inputs artifact, internal evidence coverage, and evidence gaps.

`/pipeline-hygiene` is the CRM data-quality view. It is deliberately Salesforce-only. It checks whether the Salesforce record is clean and names the dominant data gap. It does not inspect Gmail, Calendar, Zoom, Slack, or Drive, and it does not propose fixes.

## Shared core

`core/` owns the mechanics that should stay identical across surfaces:

```text
core/
├── adapters/      # Salesforce, Gmail, Calendar, calls, Slack, and Drive boundaries
├── config/        # risk model, Salesforce fields, depth profiles, source contracts
├── schemas/       # evidence bundle, analyzed deal, and rollup contracts
├── scripts/       # plan, analyze, compute, callstats, and rollup entrypoints
├── validators/    # separate deal and pipeline output gates
└── tests/         # shared fixtures and parity tests
```

Important shared files:

- `core/config/risk-model.json`
- `core/config/sf-fields.json`
- `core/config/depth-profiles.json`
- `core/config/source-contracts.json`
- `core/scripts/plan.py`
- `core/scripts/analyze.py`
- `core/scripts/rollup.py`

Surface scripts in `deal-read/scripts/` and `pipeline-read/scripts/` are compatibility wrappers into `core/`. Surface docs, modes, command routing, output shape, and write policy remain surface-owned.

## Source boundaries

The core has explicit depth profiles:

- `deal`: one-opportunity deep read across Salesforce, Gmail, Calendar, Zoom, Slack, and Drive.
- `pipeline`: multi-opportunity read that stays shallow enough to run across a full pipeline.
- `hygiene`: Salesforce-only scan for CRM record quality.

The source boundary is intentional and lives in `core/config/source-contracts.json`:

- Salesforce owns opportunity truth: amount, stage, close date, owner, forecast category, contacts, next step, legal status, and CRM hygiene fields.
- Gmail owns Gmail thread, participant, timestamp, inbound/outbound, unanswered-thread, and email-recency truth.
- Google Calendar owns meeting, attendee, timestamp, title, and event-description truth.
- Zoom owns Zoom meeting, recording, summary, transcript, and call-participant truth.
- Slack owns Slack channel, message, deal-room existence, and internal-activity truth through Slack MCP only. Salesforce is never Slack evidence.
- Google Drive owns linked document metadata and proposal document content.
- Missing or incomplete connector reads are coverage gaps, not clean negative findings.
- Hygiene remains Salesforce-only.

## Coverage proof

Source boundaries are enforced by bundle metadata and validators, not prompt wording.

- Every active `deal` / `pipeline` / `hygiene` bundle carries a coverage manifest. `plan.py` emits the expected source list for the selected profile, the gather step fills `source_reads`, and `analyze.py` fails before analysis if an expected source read is missing.
- Each `source_reads` entry records the connector source, final status (`ok`, `empty`, `timeout`, `error`, or `partial`), retries, queries, and source refs where available. Degraded statuses become coverage gaps; missing proof is a gather failure.
- Gmail coverage must prove company-domain search. The bundle records searched contact emails, contact-union emails, searched domains, contact domains, and either the newest matching company-domain thread id or `domain_thread_search_status=no_match`.
- Slack coverage must prove a Slack MCP read. The bundle records `slack_mcp_checked`, searched channel names, channel matches, and the Slack-source `deal_room.source_ref`.
- A missing Gmail/Slack proof becomes a coverage gap. It cannot become "no email thread," "email went quiet," "no Slack room," or "no Slack activity."
- `deal-read` validates these claims before presentation. A brief fails if it cites Salesforce as Slack evidence or makes absence claims without the required connector proof.
- Confidence is capped by computed inputs. `core/config/confidence-policy.json` owns the chosen ceiling rules, `analyze.py` and `rollup.py` emit `confidence.max_label`, and validators reject briefs that exceed it.

## Agent governance

This repo treats each slash-command surface as a scoped operator over opportunity evidence, not as an unrestricted assistant.

- Identity: the active agent surfaces are the local Claude commands installed from this checkout.
- Source access: Salesforce, Gmail, Calendar, Zoom, Slack, and Drive are evidence sources. Access should stay read-only unless a future write path is explicitly designed and permissioned.
- Current write path: `deal-read` may create a Gmail draft only after explicit user confirmation. It never sends email.
- No-write surface: `pipeline-read` makes no writes. Read, forecast, and hygiene are read-only outputs.
- Human approval: externally visible actions require an explicit user confirmation for the exact action. Prior approval does not carry over to a different action.
- Auditability: deal and pipeline briefs must carry computed-inputs evidence and pass the relevant validator before they are treated as final. Validators enforce coverage gaps and source-boundary claims.
- Confidence: briefs may sound less certain than the computed ceiling, but never more certain.
- Failure handling: missing or unauthorized connectors become source gaps. The agent should not infer risk from unavailable evidence.
- Model boundary: this repo uses deterministic flags and posture labels. It does not predict win probability or create local predictive weights.

## Scoring system

The repo does not predict win probability. It sorts observed evidence into deterministic flags.

```text
pipeline read / forecast scoring
├── red flags rank first
│   ├── overdue_close        # close date is in the past
│   ├── close_date_slipped   # close date has been pushed
│   ├── single_threaded      # one or fewer engaged contacts
│   ├── stalled_in_stage     # stage age is past the configured threshold
│   └── calendar_no_upcoming_late_stage
│                            # late-stage deal has no future customer meeting
├── amber flags rank second
│   ├── stale_activity       # Salesforce activity is stale
│   ├── email_data_stale     # email evidence lags latest known activity
│   ├── calendar_no_recent_meeting_after_stage_move
│   │                        # stage moved recently but no later customer meeting
│   └── calendar_next_meeting_no_buyer_attendees
│                            # next meeting has no visible buyer-side attendee
├── clean deals rank last
└── tie-breakers
    ├── more active flags first
    ├── larger amount first
    └── fewer days to close first
```

The first active red flag becomes the dominant risk. If there is no red flag, the first active amber flag becomes the dominant risk.

Calendar flags only count when Calendar coverage is available. If Calendar is not authorized, unavailable, or cannot match the deal, the repo records an evidence gap instead of creating risk.

```text
forecast labels
├── downgrade        # commit deal with red risk
├── inspect          # stale evidence, unknown category, missing amount, or unclear posture
├── possible_upside  # clean upside or pipeline deal
└── keep             # clean commit or upside deal
```

Forecast labels are posture labels only. They are not CRM writebacks and not probability scores.

```text
pipeline hygiene scoring
├── Salesforce-only data-quality view
├── dominant gap precedence
│   ├── no_contact_roles
│   ├── single_threaded
│   ├── no_champion
│   ├── missing_amount
│   ├── missing_next_step
│   ├── stale_activity
│   └── overdue_close
└── tie-breakers
    ├── more gaps first
    ├── larger amount first
    └── fewer days to close first
```

`/pipeline-hygiene` scores CRM record quality, not deal risk.

Do not add local win-probability modeling here. If that ever exists, it belongs in a separate pooled data product.

## Setup

For local setup, Claude command registration, and verification, see [SETUP.md](SETUP.md).

The old standalone GitHub repos are archived. Treat this repo as the active home.

## Repository layout

```text
opp-intel/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── SETUP.md
├── core/
├── deal-read/
├── pipeline-read/
└── scripts/
```

Start with `AGENTS.md` for repo-wide rules. Claude can start at `CLAUDE.md`, which is only a thin pointer back to `AGENTS.md`.

Use the surface docs for surface-specific behavior:

- `deal-read/README.md`
- `deal-read/AGENTS.md`
- `deal-read/SKILL.md`
- `pipeline-read/README.md`
- `pipeline-read/AGENTS.md`
- `pipeline-read/SKILL.md`

## Verify changes

Run the full local gate before changing shared core behavior:

```bash
scripts/test.sh
```

The gate runs shared core tests, the `deal-read` surface tests, and the `pipeline-read` surface tests.

## Working rules

- Preserve behavior first.
- Make small, testable changes.
- Freeze fixtures before changing shared mechanics.
- Keep source access read-only.
- Do not fold `deal-read` into `pipeline-read`.
- Do not introduce predictive weights.
- Do not make hygiene inspect anything outside Salesforce.
- Do not let `deal-read` create Gmail drafts without explicit confirmation.

The shared-core migration is complete through the planned Phase 6 extraction. Future changes should still follow the same rule: move one layer, prove parity, then continue.
