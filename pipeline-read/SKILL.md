---
name: pipeline-read
description: Shared engine for /pipeline-read, /pipeline-forecast, and /pipeline-hygiene. Resolves the running rep's open opportunities closing in the current fiscal quarter by default and rolls them into one of three views - read (riskiest deals first, each with its dominant risk and next move), forecast (the number, category rollup, keep/downgrade labels), or hygiene (a cheap Salesforce-only CRM data-quality scan: contacts, champion, next-step, amount, freshness) - all with a computed-inputs audit footer. Standard read/forecast mode is fast and bulk-first by default; --deep-search opts into richer per-deal connector fan-out. Per-rep, live connectors, read-only, no writes. Do NOT use for a deep read of one named deal (that's deal-read) or for another rep's pipeline.
---

# Pipeline Read

Coach one rep across their whole forecast. Standard read/forecast mode is **fast** by default: resolve
the portfolio once, run bulk Salesforce evidence queries, reduce those rows into compact per-deal
`analyze.py` bundles, and escalate only material/risky/blind deals to bounded Gmail/Calendar/Zoom or
internal evidence. `--deep-search` opts into richer per-deal connector fan-out when the user accepts
the time and token cost. Read-only across all sources. Makes no writes at all, not even a draft.

## Input

This file is the shared **engine**: scope resolution, fast/deep-search gather, the roll-up, and all
three output views. The view mode is chosen by the **command**, not inferred:

- **`/pipeline-read`** → run in read mode, present the ranked forecast-risk brief (§5).
- **`/pipeline-forecast`** → run in forecast mode, present the forecast-read view (§5-forecast).
- **`/pipeline-hygiene`** → run in hygiene mode, present the CRM data-quality view (§5-hygiene).

The three commands are thin frontends in `commands/`; all read this engine and differ in the mode
they set on the roll-up bundle and the section they present. No deal name: this skill always operates on
the rep's whole in-scope pipeline. The default scope is **open opportunities the running rep owns whose
CloseDate falls inside JSQ's current fiscal quarter**. JSQ's fiscal year starts Feb 1, so quarters run
Feb-Apr, May-Jul, Aug-Oct, and Nov-Jan. To run the next fiscal quarter, pass `--next-quarter`,
`--window next_quarter`, or say next quarter. Other ad hoc windows like `--window 30d` remain available,
but do not use them unless the user asks.

**Hygiene asks a different question.** Read and forecast both score deal *risk* off live evidence
(email, calls, internal rooms). Hygiene asks "is the Salesforce *record* clean?" — contacts logged, a
champion role set, `NextStep` and amount filled, activity recent. A deal can be commercially healthy
with filthy CRM data, or have clean data on a dying deal, so hygiene has its own flags, its own ranking,
and a deliberately **cheaper, Salesforce-only gather** (no Gmail, Calendar, Zoom, Slack, or Drive; see §2-3-hygiene).
Like the old `pipeline-health`, it proposes **no fixes or next moves** — that is the clean line versus
read.

Forecast mode (`/pipeline-forecast`) also accepts:
- `--next-quarter`
- `--window current_quarter|next_quarter|30d`
- `--posture conservative|defend-commit|identify-upside`
- `--amount-basis acv`
- `--compare <prior-computed-inputs.json>`
- `--deep-search`
- `--internal auto|off|force`
- `--internal-window 30d`

**Three views, one pipeline:**
- Read (steps 1–4 then §5): the ranked forecast-risk brief.
- Forecast (steps 1–4 then §5-forecast): same gather + roll-up, a forecast-read view. Lead with
  forecast posture, category rollup, recommendation labels, movement if a prior computed-inputs JSON is
  supplied, internal evidence coverage, and named evidence gaps.
- Hygiene (step 1, then §2-3-hygiene, then §4 and §5-hygiene): the cheap Salesforce-only CRM
  data-quality scan. It does **not** run fast/deep-search evidence gather.

The roll-up bundle's `mode` field is set explicitly by the command (`read`, `forecast`, or
`hygiene`). `rollup.py` obeys that field; it does **not** infer the view from the presence of
`amount_basis` or `posture`.

## Connectors

All reads are read-only. **`pipeline-read` makes no writes**. Drafting a follow-up is a per-deal action
that lives in `deal-read`.

