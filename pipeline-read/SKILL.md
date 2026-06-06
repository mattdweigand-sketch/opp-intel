---
name: pipeline-read
description: Shared engine for /pipeline-triage, /pipeline-forecast, and /pipeline-hygiene. Resolves the running rep's open opportunities closing in the current fiscal quarter by default and rolls them into one of three views - triage (riskiest deals first, each with its dominant risk and next move), forecast (the number, category rollup, keep/downgrade labels), or hygiene (a cheap Salesforce-only CRM data-quality scan: contacts, champion, next-step, amount, freshness) - all with a computed-inputs audit footer. Per-rep, live connectors (Salesforce, Gmail, Google Calendar, Zoom, mapped Slack deal rooms, linked Google Drive proposal docs), read-only, no writes. Do NOT use for a deep read of one named deal (that's deal-read) or for another rep's pipeline.
---

# Pipeline Read

Coach one rep across their whole forecast. Pull that rep's own Salesforce, Gmail, Google Calendar, and Zoom data for
every open opportunity closing inside the current fiscal quarter by default, add mapped Slack deal-room and linked
proposal-doc evidence by default in every mode (turn it off with `--internal off`), run each deal through the same deal-risk model
`deal-read` uses, and roll the results up into one ranked triage. Read-only across all sources. Makes
no writes at all, not even a draft.

## Input

This file is the shared **engine**: scope resolution, the per-deal gather loop, the roll-up, and all
three output views. The mode is chosen by the **command**, not inferred:

- **`/pipeline-triage`** → run in triage mode, present the ranked forecast-risk brief (§5).
- **`/pipeline-forecast`** → run in forecast mode, present the forecast-read view (§5-forecast).
- **`/pipeline-hygiene`** → run in hygiene mode, present the CRM data-quality view (§5-hygiene).

The three commands are thin frontends in `commands/`; all read this engine and differ in the mode
they set on the roll-up bundle and the section they present. No deal name: this skill always operates on
the rep's whole in-scope pipeline. The default scope is **open opportunities the running rep owns whose
CloseDate falls inside JSQ's current fiscal quarter**. JSQ's fiscal year starts Feb 1, so quarters run
Feb-Apr, May-Jul, Aug-Oct, and Nov-Jan. To run the next fiscal quarter, pass `--next-quarter`,
`--window next_quarter`, or say next quarter. Other ad hoc windows like `--window 30d` remain available,
but do not use them unless the user asks.

**Hygiene asks a different question.** Triage and forecast both score deal *risk* off live evidence
(email, calls, internal rooms). Hygiene asks "is the Salesforce *record* clean?" — contacts logged, a
champion role set, `NextStep` and amount filled, activity recent. A deal can be commercially healthy
with filthy CRM data, or have clean data on a dying deal, so hygiene has its own flags, its own ranking,
and a deliberately **cheaper, Salesforce-only gather** (no Gmail, Calendar, Zoom, Slack, or Drive; see §2-3-hygiene).
Like the old `pipeline-health`, it proposes **no fixes or next moves** — that is the clean line versus
triage.

Forecast mode (`/pipeline-forecast`) also accepts:
- `--next-quarter`
- `--window current_quarter|next_quarter|30d`
- `--posture conservative|defend-commit|identify-upside`
- `--amount-basis acv|crm-primary-amount`
- `--compare <prior-computed-inputs.json>`
- `--internal auto|off|force`
- `--internal-window 30d`

**Three views, one pipeline:**
- Triage (steps 1–4 then §5): the ranked forecast-risk brief.
- Forecast (steps 1–4 then §5-forecast): same gather + roll-up, a forecast-read view. Lead with
  forecast posture, category rollup, recommendation labels, movement if a prior computed-inputs JSON is
  supplied, internal evidence coverage, and named evidence gaps.
- Hygiene (step 1, then §2-3-hygiene, then §4 and §5-hygiene): the cheap Salesforce-only CRM
  data-quality scan. It does **not** run the per-deal Gmail/Calendar/Zoom/Slack loop in §2-3.

