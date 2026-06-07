#!/usr/bin/env python3
"""Tests for plan.py — pins the emitted queries. Run: python3 test_plan.py"""
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


def run_fail(ctx):
    return subprocess.run([sys.executable, PLAN], input=json.dumps(ctx),
                          capture_output=True, text=True)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    non_added_arr_money_field = "Calculated_A" + "CV__c"

    full = run({
        "deal_name": "Providence Investments", "opp_id": "006X", "account_id": "001X",
        "account_name": "Providence Investments",
        "contact_emails": ["a@x.com", "b@x.com"],
        "created_date": "2026-05-21", "today": "2026-06-03",
    })
    opp = full["salesforce"]["opportunity"]
    # The bug guard: Added ARR is Added ARR only, with no non-Added-ARR money fallback.
    ok &= check("opp query uses Added_ARR__c", "Added_ARR__c" in opp)
    ok &= check("opp query has no non-Added-ARR money field",
                non_added_arr_money_field not in opp and "Amount__c" not in opp and ", Amount," not in opp and "(Amount," not in opp)
    ok &= check("prior opps filter IsClosed", "IsClosed = true" in full["salesforce"]["prior_account_opps"])
    ok &= check("history ordered ASC", "ORDER BY CreatedDate ASC" in full["salesforce"]["history"])
    ok &= check("gmail sent_freshness present", full["gmail"]["sent_freshness"] == "in:sent newer_than:90d")
    ok &= check("gmail thread_search uses emails", "a@x.com" in full["gmail"]["thread_search"])
    ok &= check("gmail domain search emitted",
                full["gmail"]["domain_thread_search"] == "from:(x.com) OR to:(x.com) newer_than:90d")
    ok &= check("gmail newest domain thread required",
                full["gmail"]["most_recent_thread_search"]["sort"] == "newest_first")
    ok &= check("calendar emitted", full["calendar"]["source"] == "google_calendar")
    ok &= check("calendar uses attendees", "a@x.com" in full["calendar"]["query"]["attendees"])
    ok &= check("calendar has future lookup", full["calendar"]["future"]["to"] == "next 60 days")
    ok &= check("zoom q set", full["zoom"]["q"] == "Providence Investments")
    ok &= check("contact_roles is getRelatedRecords", full["salesforce"]["contact_roles"]["tool"] == "getRelatedRecords")
    ok &= check("contact_roles read_fields includes Role", "Role" in full["salesforce"]["contact_roles"]["read_fields"])
    ok &= check("contact_roles read_fields includes IsPrimary", "IsPrimary" in full["salesforce"]["contact_roles"]["read_fields"])
    ok &= check("opp query includes Legal_Status__c", "Legal_Status__c" in opp)
    ok &= check("opp query includes Decision_Maker__c", "Decision_Maker__c" in opp)

    # Partial context: only what the inputs allow.
    early = run({"deal_name": "NW1"})
    ok &= check("early: find present", "find" in early["salesforce"])
    ok &= check("early: no opp query yet", "opportunity" not in early["salesforce"])
    ok &= check("early: sent_freshness still present", "sent_freshness" in early["gmail"])
    ok &= check("early: no thread_search without emails", "thread_search" not in early["gmail"])
    ok &= check("early: calendar uses deal name", early["calendar"]["query"]["terms"] == ["NW1"])
    empty = run({})
    ok &= check("empty: calendar gap named", empty["calendar"]["coverage"] == "insufficient_context")

    blocked = run_fail({"mode": "pipeline", "today": "2026-06-06", "owner_id": "005X"})
    ok &= check("deal surface: pipeline mode rejected",
                blocked.returncode != 0 and "does not emit pipeline" in blocked.stderr)

    # Internal evidence (Slack + Drive) — auto can search channel names; force permits
    # message-body fallback.
    auto = run({"account_name": "Providence Investments"})
    ok &= check("internal auto: channel-name lookup emitted",
                auto["internal_evidence"]["slack"]["query_type"] == "channel_name_lookup")
    ok &= check("internal auto: broad search not allowed",
                auto["internal_evidence"]["broad_search_allowed"] is False
                and auto["internal_evidence"]["slack"]["broad_search_allowed"] is False)
    ok &= check("internal auto: Providence hyphen channel variant emitted",
                "providence-investments" in auto["internal_evidence"]["slack"]["terms"])
    forced = run({"account_name": "Providence Investments", "internal": "force"})
    ok &= check("internal force: bounded fallback lookup emitted",
                forced["internal_evidence"]["slack"]["query_type"] == "bounded_fallback_lookup")
    ok &= check("internal force: broad search allowed",
                forced["internal_evidence"]["broad_search_allowed"] is True)
    ok &= check("internal force: deal depth caps applied",
                forced["internal_evidence"]["max_messages"] == 80
                and forced["internal_evidence"]["max_linked_docs"] == 5)
    ok &= check("internal force: linked docs emitted",
                forced["internal_evidence"]["linked_docs"]["source"] == "google_drive")
    disabled = run({"account_name": "Providence Investments", "internal": "off"})
    ok &= check("internal off: no internal evidence emitted",
                "internal_evidence" not in disabled)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