- **Salesforce** — `getUserInfo`, `getObjectSchema`, `find`, `soqlQuery`, `getRelatedRecords`
- **Google Calendar** — historical and upcoming meeting lookup
- **Zoom** — `search_meetings`, `get_meeting_assets`, `recordings_list`
- **Gmail** — `search_threads`, `get_thread`
- **Slack** — mapped deal-room reads first; `internal=auto` may run bounded channel-name lookup when
  no mapping exists; `internal=force` also permits bounded message-content lookup
- **Google Drive** — proposal docs linked from the mapped Slack room or explicit deal context only

**Hygiene mode is Salesforce-only.** It reads the portfolio list plus one batched
`OpportunityContactRole` query; it does not touch Gmail, Calendar, Zoom, Slack, or Drive. The other connectors
above apply to read and forecast only.

If a connector is not authorized, say so and proceed with the sources you have. Note in the brief
which evidence is missing and how that limits confidence across the affected deals.

## Files (the deterministic core — do not recite or reinvent from memory)

This surface is thin. Shared mechanics live in `../core/`; the local `scripts/` files are compatibility
wrappers that delegate there. This SKILL.md owns command routing, mode choice, portfolio output shape,
and the no-write policy. You invoke five wrapper scripts directly: `scripts/plan.py` (what to query,
both phases), `scripts/pipeline_bulk_reduce.py` (fast-mode bulk Salesforce grouping),
`scripts/pipeline_reduce.py` (deep-search per-deal evidence reduction), `scripts/analyze.py`
(per-deal processing, once per deal), and `scripts/rollup.py` (the pipeline aggregation, once over all
deals).

- **`scripts/plan.py`** — two phases. With `{"mode":"pipeline", ...}` it emits the portfolio-list
  query, `run_depth`, `execution_strategy`, forecast fields, amount basis, category field, and
  internal-evidence plan. Default `run_depth` is `fast` and default `execution_strategy` is
  `bulk_first`; pass `"run_depth":"deep_search"` for deep search. Without `mode`, it
  emits the per-deal Salesforce/Gmail/Calendar/Zoom queries plus mapped Slack/linked-doc instructions when
  enabled. You execute what it prints; you never improvise SOQL or broad Slack/Drive search. In a
  `{"mode":"pipeline","hygiene":true,...}` plan, forecast and internal evidence are forced off and
  `per_deal_connectors` is Salesforce-only; pass `"opp_ids":[...]` after the portfolio list to get the
  batched `contact_roles_bulk` query and the `champion_roles` list.
- **`scripts/pipeline_bulk_reduce.py`** — the standard fast-mode reducer. Feed it portfolio rows plus
  bulk Salesforce result sets (`contact_roles`, `account_contacts`, `tasks`, `history`); it emits
  compact per-deal `analyze.py` bundles and marks deferred primary sources as coverage gaps so missing
  Gmail/Calendar/Zoom cannot become false silence.
- **`scripts/pipeline_reduce.py`** — the per-deal evidence boundary. Feed it saved connector payloads
  for one deal; it emits a compact `analyze.py` bundle plus evidence metadata. `source_ref` is an audit
  trail, not routine roll-up context.
- **`scripts/analyze.py`** — the per-deal processing entrypoint. Feed it the reduced bundle from
  `pipeline_reduce.py`; it runs `compute.py` + `callstats.py` and parses account history. Run it once
  per in-scope deal.
- **`scripts/rollup.py`** — the pipeline aggregator. Feed it every per-deal `analyze.py` output; it
  ranks deals by severity of current evidence, computes portfolio and forecast aggregates, emits
  deterministic recommendation labels, and compares against a prior Computed inputs artifact when
  supplied. Do not rank, label, compare, or sum in your head.
- **`../core/config/risk-model.json`** — chosen framework plus the `pipeline`, `forecast`, and
  `internal_evidence` blocks. To change posture options, recommendation labels, close-window controls,
  or internal-evidence caps, edit this file.
- **`../core/config/sf-fields.json`** — chosen Salesforce field/query mapping, including `pipeline_scope`,
  amount basis, forecast category convention, and internal source mapping fields. To retarget another
  org, edit this.
- **`scripts/compute.py` / `scripts/callstats.py` / `scripts/transcript_extract.py`** — deterministic
  metrics and transcript signal reduction, invoked by `analyze.py`. Don't call them directly.