The roll-up bundle's `mode` field is set explicitly by the command (`triage`, `forecast`, or
`hygiene`). `rollup.py` obeys that field; it does **not** infer the view from the presence of
`amount_basis` or `posture`.

## Connectors

All reads are read-only. **`pipeline-read` makes no writes**. Drafting a follow-up is a per-deal action
that lives in `deal-read`.

- **Salesforce** — `getUserInfo`, `getObjectSchema`, `find`, `soqlQuery`, `getRelatedRecords`
- **Google Calendar** — historical and upcoming meeting lookup
- **Zoom** — `search_meetings`, `get_meeting_assets`, `recordings_list`
- **Gmail** — `search_threads`, `get_thread`
- **Slack** — mapped deal-room reads only in `internal=auto`; bounded fallback lookup only in
  `internal=force`
- **Google Drive** — proposal docs linked from the mapped Slack room or explicit deal context only

**Hygiene mode is Salesforce-only.** It reads the portfolio list plus one batched
`OpportunityContactRole` query; it does not touch Gmail, Calendar, Zoom, Slack, or Drive. The other connectors
above apply to triage and forecast only.

If a connector is not authorized, say so and proceed with the sources you have. Note in the brief
which evidence is missing and how that limits confidence across the affected deals.

## Files (the deterministic core — do not recite or reinvent from memory)

This surface is thin. Shared mechanics live in `../core/`; the local `scripts/` files are compatibility
wrappers that delegate there. This SKILL.md owns command routing, mode choice, portfolio output shape,
and the no-write policy. You invoke three wrapper scripts directly: `scripts/plan.py` (what to query,
both phases), `scripts/analyze.py` (per-deal processing, once per deal), and `scripts/rollup.py` (the
pipeline aggregation, once over all deals).

- **`scripts/plan.py`** — two phases. With `{"mode":"pipeline", ...}` it emits the portfolio-list
  query, forecast fields, amount basis, category field, and internal-evidence plan. Without `mode`, it
  emits the per-deal Salesforce/Gmail/Calendar/Zoom queries plus mapped Slack/linked-doc instructions when
  enabled. You execute what it prints; you never improvise SOQL or broad Slack/Drive search. In a
  `{"mode":"pipeline","hygiene":true,...}` plan, forecast and internal evidence are forced off and
  `per_deal_connectors` is Salesforce-only; pass `"opp_ids":[...]` after the portfolio list to get the
  batched `contact_roles_bulk` query and the `champion_roles` list.
- **`scripts/analyze.py`** — the per-deal processing entrypoint (copied from `deal-read`). Feed it one
  deal's bundle; it runs `compute.py` + `callstats.py` and parses account history. Run it once per
  in-scope deal.
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
- **`scripts/compute.py` / `scripts/callstats.py`** — deterministic metrics, invoked by `analyze.py`.
  Don't call them directly.
- **`scripts/validate_brief.py`** — the output-contract gate. Pipe your drafted brief into it before
  presenting: it confirms the `Computed inputs` footer is `rollup.py` output, the schema is present,
  stale or missing evidence limits confidence, and forecast-mode sections are present. A non-zero exit
  means fix the brief, don't ship it.

## Pipeline

### 1. Resolve scope and list the in-scope opps

1. Run `python3 <skill-dir>/scripts/plan.py` with `{"mode":"pipeline","today":"<YYYY-MM-DD>"}`. This
   resolves JSQ's current fiscal quarter from the Feb 1 fiscal-year start. Add `"next_quarter":true` or
   `"window":"next_quarter"` when the user asks for next quarter, or `"window":"30d"`, `"forecast":true`,
   `"posture":"conservative"`, `"amount_basis":"acv"`, `"internal":"auto"`, or similar when the user
   asked for them. On the first pass it returns a
   `whoami` step: call Salesforce `getUserInfo` to get the running rep's Id.
