#!/usr/bin/env python3
"""Emit the exact Salesforce/Gmail/Calendar/Zoom queries for a pipeline-read run.

Two phases share this one script:

  1. PORTFOLIO phase — list the rep's open, closing-window opportunities.
     Input:  {"mode":"pipeline","today":"2026-06-04","window":"current_quarter"|"next_quarter"|"90d",
              "next_quarter":true,"owner_id":"005...","forecast":true,"posture":"conservative",
              "amount_basis":"acv","internal":"auto"}   (owner_id optional on the first pass)
     Output: a getUserInfo step (to resolve OwnerId when not supplied) and, once owner_id
             is known, the scoped Opportunity SOQL.

  2. PER-DEAL phase — identical to deal-read: the model loops the in-scope opps and, for each,
     calls plan.py with that deal's context to get its opp/roles/tasks/history/prior + Gmail +
     Calendar + Zoom queries. Same code path as deal-read so the per-deal plan stays in lockstep.

The model still EXECUTES the queries (only it can call the MCP connectors); it never improvises
them. Field names come from sf-fields.json, windows from risk-model.json.

Usage: python3 plan.py            # reads context JSON on stdin, prints the query plan
Per-deal context keys (all optional — emit what the inputs allow):
  {"deal_name","opp_id","account_id","account_name","contact_emails":[...],
   "created_date","today","internal":"auto|off|force","Slack_Channel__c":"C...",
   "Deal_Room_URL__c":"https://..."}
"""
import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "config"))


def load(name):
    with open(os.path.join(CONFIG, name)) as f:
        return json.load(f)


def dedupe(items):
    out = []
    seen = set()
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def parse(d):
    return date.fromisoformat(d) if d else None


def add_months(d, months):
    total = (d.year * 12 + d.month - 1) + months
    year = total // 12
    month = total % 12 + 1
    return date(year, month, d.day)


def fiscal_quarter(today, start_month, start_day, offset=0):
    """Return the start/end dates for today's fiscal quarter, plus offset quarters."""
    fy_start = date(today.year, start_month, start_day)
    if today < fy_start:
        fy_start = date(today.year - 1, start_month, start_day)
    months_since_fy_start = (today.year - fy_start.year) * 12 + today.month - fy_start.month
    current_q_index = months_since_fy_start // 3
    start = add_months(fy_start, (current_q_index + offset) * 3)
    end = date.fromordinal(add_months(start, 3).toordinal() - 1)
    return start, end


def resolve_window(today, window, scope_cfg):
    """Resolve the close window to a lower/upper bound and metadata."""
    default_days = scope_cfg.get("default_window_days", 90)
    token = str(window or scope_cfg.get("close_window") or "current_quarter").strip().lower()
    token = token.replace("-", "_")

    current_aliases = {"current_quarter", "current_fiscal_quarter"}
    next_aliases = {"next_quarter", "next_fiscal_quarter"}
    if token in current_aliases or token in next_aliases:
        start_month = int(scope_cfg.get("fiscal_year_start_month", 1))
        start_day = int(scope_cfg.get("fiscal_year_start_day", 1))
        offset = 1 if token in next_aliases else 0
        start, end = fiscal_quarter(today, start_month, start_day, offset=offset)
        return {
            "today": today.isoformat(),
            "name": "next_quarter" if offset else "current_quarter",
            "fiscal_year_start": f"{start_month:02d}-{start_day:02d}",
            "close_on_or_after": start.isoformat(),
            "close_on_or_before": end.isoformat(),
        }

    w = token.rstrip("d")
    try:
        days = int(w)
    except ValueError:
        days = default_days
    return {
        "today": today.isoformat(),
        "name": f"{days}d",
        "close_on_or_before": date.fromordinal(today.toordinal() + days).isoformat(),
    }


def normalize_token(value):
    return str(value or "").strip().lower().replace("-", "_")