- **`scripts/validate_brief.py`** — the output-contract gate. Pipe your drafted brief into it before
  presenting: it confirms the `Computed inputs` footer is `rollup.py` output, the schema is present,
  stale or missing evidence limits confidence, and forecast-mode sections are present. A non-zero exit
  means fix the brief, don't ship it.

## Pipeline

### 1. Resolve scope and list the in-scope opps

1. Run `python3 <skill-dir>/scripts/plan.py` with `{"mode":"pipeline","today":"<YYYY-MM-DD>"}`. This
   resolves JSQ's current fiscal quarter from the Feb 1 fiscal-year start. Add `"next_quarter":true` or
   `"window":"next_quarter"` when the user asks for next quarter, or `"window":"30d"`, `"forecast":true`,
   `"posture":"conservative"`, `"amount_basis":"acv"`, `"internal":"auto"`,
   `"run_depth":"deep_search"`, or similar when the user asked for them. On the first pass it returns a
   `whoami` step: call Salesforce `getUserInfo` to get the running rep's Id.
2. Run `plan.py` again with `{"mode":"pipeline","today":...,"window":...,"owner_id":"<your Id>",...}`.
   It returns the `salesforce.pipeline` SOQL, the resolved `window` (`close_on_or_after` and
   `close_on_or_before` for quarter windows), the `run_depth`, the `execution_strategy`, the
   `large_run_threshold`, and, in forecast mode, the exact posture, amount basis, forecast category
   field, and internal-evidence mode. Run the SOQL as
   written via `soqlQuery`.
3. **Large-run guardrail.** Count the returned opps. In fast mode, `per_deal_connectors` is
   Salesforce-only and the next step is a small number of bulk SOQL queries, so the threshold prompt is
   informational. In deep search, if the count exceeds `large_run_threshold`, list the opps (name,
   stage, ACV, close date) and confirm before gathering because every in-scope deal fans out to the
   connectors in `per_deal_connectors`.

### 2-3-fast. Gather and analyze (standard fast mode)

Fast mode is the default for read and forecast.

1. After the portfolio list, run `plan.py` again with
   `{"mode":"pipeline","today":...,"opp_ids":[...],"account_ids":[...]}`. It returns bulk Salesforce
   queries for contact roles, account contacts, tasks, and opportunity history. Run those SOQL queries
   as written.
2. Feed the portfolio rows plus the bulk Salesforce results to
   `python3 <skill-dir>/scripts/pipeline_bulk_reduce.py`. It emits one compact `analyze.py` bundle per
   deal. Deferred Gmail/Calendar/Zoom are marked as coverage gaps; do not convert those gaps into
   "went quiet" or "no meeting" findings.
3. Run `python3 <skill-dir>/scripts/analyze.py < analyze-bundle.json` once per deal. Assemble the
   roll-up bundle from those outputs and proceed to §4.
4. Escalate only when the planner's `escalation_policy` or `rollup.py` confidence gate says extra
   evidence can change confidence or action: material amount, red/amber risk, `email_data_stale`,
   `activity_coverage_gap`, or a primary connector degraded gap. For those deals only, run the bounded
   per-deal plan below, reduce with `pipeline_reduce.py`, re-run `analyze.py`, and replace that deal's
   fast result before the final roll-up. If the gap remains unresolved, keep the confidence block and
   say to reconcile before trusting the read.

### 2-3-deep-search. Gather and analyze each deal (explicit deep search)

Only use this path when `run_depth` is `deep_search` / `--deep-search`.

For **each** in-scope opp, run the bounded per-deal pipeline:

