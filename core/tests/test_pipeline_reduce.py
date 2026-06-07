#!/usr/bin/env python3
"""Tests for pipeline_reduce.py per-deal evidence compaction."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE_SCRIPTS = os.path.join(ROOT, "core", "scripts")


def run(script, payload):
    proc = subprocess.run(
        [sys.executable, os.path.join(CORE_SCRIPTS, script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip())
    return json.loads(proc.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    gather = {
        "rep_name": "Matt",
        "internal_domains": ["junipersquare.com"],
        "prospect_domains": ["acme.com"],
        "compute_input": {
            "today": "2026-06-06",
            "opportunity": {"last_activity_date": "2026-06-05"},
            "logged_contact_roles": 1,
        },
        "email_threads": [
            {
                "id": "thread-1",
                "subject": "Acme - Next Steps",
                "messages": [
                    {
                        "id": "msg-1",
                        "date": "2026-06-01T15:00:00Z",
                        "from": "matt@junipersquare.com",
                        "to": ["buyer@acme.com"],
                        "body": "Large body that should not be copied into the reducer output.",
                    },
                    {
                        "id": "msg-2",
                        "date": "2026-06-03T15:00:00Z",
                        "from": "buyer@acme.com",
                        "to": ["matt@junipersquare.com"],
                        "body": "Another large body that should not survive.",
                    },
                ],
            }
        ],
        "calendar_evidence": {
            "coverage": "available",
            "future": [
                {
                    "id": "cal-1",
                    "title": "Acme legal review",
                    "start": "2026-06-10T15:00:00Z",
                    "attendees": ["buyer@acme.com", "matt@junipersquare.com"],
                    "description": "Calendar raw description should not survive reduction.",
                }
            ],
        },
        "zoom_meetings": [
            {
                "uuid": "zoom-1",
                "topic": "Acme discovery",
                "start_time": "2026-06-04T15:00:00Z",
                "attendees": ["buyer@acme.com", "matt@junipersquare.com"],
                "transcript": "This raw transcript must not survive.",
            }
        ],
        "internal_evidence": {
            "mode": "auto",
            "deal_room": {"source": "slack", "coverage": "mapped", "source_ref": "C123"},
            "raw_messages": [{"text": "Slack raw message should not survive reduction."}],
            "signals": [
                {
                    "type": "legal",
                    "summary": "Legal review is active.",
                    "source_ref": "C123/1710000000",
                    "confidence": "Medium",
                }
            ],
        },
        "connector_status": {"email": "ok", "zoom": "ok", "calendar": "ok"},
    }

    reduced = run("pipeline_reduce.py", gather)
    compute_input = reduced["compute_input"]
    ok &= check("reduce: email count", len(compute_input["emails"]) == 2)
    ok &= check("reduce: outbound direction", compute_input["emails"][0]["direction"] == "out")
    ok &= check("reduce: inbound direction", compute_input["emails"][1]["direction"] == "in")
    ok &= check("reduce: observed participant", compute_input["observed_participants"] == ["buyer@acme.com"])
    ok &= check("reduce: latest call date", compute_input["latest_call_date"] == "2026-06-04")
    ok &= check("reduce: calendar preserved", reduced["calendar_evidence"]["upcoming_meetings"][0]["buyer_attendees"] == ["buyer@acme.com"])
    ok &= check("reduce: no raw email bodies", "Large body" not in json.dumps(reduced))
    ok &= check("reduce: no raw calendar descriptions", "Calendar raw description" not in json.dumps(reduced))
    ok &= check("reduce: no raw internal messages", "Slack raw message" not in json.dumps(reduced))
    ok &= check("reduce: no raw transcript", "raw transcript" not in json.dumps(reduced))
    ok &= check("reduce: compact source refs", reduced["evidence_summary"]["emails"][1]["source_ref"] == "msg-2")

    analyzed = run("analyze.py", reduced)
    ok &= check("analyze reduced: email freshness fresh", analyzed["deal_metrics"]["flags"]["email_data_stale"] is False)
    ok &= check("analyze reduced: calendar buyer attendees", analyzed["deal_metrics"]["flags"]["calendar_next_meeting_no_buyer_attendees"] is False)
    ok &= check("analyze reduced: internal signal preserved", analyzed["internal_evidence"]["signals"][0]["source_ref"] == "C123/1710000000")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
