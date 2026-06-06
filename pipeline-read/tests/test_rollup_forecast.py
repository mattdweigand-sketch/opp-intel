#!/usr/bin/env python3
"""Tests for forecast-mode rollup output. Run: python3 test_rollup_forecast.py"""
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


def deal(name, oid, amount, category, flags, internal=None):
    base = {"single_threaded": False, "stale_activity": False, "overdue_close": False,
            "close_date_slipped": False, "stalled_in_stage": False, "email_data_stale": False}
    base.update(flags)
    return {
        "name": name,
        "opportunity_id": oid,
        "stage": "Negotiation",
        "acv": amount,
        "close_date": "2026-06-30",
        "forecast_category": category,
        "internal_evidence": internal,
        "analyze_output": {"deal_metrics": {"days_to_close": 25, "flags": base}},
    }


def main():
    ok = True

    out = run({
        "rep_name": "Matthew Weigand",
        "mode": "forecast",
        "posture": "defend_commit",
        "amount_basis": "acv",
        "internal": "auto",
        "window": {"today": "2026-06-05", "close_on_or_before": "2026-06-30"},
        "deals": [
            deal("Risky Commit", "006A", 100000, "Commit", {"single_threaded": True}),
            deal("Clean Upside", "006B", 80000, "Best Case", {}),
            deal("Clean Commit Internal", "006C", 300000, "Commit", {}, {
                "mode": "auto",
                "deal_room": {"source": "slack", "coverage": "mapped", "source_ref": "C123/1710000000"},
                "signals": [
                    {"type": "legal_blocker", "summary": "Waiting on redlines.",
                     "source_ref": "C123/1710000000", "confidence": "Medium"}
                ],
            }),
            deal("Unknown Stale", "006D", 50000, "Omitted", {"email_data_stale": True}),
        ],
    })

    ok &= check("schema: computed-inputs version present",
                out["schema_version"] == "pipeline-read.computed-inputs.v1")
    ok &= check("run: forecast mode recorded", out["run"]["mode"] == "forecast")
    ok &= check("forecast: posture recorded", out["forecast"]["posture"] == "defend_commit")

    roll = out["forecast"]["category_rollup"]
    ok &= check("category: commit amount and risk",
                roll["commit"] == {"count": 2, "amount": 400000, "amount_at_risk": 100000})
    ok &= check("category: upside amount",
                roll["upside"] == {"count": 1, "amount": 80000, "amount_at_risk": 0})
    ok &= check("category: unknown amount at risk from stale amber is zero",
                roll["unknown"] == {"count": 1, "amount": 50000, "amount_at_risk": 0})

    recs = {r["deal"]: r for r in out["forecast"]["recommendations"]}
    ok &= check("recommendation: risky commit downgraded",
                recs["Risky Commit"]["recommendation"] == "downgrade")
    ok &= check("recommendation: clean upside is possible upside",
                recs["Clean Upside"]["recommendation"] == "possible_upside")
    ok &= check("recommendation: unknown stale is inspect",
                recs["Unknown Stale"]["recommendation"] == "inspect"
                and recs["Unknown Stale"]["confidence"] == "Low")
    ok &= check("internal signal: changes confidence, not ranking",
                recs["Clean Commit Internal"]["recommendation"] == "keep"
                and recs["Clean Commit Internal"]["confidence"] == "Medium"
                and [r["name"] for r in out["ranking"]][0] == "Risky Commit")
    ok &= check("internal signal: source ref preserved",
                out["internal_evidence"]["signals"][0]["source_ref"] == "C123/1710000000")

    # Regression: category_rollup must honor amount_basis, not silently sum CRM amount.
    # Each deal carries a distinct acv and a larger CRM amount; the rollup total must
    # follow the requested basis. (Previously amount_for_basis returned deal["amount"]
    # first, so an --amount-basis acv run reported CRM-amount totals.)
    basis_deals = [
        {"name": "Big CRM Small ACV", "opportunity_id": "006E", "stage": "Negotiation",
         "acv": 18000, "amount": 120000, "close_date": "2026-06-30", "forecast_category": "Commit",
         "analyze_output": {"deal_metrics": {"days_to_close": 25, "flags": {}}}},
        {"name": "Small Both", "opportunity_id": "006F", "stage": "Negotiation",
         "acv": 3750, "amount": 25000, "close_date": "2026-06-30", "forecast_category": "Commit",
         "analyze_output": {"deal_metrics": {"days_to_close": 25, "flags": {}}}},
    ]
    acv_run = run({"mode": "forecast", "amount_basis": "acv", "internal": "off",
                   "window": {"today": "2026-06-05", "close_on_or_before": "2026-06-30"},
                   "deals": basis_deals})
    ok &= check("basis acv: category rollup sums ACV not CRM amount",
                acv_run["forecast"]["category_rollup"]["commit"]["amount"] == 21750)
    ok &= check("basis acv: portfolio and category totals agree",
                acv_run["portfolio"]["total_acv"] == acv_run["forecast"]["category_rollup"]["commit"]["amount"])
    crm_run = run({"mode": "forecast", "amount_basis": "crm_primary_amount", "internal": "off",
                   "window": {"today": "2026-06-05", "close_on_or_before": "2026-06-30"},
                   "deals": basis_deals})
    ok &= check("basis crm_primary_amount: category rollup sums CRM amount",
                crm_run["forecast"]["category_rollup"]["commit"]["amount"] == 145000)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
