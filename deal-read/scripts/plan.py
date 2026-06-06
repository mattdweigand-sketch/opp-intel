#!/usr/bin/env python3
"""Emit the exact Salesforce/Gmail/Zoom queries for a deal-read run.

The model still EXECUTES the queries (only it can call the MCP connectors), but it
no longer improvises them — field names come from sf-fields.json, the email window
from risk-model.json. This removes SOQL field guesses (the 'Amount' error) and bakes
in the in:sent freshness query (the NW1 staleness fix).

Usage: python3 plan.py            # reads context JSON on stdin, prints query plan
Context keys (all optional — emit what the inputs allow):
  {"deal_name","opp_id","account_id","account_name","contact_emails":[...],
   "created_date","today"}
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "..", "core", "config"))


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


def normalize_token(value):
    return str(value or "").strip().lower().replace("-", "_")


def internal_mode_for(ctx, model):
    # An explicit --internal flag always wins. Otherwise the chosen default lives in
    # config (internal_evidence.default). In auto mode, only mapped rooms run by default.
    # To turn it off, set that config default to "off" or pass --internal off.
    if ctx.get("internal") is not None:
        return normalize_token(ctx.get("internal"))
    cfg = model.get("internal_evidence", {})
    return normalize_token((cfg.get("default_by_profile") or {}).get("deal") or cfg.get("default", "auto"))


def internal_plan(ctx, fields, model):
    mode = internal_mode_for(ctx, model)
    if mode not in {"auto", "off", "force"}:
        raise ValueError(f"unknown internal mode: {ctx.get('internal')}")
    if mode == "off":
        return None

    cfg = model.get("internal_evidence", {})
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
        "max_messages": cfg.get("max_messages_per_room", 80),
        "max_linked_docs": cfg.get("max_linked_docs_per_room", 5),
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


def main():
    ctx = json.load(sys.stdin) if not sys.stdin.isatty() else {}
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
        sf["contact_roles"] = {
            "tool": "getRelatedRecords",
            "sobject-name": "Opportunity",
            "id": oid,
            "relationship-path": fields["contact_roles_relationship"],
            # getRelatedRecords takes no field filter; read_fields tells the model
            # which fields to pull off each role. Role/IsPrimary ground the champion
            # and economic_buyer dimensions instead of guessing from job titles.
            "read_fields": fields["contact_fields"],
        }
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

    gmail = {"sent_freshness": f"in:sent newer_than:{window}d"}
    emails = ctx.get("contact_emails") or []
    if emails:
        ors = " OR ".join(emails)
        gmail["thread_search"] = f"from:({ors}) OR to:({ors}) newer_than:{window}d"

    zoom = {}
    if ctx.get("account_name"):
        zoom = {
            "q": ctx["account_name"],
            "from": ctx.get("created_date", f"last {window} days"),
            "to": ctx.get("today", "now"),
            "include_zoom_my_notes": True,
        }

    out = {"salesforce": sf, "gmail": gmail, "zoom": zoom}
    try:
        internal = internal_plan(ctx, fields, model)
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)
    if internal:
        out["internal_evidence"] = internal

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