1. Per-deal queries: run `plan.py` (no `mode`) with that deal's context
   `{"opp_id","account_id","account_name","contact_emails":[...],"created_date","today","forecast":true,
   "internal":"auto|off|force","Slack_Channel__c","Deal_Room_URL__c"}` as applicable. Execute the
   returned Salesforce (`opportunity`, `contact_roles`, `account_contacts`, `tasks`, `history`,
   `prior_account_opps`), Gmail (`sent_freshness` + `thread_search`), Calendar (`calendar`), Zoom (`search_meetings`), and
   bounded internal-evidence instructions.

   **Contact union before Gmail search.** After running `contact_roles` and `account_contacts`, union
   all non-null Email values from both result sets. Use the full union as the email list for
   `thread_search` — do not rely solely on whatever `contact_emails` was passed in. This catches
   contacts logged on the account but not yet added as opp contact roles.
   - `internal=auto`: use mapped Slack deal rooms from the configured Salesforce mapping fields first.
     If no room is mapped, execute the emitted `slack_search_channels` step against account/deal terms.
     If a named channel matches, read up to `max_messages` and set `coverage=found`; if none matches,
     set `coverage=deal_room_missing`. Do not run Slack message-content search in auto.
   - `internal=off`: emit and gather no Slack or linked-doc evidence.
   - `internal=force`: execute the `steps` array `plan.py` emits — **in order, no skipping**:
     **Step 1** — call `slack_search_channels` with each term, including `private_channel`. If any
     channel whose name matches a term is found, read up to `max_messages` from it and set
     `coverage=found`; do **not** run step 2. **Step 2** — only if step 1 found no named channel: call
     `slack_search_public_and_private` with the terms to surface signals in existing channels; set
     `coverage=checked_no_match`. Keep message window and doc count within the plan output.
   - Linked Google Drive proposal docs are read only when linked from the mapped room or explicit deal
     context. Do not broad-search Drive.
2. **Read full email threads; keep Zoom at metadata only.** Every structural flag (slippage, stall,
   threading) is computable from SF fields and Zoom attendee lists without reading bodies. For email,
   read full thread bodies via `get_thread` — this catches active conversations that don't appear in SF
   task logs. For Zoom, use `meeting_summary` and the attendee list only (never `get_meeting_assets` /
   transcript bodies). Do **not** read Zoom transcripts to produce the read; that belongs in
   `/deal-read`.

   **The snippet trap — derive email freshness from `get_thread`, never from the search snippet
   (this is the rule `plan.py` emits as `gmail._freshness_rule`).** `search_threads` returns a thread
   when *any* of its messages matches, but the snippet it shows is frequently the *oldest* message in
   that thread. Firms reuse one subject line (e.g. "<Company> - Next Steps") for the entire relationship,
   so a deal's newest inbound can be the last message of a thread whose snippet shows month-old mail.
   Expand only the capped set from `gmail.max_threads` in the plan output (3 for pipeline reads). If
   result metadata exposes latest thread dates, use the newest capped set; otherwise use the first
   `max_threads` returned by the connector. For **every** thread in that capped set, call `get_thread`
   and read its full message list; compute the deal's `newest_email`, `last_inbound`, and
   `last_outbound` from the **max message date across the expanded threads**, not from the snippet.
   Never discard a thread in the capped set because its visible snippet predates the window — it was
   returned because it holds an in-window message; expand it. Do not expand beyond `max_threads`; for
   deeper email history, hand the deal to `/deal-read`. Asserting `email_data_stale` (or "went quiet")
   off a stale snippet date, while a fresh reply sits deeper in the same thread, is the exact regression
   this rule prevents.
3. Save raw connector payloads to per-deal files and run
   `python3 <skill-dir>/scripts/pipeline_reduce.py < gather.json`. The reducer accepts saved
   `email_threads_file`, `calendar_evidence_file`, `zoom_meetings_file`, and `internal_evidence_file`
   paths, plus `compute_input`, `prior_opps`, `connector_status`, `internal_domains`, and optional
   `prospect_domains`. It emits the compact bundle for `analyze.py`; do not paste raw email bodies,
   Slack messages, or meeting payloads into the orchestration context.
4. Run `python3 <skill-dir>/scripts/analyze.py < reduced-bundle.json` once per deal. The reduced
   `compute_input` contains the email list (direction + date), `observed_participants`, and
   `latest_call_date` when available, so `analyze.py` computes freshness and latency deterministically.
   When `flags.email_data_stale` is true for a deal, that deal's email view is lagging: say so and lower
   its confidence rather than asserting it went quiet.
5. Whenever internal evidence is on (the default in every mode unless `--internal off`), add
   `internal_evidence` to the per-deal `analyze.py` bundle when Slack or linked
   proposal-doc evidence was gathered. Preserve source refs. Slack/Drive evidence can affect confidence,
   source gaps, risk notes, internal owner, and next-move wording. It cannot change Salesforce-owned
   truth: amount, stage, close date, owner, or forecast category.