def forecast_options(ctx, fields, model):
    forecast_cfg = model.get("forecast", {})
    amount_cfg = fields.get("amount_basis", {})
    category_cfg = fields.get("forecast_category", {})
    internal_cfg = model.get("internal_evidence", {})

    posture = normalize_token(ctx.get("posture") or forecast_cfg.get("default_posture", "conservative"))
    if posture not in forecast_cfg.get("postures", []):
        raise ValueError(f"unknown forecast posture: {ctx.get('posture')}")

    amount_basis = normalize_token(ctx.get("amount_basis") or amount_cfg.get("default", "acv"))
    amount_fields = amount_cfg.get("fields", {})
    if amount_basis not in amount_fields:
        raise ValueError(f"unknown amount_basis: {ctx.get('amount_basis')}")

    internal = normalize_token(ctx.get("internal") or internal_cfg.get("default", "auto"))
    if internal not in {"auto", "off", "force"}:
        raise ValueError(f"unknown internal mode: {ctx.get('internal')}")

    return {
        "enabled": True,
        "posture": posture,
        "amount_basis": amount_basis,
        "amount_field": amount_fields[amount_basis],
        "forecast_category_field": category_cfg.get("field"),
        "category_convention": category_cfg.get("convention", {}),
        "internal": internal,
    }


def internal_mode_for(ctx, model, profile="pipeline"):
    # An explicit --internal flag always wins. Otherwise the chosen default lives in
    # config (internal_evidence.default), so Slack/Drive evidence runs on every mode,
    # read included. To turn it off, set that config default to "off" or pass
    # --internal off; do not special-case a mode here.
    if ctx.get("internal") is not None:
        return normalize_token(ctx.get("internal"))
    cfg = model.get("internal_evidence", {})
    return normalize_token((cfg.get("default_by_profile") or {}).get(profile) or cfg.get("default", "auto"))


def internal_plan(ctx, fields, model, profile="pipeline"):
    mode = internal_mode_for(ctx, model, profile=profile)
    if mode not in {"auto", "off", "force"}:
        raise ValueError(f"unknown internal mode: {ctx.get('internal')}")
    if mode == "off":
        return None

    cfg = model.get("internal_evidence", {})
    profile_cfg = load("depth-profiles.json").get(profile, {})
    slack_profile = profile_cfg.get("slack", {}) if isinstance(profile_cfg.get("slack"), dict) else {}
    drive_profile = profile_cfg.get("drive", {}) if isinstance(profile_cfg.get("drive"), dict) else {}
    source_cfg = fields.get("internal_sources", {})
    room_cfg = source_cfg.get("slack_deal_room", {})
    doc_cfg = source_cfg.get("linked_docs", {})
    mapping_fields = room_cfg.get("mapping_fields", [])

    room = (
        ctx.get("slack_deal_room")
        or ctx.get("Slack_Channel__c")
        or ctx.get("Deal_Room_URL__c")
        or ctx.get("deal_room_url")
    )
    account_or_deal = dedupe([
        ctx.get("account_name"),
        ctx.get("deal_name"),
        ctx.get("opportunity_name"),
        *([str(h) for h in ctx.get("internal_hints", [])] if ctx.get("internal_hints") else []),
    ])

    out = {
        "mode": mode,
        "window_days": int(ctx.get("internal_window") or cfg.get("default_window_days", 30)),
        "mapping_fields": mapping_fields,
        "max_messages": slack_profile.get("max_messages", cfg.get("max_messages_per_room", 80)),
        "max_linked_docs": drive_profile.get("max_docs", cfg.get("max_linked_docs_per_room", 5)),
        "signals": cfg.get("signals", []),
        "broad_search_allowed": mode == "force",
    }

    if room:
        out["slack"] = {
            "query_type": "mapped_deal_room",
            "room": room,
            "read": ["recent_messages", "pinned_items", "bookmarks"],
            "max_messages": out["max_messages"],
            "broad_search_allowed": False,
        }
        out["linked_docs"] = {
            "source": "google_drive",
            "relationship": doc_cfg.get("relationship", "linked_from_deal_room"),
            "allowed_sources": doc_cfg.get("allowed_sources", ["google_drive"]),
            "max_docs": out["max_linked_docs"],
            "allowed_when": ["linked_from_deal_room", "explicit_deal_context"],
        }
        return out

    if mode == "auto":
        out["coverage"] = "deal_room_missing"
        out["source_gaps"] = ["deal_room_missing"]
        return out

    out["slack"] = {
        "query_type": "bounded_fallback_lookup",
        "steps": [
            {
                "step": 1,
                "action": "slack_search_channels",
                "terms": account_or_deal,
                "channel_types": "public_channel,private_channel",
                "on_match": "read up to max_messages from the matched channel; set coverage=found; skip step 2",
                "on_no_match": "proceed to step 2",
            },
            {
                "step": 2,
                "action": "slack_search_public_and_private",
                "terms": account_or_deal,
                "window_days": out["window_days"],
                "on_match": "capture signals with source_refs; set coverage=checked_no_match",
                "on_no_match": "set coverage=checked_no_match; no signals",
            },
        ],
        "terms": account_or_deal,
        "window_days": out["window_days"],
        "max_messages": out["max_messages"],
        "broad_search_allowed": True,
        "requires_internal_force": True,
    }
    out["linked_docs"] = {
        "source": "google_drive",
        "relationship": doc_cfg.get("relationship", "linked_from_deal_room"),
        "allowed_sources": doc_cfg.get("allowed_sources", ["google_drive"]),
        "max_docs": out["max_linked_docs"],
        "allowed_when": ["linked_from_deal_room", "explicit_deal_context"],
    }
    return out


