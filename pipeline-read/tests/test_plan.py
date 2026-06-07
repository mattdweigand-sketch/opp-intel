#!/usr/bin/env python3
"""Tests for plan.py — pins both the pipeline (portfolio) and per-deal query phases.
Run: python3 test_plan.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, "..", "scripts", "plan.py")


def run(ctx):
    p = subprocess.run([sys.executable, PLAN], input=json.dumps(ctx),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    non_added_arr_money_field = "Calculated_A" + "CV__c"

    # --- Pipeline phase, no owner_id: must ask for getUserInfo first, no opp query yet.
    p1 = run({"mode": "pipeline", "today": "2026-06-04", "window": "current_quarter"})
    ok &= check("pipeline: whoami emitted when owner unknown", p1["salesforce"].get("whoami", {}).get("tool") == "getUserInfo")
    ok &= check("pipeline: no pipeline query without owner", "pipeline" not in p1["salesforce"])
    ok &= check("pipeline: current_quarter starts May 1 for Feb 1 fiscal year",
                p1["window"]["close_on_or_after"] == "2026-05-01")
    ok &= check("pipeline: current_quarter ends July 31 for Feb 1 fiscal year",
                p1["window"]["close_on_or_before"] == "2026-07-31")
    ok &= check("pipeline: fiscal-year start surfaced",
                p1["window"]["fiscal_year_start"] == "02-01")
    ok &= check("pipeline: large_run_threshold surfaced", p1["large_run_threshold"] == 15)
    ok &= check("pipeline: read default runs Calendar and Slack/Drive",
                p1["per_deal_connectors"] == ["Salesforce", "Gmail", "Google Calendar", "Zoom", "Slack", "Google Drive"])

    # --- Pipeline phase, owner_id known + named quarter window: scoped SOQL with the right WHERE clauses.
    pq = run({"mode": "pipeline", "today": "2026-06-04", "owner_id": "005XX"})
    qq = pq["salesforce"]["pipeline"]
    ok &= check("pipeline: current quarter lower bound applied", "CloseDate >= 2026-05-01" in qq)
    ok &= check("pipeline: current quarter upper bound applied", "CloseDate <= 2026-07-31" in qq)

    # --- Next-quarter option follows the same Feb 1 fiscal-year calendar.
    pn = run({"mode": "pipeline", "today": "2026-06-04", "window": "next_quarter", "owner_id": "005XX"})
    nq = pn["salesforce"]["pipeline"]
    ok &= check("pipeline: next_quarter window named", pn["window"]["name"] == "next_quarter")
    ok &= check("pipeline: next_quarter starts Aug 1", pn["window"]["close_on_or_after"] == "2026-08-01")
    ok &= check("pipeline: next_quarter ends Oct 31", pn["window"]["close_on_or_before"] == "2026-10-31")
    ok &= check("pipeline: next_quarter lower bound applied", "CloseDate >= 2026-08-01" in nq)
    ok &= check("pipeline: next_quarter upper bound applied", "CloseDate <= 2026-10-31" in nq)

    pnf = run({"mode": "pipeline", "today": "2026-06-04", "next_quarter": True, "owner_id": "005XX"})
    ok &= check("pipeline: next_quarter flag maps to next_quarter window",
                pnf["window"]["name"] == "next_quarter")

    # --- January belongs to the Nov-Jan fiscal quarter, not a calendar Q1.
    pj = run({"mode": "pipeline", "today": "2026-01-15", "owner_id": "005XX"})
    ok &= check("pipeline: Jan current quarter starts prior Nov",
                pj["window"]["close_on_or_after"] == "2025-11-01")
    ok &= check("pipeline: Jan current quarter ends Jan 31",
                pj["window"]["close_on_or_before"] == "2026-01-31")

    # --- Pipeline phase, owner_id known + Nd window: scoped SOQL with the right WHERE clauses.
    p2 = run({"mode": "pipeline", "today": "2026-06-04", "window": "30d", "owner_id": "005XX"})
    q = p2["salesforce"]["pipeline"]
    ok &= check("pipeline: owner filter present", "OwnerId = '005XX'" in q)
    ok &= check("pipeline: open filter present", "IsClosed = false" in q)
    ok &= check("pipeline: window upper bound applied", "CloseDate <= 2026-07-04" in q)
    ok &= check("pipeline: numeric window keeps legacy no-lower-bound behavior", "CloseDate >=" not in q)
    ok &= check("pipeline: ordered by CloseDate ASC", "ORDER BY CloseDate ASC" in q)
    ok &= check("pipeline: account name relationship field selected", "Account.Name" in q)
    ok &= check("pipeline: uses Added ARR only for Added ARR",
                "Added_ARR__c" in q and non_added_arr_money_field not in q and "Amount__c" not in q and ", Amount," not in q)
    ok &= check("pipeline: 30d window end is 2026-07-04", p2["window"]["close_on_or_before"] == "2026-07-04")

    # --- Forecast portfolio phase: selected amount basis, category, posture, and internal controls.
    pf = run({
        "mode": "pipeline", "today": "2026-06-04", "window": "30d", "owner_id": "005XX",
        "forecast": True, "posture": "defend-commit", "amount_basis": "added_arr",
    })
    fq = pf["salesforce"]["pipeline"]
    ok &= check("forecast: posture normalized", pf["forecast"]["posture"] == "defend_commit")
    ok &= check("forecast: amount basis surfaced", pf["forecast"]["amount_basis"] == "added_arr")
    ok &= check("forecast: category field selected", "ForecastCategoryName" in fq)
    ok &= check("forecast: amount field selected", "Added_ARR__c" in fq)
    ok &= check("forecast: no phantom mapping fields in pipeline query", "Slack_Channel__c" not in fq and "Deal_Room_URL__c" not in fq)
    ok &= check("forecast: default internal is auto", pf["forecast"]["internal"] == "auto")
    ok &= check("forecast: connectors include Calendar, Slack, and Drive when internal on",
                pf["per_deal_connectors"] == ["Salesforce", "Gmail", "Google Calendar", "Zoom", "Slack", "Google Drive"])

    poff = run({
        "mode": "pipeline", "today": "2026-06-04", "owner_id": "005XX",
        "forecast": True, "internal": "off",
    })
    ok &= check("internal off: no internal plan emitted", "internal_evidence" not in poff)
    ok &= check("internal off: no Slack mapping fields selected",
                "Slack_Channel__c" not in poff["salesforce"]["pipeline"])
    ok &= check("internal off: connectors exclude Slack/Drive but keep Calendar",
                poff["per_deal_connectors"] == ["Salesforce", "Gmail", "Google Calendar", "Zoom"])

    # --- Per-deal phase: unchanged deal-read contract (no mode key => deal plan).
    full = run({
        "deal_name": "Providence Investments", "opp_id": "006X", "account_id": "001X",
        "account_name": "Providence Investments",
        "contact_emails": ["a@x.com", "b@x.com"],
        "created_date": "2026-05-21", "today": "2026-06-03",
    })
    opp = full["salesforce"]["opportunity"]
    ok &= check("per-deal: opp query uses Added ARR only for Added ARR",
                "Added_ARR__c" in opp and non_added_arr_money_field not in opp and "Amount__c" not in opp and ", Amount," not in opp and "(Amount," not in opp)
    ok &= check("per-deal: prior opps filter IsClosed", "IsClosed = true" in full["salesforce"]["prior_account_opps"])
    ok &= check("per-deal: history ordered ASC", "ORDER BY CreatedDate ASC" in full["salesforce"]["history"])
    ok &= check("per-deal: gmail sent_freshness present", full["gmail"]["sent_freshness"] == "in:sent newer_than:90d")
    ok &= check("per-deal: gmail domain search emitted",
                full["gmail"]["domain_thread_search"] == "from:(x.com) OR to:(x.com) newer_than:90d")
    ok &= check("per-deal: most recent domain thread required",
                full["gmail"]["most_recent_thread_search"]["read"] == "get_thread on the most recent matching thread")
    ok &= check("per-deal: calendar emitted", full["calendar"]["source"] == "google_calendar")
    ok &= check("per-deal: calendar future lookup", full["calendar"]["future"]["to"] == "next 30 days")
    ok &= check("per-deal: contact_roles is getRelatedRecords", full["salesforce"]["contact_roles"]["tool"] == "getRelatedRecords")
    ok &= check("per-deal: zoom q set", full["zoom"]["q"] == "Providence Investments")

    missing = run({
        "deal_name": "Providence Investments", "account_name": "Providence Investments",
        "forecast": True, "internal": "auto",
    })
    ok &= check("internal auto: channel-name lookup emitted",
                missing["internal_evidence"]["slack"]["query_type"] == "channel_name_lookup")
    ok &= check("internal auto: message-body search still disabled",
                missing["internal_evidence"]["slack"]["broad_search_allowed"] is False)
    ok &= check("internal auto: Providence channel hyphen variant emitted",
                "providence-investments" in missing["internal_evidence"]["slack"]["terms"])

    default_internal = run({
        "deal_name": "Providence Investments", "account_name": "Providence Investments",
    })
    ok &= check("internal default: channel lookup emitted",
                default_internal["internal_evidence"]["mode"] == "auto"
                and default_internal["internal_evidence"]["slack"]["query_type"] == "channel_name_lookup")

    nw1 = run({
        "deal_name": "NW1 - FA + GPX", "account_name": "NW1",
    })
    terms = nw1["internal_evidence"]["slack"]["terms"]
    ok &= check("internal auto: NW1 channel aliases include nwl",
                "NW1" in terms and "nwl" in terms)

    fund_admin = run({
        "deal_name": "Fund Admin Sales", "account_name": "Fund Admin Sales",
    })
    ok &= check("internal auto: underscore Slack channel variant emitted",
                "fund_admin_sales" in fund_admin["internal_evidence"]["slack"]["terms"])

    force = run({
        "deal_name": "Providence Investments", "account_name": "Providence Investments",
        "forecast": True, "internal": "force",
    })
    ok &= check("internal force: bounded fallback lookup emitted",
                force["internal_evidence"]["slack"]["query_type"] == "bounded_fallback_lookup")
    ok &= check("internal force: broad search allowed only there",
                force["internal_evidence"]["slack"]["broad_search_allowed"] is True)
    ok &= check("internal force: pipeline depth caps applied",
                force["internal_evidence"]["max_messages"] == 40
                and force["internal_evidence"]["max_linked_docs"] == 3)

    # --- Workflow-tool inbox sweep: Gmail query targets known notification senders scoped by name.
    eca = run({"deal_name": "Emerald City Associates", "account_name": "Emerald City Associates",
               "today": "2026-06-04"})
    ws = eca["gmail"].get("workflow_signals", "")
    ok &= check("workflow: workflow_signals query emitted", bool(ws))
    ok &= check("workflow: targets ironclad sender domain", "ironcladapp.com" in ws)
    ok &= check("workflow: scoped to the account name", "Emerald City" in ws)
    ok &= check("workflow: keeps existing gmail keys intact",
                eca["gmail"]["sent_freshness"] == "in:sent newer_than:90d")
    ok &= check("workflow: registry-mapping note present", "_workflow_note" in eca["gmail"])

    # No scoping term => no workflow query (backward compatible).
    no_scope = run({"opp_id": "006X", "today": "2026-06-04"})
    ok &= check("workflow: no scope term means no workflow_signals",
                "workflow_signals" not in no_scope["gmail"])

    # risk-model.json carries the workflow_tools registry including the ironclad domain.
    model_path = os.path.join(HERE, "..", "..", "core", "config", "risk-model.json")
    with open(model_path) as f:
        rm = json.load(f)
    wt = rm["internal_evidence"]["workflow_tools"]
    ok &= check("workflow: registry present in risk-model.json", isinstance(wt, list) and len(wt) > 0)
    ok &= check("workflow: registry includes ironclad domain",
                any(e.get("domain") == "ironcladapp.com" and e.get("signal_type") == "clm_stage" for e in wt))

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