**Per-deal isolation contract (portable — every agent satisfies this, however it executes the loop).**
The per-deal work is a self-contained unit: gather that one deal's metadata, reduce it, run `analyze.py`
on the reduced bundle, and **emit only a compact result** — the deal's `analyze.py` JSON output plus
`pipeline_reduce.py`'s `evidence_summary` metadata (e.g. latest call date, last inbound/outbound email
date, and source refs). The
raw connector payloads (transcripts, thread bodies, full task lists) stay inside the per-deal step and
**must not flow into the roll-up context**. The orchestrating step collects these compact results and
feeds them to `rollup.py` once (§4); it never holds raw bodies. This keeps a full run's context to N
small summaries instead of N piles of raw data, and it is the same shape whether one agent loops the
deals inline or a harness fans them out — the deterministic core (`analyze.py` per deal, `rollup.py`
once) is identical either way.

**Connector-status contract (a failed connector is a coverage gap, never a finding).** Each per-deal
gather must distinguish "this source ran and found nothing" from "this source did not run." Three
requirements bind every per-deal subagent:
1. **Retry transient failures.** When a connector (Salesforce, Gmail, Calendar, Zoom) times out or
   errors, retry it up to **2 times** before giving up. Only mark it degraded after the retries fail.
2. **Report `connector_status` in the returned bundle.** Add a `connector_status` object to the
   per-deal `compute_input` with one entry per source — `email`, `zoom`, `calendar`, `salesforce` —
   set to `"ok"` (ran, returned data), `"empty"` (ran cleanly, genuinely found nothing), or
   `"timeout"`/`"error"`/`"partial"` (degraded after retries). Absent or unrecognized is treated as not
   degraded. `compute.py` reads this and appends `<source>_connector_degraded` to `coverage_gaps`, which
   carries confidence/blindness downstream and never enters ranking.
3. **Do not assert absence-based claims from a degraded connector.** A single-thread call, a "no reply"
   or "went quiet" read, or any negative finding may only stand when the source it relies on ran
   cleanly (`ok` or `empty`). If the connector that would witness the finding was degraded, it becomes a
   coverage gap, not a finding. `compute.py` already enforces this for email — when email is degraded it
   nulls the inbound and unanswered counts, refuses to assert email staleness, and drops
   `single_threaded` unless the Salesforce-sourced `logged_contact_roles` independently supports it — so
   report the status honestly and let the engine neutralize. In the brief, name the degraded source
   under "Where you're blind" and lower confidence; never present its silence as the prospect going
   quiet.

> **Claude Code deep-search execution (the Claude-Code-specific way to satisfy the contract above).** Run each in-
> scope deal as its own subagent via the `Agent` tool only in deep search — launch them concurrently (one
> message, multiple `Agent` calls) so the deals gather in parallel and each deal's raw payload lands in
> that subagent's throwaway context, not the orchestrator's. Pass `model: "haiku"` to each `Agent` call.
> Give each subagent a **narrow** prompt: the deal-context dict, "follow SKILL.md §2-3-deep-search steps 1-4,
> metadata only," and the return contract — "reply
> with **only** this deal's `analyze.py` JSON output plus `pipeline_reduce.py`'s `evidence_summary`; do
> not include quotes, raw transcripts, or email bodies." The orchestrator collects the compact replies and runs `rollup.py` once
> over them (§4). This is execution mechanism, not policy: the contract above is what binds, and a raw-
> API harness or another agent that loops inline is equally correct as long as raw bodies never reach the
> roll-up.

### 2-3-hygiene. Gather (Salesforce-only, no per-deal loop)

**Hygiene mode skips fast/deep-search gather entirely.** Do not fan out subagents, do not read Zoom or Gmail. The whole
scan is the §1 portfolio list plus one batched contact-roles query:

1. After the §1 portfolio list, run `plan.py` once more with
   `{"mode":"pipeline","hygiene":true,"opp_ids":[<every in-scope Id>]}`. It returns
   `salesforce.contact_roles_bulk` (one SOQL over all the opps) and `champion_roles` (the role names
   that count as a champion). Run that SOQL via `soqlQuery`.
2. Group the contact-role rows by `OpportunityId`. For each opp compute, **deterministically, no
   judgement**: `logged_contact_roles` = number of its role rows; `champion_contact_roles` = number of
   those rows whose `Role` matches `champion_roles` (case-insensitive). The opp-level inputs —
   `NextStep`, the amount field, `CloseDate`, `LastActivityDate` — already came back on the §1 portfolio
   row; do not re-query them.
