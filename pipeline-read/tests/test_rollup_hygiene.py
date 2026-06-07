#!/usr/bin/env python3
"""Tests for rollup.py hygiene mode — pins dominant-flag precedence, ranking, and the
distribution rollup for /pipeline-hygiene. Run: python3 test_rollup_hygiene.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROLLUP = os.path.join(HERE, "..", "scripts", "rollup.py")


def run(bundle):
    p = subprocess.run([sys.executable, ROLLUP], input=json.dumps(bundle),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def deal(name, added_arr, dtc, flags, contacts=None, days_since_activity=None):
    base = {"no_contact_roles": False, "single_threaded": False, "no_champion": False,
            "missing_next_step": False, "stale_activity": False, "overdue_close": False}
    base.update(flags)
    return {"name": name, "stage": "X", "Added_ARR__c": added_arr, "close_date": "2026-07-30",
            "analyze_output": {"deal_metrics": {"days_to_close": dtc, "contacts_engaged": contacts,
                                                 "days_since_last_activity": days_since_activity,
                                                 "flags": base}}}


def main():
    ok = True

    out = run({
        "rep_name": "Matthew Weigand",
        "mode": "hygiene",
        "window": {"today": "2026-06-05", "close_on_or_before": "2026-07-31"},
        "deals": [
            # null added_arr -> rollup derives missing_amount (not a compute.py flag).
            deal("Cendris", None, 35, {}, contacts=2),
            deal("Arcticum", 120000, 40, {"no_contact_roles": True, "no_champion": True,
                                          "single_threaded": True, "stale_activity": True}, contacts=0),
            deal("Brunderic", 90000, 45, {"no_champion": True}, contacts=3),
            deal("Dovetail", 60000, 50, {}, contacts=4),
        ],
    })

    ok &= check("mode: run.mode is hygiene", out["run"]["mode"] == "hygiene")
    ok &= check("mode: hygiene emits no forecast block", "forecast" not in out)
    ok &= check("mode: hygiene block present", "hygiene" in out and "flag_precedence" in out["hygiene"])

    rank = [(r["name"], r["dominant_flag"]) for r in out["ranking"]]
    ok &= check(
        "ranking: precedence order (no_contact_roles > no_champion > missing_amount > clean)",
        rank == [("Arcticum", "no_contact_roles"), ("Brunderic", "no_champion"),
                 ("Cendris", "missing_amount"), ("Dovetail", None)],
    )
    ok &= check("dominant: Arcticum picks highest-precedence flag, not single_threaded",
                out["ranking"][0]["dominant_flag"] == "no_contact_roles")
    ok &= check("missing_amount: derived by rollup from null added_arr",
                "missing_amount" in [r for r in out["ranking"] if r["name"] == "Cendris"][0]["hygiene_flags"])
    ok &= check("clean deal: dominant_flag None, severity_tier clean",
                out["ranking"][-1]["dominant_flag"] is None and out["ranking"][-1]["severity_tier"] == "clean")

    p = out["portfolio"]
    ok &= check("portfolio: deal_count", p["deal_count"] == 4)
    ok &= check("portfolio: flagged/clean split", p["flagged_deals"] == 3 and p["clean_deals"] == 1)
    dist = p["distribution"]
    ok &= check("distribution: dominant flags counted once each",
                dist["no_contact_roles"] == 1 and dist["no_champion"] == 1
                and dist["missing_amount"] == 1 and dist["clean"] == 1)
    ok &= check("distribution: single_threaded not double-counted (lost to no_contact_roles)",
                dist["single_threaded"] == 0)

    # Tie-break: same dominant flag -> larger Added ARR first.
    tie = run({"mode": "hygiene", "deals": [
        deal("Small", 10000, 5, {"no_champion": True}),
        deal("Big", 90000, 5, {"no_champion": True}),
    ]})
    ok &= check("tie-break: larger Added ARR first", [r["name"] for r in tie["ranking"]] == ["Big", "Small"])

    # All-clean pipeline: everything ranks clean, distribution all-clean.
    clean = run({"mode": "hygiene", "deals": [deal("Solo", 50000, 10, {}, contacts=3)]})
    ok &= check("all-clean: flagged 0", clean["portfolio"]["flagged_deals"] == 0)
    ok &= check("all-clean: dominant None", clean["ranking"][0]["dominant_flag"] is None)

    # Empty pipeline doesn't crash.
    empty = run({"mode": "hygiene", "deals": []})
    ok &= check("empty: deal_count 0, no crash", empty["portfolio"]["deal_count"] == 0)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
