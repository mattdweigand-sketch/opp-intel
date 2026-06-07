#!/usr/bin/env python3
"""Tests for rollup.py — pins ranking order and portfolio aggregates. Run: python3 test_rollup.py"""
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


def deal(name, acv, dtc, flags):
    base = {"single_threaded": False, "stale_activity": False, "overdue_close": False,
            "close_date_slipped": False, "stalled_in_stage": False, "email_data_stale": False}
    base.update(flags)
    return {"name": name, "stage": "X", "Added_ARR__c": acv, "close_date": "2026-06-30",
            "analyze_output": {"deal_metrics": {"days_to_close": dtc, "flags": base}}}


def main():
    ok = True

    out = run({
        "rep_name": "Matthew Weigand",
        "window": {"today": "2026-06-04", "close_on_or_before": "2026-06-30"},
        "deals": [
            deal("Providence", 120000, 16, {"single_threaded": True, "stale_activity": True}),
            deal("Acme", 80000, -5, {"overdue_close": True, "close_date_slipped": True,
                                     "stale_activity": True, "email_data_stale": True}),
            deal("Globex", 50000, 24, {}),
        ],
    })
    rank = [r["name"] for r in out["ranking"]]
    ok &= check("ranking: most red flags first (Acme > Providence > Globex)", rank == ["Acme", "Providence", "Globex"])
    ok &= check("ranking: Acme dominant flag is overdue_close (config order)", out["ranking"][0]["dominant_flag"] == "overdue_close")
    ok &= check("ranking: clean deal tier is none", out["ranking"][-1]["severity_tier"] == "none")

    p = out["portfolio"]
    ok &= check("portfolio: total ACV summed", p["total_acv"] == 250000)
    ok &= check("portfolio: ACV at risk = red deals only", p["acv_at_risk"] == 200000)
    ok &= check("portfolio: at-risk pct", p["acv_at_risk_pct"] == 0.8)
    ok &= check("portfolio: deals_at_risk counts red tier", p["deals_at_risk"] == 2)
    ok &= check("portfolio: single_threaded count", p["single_threaded"] == 1)
    ok &= check("portfolio: slipped_or_overdue counts a deal once", p["slipped_or_overdue"] == 1)
    ok &= check("portfolio: stale_data_deals count", p["stale_data_deals"] == 1)

    # Tie-break: same tier + flag count -> larger ACV ranks first.
    tie = run({"deals": [
        deal("Small", 10000, 5, {"single_threaded": True}),
        deal("Big", 90000, 5, {"single_threaded": True}),
    ]})
    ok &= check("tie-break: larger ACV first", [r["name"] for r in tie["ranking"]] == ["Big", "Small"])

    # Non-risk flags (e.g. recent_rep_outbound) never count toward severity.
    nr = run({"deals": [deal("Quiet", 5000, 10, {})]})
    nr["ranking"][0]  # smoke
    ok &= check("clean deal has zero flag_count", nr["ranking"][0]["flag_count"] == 0)

    calendar = run({"mode": "read", "deals": [
        deal("Calendar Risk", 100000, 12, {"calendar_no_upcoming_late_stage": True}),
        deal("Calendar Amber", 90000, 12, {"calendar_next_meeting_no_buyer_attendees": True}),
        deal("Clean", 80000, 12, {}),
    ]})
    ok &= check("calendar: no-upcoming late-stage ranks red",
                calendar["ranking"][0]["dominant_flag"] == "calendar_no_upcoming_late_stage"
                and calendar["ranking"][0]["severity_tier"] == "red")
    ok &= check("calendar: no buyer attendee ranks amber",
                calendar["ranking"][1]["dominant_flag"] == "calendar_next_meeting_no_buyer_attendees"
                and calendar["ranking"][1]["severity_tier"] == "amber")

    # Empty pipeline doesn't divide by zero.
    empty = run({"deals": []})
    ok &= check("empty: pct is None, no crash", empty["portfolio"]["acv_at_risk_pct"] is None)

    # Coverage gaps: aggregate into top-level source_gaps + portfolio.coverage_gap_deals,
    # carry last_touch/last_touch_source on rows, and never reorder the ranking.
    def gap_deal(name, acv, dtc, flags, coverage_gaps=None, anchor=None, anchor_src=None):
        d = deal(name, acv, dtc, flags)
        m = d["analyze_output"]["deal_metrics"]
        if coverage_gaps is not None:
            m["coverage_gaps"] = coverage_gaps
        if anchor is not None or anchor_src is not None:
            m["freshness"] = {"activity_anchor_date": anchor, "activity_anchor_source": anchor_src}
        return d

    base_deals = [
        gap_deal("Northwind", 120000, 16, {"single_threaded": True, "email_data_stale": True},
                 anchor="2026-05-26", anchor_src="call"),
        gap_deal("Acme", 80000, 10, {"overdue_close": True}),
        gap_deal("Globex", 50000, 24, {}),
    ]
    no_gap = run({"mode": "read", "deals": base_deals})
    with_gap = run({"mode": "read", "deals": [
        gap_deal("Northwind", 120000, 16, {"single_threaded": True, "email_data_stale": True},
                 coverage_gaps=["activity_coverage_gap"], anchor="2026-05-26", anchor_src="call"),
        gap_deal("Acme", 80000, 10, {"overdue_close": True}),
        gap_deal("Globex", 50000, 24, {}),
    ]})

    ok &= check("coverage gap: top-level source_gaps carries the gap",
                "activity_coverage_gap" in (with_gap.get("source_gaps") or []))
    ok &= check("coverage gap: portfolio.coverage_gap_deals lists the deal",
                with_gap["portfolio"]["coverage_gap_deals"] == ["Northwind"])
    nw = next(r for r in with_gap["ranking"] if r["name"] == "Northwind")
    ok &= check("coverage gap: ranked row carries last_touch", nw["last_touch"] == "2026-05-26")
    ok &= check("coverage gap: ranked row carries last_touch_source", nw["last_touch_source"] == "call")
    ok &= check("coverage gap: clean deal has empty coverage_gaps on row",
                next(r for r in with_gap["ranking"] if r["name"] == "Acme")["coverage_gaps"] == [])
    ok &= check("coverage gap: ranking order unchanged vs no-gap bundle",
                [r["name"] for r in with_gap["ranking"]] == [r["name"] for r in no_gap["ranking"]])

    calendar_gap = gap_deal("Calendar Gap", 60000, 12, {})
    calendar_gap["analyze_output"]["deal_metrics"]["calendar"] = {
        "coverage": "unavailable",
        "source_gaps": ["calendar_unavailable"],
    }
    internal_gap = gap_deal("Internal Gap", 50000, 12, {})
    internal_gap["internal_evidence"] = {
        "deal_room": {"coverage": "deal_room_missing"},
        "source_gaps": ["deal_room_missing"],
    }
    gap_sources = run({"mode": "read", "deals": [calendar_gap, internal_gap]})
    ok &= check("source gaps: calendar gap reaches top-level source_gaps",
                "calendar_unavailable" in gap_sources["source_gaps"])
    ok &= check("source gaps: internal gap reaches top-level source_gaps",
                "deal_room_missing" in gap_sources["source_gaps"])
    ok &= check("source gaps: read mode includes internal evidence rollup",
                gap_sources["run"]["internal_evidence"] == "auto"
                and gap_sources["internal_evidence"]["deal_room_coverage"]["missing"] == 1)
    ok &= check("source gaps: ranked rows carry non-risk gaps",
                next(r for r in gap_sources["ranking"] if r["name"] == "Calendar Gap")["coverage_gaps"] == ["calendar_unavailable"]
                and next(r for r in gap_sources["ranking"] if r["name"] == "Internal Gap")["coverage_gaps"] == ["deal_room_missing"])

    # Backward compat: a bundle with no coverage_gaps/freshness yields empty gaps + null last_touch.
    legacy = run({"mode": "read", "deals": [deal("Legacy", 10000, 5, {"single_threaded": True})]})
    ok &= check("legacy: source_gaps empty when no coverage_gaps", legacy.get("source_gaps") == [])
    ok &= check("legacy: coverage_gap_deals empty", legacy["portfolio"]["coverage_gap_deals"] == [])
    ok &= check("legacy: last_touch null when freshness absent",
                legacy["ranking"][0]["last_touch"] is None
                and legacy["ranking"][0]["last_touch_source"] is None)

    # Mode contract: an explicit read bundle stays read and emits no forecast block,
    # even when amount_basis is present. (amount_basis must not infer forecast.)
    read_mode = run({"mode": "read", "amount_basis": "acv",
                     "deals": [deal("Solo", 10000, 5, {"single_threaded": True})]})
    ok &= check("mode: explicit read stays read", read_mode["run"]["mode"] == "read")
    ok &= check("mode: read emits no forecast block", "forecast" not in read_mode)
    legacy_mode = run({"mode": "triage", "amount_basis": "acv",
                       "deals": [deal("Solo", 10000, 5, {"single_threaded": True})]})
    ok &= check("mode: legacy triage input normalizes to read", legacy_mode["run"]["mode"] == "read")
    # And mode "forecast" still produces the forecast block.
    fc = run({"mode": "forecast",
              "deals": [deal("Solo", 10000, 5, {"single_threaded": True})]})
    ok &= check("mode: forecast emits forecast block", fc["run"]["mode"] == "forecast" and "forecast" in fc)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