3. For each opp, run `python3 <skill-dir>/scripts/analyze.py < bundle.json` with a light hygiene bundle
   (no transcript, no emails, no internal evidence):
   ```json
   {"compute_input": {"today": "<today>", "hygiene": true,
     "opportunity": {"close_date": "<CloseDate>", "last_activity_date": "<LastActivityDate>"},
     "logged_contact_roles": <N>, "champion_contact_roles": <M>, "next_step": "<NextStep or empty>"}}
   ```
   compute.py emits the hygiene flags (`no_contact_roles`, `no_champion`, `missing_next_step`,
   `single_threaded`, `stale_activity` at the looser hygiene threshold, `overdue_close`). `rollup.py`
   adds `missing_amount` itself, since it owns the amount basis.
4. Go to §4 with `"mode":"hygiene"`, then present §5-hygiene. No subagents, no `--compare`, no internal
   evidence.

### 4. Roll the pipeline up

Assemble the roll-up bundle and run it once:
`python3 <skill-dir>/scripts/rollup.py < rollup_bundle.json`. The bundle is:
```json
{
  "rep_name": "<rep>",
  "mode": "read|forecast|hygiene",
  "posture": "conservative|defend_commit|identify_upside",
  "amount_basis": "acv",
  "internal": "auto|off|force",
  "window": { ...the window block plan.py returned... },
  "prior_rollup": { ...prior Computed inputs JSON... },
  "deals": [
    {
      "opportunity_id",
      "name",
      "stage",
      "Added_ARR__c",
      "forecast_category",
      "close_date",
      "internal_evidence",
      "analyze_output": <that deal's analyze.py output>
    },
    ...
  ]
}
```
The `name`, `stage`, `Added_ARR__c`, and `close_date` come straight from the §1 portfolio list the orchestrator
already holds — the per-deal step only owes you `analyze_output` plus `evidence_summary` metadata, so a
subagent need not echo the deal facts back. For ARR, pass only `Added_ARR__c`; do not pass or derive from
`Calculated_ACV__c`, `Amount__c`, generic `amount`, or generic `acv`. For forecast mode, also pass the forecast
category from the same Salesforce portfolio row. If the user supplied `--compare`, load that file as
JSON and pass the parsed object as `prior_rollup` (or a path as `compare_file`). It must be a prior
Computed inputs object, not a prose brief. `rollup.py`
returns `portfolio` (totals, ACV at risk, counts) and `ranking` (deals sorted by severity of current
evidence: red flags before amber, then flag count, then amount, then days-to-close). In forecast mode it
also returns `forecast.category_rollup`, `forecast.recommendations`, `internal_evidence`, and optional
`movement`. In hygiene mode it returns `portfolio.distribution` (deals per dominant hygiene flag),
`portfolio.flagged_deals`/`clean_deals`, and `hygiene.flag_precedence`; `ranking` is ordered by
hygiene-flag precedence instead of risk severity, and each row carries `dominant_flag`, `hygiene_flags`,
`contacts`, `has_champion`, and `next_step_present`. Read these; do not re-rank, re-label, re-compare,
or re-sum yourself. Ranking is severity of evidence (or hygiene precedence), never a win-probability —
there are no predictive weights here by design (see `../core/config/risk-model.json`).
Calendar flags only enter this ranking when Calendar coverage is available. Missing authorization,
unavailable Calendar, or no confident deal match is an evidence gap, not a risk flag. Hygiene mode never
uses Calendar flags.

For each ranked deal, turn its `dominant_flag` and `risk_flags` into one cited risk line and one
concrete next move, drawing the evidence from that deal's gather (call date, email date, Calendar event,
or SF field).
Where observed participants exceeded logged contact roles for a deal, you may add a one-line CRM-hygiene
note, separate from the threading risk.

### 5. Output the read brief

Conversational, direct, second person ("you"), coaching tone — a forecast read a rep reads in two
minutes, not a report dump. Reference the writing-style skill for voice. Structure:

```
Pipeline Read — <rep>, <N> deals closing by <window end>. Run <date>.

Confidence: <High / Medium / Low> — <one clause on coverage, e.g. "Medium: full read on 9 of 11 deals;
2 had stale email data and are flagged below.">

Forecast at a glance: <total ACV in window; ACV at risk $X (Y%); single-threaded N; slipped/overdue N;
stale-data N>. <one honest sentence on whether this forecast is as solid as it looks>

Riskiest first
1. <Deal> — <Stage>, <ACV>, closes <date>. Dominant risk: <X>, <evidence, cited>. → Do this: <specific
   action with a who/when>. Confidence: <H/M/L>.
2. ...
3. ...

On track: <deals with no red flags, one line each — name them so it's not all red>

Where you're blind: <deals with stale or thin data — named, with what you couldn't see. Do NOT assert
risks on these; say what to confirm first.>

Your move this week: <the single highest-leverage action across the pipeline — usually the top 1–2
deals. For a deep call/email read on one, point to "/deal-read <deal>".>

Computed inputs:
```json
<paste rollup.py's verbatim JSON output here — the whole object. This is the audit trail: if it's
missing or empty, the deterministic roll-up was skipped and the brief above is untrustworthy.>
```
```

Rules:
- Every risk cites real evidence (call date, email date, SF field). No generic sales advice.
- Actions are specific and assignable: "Email <name> to get the security review scheduled before
  <date>", not "build urgency."
- Rank by `rollup.py`'s `ranking`. Do not reorder by gut feel or by assumed win probability.
- **Calibrate confidence to evidence, and lead with it.** Rate Low when most deals had thin or stale
  data; Medium on partial coverage; High only when you got a current read across the whole in-scope set.
  Name the deals you could not see in "Where you're blind".
- **The Computed inputs footer is required in the brief file.** Paste `rollup.py`'s verbatim output into
  the brief before validating. Never hand-write or summarize it; if you didn't run `rollup.py`, say so
  rather than fabricating the block.
- **Validate before presenting.** Pipe the finished brief into
  `python3 <skill-dir>/scripts/validate_brief.py`. It enforces the footer-present and no-High-on-stale
  rules in code. On success it prints `Validation: PASS`. If it exits non-zero, fix what it names and
  re-run; don't present a brief that fails.
- **Do not show the Computed inputs JSON to the user.** Show only `Validation: PASS` (or the failure
  reason) at the end of the presented brief. The JSON stays in the brief file as the audit trail; it
  does not appear in the chat output.

### 5-forecast. Output the forecast-read view (--forecast mode)

Same gather + roll-up (§1–4), different emphasis. Lead with the forecast posture, the number, category
rollup, movement if a prior snapshot exists, recommendation labels from `rollup.py`, highest-risk deals,
evidence gaps, and one move for the week. Structure:

```
Forecast Read - <rep>, <N> deals closing by <window end>. Run <date>.

Confidence: <High / Medium / Low> - <coverage clause>.

Review scope: <live Salesforce + Gmail + Calendar + Zoom, amount basis, forecast posture, category convention>.

Internal evidence: <internal mode; deal rooms mapped for N of M deals; linked proposal docs read for X
deals; missing/unavailable rooms named when material>.

The number: <total amount in window>. Realistic call: <amount you would actually bank, based on computed
risk posture and recommendations>.

Category rollup:
- Commit: <count>, <amount>, <amount at risk>
- Upside: <count>, <amount>, <amount at risk>
- Pipeline: <count>, <amount>, <amount at risk>
- Unknown: <count>, <amount>, <amount at risk>

Key movements: <only if --compare supplied and movement.evaluated is true; otherwise say movement was
not evaluated, or say the comparison snapshot was missing/invalid if rollup.py recorded that>.

Recommendation changes:
1. <Deal> - <keep/downgrade/inspect/possible_upside>. <computed reason code plus cited evidence>.
   Confidence: <H/M/L>.

Highest-risk deals:
1. <Deal> - <risk, evidence, next move>.

Evidence gaps: <source gaps, stale data, missing connector data, unknown forecast category, missing
amount, missing comparison snapshot, missing deal room, unavailable linked docs>.

Your move this week: <single highest-leverage action>.

Computed inputs:
```json
<rollup.py verbatim output>
```
```

Rules:
- Use `forecast.category_rollup` verbatim for category totals.
- Use `forecast.recommendations` verbatim for labels. Do not invent category changes.
- Use `movement` only when it comes from a prior Computed inputs artifact. Do not infer movement from
  current-state CRM history.