def calendar_plan(ctx, model, profile="pipeline"):
    """Emit read-only Google Calendar lookups for historical and future meetings."""
    cfg = (model.get("calendar") or {}).get(profile, {})
    if not cfg or cfg == "off":
        return None

    terms = dedupe([
        ctx.get("account_name"),
        ctx.get("deal_name"),
        ctx.get("opportunity_name"),
        *([str(h) for h in ctx.get("calendar_hints", [])] if ctx.get("calendar_hints") else []),
    ])
    emails = ctx.get("contact_emails") or []
    if not terms and not emails:
        return {
            "source": "google_calendar",
            "coverage": "insufficient_context",
            "source_gaps": ["calendar_context_missing"],
            "read_only": True,
        }

    lookback_days = int(ctx.get("calendar_history_days") or cfg.get("history_days", 180))
    lookahead_days = int(ctx.get("calendar_future_days") or cfg.get("future_days", 60))
    return {
        "source": "google_calendar",
        "query": {
            "terms": terms,
            "attendees": emails,
        },
        "history": {
            "from": ctx.get("created_date") or f"last {lookback_days} days",
            "to": ctx.get("today", "now"),
            "max_events": int(cfg.get("max_historical_events", 10)),
        },
        "future": {
            "from": ctx.get("today", "now"),
            "to": f"next {lookahead_days} days",
            "max_events": int(cfg.get("max_future_events", 10)),
        },
        "read": cfg.get("read", ["title", "time", "attendees", "conference_link"]),
        "read_only": True,
    }