2. Run `plan.py` again with `{"mode":"pipeline","today":...,"window":...,"owner_id":"<your Id>",...}`.
   It returns the `salesforce.pipeline` SOQL, the resolved `window` (`close_on_or_after` and
   `close_on_or_before` for quarter windows), the `large_run_threshold`, and, in forecast mode, the
   exact posture, amount basis, forecast category field, and internal-evidence mode. Run the SOQL as
   written via `soqlQuery`.
3. **Large-run guardrail.** Count the returned opps. If the count exceeds `large_run_threshold`, list
   them (name, stage, ACV, close date) and confirm with the rep before gathering — in triage and
   forecast each in-scope deal fans out its own subagent hitting the connectors in `plan.py`'s
   `per_deal_connectors` (Salesforce, Gmail, Google Calendar, and Zoom always; Slack and Google Drive whenever internal
   evidence is on, which is the default in those modes unless `--internal off` is passed). State that
   connector list verbatim from `per_deal_connectors`; do not recite it from memory, since the set
   shifts with the resolved mode. A large set means that many parallel connector runs at once. Offer to
   narrow the window if the set is large. **In hygiene mode there is no per-deal fan-out** —
   `per_deal_connectors` is Salesforce-only and the whole scan is two queries, so it stays cheap even on
   a large pipeline; the threshold prompt is informational there.

### 2–3. Gather and analyze each deal (the deal-read loop)

For **each** in-scope opp, run the per-deal `deal-read` pipeline. This is the same gather-and-score as
`deal-read` §1–4; do it per deal:

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
   - `internal=auto`: use only mapped Slack deal rooms from the configured Salesforce mapping fields.
     If no room is mapped, record `deal_room_missing`; do not broad-search Slack.
   - `internal=off`: emit and gather no Slack or linked-doc evidence.
   - `internal=force`: bounded fallback lookup by account/opportunity/internal hints is allowed. Keep the
     message window and doc count within the plan output.
   - Linked Google Drive proposal docs are read only when linked from the mapped room or explicit deal
     context. Do not broad-search Drive.
2. **Read full email threads; keep Zoom at metadata only.** Every structural flag (slippage, stall,
   threading) is computable from SF fields and Zoom attendee lists without reading bodies. For email,
   read full thread bodies via `get_thread` — this catches active conversations that don't appear in SF
   task logs. For Zoom, use `meeting_summary` and the attendee list only (never `get_meeting_assets` /
   transcript bodies). Do **not** read Zoom transcripts to produce the triage; that belongs in
   `/deal-read`.
3. Build the per-deal bundle and run
   `python3 <skill-dir>/scripts/analyze.py < bundle.json` once per deal. For `compute_input`, pass
   `observed_participants` and `logged_contact_roles` (not a pre-counted contact total),
   `stage_entered_date`, `close_date_history`, and `latest_call_date` when available — same contract as
   `deal-read`. Keep each deal's `analyze.py` output; you feed them all to `rollup.py` next.
4. Note for each deal a `latest_call_date` and the email list (direction + date), so `analyze.py`
   computes freshness and latency deterministically. When `flags.email_data_stale` is true for a deal,
   that deal's email view is lagging: say so and lower its confidence rather than asserting it went
   quiet.
5. Whenever internal evidence is on (the default in every mode unless `--internal off`), add
   `internal_evidence` to the per-deal `analyze.py` bundle when Slack or linked
   proposal-doc evidence was gathered. Preserve source refs. Slack/Drive evidence can affect confidence,
   source gaps, risk notes, internal owner, and next-move wording. It cannot change Salesforce-owned
   truth: amount, stage, close date, owner, or forecast category.

