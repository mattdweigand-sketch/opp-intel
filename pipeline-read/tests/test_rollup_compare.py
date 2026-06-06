#!/usr/bin/env python3
"""Tests for prior Computed inputs comparison. Run: python3 test_rollup_compare.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROLLUP = os.path.join(HERE, "..", "scripts", "rollup.py")


def run(bundle):
    return subprocess.run([sys.executable, ROLLUP], input=json.dumps(bundle),
                          capture_output=True, text=True)


def parse_ok(bundle):
    p = run(bundle)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def deal(name, oid, amount, close_date, flags):
    base = {"single_threaded": False, "stale_activity": False, "overdue_close": False,
            "close_date_slipped": False, "stalled_in_stage": False, "email_data_stale": False}
    base.update(flags)
    out = {
        "name": name,
        "stage": "Negotiation",
        "acv": amount,
        "close_date": close_date,
        "forecast_category": "Commit",
        "analyze_output": {"deal_metrics": {"days_to_close": 10, "flags": base}},
    }
    if oid:
        out["opportunity_id"] = oid
    return out


def main():
    ok = True

    prior = {
        "schema_version": "pipeline-read.computed-inputs.v1",
        "portfolio": {"deal_count": 3},
        "ranking": [
            {"opportunity_id": "006A", "name": "Acme", "amount": 100000,
             "close_date": "2026-06-15", "severity_tier": "amber",
             "risk_flags": ["stale_activity"]},
            {"name": "Name Fallback", "amount": 20000,
             "close_date": "2026-06-30", "severity_tier": "none", "risk_flags": []},
            {"opportunity_id": "006Removed", "name": "Removed Deal", "amount": 90000,
             "close_date": "2026-06-30", "severity_tier": "red",
             "risk_flags": ["single_threaded"]},
        ],
    }
    out = parse_ok({
        "mode": "forecast",
        "prior_rollup": prior,
        "prior_rollup_source": "deliverables/prior-computed-inputs.json",
        "deals": [
            deal("Acme", "006A", 120000, "2026-06-30", {"single_threaded": True}),
            deal("Name Fallback", None, 25000, "2026-06-30", {}),
            deal("New Deal", "006New", 75000, "2026-06-30", {}),
        ],
    })
    movement = out["movement"]
    ok &= check("movement: evaluated from prior object", movement["evaluated"] is True)
    ok &= check("movement: source recorded",
                movement["source"] == "deliverables/prior-computed-inputs.json")
    ok &= check("movement: summary counts",
                movement["summary"]["new_deals"] == 1
                and movement["summary"]["removed_deals"] == 1
                and movement["summary"]["risk_increased"] == 1
                and movement["summary"]["amount_changed"] == 2
                and movement["summary"]["close_date_changed"] == 1)
    acme = next(d for d in movement["deals"] if d["deal"] == "Acme")
    ok &= check("movement: opportunity id match preferred",
                acme["match_basis"] == "id"
                and set(acme["movement"]) == {"amount_changed", "close_date_changed", "risk_changed"})
    fallback = next(d for d in movement["deals"] if d["deal"] == "Name Fallback")
    ok &= check("movement: name fallback used only without id",
                fallback["match_basis"] == "name" and fallback["movement"] == ["amount_changed"])

    invalid = run({"mode": "forecast", "prior_rollup": {"ranking": []}, "deals": []})
    ok &= check("movement: invalid prior fails before drafting",
                invalid.returncode == 1 and "prior_rollup" in invalid.stderr)

    missing = parse_ok({"mode": "forecast", "compare_file": "/tmp/pipeline-read-missing-prior.json", "deals": []})
    ok &= check("movement: missing compare file recorded as unevaluated",
                missing["movement"]["evaluated"] is False
                and missing["movement"]["reason"] == "compare_file_missing")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