def pipeline_plan(ctx):
    fields = load("sf-fields.json")
    model = load("risk-model.json")
    scope = fields["pipeline_scope"]
    pipe_cfg = model.get("pipeline", {})
    scope_cfg = pipe_cfg.get("scope", {})

    today = parse(ctx.get("today")) or date.today()
    requested_window = ctx.get("window") or ("next_quarter" if ctx.get("next_quarter") else None)
    window = resolve_window(today, requested_window or scope_cfg.get("close_window"), scope_cfg)

    # Hygiene is a deliberately cheap SF-only scan: no forecast block, no internal
    # evidence lane, and the per-deal loop reads Salesforce only (no Gmail/Zoom).
    hygiene = bool(ctx.get("hygiene") or normalize_token(ctx.get("mode")) == "hygiene")

    forecast_enabled = bool(ctx.get("forecast")) and not hygiene
    forecast = forecast_options(ctx, fields, model) if forecast_enabled else None
    internal = None if hygiene else internal_plan(ctx, fields, model, profile="pipeline")

    # Connectors that each per-deal subagent will hit, derived from the resolved mode so
    # the large-run confirmation prompt is accurate on every run instead of recited from
    # prose. Hygiene hits Salesforce only; read/forecast add Gmail/Calendar/Zoom, plus
    # Slack and Google Drive when internal evidence is on (forecast default, or
    # --internal auto|force).
    # See SKILL.md §1.3.
    per_deal_connectors = ["Salesforce"] if hygiene else ["Salesforce", "Gmail", "Google Calendar", "Zoom"]
    if internal:
        per_deal_connectors += ["Slack", "Google Drive"]

    out = {"salesforce": {}, "window": window,
           "large_run_threshold": pipe_cfg.get("large_run_threshold", 15),
           "per_deal_connectors": per_deal_connectors}
    if hygiene:
        out["mode"] = "hygiene"
    if forecast:
        out["forecast"] = forecast
    if internal:
        out["internal_evidence"] = internal

    # Phase 3 of the hygiene scan: the portfolio list already ran; batch-pull contact
    # roles for those opp ids in one query, then group by OpportunityId in the model.
    if hygiene and ctx.get("opp_ids"):
        h_scope = fields.get("hygiene_scope", {})
        sobject = h_scope.get("contact_roles_sobject", "OpportunityContactRole")
        cr_fields = h_scope.get("contact_roles_fields", ["OpportunityId", "Role", "IsPrimary"])
        id_field = h_scope.get("opportunity_id_field", "OpportunityId")
        ids = ", ".join("'%s'" % str(i).replace("'", "") for i in ctx["opp_ids"])
        out["salesforce"]["contact_roles_bulk"] = (
            f'SELECT {", ".join(cr_fields)} FROM {sobject} WHERE {id_field} IN ({ids})'
        )
        out["champion_roles"] = model.get("hygiene", {}).get("champion_roles", [])
        return out

    select = list(scope["fields"])
    if scope.get("account_name_field"):
        select.append(scope["account_name_field"])
    if forecast:
        select.extend([forecast.get("amount_field"), forecast.get("forecast_category_field")])
    if internal:
        select.extend(fields.get("internal_sources", {}).get("slack_deal_room", {}).get("mapping_fields", []))
    select = dedupe(select)

    owner_id = ctx.get("owner_id")
    if not owner_id:
        out["salesforce"]["whoami"] = {
            "tool": "getUserInfo",
            "note": "resolve the running rep's Id, then re-run plan.py with owner_id set",
        }
        return out

    where = " AND ".join([
        scope["owner_filter"].format(owner_id=owner_id),
        scope["open_filter"],
        *([f"CloseDate >= {window['close_on_or_after']}"] if window.get("close_on_or_after") else []),
        f"CloseDate <= {window['close_on_or_before']}",
    ])
    out["salesforce"]["pipeline"] = (
        f'SELECT {", ".join(select)} FROM Opportunity '
        f'WHERE {where} ORDER BY {scope["order_by"]}'
    )
    return out


