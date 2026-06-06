#!/usr/bin/env python3
"""Direct checks for Phase 3 core script entrypoints."""

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
    deal = run("compute.py", {"roles": ["Champion", "Economic Buyer"], "opportunity": {"legal_status": "NA"}})
    ok &= check("core compute: deal flags preserved", deal["flags"]["champion_identified"] is True)
    ok &= check("core compute: paper flag preserved", deal["flags"]["paper_not_started"] is True)

    hygiene = run("compute.py", {
        "hygiene": True,
        "today": "2026-06-05",
        "opportunity": {"last_activity_date": "2026-04-01"},
        "logged_contact_roles": 0,
        "champion_contact_roles": 0,
        "next_step": "",
    })
    ok &= check("core compute: hygiene flags preserved", hygiene["flags"]["no_contact_roles"] is True)

    analyzed = run("analyze.py", {
        "compute_input": {},
        "prior_opps": [],
        "calendar_evidence": {
            "coverage": "available",
            "future": [{"title": "Buyer follow-up", "start": "2026-06-10T15:00:00Z"}],
        },
    })
    ok &= check("core analyze: deal metrics emitted", "deal_metrics" in analyzed)
    ok &= check("core analyze: account history emitted", "account_history" in analyzed)
    ok &= check("core analyze: calendar emitted", analyzed["calendar_evidence"]["upcoming_meetings"][0]["title"] == "Buyer follow-up")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
