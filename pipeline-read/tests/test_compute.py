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
    ok &= check("empty: no hygiene flags leak into a non-hygiene run",
                "no_contact_roles" not in r["flags"] and "no_champion" not in r["flags"]
                and "missing_next_step" not in r["flags"])

    # Fixture 7: hygiene run emits the CRM data-quality flags. Empty contact roles, no
    # champion, blank next step, and activity older than the hygiene threshold (30d).
    r = run({
        "hygiene": True,
        "today": "2026-06-05",
        "opportunity": {"close_date": "2026-05-01", "last_activity_date": "2026-04-01"},
        "logged_contact_roles": 0,
        "champion_contact_roles": 0,
        "next_step": "",
    })
    ok &= check("hygiene: no_contact_roles True", r["flags"]["no_contact_roles"] is True)
    ok &= check("hygiene: no_champion True", r["flags"]["no_champion"] is True)
    ok &= check("hygiene: missing_next_step True", r["flags"]["missing_next_step"] is True)
    ok &= check("hygiene: overdue_close True (close in past)", r["flags"]["overdue_close"] is True)
    ok &= check("hygiene: stale_activity True at 30d threshold", r["flags"]["stale_activity"] is True)

    r = run({
        "hygiene": True,
        "today": "2026-06-05",
        "opportunity": {"close_date": "2026-06-20", "stage_entered_date": "2026-06-01"},
        "calendar_evidence": {"coverage": "available", "upcoming_meetings": []},
    })
    ok &= check("hygiene: Calendar risk flags suppressed",
                r["flags"]["calendar_no_upcoming_late_stage"] is False
                and r["flags"]["calendar_no_recent_meeting_after_stage_move"] is False
                and r["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)

    # Clean hygiene record: roles logged, champion present, next step set, recent activity.
    r = run({
        "hygiene": True,
        "today": "2026-06-05",
        "opportunity": {"close_date": "2026-07-30", "last_activity_date": "2026-06-02"},
        "logged_contact_roles": 3,
        "champion_contact_roles": 1,
        "next_step": "Send MSA for legal review by 2026-06-12",
    })
    ok &= check("hygiene clean: no_contact_roles False", r["flags"]["no_contact_roles"] is False)
    ok &= check("hygiene clean: no_champion False", r["flags"]["no_champion"] is False)
    ok &= check("hygiene clean: missing_next_step False", r["flags"]["missing_next_step"] is False)
    ok &= check("hygiene clean: stale_activity False", r["flags"]["stale_activity"] is False)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
