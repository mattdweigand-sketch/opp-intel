#!/usr/bin/env python3
"""Tests for compute.py — pins the deterministic flags against real deal fixtures.

No pytest needed. Run: python3 test_compute.py
Exits non-zero if any check fails, so it can gate edits in CI.
Fixtures use wide margins so they survive reasonable threshold retuning.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPUTE = os.path.join(HERE, "..", "scripts", "compute.py")


def run(snapshot):
    p = subprocess.run(
        [sys.executable, COMPUTE],
        input=json.dumps(snapshot),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    # Fixture 1: NW1 staleness — SF/call activity 34 days newer than newest email.
    # This is the failure that shipped a redundant-draft suggestion; it must flag.
    r = run({
        "today": "2026-06-03",
        "opportunity": {"last_activity_date": "2026-05-26"},
        "latest_call_date": "2026-05-26",
        "emails": [
            {"direction": "out", "date": "2026-04-21"},
            {"direction": "in", "date": "2026-04-22"},
        ],
    })
    ok &= check("NW1: email_data_stale True", r["flags"]["email_data_stale"] is True)
    ok &= check("NW1: recent_rep_outbound False", r["flags"]["recent_rep_outbound"] is False)

    # Fixture 2: Providence — rep emailed today; data fresh, draft should be gated.
    r = run({
        "today": "2026-06-03",
        "opportunity": {"last_activity_date": "2026-06-03"},
        "latest_call_date": "2026-05-21",
        "emails": [
            {"direction": "out", "date": "2026-06-03"},
            {"direction": "in", "date": "2026-06-03"},
        ],
    })
    ok &= check("Providence: email_data_stale False", r["flags"]["email_data_stale"] is False)
    ok &= check("Providence: recent_rep_outbound True", r["flags"]["recent_rep_outbound"] is True)

    # Fixture 3: stage velocity + close-date slippage.
    r = run({
        "today": "2026-06-03",
        "opportunity": {
            "created_date": "2025-01-15",
            "close_date": "2026-06-30",
            "stage_entered_date": "2026-05-01",
            "close_date_history": ["2026-03-31", "2026-05-31", "2026-06-30"],
        },
    })
    ok &= check("stage: days_in_current_stage 33", r["days_in_current_stage"] == 33)
    ok &= check("slippage: times_pushed 2", r["close_date_slippage"]["times_pushed"] == 2)
    ok &= check("slippage: total_slip_days 91", r["close_date_slippage"]["total_slip_days"] == 91)
    ok &= check("slippage: close_date_slipped True", r["flags"]["close_date_slipped"] is True)

    # Fixture 4: single-threaded + stale activity.
    r = run({
        "today": "2026-06-03",
        "opportunity": {"last_activity_date": "2026-05-10"},
        "contacts_engaged": 1,
    })
    ok &= check("threading: single_threaded True", r["flags"]["single_threaded"] is True)
    ok &= check("activity: stale_activity True", r["flags"]["stale_activity"] is True)

    # Fixture 5: contacts_engaged derived from observed participants + role floor.
    # Two distinct prospect people observed (case/space-insensitive dedup), one
    # logged role; the union floor is 2, so single_threaded must be False.
    r = run({
        "today": "2026-06-03",
        "opportunity": {"last_activity_date": "2026-06-03"},
        "observed_participants": ["Jane@x.com", "jane@x.com ", "Bob@x.com"],
        "logged_contact_roles": 1,
    })
    ok &= check("derive: contacts_engaged 2", r["contacts_engaged"] == 2)
    ok &= check("derive: single_threaded False", r["flags"]["single_threaded"] is False)

    # Logged roles can exceed observed and act as the floor.
    r = run({"observed_participants": ["a@x.com"], "logged_contact_roles": 3})
    ok &= check("floor: contacts_engaged 3", r["contacts_engaged"] == 3)

    # Explicit contacts_engaged still wins (back-compat path untouched).
    r = run({"contacts_engaged": 1, "observed_participants": ["a@x.com", "b@x.com"]})
    ok &= check("explicit count wins", r["contacts_engaged"] == 1)

    # Fixture 7: MEDDPICC grounding from structured fields.
    # Roles drive economic_buyer/champion; legal_status drives paper_not_started.
    r = run({
        "roles": ["Champion", "Economic Buyer", "Influencer"],
        "opportunity": {"legal_status": "NA"},
    })
    ok &= check("meddpicc: economic_buyer_named True (role)", r["flags"]["economic_buyer_named"] is True)
    ok &= check("meddpicc: champion_identified True", r["flags"]["champion_identified"] is True)
    ok &= check("meddpicc: paper_not_started True (NA)", r["flags"]["paper_not_started"] is True)

    # Economic buyer via Decision_Maker__c presence, no roles list; legal advanced.
    r = run({
        "opportunity": {"economic_buyer_named": True, "legal_status": "Approved"},
    })
    ok &= check("meddpicc: economic_buyer_named True (decision_maker)", r["flags"]["economic_buyer_named"] is True)
    ok &= check("meddpicc: champion_identified False (no role)", r["flags"]["champion_identified"] is False)
    ok &= check("meddpicc: paper_not_started False (Approved)", r["flags"]["paper_not_started"] is False)

    # Legal status absent is "not asserted", not a risk; case-insensitive match.
    r = run({"opportunity": {"legal_status": "under review"}})
    ok &= check("meddpicc: paper_not_started True (case-insensitive)", r["flags"]["paper_not_started"] is True)
    r = run({"roles": ["influencer"]})
    ok &= check("meddpicc: economic_buyer_named False (influencer only)", r["flags"]["economic_buyer_named"] is False)

    # Calendar flags are deterministic and only fire when Calendar coverage is available.
    r = run({
        "today": "2026-06-03",
        "opportunity": {"close_date": "2026-06-20"},
        "calendar_evidence": {"coverage": "available", "historical_meetings": [], "upcoming_meetings": []},
    })
    ok &= check("calendar: no upcoming late-stage True", r["flags"]["calendar_no_upcoming_late_stage"] is True)

    r = run({
        "today": "2026-06-03",
        "opportunity": {"stage_entered_date": "2026-05-29", "close_date": "2026-07-15"},
        "calendar_evidence": {
            "coverage": "available",
            "historical_meetings": [{"start": "2026-05-20T15:00:00Z"}],
            "upcoming_meetings": [{"start": "2026-06-10T15:00:00Z", "attendees": ["buyer@example.com"]}],
        },
    })
    ok &= check("calendar: no recent meeting after stage move True",
                r["flags"]["calendar_no_recent_meeting_after_stage_move"] is True)
    ok &= check("calendar: buyer attendee prevents attendee flag",
                r["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)

    r = run({
        "today": "2026-06-03",
        "opportunity": {"close_date": "2026-06-20"},
        "calendar_evidence": {"coverage": "available", "upcoming_meetings": [{"start": "2026-06-10T15:00:00Z", "attendees": []}]},
    })
    ok &= check("calendar: next meeting no buyer attendees True",
                r["flags"]["calendar_next_meeting_no_buyer_attendees"] is True)
    ok &= check("calendar: upcoming meeting prevents no-upcoming flag",
                r["flags"]["calendar_no_upcoming_late_stage"] is False)

    r = run({
        "today": "2026-06-03",
        "opportunity": {"close_date": "2026-06-20", "stage_entered_date": "2026-05-29"},
        "calendar_evidence": {"coverage": "unavailable", "source_gaps": ["calendar_unavailable"]},
    })
    ok &= check("calendar: unavailable does not create risk flags",
                r["flags"]["calendar_no_upcoming_late_stage"] is False
                and r["flags"]["calendar_no_recent_meeting_after_stage_move"] is False
                and r["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)

    r = run({
        "today": "2026-06-03",
        "opportunity": {"close_date": "2026-06-20", "StageName": "Closed Won"},
        "calendar_evidence": {"coverage": "available", "upcoming_meetings": []},
    })
    ok &= check("calendar: closed opp suppresses no-upcoming flag",
                r["flags"]["calendar_no_upcoming_late_stage"] is False)

    # Fixture 6: empty input is null-safe, no crash, every flag False.
    r = run({})
    ok &= check("empty: flags all False", all(v is False for v in r["flags"].values()))

    r = run({
        "today": "2026-06-06",
        "observed_participants": ["solo@prospect.com"],
        "email_coverage": {
            "contact_domains": ["prospect.com"],
            "searched_domains": ["prospect.com"],
        },
    })
    ok &= check("email coverage: newest domain thread proof required",
                "email_newest_thread_coverage_gap" in r["coverage_gaps"])
    ok &= check("email coverage: newest thread gap suppresses single-thread without SF basis",
                r["flags"]["single_threaded"] is False)

    r = run({
        "today": "2026-06-06",
        "observed_participants": ["solo@prospect.com"],
        "email_coverage": {
            "contact_domains": ["prospect.com"],
            "searched_domains": ["prospect.com"],
            "domain_thread_search_status": "no_match",
        },
    })
    ok &= check("email coverage: no-match domain proof avoids newest-thread gap",
                "email_newest_thread_coverage_gap" not in r["coverage_gaps"])

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
