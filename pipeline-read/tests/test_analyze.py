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

    r = run({
        "compute_input": {},
        "calendar_evidence": {
            "coverage": "available",
            "history": [{"title": "Discovery", "start_time": "2026-05-20T15:00:00Z"}],
            "future": [{"title": "Renewal review", "start_time": "2026-06-10T15:00:00Z",
                        "buyer_attendees": ["buyer@example.com"]}],
        },
    })
    ok &= check("calendar evidence preserved", r["calendar_evidence"]["upcoming_meetings"][0]["title"] == "Renewal review")
    ok &= check("calendar buyer attendees preserved",
                r["calendar_evidence"]["upcoming_meetings"][0]["buyer_attendees"] == ["buyer@example.com"])
    ok &= check("calendar buyer attendee prevents no-buyer flag",
                r["deal_metrics"]["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)

    r = run({
        "compute_input": {
            "today": "2026-06-06",
            "emails": [{"direction": "out", "date": "2026-05-01"}],
        },
        "connector_status": {"email": "timeout"},
    })
    ok &= check("connector status reaches compute",
                "email_connector_degraded" in r["deal_metrics"]["coverage_gaps"])

    r = run({
        "compute_input": {
            "today": "2026-06-06",
            "emails": [{"direction": "out", "date": "2026-04-21"}],
        },
        "email_coverage": {"latest_sent_date": "2026-06-05"},
    })
    ok &= check("email coverage reaches compute",
                "email_thread_coverage_gap" in r["deal_metrics"]["coverage_gaps"])

    # Empty-ish bundle: null-safe, no prior history.
    r = run({"compute_input": {}})
    ok &= check("empty: no crash", "deal_metrics" in r)
    ok &= check("empty: no prior history", r["account_history"]["prior_losses"] == 0)
    ok &= check("empty: history summary", "No prior closed deals" in r["account_history"]["summary"])
    ok &= check("empty: calendar evidence null", r["calendar_evidence"] is None)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