**Per-deal isolation contract (portable — every agent satisfies this, however it executes the loop).**
The per-deal work is a self-contained unit: gather that one deal's metadata, run `analyze.py` on it, and
**emit only a compact result** — the deal's `analyze.py` JSON output plus a short list of cited evidence
strings (e.g. `latest_call_date`, last inbound/outbound email date, the one load-bearing SF note). The
raw connector payloads (transcripts, thread bodies, full task lists) stay inside the per-deal step and
**must not flow into the roll-up context**. The orchestrating step collects these compact results and
feeds them to `rollup.py` once (§4); it never holds raw bodies. This keeps a full run's context to N
small summaries instead of N piles of raw data, and it is the same shape whether one agent loops the
deals inline or a harness fans them out — the deterministic core (`analyze.py` per deal, `rollup.py`
once) is identical either way.

> **Claude Code execution (the Claude-Code-specific way to satisfy the contract above).** Run each in-
> scope deal as its own subagent via the `Agent` tool, **on every run** — launch them concurrently (one
> message, multiple `Agent` calls) so the deals gather in parallel and each deal's raw payload lands in
> that subagent's throwaway context, not the orchestrator's. Give each subagent a **narrow** prompt: the
> deal-context dict, "follow SKILL.md §2–3 steps 1–4, metadata only," and the return contract — "reply
> with **only** this deal's `analyze.py` JSON output plus the cited evidence strings; do not include raw
> transcripts or email bodies." The orchestrator collects the compact replies and runs `rollup.py` once
> over them (§4). This is execution mechanism, not policy: the contract above is what binds, and a raw-
> API harness or another agent that loops inline is equally correct as long as raw bodies never reach the
> roll-up.

### 2-3-hygiene. Gather (Salesforce-only, no per-deal loop)

**Hygiene mode skips §2–3 entirely.** Do not fan out subagents, do not read Zoom or Gmail. The whole
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
  "mode": "triage|forecast|hygiene",
  "posture": "conservative|defend_commit|identify_upside",
  "amount_basis": "acv|crm_primary_amount",
  "internal": "auto|off|force",
  "window": { ...the window block plan.py returned... },
  "prior_rollup": { ...prior Computed inputs JSON... },
  "deals": [
    {
      "opportunity_id",
      "name",
      "stage",
      "acv",
      "amount",
      "forecast_category",
      "close_date",
      "internal_evidence",
      "analyze_output": <that deal's analyze.py output>
    },
    ...
  ]
}
```
The `name`, `stage`, `acv`, and `close_date` come straight from the §1 portfolio list the orchestrator
already holds — the per-deal step only owes you `analyze_output` plus its cited evidence, so a subagent
need not echo the deal facts back. For `acv`, pass the deal's real ACV from the opp record (the
`Added_ARR__c` you queried). For forecast mode, also pass the configured amount field and forecast
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

### 5. Output the triage brief

Conversational, direct, second person ("you"), coaching tone — a forecast triage a rep reads in two
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
  add a recommendation, next step, or coaching line** — that is what makes this hygiene and not triage.
  If the rep wants the fix, that is `/pipeline-triage` or `/deal-read`.
- Calibrate confidence to read coverage: High when the contact-roles query returned for every opp;
  lower it and name the opps whose roles you could not read.
- Same computed footer and validate gate as §5. Pipe the finished brief into
  `python3 <skill-dir>/scripts/validate_brief.py` (it requires the `Hygiene distribution` and `By deal`
  sections plus the footer). Show only `Validation: PASS` in chat; keep the JSON in the brief file only.

### 6. Hand off for a deep read (no drafting here)

`pipeline-read` does not draft email — that is a per-deal action. When the triage shows a deal that
needs the full call/email coaching read or a follow-up draft, point the rep to the sibling:
`/deal-read <deal>`. Keep the responsibilities clean: pipeline-read ranks and triages; deal-read goes
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
- Confirm before a large run (see §1.3). A full read loops the connectors per deal.
- Triage and forecast propose actions; hygiene proposes none (it names data gaps only). Either way
  `pipeline-read` takes no outbound action and makes no writes of any kind.
- No Sales plugin dependency. Downstream workflows may cite the Computed inputs JSON but should not
  re-score or rewrite its deterministic labels.
- Broad Slack or Drive lookup is allowed only under `internal=force`; `internal=auto` uses mapped deal
  rooms and linked proposal docs only.
