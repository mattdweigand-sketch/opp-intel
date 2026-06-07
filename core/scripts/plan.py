#!/usr/bin/env python3
"""Emit the exact Salesforce/Gmail/Calendar/Zoom queries for a pipeline-read run.

Two phases share this one script:

  1. PORTFOLIO phase — list the rep's open, closing-window opportunities.
     Input:  {"mode":"pipeline","today":"2026-06-04","window":"current_quarter"|"next_quarter"|"90d",
              "next_quarter":true,"owner_id":"005...","forecast":true,"posture":"conservative",
              "amount_basis":"added_arr","internal":"auto"}   (owner_id optional on the first pass)
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
   "created_date","today","internal":"auto|off|force"}
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


def source_contracts():
    return load("source-contracts.json")


def source_contract_summary(contracts, source_names):
    ownership = contracts.get("source_ownership", {})
    rules = contracts.get("coverage_rules", {})
    out = {
        "canonical_config": "core/config/source-contracts.json",
        "source_of_truth": {},
        "clean_negative_requires_successful_connector_read": bool(
            rules.get("clean_negative_requires_successful_connector_read")
        ),
        "missing_connector_read": rules.get("missing_connector_read", "coverage_gap"),
        "cross_source_substitution_allowed": bool(rules.get("cross_source_substitution_allowed")),
    }
    for name in source_names:
        cfg = ownership.get(name, {})
        out["source_of_truth"][name] = cfg.get("source_of_truth", name)
    return out


def coverage_manifest_contract(contracts, profile, source_names):
    cfg = contracts.get("coverage_manifest", {})
    return {
        "required": True,
        "profile": profile,
        "bundle_field": cfg.get("bundle_fields", {}).get("manifest", "coverage_manifest"),
        "source_reads_bundle_field": cfg.get("bundle_fields", {}).get("source_reads", "source_reads"),
        "expected_sources": source_names,
        "source_read_statuses": cfg.get("source_read_statuses", []),
        "clean_statuses": cfg.get("clean_statuses", []),
        "degraded_statuses": cfg.get("degraded_statuses", []),
        "missing_expected_source": cfg.get("missing_expected_source"),
        "clean_source_without_required_proof": cfg.get("clean_source_without_required_proof"),
        "degraded_source": cfg.get("degraded_source"),
        "connector_status_mapping": cfg.get("connector_status_mapping", {}),
    }


def source_requirement(contracts, name):
    cfg = (contracts.get("source_ownership") or {}).get(name, {})
    return {
        "source_of_truth": cfg.get("source_of_truth", name),
        "owns": cfg.get("owns", []),
        "does_not_own": cfg.get("does_not_own", []),
        "required_search": cfg.get("required_search", []),
    }


def dedupe(items):
    out = []
    seen = set()
    for item in items:
        if item is None:
            continue
        key = str(item).strip()
        if key and key not in seen:
            out.append(key)
            seen.add(key)
    return out


def slack_lookup_terms(values, max_terms=12):
    """Deterministic Slack channel-name terms.

    This is intentionally channel-name only. It broadens "NW1" to "nwl" and
    normalizes punctuation, but does not search message bodies unless internal
    evidence is explicitly forced.
    """
    candidates = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in raw)
        spaced = " ".join(cleaned.split())
        compact = "".join(spaced.split())
        dashed = "-".join(spaced.split())
        underscored = "_".join(spaced.split())
        tokens = [tok for tok in spaced.split() if len(tok) >= 3 or any(ch.isdigit() for ch in tok)]
        for term in [raw, spaced, compact, dashed, underscored, *tokens]:
            if term:
                candidates.append(term)
                if "1" in term:
                    candidates.append(term.replace("1", "l"))
                if "0" in term:
                    candidates.append(term.replace("0", "o"))
    return dedupe(candidates)[:max_terms]


PUBLIC_EMAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}


def company_domains_from_emails(emails):
    domains = []
    for email in emails or []:
        raw = str(email or "").strip().lower()
        if "@" not in raw:
            continue
        domain = raw.rsplit("@", 1)[1].strip(" >)")
        if domain and domain not in PUBLIC_EMAIL_DOMAINS:
            domains.append(domain)
    return dedupe(domains)


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

    amount_basis = normalize_token(ctx.get("amount_basis") or amount_cfg.get("default", "added_arr"))
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
    doc_cfg = source_cfg.get("linked_docs", {})
    contracts = source_contracts()
    slack_requirement = source_requirement(contracts, "slack")
    drive_requirement = source_requirement(contracts, "google_drive")
    account_or_deal = dedupe([
        ctx.get("account_name"),
        ctx.get("deal_name"),
        ctx.get("opportunity_name"),
        *([str(h) for h in ctx.get("internal_hints", [])] if ctx.get("internal_hints") else []),
    ])
    channel_terms = slack_lookup_terms(account_or_deal)

    out = {
        "mode": mode,
        "window_days": int(ctx.get("internal_window") or cfg.get("default_window_days", 30)),
        "mapping_fields": [],
        "source_contract": source_contract_summary(contracts, ["slack", "google_drive"]),
        "max_messages": slack_profile.get("max_messages", cfg.get("max_messages_per_room", 80)),
        "max_linked_docs": drive_profile.get("max_docs", cfg.get("max_linked_docs_per_room", 5)),
        "signals": cfg.get("signals", []),
        "broad_search_allowed": mode == "force",
    }

    if mode == "auto" and not channel_terms:
        out["coverage"] = "deal_room_missing"
        out["source_gaps"] = ["deal_room_missing"]
        return out

    if mode == "auto":
        out["slack"] = {
            "source": "slack",
            "connector": "slack_mcp",
            "source_contract": slack_requirement,
            "salesforce_mapping_allowed": False,
            "query_type": "channel_name_lookup",
            "steps": [
                {
                    "step": 1,
                    "action": "slack_search_channels",
                    "terms": channel_terms,
                    "channel_types": "public_channel,private_channel",
                    "on_match": (
                        "read up to max_messages from the matched channel; set "
                        "deal_room.coverage=found and source_ref to the channel id"
                    ),
                    "on_no_match": "set deal_room.coverage=checked_no_match; no message-body search",
                },
            ],
            "terms": channel_terms,
            "max_messages": out["max_messages"],
            "broad_search_allowed": False,
            "requires_internal_force": False,
            "coverage_requirements": {
                "checked_bundle_field": "internal_evidence.slack_mcp_checked",
                "searched_channels_bundle_field": "internal_evidence.slack_channels_searched",
                "channel_matches_bundle_field": "internal_evidence.slack_channel_matches",
                "deal_room_coverage_bundle_field": "internal_evidence.deal_room.coverage",
                "deal_room_source_ref_bundle_field": "internal_evidence.deal_room.source_ref",
                "clean_negative_rule": "Only claim no Slack room/activity after Slack MCP channel search completed and searched channels are recorded.",
            },
        }
        out["linked_docs"] = {
            "source": "google_drive",
            "source_contract": drive_requirement,
            "relationship": doc_cfg.get("relationship", "linked_from_deal_room"),
            "allowed_sources": doc_cfg.get("allowed_sources", ["google_drive"]),
            "max_docs": out["max_linked_docs"],
            "allowed_when": ["linked_from_deal_room", "explicit_deal_context"],
        }
        return out

    out["slack"] = {
        "source": "slack",
        "connector": "slack_mcp",
        "source_contract": slack_requirement,
        "salesforce_mapping_allowed": False,
        "query_type": "bounded_fallback_lookup",
        "steps": [
            {
                "step": 1,
                "action": "slack_search_channels",
                "terms": channel_terms,
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
        "terms": channel_terms,
        "window_days": out["window_days"],
        "max_messages": out["max_messages"],
        "broad_search_allowed": True,
        "requires_internal_force": True,
        "coverage_requirements": {
            "checked_bundle_field": "internal_evidence.slack_mcp_checked",
            "searched_channels_bundle_field": "internal_evidence.slack_channels_searched",
            "channel_matches_bundle_field": "internal_evidence.slack_channel_matches",
            "deal_room_coverage_bundle_field": "internal_evidence.deal_room.coverage",
            "deal_room_source_ref_bundle_field": "internal_evidence.deal_room.source_ref",
            "clean_negative_rule": "Only claim no Slack room/activity after Slack MCP channel search completed and searched channels are recorded.",
        },
    }
    out["linked_docs"] = {
        "source": "google_drive",
        "source_contract": drive_requirement,
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
    contracts = source_contracts()

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
            "source_contract": source_requirement(contracts, "google_calendar"),
            "coverage": "insufficient_context",
            "source_gaps": ["calendar_context_missing"],
            "read_only": True,
        }

    lookback_days = int(ctx.get("calendar_history_days") or cfg.get("history_days", 180))
    lookahead_days = int(ctx.get("calendar_future_days") or cfg.get("future_days", 60))
    return {
        "source": "google_calendar",
        "source_contract": source_requirement(contracts, "google_calendar"),
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
    contracts = source_contracts()
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
    source_names = ["salesforce"] if hygiene else ["salesforce", "gmail", "google_calendar", "zoom"]
    if internal:
        per_deal_connectors += ["Slack", "Google Drive"]
        source_names += ["slack", "google_drive"]

    out = {"salesforce": {}, "window": window,
           "profile": "hygiene" if hygiene else "pipeline",
           "coverage_manifest": coverage_manifest_contract(
               contracts, "hygiene" if hygiene else "pipeline", source_names
           ),
           "source_contract": source_contract_summary(contracts, source_names),
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
        select.extend(fields.get("internal_sources", {}).get("slack", {}).get("mapping_fields", []))
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
    contracts = source_contracts()
    window = model["thresholds"]["email_window_days"]

    sf = {"source_contract": source_requirement(contracts, "salesforce")}
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

    gmail = {
        "source_contract": source_requirement(contracts, "gmail"),
        "coverage_requirements": {
            "derive_domains_from": "Salesforce account/contact emails only as search context, not as Gmail evidence",
            "searched_emails_bundle_field": "email_coverage.searched_emails",
            "contact_union_bundle_field": "email_coverage.contact_union_emails",
            "searched_domains_bundle_field": "email_coverage.searched_domains",
            "contact_domains_bundle_field": "email_coverage.contact_domains",
            "newest_thread_bundle_field": "email_coverage.newest_domain_thread_id",
            "domain_thread_search_status_bundle_field": "email_coverage.domain_thread_search_status",
            "newest_thread_rule": (
                "Read get_thread on the most recent matching company-domain thread before recency claims; "
                "if domain search returns no matches, record domain_thread_search_status=no_match."
            ),
        },
        "sent_freshness": f"in:sent newer_than:{window}d",
    }
    emails = ctx.get("contact_emails") or []
    if emails:
        ors = " OR ".join(emails)
        gmail["thread_search"] = f"from:({ors}) OR to:({ors}) newer_than:{window}d"
        domains = company_domains_from_emails(emails)
        if domains:
            domain_clause = " OR ".join(domains)
            gmail["domain_thread_search"] = (
                f"from:({domain_clause}) OR to:({domain_clause}) newer_than:{window}d"
            )
            gmail["most_recent_thread_search"] = {
                "query": gmail["domain_thread_search"],
                "sort": "newest_first",
                "read": "get_thread on the most recent matching thread",
            }
    if profile == "pipeline":
        gmail["_note"] = (
            "After running account_contacts and contact_roles, union all non-null Email values "
            "and derive company domains from those addresses. Re-run thread_search for the exact "
            "addresses and domain_thread_search for any email from those company domains: "
            "from:(<domains>) OR to:(<domains>) newer_than:{window}d. Read full thread bodies, "
            "not metadata only, and always read get_thread on the most recent matching domain thread."
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
            "source": "zoom",
            "source_contract": source_requirement(contracts, "zoom"),
            "q": ctx["account_name"],
            "from": ctx.get("created_date", f"last {window} days"),
            "to": ctx.get("today", "now"),
            "include_zoom_my_notes": True,
        }

    source_names = ["salesforce", "gmail", "google_calendar", "zoom"]
    internal = internal_plan(ctx, fields, model, profile=profile)
    if internal:
        source_names.extend(["slack", "google_drive"])
    out = {
        "profile": profile,
        "coverage_manifest": coverage_manifest_contract(contracts, profile, source_names),
        "source_contract": source_contract_summary(contracts, source_names),
        "salesforce": sf,
        "gmail": gmail,
        "zoom": zoom,
    }
    if calendar:
        out["calendar"] = calendar
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