- Every Slack or Drive claim needs the source ref captured in `internal_evidence.signals`; omit claims
  without a source ref.
- Pipeline-read should not use direct quotes by default. `source_ref` is for audit trail and manual
  drill-back only, not routine context.
- Slack and Drive can sharpen confidence, risk notes, evidence gaps, internal owner, and next move. They
  cannot override Salesforce-owned amount, stage, close date, owner, or forecast category.
- Same computed footer and validate gate as §5. Forecast briefs must pass
  `python3 <skill-dir>/scripts/validate_brief.py` before presenting. Show only `Validation: PASS` in
  the chat output; keep the JSON in the brief file only.

### 5-hygiene. Output the CRM data-quality view (--hygiene mode)

A flat hygiene scan, not a coaching brief. One row per in-scope opp, ordered by `rollup.py`'s hygiene
`ranking`, each showing its single dominant flag. **Propose no fixes and no next moves** — naming the
gap is the deliverable. Structure:

```
Pipeline Hygiene — <rep>, <N> deals closing by <window end>. Run <date>.

Confidence: <High / Medium / Low> — <coverage clause, e.g. "High: Salesforce read cleanly on all N
opps." Lower it only if contact roles could not be read for some opps.>

Hygiene distribution:
- NO CONTACTS: <n>
- SINGLE-THREADED: <n>
- NO CHAMPION: <n>
- MISSING AMOUNT: <n>
- MISSING NEXT STEP: <n>
- STALE 30+: <n>
- OVERDUE CLOSE: <n>
- Clean: <n>

By deal:
1. <Deal> — <Stage>, <ACV>, closes <date>. <DOMINANT FLAG>: <the bare fact, e.g. "0 contact roles
   logged" / "no champion role among 3 contacts" / "NextStep blank" / "last activity 47 days ago">.
2. ...

Clean: <opps with no hygiene flag, one line each — name them so the list isn't all red>.

Computed inputs:
```json
<rollup.py verbatim output>
```
```

Rules:
- Use `portfolio.distribution` verbatim for the distribution counts and `ranking` verbatim for the
  order. One dominant flag per deal; do not list a deal's secondary flags as if they were separate rows.
- State the bare fact behind each flag (the count, the blank field, the days-since-activity). **Do not
  add a recommendation, next step, or coaching line** — that is what makes this hygiene and not read.
  If the rep wants the fix, that is `/pipeline-read` or `/deal-read`.
- Calibrate confidence to read coverage: High when the contact-roles query returned for every opp;
  lower it and name the opps whose roles you could not read.
- Same computed footer and validate gate as §5. Pipe the finished brief into
  `python3 <skill-dir>/scripts/validate_brief.py` (it requires the `Hygiene distribution` and `By deal`
  sections plus the footer). Show only `Validation: PASS` in chat; keep the JSON in the brief file only.

### 6. Hand off for a deep read (no drafting here)

`pipeline-read` does not draft email — that is a per-deal action. When the read shows a deal that
needs the full call/email coaching read or a follow-up draft, point the rep to the sibling:
`/deal-read <deal>`. Keep the responsibilities clean: pipeline-read ranks the pipeline; deal-read goes
deep on one and can draft the follow-up.

## Save (optional)

Default to chat only. If the user asks to save it, write to the current project's `deliverables/`
folder, keep the Computed inputs JSON in the saved file, and report:

```text
Validation: PASS

Saved to deliverables/<file>.md.
```

Also return a `computer://` link to the saved file. This skill is self-contained and portable across
reps; it does not write to Open Brain or deal-management.

## Scope guardrails

- Whole in-scope pipeline per run, one rep. For a deep read of a single deal, redirect to `/deal-read`.
- Per-rep only: operate on the running user's own connected accounts. Do not access another rep's
  mailbox or recordings.
- Confirm before a large deep-search run (see §1.3). Standard fast mode is bulk-first.
- Read and forecast propose actions; hygiene proposes none (it names data gaps only). Either way
  `pipeline-read` takes no outbound action and makes no writes of any kind.
- No Sales plugin dependency. Downstream workflows may cite the Computed inputs JSON but should not
  re-score or rewrite its deterministic labels.
- Slack message-content lookup is allowed only under `internal=force`; `internal=auto` uses mapped rooms
  or bounded channel-name lookup. Drive stays limited to linked proposal docs or explicit deal context.
