#!/usr/bin/env python3
"""Tests for analyze.py — pins the merged output. Run: python3 test_analyze.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE = os.path.join(HERE, "..", "scripts", "analyze.py")


def run(bundle):
    p = subprocess.run([sys.executable, ANALYZE], input=json.dumps(bundle),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    # Bundle with prior losses, no transcript.
    r = run({
        "rep_name": "Matthew Weigand",
        "compute_input": {
            "today": "2026-06-03",
            "opportunity": {"last_activity_date": "2026-06-03"},
            "contacts_engaged": 2,
        },
        "prior_opps": [
            {"Name": "X - May 2020", "StageName": "Lost", "CloseDate": "2020-06-02",
             "IsWon": False, "JSQ_Loss_Notes__c": "Won't spend $18K at one time."},
            {"Name": "X - 2019", "StageName": "Lost", "CloseDate": "2019-11-19", "IsWon": False},
            {"Name": "X - Renewal", "StageName": "Won", "CloseDate": "2021-01-01", "IsWon": True},
        ],
    })
    ok &= check("deal_metrics present", "flags" in r["deal_metrics"])
    ok &= check("call_execution null without transcript", r["call_execution"] is None)
    ok &= check("prior_losses == 2", r["account_history"]["prior_losses"] == 2)
    ok &= check("prior_wins == 1", r["account_history"]["prior_wins"] == 1)
    ok &= check("most_recent_loss reason carries note",
                "18K" in r["account_history"]["most_recent_loss"]["reason"])
    ok &= check("most_recent_loss is the newest (2020)",
                r["account_history"]["most_recent_loss"]["close_date"] == "2020-06-02")

    # Salesforce commonly returns "Closed Lost"; since the query is already scoped
    # to closed opportunities, IsWon false is the durable loss signal.
    r = run({
        "compute_input": {},
        "prior_opps": [
            {"Name": "Closed Lost Deal", "StageName": "Closed Lost", "CloseDate": "2026-01-01",
             "IsWon": False, "Lost_Reason__c": "Price"},
            {"Name": "Closed Won Deal", "StageName": "Closed Won", "CloseDate": "2025-01-01",
             "IsWon": True},
        ],
    })
    ok &= check("closed lost: prior_losses == 1", r["account_history"]["prior_losses"] == 1)
    ok &= check("closed lost: prior_wins == 1", r["account_history"]["prior_wins"] == 1)
    ok &= check("closed lost: reason carries through",
                r["account_history"]["most_recent_loss"]["reason"] == "Price")

    # Internal evidence is normalized into the computed footer: source-backed
    # Slack/Drive signals survive, unsourced claims do not, and coverage gaps
    # become explicit source_gaps.
    r = run({
        "compute_input": {},
        "internal_evidence": {
            "mode": "auto",
            "slack_mcp_checked": True,
            "slack_channels_searched": ["nw1", "nw1-partners"],
            "slack_channel_matches": ["nw1"],
            "deal_room": {"source": "slack", "coverage": "found", "source_ref": "slack:C123"},
            "linked_docs": [
                {"source": "google_drive", "title": "Proposal v3", "coverage": "read",
                 "source_ref": "drive:doc-1"},
                {"source": "google_drive", "title": "MSA", "coverage": "unavailable",
                 "source_ref": "drive:doc-2"},
            ],
            "signals": [
                {"type": "proposal_sent", "summary": "Proposal v3 was shared with procurement.",
                 "source_ref": "drive:doc-1", "confidence": "high"},
                {"type": "unsupported", "summary": "No source ref, so drop it."},
            ],
        },
    })
    internal = r["internal_evidence"]
    ok &= check("internal: deal room found", internal["deal_room"]["coverage"] == "found")
    ok &= check("internal: Slack MCP proof preserved",
                internal["deal_room"]["slack_mcp_checked"] is True
                and internal["deal_room"]["slack_channels_searched"] == ["nw1", "nw1-partners"])
    ok &= check("internal: linked docs preserved", len(internal["linked_docs"]) == 2)
    ok &= check("internal: unavailable linked doc gap",
                "linked_doc_unavailable" in internal["source_gaps"])
    ok &= check("internal: source-backed signal preserved", len(internal["signals"]) == 1)
    ok &= check("internal: signal source ref preserved",
                internal["signals"][0]["source_ref"] == "drive:doc-1")
    ok &= check("confidence: internal gap caps at Medium",
                r["confidence"]["max_label"] == "Medium"
                and "internal_gap" in r["confidence"]["reason_codes"])

    r = run({
        "compute_input": {},
        "calendar_evidence": {
            "coverage": "available",
            "historical_meetings": [
                {
                    "title": "Discovery",
                    "start": "2026-05-20T15:00:00Z",
                    "attendees": ["buyer@example.com"],
                    "source_ref": "calendar:event-1",
                }
            ],
            "upcoming_meetings": [
                {
                    "title": "Legal review",
                    "start": "2026-06-10T15:00:00Z",
                    "buyer_attendees": ["buyer@example.com"],
                    "conference_link": "https://meet.example/abc",
                    "source_ref": "calendar:event-2",
                }
            ],
        },
    })
    calendar = r["calendar_evidence"]
    ok &= check("calendar: historical meeting preserved", calendar["historical_meetings"][0]["title"] == "Discovery")
    ok &= check("calendar: upcoming meeting preserved", calendar["upcoming_meetings"][0]["source_ref"] == "calendar:event-2")
    ok &= check("calendar: buyer attendees preserved",
                calendar["upcoming_meetings"][0]["buyer_attendees"] == ["buyer@example.com"])
    ok &= check("calendar: buyer attendee prevents no-buyer flag",
                r["deal_metrics"]["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)

    r = run({"compute_input": {}, "calendar_evidence": {"coverage": "insufficient_context"}})
    ok &= check("calendar: source gap preserved", "calendar_context_missing" in r["calendar_evidence"]["source_gaps"])

    r = run({
        "compute_input": {
            "today": "2026-06-06",
            "emails": [{"direction": "out", "date": "2026-05-01"}],
        },
        "connector_status": {"email": "timeout"},
    })
    ok &= check("connector status: top-level status reaches compute",
                "email_connector_degraded" in r["deal_metrics"]["coverage_gaps"])
    ok &= check("connector status: degraded email neutralizes stale flag",
                r["deal_metrics"]["flags"]["email_data_stale"] is False)
    ok &= check("confidence: degraded email caps at Low",
                r["confidence"]["max_label"] == "Low"
                and "email_coverage_gap" in r["confidence"]["reason_codes"])

    r = run({
        "compute_input": {},
        "internal_evidence": {"mode": "auto", "coverage": "deal_room_missing"},
    })
    ok &= check("internal: top-level missing coverage preserved",
                r["internal_evidence"]["deal_room"]["coverage"] == "deal_room_missing")
    ok &= check("internal: missing room gap",
                "deal_room_missing" in r["internal_evidence"]["source_gaps"])
    ok &= check("internal: missing Slack proof gap",
                "slack_coverage_unproven" in r["internal_evidence"]["source_gaps"])

    r = run({
        "compute_input": {
            "today": "2026-06-06",
            "observed_participants": ["vanda@nw1.com"],
        },
        "email_coverage": {
            "contact_domains": ["nw1.com"],
            "searched_domains": ["nw1.com"],
            "newest_domain_thread_id": "gmail:thread-20260605",
        },
        "internal_evidence": {
            "mode": "auto",
            "slack_mcp_checked": True,
            "slack_channels_searched": ["nw1", "nw1-partners"],
            "slack_channel_matches": ["nw1"],
            "deal_room": {"source": "slack", "coverage": "found", "source_ref": "slack:Cnw1"},
        },
    })
    ok &= check("NW1-like: Gmail newest-domain proof avoids coverage gap",
                "email_newest_thread_coverage_gap" not in r["deal_metrics"]["coverage_gaps"])
    ok &= check("NW1-like: Slack room found via Slack proof",
                r["internal_evidence"]["deal_room"]["coverage"] == "found"
                and r["internal_evidence"]["source_gaps"] == [])
    ok &= check("NW1-like: clean coverage can be High",
                r["confidence"]["max_label"] == "High")

    # Empty-ish bundle: null-safe, no prior history.
    r = run({"compute_input": {}})
    ok &= check("empty: no crash", "deal_metrics" in r)
    ok &= check("empty: no prior history", r["account_history"]["prior_losses"] == 0)
    ok &= check("empty: history summary", "No prior closed deals" in r["account_history"]["summary"])
    ok &= check("empty: internal evidence null", r["internal_evidence"] is None)
    ok &= check("empty: calendar evidence null", r["calendar_evidence"] is None)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