def deal_plan(ctx, profile="pipeline"):
    """Per-deal query plan — identical contract to deal-read's plan.py."""
    fields = load("sf-fields.json")
    model = load("risk-model.json")
    window = model["thresholds"]["email_window_days"]

    sf = {}
    if ctx.get("deal_name"):
        name = ctx["deal_name"].replace('"', "")
        sf["find"] = (
            f'FIND {{{name}*}} IN NAME FIELDS RETURNING '
            f'Opportunity({", ".join(fields["find_fields"])})'
        )
    if ctx.get("opp_id"):
        oid = ctx["opp_id"]
        sf["opportunity"] = (
            f'SELECT {", ".join(fields["opportunity_fields"])} '
            f"FROM Opportunity WHERE Id = '{oid}'"
        )
        contact_roles = {
            "tool": "getRelatedRecords",
            "sobject-name": "Opportunity",
            "id": oid,
            "relationship-path": fields["contact_roles_relationship"],
        }
        if profile == "deal":
            contact_roles["read_fields"] = fields["contact_fields"]
        sf["contact_roles"] = contact_roles
        sf["tasks"] = (
            f'SELECT {", ".join(fields["task_fields"])} '
            f"FROM Task WHERE WhatId = '{oid}' ORDER BY ActivityDate DESC LIMIT 25"
        )
        sf["history"] = (
            f'SELECT {", ".join(fields["history_fields"])} '
            f"FROM OpportunityHistory WHERE OpportunityId = '{oid}' ORDER BY CreatedDate ASC"
        )
    if ctx.get("account_id"):
        sf["prior_account_opps"] = (
            f'SELECT {", ".join(fields["prior_opp_fields"])} '
            f"FROM Opportunity WHERE AccountId = '{ctx['account_id']}' "
            "AND IsClosed = true ORDER BY CloseDate DESC"
        )
        if profile == "pipeline":
            sf["account_contacts"] = (
                f'SELECT {", ".join(fields["contact_fields"])} '
                f"FROM Contact WHERE AccountId = '{ctx['account_id']}' AND Email != null"
            )

    gmail = {"sent_freshness": f"in:sent newer_than:{window}d"}
    emails = ctx.get("contact_emails") or []
    if emails:
        ors = " OR ".join(emails)
        gmail["thread_search"] = f"from:({ors}) OR to:({ors}) newer_than:{window}d"
    if profile == "pipeline":
        gmail["_note"] = (
            "After running account_contacts and contact_roles, union all non-null Email values "
            "and re-run thread_search: from:(<emails>) OR to:(<emails>) newer_than:{window}d. "
            "Read full thread bodies, not metadata only."
        ).replace("{window}", str(window))

    # Workflow-tool inbox sweep: internal SaaS notifications (CLM, NDA/legal, call intel,
    # CRM auto-update) live in the rep's own Gmail under the vendors' sender domains, scoped
    # to the account/deal name. They never match the prospect-domain thread_search, so target
    # them explicitly. Internal-evidence lane only — never ranking or flag_severity.
    workflow_tools = (model.get("internal_evidence", {}) or {}).get("workflow_tools", [])
    scope_terms = dedupe([ctx.get("account_name"), ctx.get("deal_name")])
    domains = dedupe([wt.get("domain") for wt in workflow_tools if wt.get("domain")])
    if scope_terms and domains:
        from_clause = " OR ".join(domains)
        term_clause = " OR ".join('"%s"' % t.replace('"', "") for t in scope_terms)
        gmail["workflow_signals"] = (
            'from:(' + from_clause + ') (' + term_clause + ') newer_than:' + str(window) + 'd'
        )
        gmail["_workflow_note"] = (
            "Read these workflow-tool notifications and map each sender domain to its signal_type "
            "via internal_evidence.workflow_tools in risk-model.json (e.g. ironcladapp.com -> "
            "clm_stage). Emit each as an internal_evidence signal with a source_ref (the message "
            "id/link). Internal-evidence lane only: these inform confidence, source gaps, risk "
            "notes, and next-move wording, never Salesforce-owned truth, ranking, or flag_severity."
        )

    calendar = calendar_plan(ctx, model, profile=profile)

    zoom = {}
    if ctx.get("account_name"):
        zoom = {
            "q": ctx["account_name"],
            "from": ctx.get("created_date", f"last {window} days"),
            "to": ctx.get("today", "now"),
            "include_zoom_my_notes": True,
        }

    out = {"salesforce": sf, "gmail": gmail, "zoom": zoom}
    if calendar:
        out["calendar"] = calendar
    internal = internal_plan(ctx, fields, model, profile=profile)
    if internal:
        out["internal_evidence"] = internal
    return out


def main():
    ctx = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    surface = os.environ.get("OPP_INTEL_SURFACE", "pipeline-read")
    profile = "deal" if surface == "deal-read" else "pipeline"
    try:
        if ctx.get("mode") == "pipeline":
            plan = pipeline_plan(ctx)
        else:
            plan = deal_plan(ctx, profile=profile)
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
    json.dump(plan, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
