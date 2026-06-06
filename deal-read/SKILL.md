---
name: deal-read
description: Deal-risk coaching for a single sales opportunity. Synthesizes the running rep's own Salesforce opportunity data, Zoom call recordings/summaries, Gmail threads, mapped Slack deal-room evidence, and linked Google Drive proposal docs into a coaching brief that names where the deal is at risk and the specific next actions to de-risk it. Trigger on "/deal-read <deal>", "give me a read on <deal>", "where is <deal> at risk", "what should I do next on <deal>", or any request for a risk read or next-step coaching on a named deal. Per-rep self-serve: reads only the running user's connected accounts. Do NOT use for team rollups across reps, per-call scoring of an arbitrary recording with no deal, or a whole-pipeline view across deals (that's /pipeline-hygiene for CRM health, /pipeline-read for risk, /pipeline-forecast for the number).
---

# Deal Read

Coach one rep on one deal. Pull that rep's own Salesforce, Gmail, Google Calendar, Zoom, mapped Slack deal-room, and
linked Google Drive proposal-doc evidence for a named opportunity, run it through a deal-risk model,
and return the top risks with concrete next actions. Each action ties to evidence from a real call,
email, Salesforce field, Slack source, or proposal doc. Never writes to Salesforce, sends mail,
modifies recordings, posts to Slack, or edits Drive docs.

## Input

`/deal-read <opportunity name | account name>`. If no deal is named, ask which one. If the name matches
multiple opportunities, list the candidates (name, stage, amount, close date) and ask which.

**Two modes, same pipeline (steps 1–4 are identical):**
- Default (review): output the deal-risk coaching brief (§5).
- `--prep` (e.g. `/deal-read <deal> --prep`): you have a call coming up — output a pre-call plan instead
  of a risk review (§5-prep). Run the full gather + scoring, then convert the biggest Unknowns and
  At-risk dimensions into questions to ask on the next call.

## Connectors

Five connectors. All reads are read-only. The one write this skill can make is creating a Gmail
**draft** (never sending), and only on explicit user confirmation (see §6).

- **Salesforce** — `getObjectSchema`, `find`, `soqlQuery`, `getRelatedRecords`, `getUserInfo`
- **Google Calendar** — historical and upcoming meeting lookup
- **Zoom** — `search_meetings`, `get_meeting_assets`, `recordings_list`
- **Gmail** — `search_threads`, `get_thread`; `create_draft` (draft only, §6)
- **Slack** — mapped deal-room lookup first; auto can run bounded channel-name lookup, and
  internal=force adds bounded message-content lookup
  by account/opp name, or internal=off to skip
- **Google Drive** — proposal docs linked from the mapped Slack room or explicit deal context only

If a connector is not authorized, say so and proceed with the sources you have — note in the brief
which evidence is missing and how that limits confidence.

## Files (the deterministic core — do not recite or reinvent from memory)

This surface is thin. Shared mechanics live in `../core/`; the local `scripts/` files are compatibility
wrappers that delegate there. This SKILL.md owns orchestration, output shape, prep/review mode, and the
Gmail draft policy.

- **`scripts/plan.py`** — emits the exact Salesforce/Gmail/Calendar/Zoom queries to run for this deal. Field
  names come from `../core/config/sf-fields.json`, the email window from `../core/config/risk-model.json`. You execute
  what it prints (only you can call the connectors), but you never improvise SOQL.
- **`scripts/analyze.py`** — the single processing entrypoint. Feed it one bundle of the raw data you
  gathered; it runs `compute.py` + `callstats.py`, parses account history, and normalizes Slack/Drive
  internal evidence, returning every metric, flag, source gap, and the prior-loss summary. Do not
  stitch these yourself.
- **`../core/config/risk-model.json`** — chosen framework: scored dimensions, status enum, thresholds,
  discovery checklist. To change the model, edit this file.
- **`../core/config/sf-fields.json`** — chosen Salesforce field/query mapping. To retarget another org, edit this.
- **`scripts/compute.py` / `scripts/callstats.py` / `scripts/transcript_extract.py`** — deterministic
  metrics and transcript signal reduction, invoked by `scripts/analyze.py`. Don't call them directly.
- **`scripts/validate_brief.py`** — the output-contract gate. Pipe your drafted brief (review mode) into
  it before presenting: it confirms the `Computed inputs` footer is present and parseable and that
  Confidence isn't High on stale email data. A non-zero exit means fix the brief, don't ship it.

## Pipeline

### 1. Resolve the opportunity and gather Salesforce data

1. Run `python3 <skill-dir>/scripts/plan.py` with `{"deal_name":"<name>"}` on stdin. Execute the `salesforce.find`
   query it returns. Disambiguate if >1; the open (non-closed) one is usually the deal to coach.
2. Run `scripts/plan.py` again with full context now known:
   `{"opp_id","account_id","account_name","contact_emails":[...],"created_date","today"}`. It returns
   the exact queries — run each as written:
   - `salesforce.opportunity` → the opp record (correct field names, no `Amount` guessing).
   - `salesforce.contact_roles` → `getRelatedRecords`. Read the `read_fields` it lists, especially each
     role's `Role` picklist value (Champion / Economic Buyer / Influencer) and `IsPrimary`. Collect the
     role values into a `roles` list for the bundle — they ground the champion and economic_buyer
     dimensions deterministically. Still treat the role **count** as CRM hygiene only, NOT the real
     engagement count — reps under-log roles.
   - `salesforce.tasks` → activity cadence (counts, dates, gaps, last touch).
   - `salesforce.history` → `OpportunityHistory` for the stage-entered date and the CloseDate sequence
     (feeds stage velocity + slippage). If the org returns none, fine — `analyze.py` degrades.
   - `salesforce.prior_account_opps` → closed opps on the same account. High-value: a prior loss is
     coaching context, a prior win is a foothold. `analyze.py` summarizes these.
3. Note `getObjectSchema` is no longer required per-run — field names live in `../core/config/sf-fields.json`. Run it
   only to retarget a new org, then update that file.

### 2. Pull recent calls (Zoom)

`search_meetings` requires the user's timezone — assume the system timezone (macOS local) unless the
user states otherwise; if genuinely unknown, ask once.

1. Use the `zoom` params from `plan.py` for `search_meetings` (`include_zoom_my_notes: true`). Prefer
   `meeting_uuid` downstream.
2. For the most relevant 1–3 meetings, `get_meeting_assets` (pass the UUID) and save the returned
   asset JSON to a file. Do not paste or summarize raw transcript text into the chat context. Use the
   saved file path as `transcript_file` in `analyze.py`; it emits `call_execution` plus `call_extract`
   with capped structured transcript buckets.
3. Work from `meeting_summary` plus `call_extract` first. Only inspect transcript spans by source ref
   when you need to confirm a specific risk signal.

### 3. Pull the email thread (Gmail)

1. Run the `gmail.thread_search` query from `plan.py`. Fall back to the account domain if individual
   emails are sparse. Also run `gmail.sent_freshness` (`in:sent newer_than:Nd`) — `plan.py` always
   includes it because `search_threads` proved unreliable (it returns stale threads and silently drops
   recent messages, including ones sent today). Don't rely on a single OR-group query for recency.
2. `get_thread` (FULL_CONTENT) on the live threads. Read for substance — questions raised, stalls,
   redirects, internal-forwarding (new names). Build the email list (direction + date per message) that
   feeds `analyze.py`; it computes latency, unanswered count, and last-inbound deterministically.
3. **Freshness is computed, not eyeballed.** `analyze.py` sets `deal_metrics.flags.email_data_stale`
   when the activity anchor (SF `LastActivityDate` or newest Zoom call, fed as `latest_call_date`) is
   more than `freshness_gap_days` newer than the newest email found. When it's true, your email view is
   lagging reality: say so, lower confidence, and do NOT assert a follow-up is owed or that the deal
   went quiet. Ask the rep what they last sent first.

### 3.5. Internal evidence (Slack + Google Drive)

After Gmail, run `plan.py` again with the full deal context. Execute the `internal_evidence.slack`
instructions it returns when a mapped deal room exists. If no room is mapped, `plan.py` reports the
source gap; pass `"internal": "force"` only when you intentionally want bounded fallback search. In force
mode, execute the `steps` array `plan.py` emits **in order**: step 1 calls `slack_search_channels`
(include `private_channel`) with the account/opp name terms — if a named channel matches, read from
it (`coverage=found`) and stop; step 2 only runs if no named channel was found, calling
`slack_search_public_and_private` for message signals (`coverage=checked_no_match`).

Read linked Google Drive proposal docs only when they are linked from the mapped room or explicit deal
context. Add Slack findings, linked-doc coverage, and proposal-doc findings to the `analyze.py` bundle
as `internal_evidence`. Use this shape:

```json
{
  "mode": "auto|force",
  "deal_room": {"source": "slack", "coverage": "mapped|deal_room_missing|checked_no_match|unavailable", "source_ref": "..."},
  "linked_docs": [{"source": "google_drive", "title": "...", "coverage": "read|unavailable|skipped", "source_ref": "..."}],
  "signals": [{"type": "...", "summary": "...", "source_ref": "...", "confidence": "high|medium|low"}],
  "source_gaps": []
}
```

`analyze.py` keeps only source-backed signals and turns missing rooms or unavailable linked docs into
explicit `internal_evidence.source_gaps` in the computed footer. Slack and Drive evidence can affect
confidence, source gaps, risk notes, and next-move wording. It cannot override Salesforce-owned fields
(amount, stage, close date, owner), which stay deterministic. Pass `"internal": "off"` to skip Slack
and Drive entirely.

### 4. Score the deal-risk model

**First, run `analyze.py` once.** Assemble the bundle and pipe it in:
`python3 <skill-dir>/scripts/analyze.py < bundle.json`. The bundle is:
`{"rep_name", "compute_input": {...}, "transcript_file": "<path or omit>", "prior_opps": [...],
"calendar_evidence": {...}, "internal_evidence": {...}}`.
For `compute_input`, do NOT pre-count `contacts_engaged` yourself. Pass `observed_participants` (the list
of prospect-side people you saw: Zoom attendees and email senders/recipients on the prospect's domain)
and `logged_contact_roles` (the count from `getRelatedRecords`). `compute.py` dedups the list and applies
the role count as a floor, so the union and the count are deterministic, not eyeballed. Also include
`stage_entered_date`, `close_date_history`, and `latest_call_date` when available. For MEDDPICC grounding
pass `roles` (the `OpportunityContactRole.Role` values you saw), `opportunity.economic_buyer_named` (true
when `Decision_Maker__c` is populated or an Economic Buyer role exists), and `opportunity.legal_status`
(the `Legal_Status__c` value). `compute.py` turns these into `flags.economic_buyer_named`,
`flags.champion_identified`, and `flags.paper_not_started`. Everything below reads `analyze.py`'s output:
`deal_metrics`, `call_execution`, `call_extract` when a transcript file was provided, `account_history`,
`calendar_evidence`, and `internal_evidence`.

Score the dimensions defined in `../core/config/risk-model.json` — read them from the file, do not work from a
remembered list. For each dimension, compare what you observed against its `healthy` and `at_risk`
signals, then assign one of the statuses in the model's `statuses` enum (currently On track / At risk /
Blocked / Unknown) with one line of evidence, citing the source: call date, email date, or SF field.
"Unknown" is a finding, not a gap to hide.

The `momentum` and `paper_timeline` dimensions are grounded by `deal_metrics`: use `flags.stale_activity`,
`flags.single_threaded`, `flags.overdue_close`, `flags.close_date_slipped`, `flags.stalled_in_stage`,
`flags.paper_not_started`, `flags.calendar_no_upcoming_late_stage`,
`flags.calendar_no_recent_meeting_after_stage_move`, `flags.calendar_next_meeting_no_buyer_attendees`,
`days_since_last_activity` vs. `days_to_close`, `days_in_current_stage`, the
`close_date_slippage` block (a deal pushed 2–3× is a much louder timeline risk than the current date
alone), and the `email` latency block rather than eyeballing it. `flags.paper_not_started` is a status
read of `Legal_Status__c`; weigh it against `days_to_close` (paper not started with a near close date is
the loud signal). `flags.single_threaded` reflects the
`contacts_engaged` that `compute.py` derived from the `observed_participants` you fed the bundle, so it
won't false-positive on under-logged contact roles. If observed participants exceed the logged contact
roles, surface that as a CRM-hygiene note in the brief (which roles to add), separate from the threading
score.

Calendar flags only count when Calendar coverage is available. If Calendar is unavailable or cannot match
the deal, name the source gap and lower confidence as appropriate; do not invent meeting-cadence risk.

Score `economic_buyer` against `flags.economic_buyer_named` and `champion_multithreading` against
`flags.champion_identified` — both read the `OpportunityContactRole.Role` picklist, so they don't depend
on title-guessing. The MEDDPICC justification fields (`Pain_Need__c`, the decision-process/criteria
fields, `Competition_Justification__c`) and the event fields (`Critical_Event__c`, `Last_Meaningful_Event__c`)
are rep-entered corroboration: cite them when populated, treat a blank as a hygiene gap to name, and never
let them override the call/email evidence or the deterministic flags.

Rank risks by severity of current evidence, not by assumed correlation with outcome. There are no
predictive weights to rank by, and there is no plan to add them here: grading dimensions against
outcomes is a central data product, never something this local skill does. The `_comment` in
`../core/config/risk-model.json` is canonical on this.

**Call execution (review mode).** Combine the `call_execution` block from `analyze.py` (talk ratio,
questions, monologue, `flags.talk_ratio_high`) with `call_extract` and the meeting summary. Go through
`../core/config/risk-model.json` `call_execution.discovery_checklist` and mark which topics the rep actually covered.
The coachable pattern is a high talk ratio or long monologues paired with missed checklist items. Coverage is a
model judgment from the summary plus capped transcript spans; the ratio and counts are not. `account_history`
from `analyze.py` fills the brief's Account history line.

### 5. Output the coaching brief

Conversational, direct, second person ("you"), coaching tone — not a report dump. Reference the
writing-style skill for voice. Structure:

```
Deal: <Name> — <Stage>, Added ARR <Added_ARR__c>, closes <date> (<N> days out, <age> old)

Confidence: <High / Medium / Low> — <one clause on what it rests on, e.g. "Low: one call, no email
thread, and email data flagged stale.">

Read: <2–3 sentences. Honest momentum call. Is this deal where the stage says it is?>

Account history: <only if prior closed deals exist on this account — e.g. "You lost a near-identical
deal here in May 2025; recorded reason was X. Don't repeat it." Omit this line if there's no history.>

Top risks
1. <Risk> — <evidence, cited>. → Do this: <specific action with a who/when>.
2. ...
3. ...

What's going well: <1–2 lines, evidence-backed, so it's not all red>

How you ran the call: <only when a transcript was scored — talk ratio + question count from the
call_execution block, then the discovery topics you missed, e.g. "You talked 68% and asked 4 questions;
never surfaced budget or who signs." Omit if no transcript.>

Your next move this week: <the single highest-leverage action>

Follow-up email: <ONLY when warranted (see §6) — one line offering to draft it, e.g. "Your next move
is an email — want me to draft the reply to John's 5/28 message? I'll put it in your Drafts to review."
Omit this line entirely when an email isn't the right move.>

Computed inputs:
```json
<paste analyze.py's verbatim JSON output here — the whole object. This is the audit trail: if it's
missing or empty, the deterministic steps were skipped and the brief above is untrustworthy. You feed
this to validate_brief.py, which renders it down to a one-line pass stamp — the reader never sees the
raw object (see the validate-before-presenting rule).>
```
```

Rules:
- Every risk cites real evidence (call date, email date, SF field). No generic sales advice.
- Actions are specific and assignable: "Email <name> to get the security review scheduled before
  <date>", not "build more urgency."
- Lead with the action, then the rationale. Keep it tight — a rep should read it in under two minutes.
- **Calibrate confidence to evidence, and lead with it.** The `Confidence` line is required. Rate Low
  when you have a single call, no live email thread, or `flags.email_data_stale` is true; Medium on
  partial coverage; High only with corroborating calls + emails + SF all current. Do not write
  authoritative-sounding risks on thin or stale data — name what you couldn't see instead.
- **The Computed inputs footer is required in the draft** (review mode). Paste `analyze.py`'s verbatim
  output into the `Computed inputs` ```json fence. It's the audit trail proving the deterministic steps
  ran. Never hand-write or summarize it; if you didn't run `analyze.py`, say so rather than fabricating
  the block. The reader won't see this raw object — the gate collapses it (next rule) — but it must be
  real and parseable for the gate to pass.
- **Validate, then present what the gate emits** (review mode). Pipe the finished brief (with the full
  JSON footer) into `python3 <skill-dir>/scripts/validate_brief.py`. It enforces the two rules above in
  code: footer present and parseable, no High confidence on stale email data. On failure it exits
  non-zero with reasons — fix them and re-run; never present a brief that fails the gate. On success it
  writes the brief back to stdout with the JSON footer collapsed to a one-line verification stamp inside
  a collapsible `Computed inputs` block. **Present that stdout verbatim** — do not paste the raw JSON
  yourself. The reader sees only the pass stamp; the code, not you, owns the redaction.

### 5-prep. Output the pre-call plan (--prep mode)

Same gather + scoring (§1–4), different output. The goal is a tight plan the rep reads right before the
call. Lead with the Unknowns — the dimensions you couldn't confirm are exactly what the next call must
close. Structure:

```
Prep: <Name> — <Stage>, closes <date>. Call goal: <one line — the single thing this call must achieve>

Where you're blind (close these): <the At-risk / Unknown dimensions, one line each, cited>

Ask these 3:
1. <Question> — closes <which Unknown/risk>. Listen for: <what a good vs bad answer sounds like>.
2. ...
3. ...

Must-get before you hang up: <the one commitment or fact you cannot leave without>

Landmines: <1–2 things to avoid, from account history or prior calls — e.g. "they balked at price last time; don't lead with the number">
```

Rules: the 3 questions target the highest-severity Unknowns first, are open-ended (not yes/no), and
each ties to a specific dimension. Pull landmines from account history (prior losses) and recent call
objections. Keep it to one screen — it's read in the 60 seconds before dialing.

### 6. Draft the follow-up email (optional, on confirmation)

The skill can draft the follow-up, but never sends it. The draft lands in the rep's Gmail Drafts for them
to review and send.

**When it's warranted** — offer a draft only when an email is genuinely the highest-leverage next
move:
- The next move *is* an email: send the recap, the proposal, the answer to a question, the promised
  doc, or a scheduling reply.
- An inbound from the prospect is waiting on a reply (last message in the thread is theirs).
- A commitment the rep owes is best delivered in writing.

**When it's NOT** — stay silent, do not manufacture an email:
- The next move is a call or meeting, not an email (e.g. the prospect asked the rep to *call* them).
- The deal is stalled and another email would look needy rather than move it.
- There's nothing concrete to say yet (waiting on the prospect, or on internal scoping).

**Precondition — gated on computed flags, not judgment.** Email/activity connectors lag (see §3), so
the draft offer is governed by `compute.py` flags:
- If `flags.recent_rep_outbound` is true, the rep emailed within `recent_outbound_days` — do NOT offer a
  draft; another one would likely duplicate it.
- If `flags.email_data_stale` is true, you cannot trust that the commitment is still open — only offer
  defensively and confirm first ("if you haven't already sent the proposal, want me to draft it?").
- Otherwise, offer normally.

If the rep says it's already done, drop it. Never draft a follow-up that duplicates something recently
sent.

**Workflow:**
1. In the brief, *offer* — don't draft unprompted.
2. If the rep accepts, write the draft and **show the full text in chat first**. Keep it short, specific
   to the real next step, and in the rep's voice — defer to the writing-style skill. Reply on the
   existing thread: pass the most recent prospect message's id as `replyToMessageId` (from step 3's
   `get_thread`), and use plain email addresses only (the tool rejects "Name <email>").
3. Only after explicit confirmation, call `create_draft`. Confirm it's in Drafts and tell the rep to
   review and send — you will not send it.

## Save (optional)

Default to chat only. If the user asks to save it, write to the current project's `deliverables/`
folder and return a `computer://` link. This skill does not write to Open Brain or deal-management —
it is self-contained and portable across reps.

## Scope guardrails

- One deal per run. For "coach my whole pipeline," redirect to `/pipeline-read` (risk), `/pipeline-forecast` (the number), or `/pipeline-hygiene` (CRM health).
- Per-rep only: operate on the running user's own connected accounts. Do not attempt to access another
  rep's mailbox or recordings.
- Coaching, not auto-pilot: propose actions. The only write allowed is creating a Gmail **draft** on
  explicit confirmation (§6). Never send email, never edit Salesforce, never take outbound action on
  the rep's behalf — the rep reviews and sends every draft themselves.
