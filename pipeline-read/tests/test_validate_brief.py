#!/usr/bin/env python3
"""Tests for validate_brief.py: pins the pipeline output-contract gate.
Run: python3 test_validate_brief.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATE = os.path.join(HERE, "..", "scripts", "validate_brief.py")


def run(brief):
    p = subprocess.run([sys.executable, VALIDATE], input=brief,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def footer(stale=False):
    """A minimal but valid rollup.py-shaped footer; one deal carries stale data iff stale."""
    flags = ["email_data_stale"] if stale else ["single_threaded"]
    obj = {
        "schema_version": "pipeline-read.computed-inputs.v1",
        "run": {"mode": "read"},
        "portfolio": {"deal_count": 1, "stale_data_deals": 1 if stale else 0},
        "ranking": [{"name": "Acme", "severity_tier": "red", "risk_flags": flags}],
    }
    return "```json\n" + json.dumps(obj) + "\n```"


def main():
    ok = True

    rc, out = run("Confidence: Medium, partial coverage.\n\nComputed inputs:\n" + footer(stale=False))
    ok &= check("good brief passes", rc == 0)
    ok &= check("good brief renders pass stamp", out == "Validation: PASS\n")

    rc, out = run("Confidence: Medium.\n\nNo computed block here.")
    ok &= check("missing footer fails", rc == 1 and "Computed inputs" in out)

    rc, _ = run("Confidence: Low\n\n```json\n\n```")
    ok &= check("empty footer fails", rc == 1)

    # Footer that's deal-read shaped (deal_metrics, not portfolio/ranking) is rejected.
    rc, out = run("Confidence: Low\n\n```json\n" + json.dumps({"deal_metrics": {}}) + "\n```")
    ok &= check("per-deal footer rejected (needs portfolio/ranking)", rc == 1 and "portfolio" in out)

    rc, out = run("Confidence: High, all current.\n\nComputed inputs:\n" + footer(stale=True))
    ok &= check("High + stale deal fails", rc == 1 and "stale" in out.lower())

    rc, out = run("Confidence: Medium, partial coverage.\n\nComputed inputs:\n" + footer(stale=True))
    ok &= check("read stale without blind section fails",
                rc == 1 and "Where you're blind" in out)

    rc, _ = run("Confidence: Medium, partial coverage.\n\nWhere you're blind: Acme email data is stale.\n\nComputed inputs:\n" + footer(stale=True))
    ok &= check("read stale with blind section passes", rc == 0)

    rc, _ = run("Confidence: High, all current.\n\nComputed inputs:\n" + footer(stale=False))
    ok &= check("High + fresh passes", rc == 0)

    rc, out = run("Computed inputs:\n" + footer(stale=False))
    ok &= check("missing confidence fails", rc == 1 and "Confidence" in out)

    no_schema = {
        "portfolio": {"deal_count": 1, "stale_data_deals": 0},
        "ranking": [{"name": "Acme", "severity_tier": "none", "risk_flags": []}],
    }
    rc, out = run("Confidence: High\n\nComputed inputs:\n```json\n" + json.dumps(no_schema) + "\n```")
    ok &= check("missing schema fails", rc == 1 and "schema_version" in out)

    # Coverage gaps (Fix 4): a connector under-collected. compute.py reports it as a
    # coverage_gap; rollup.py surfaces it in source_gaps + portfolio.coverage_gap_deals.
    def gap_footer():
        obj = {
            "schema_version": "pipeline-read.computed-inputs.v1",
            "run": {"mode": "read"},
            "portfolio": {"deal_count": 1, "stale_data_deals": 0, "coverage_gap_deals": ["Acme"]},
            "source_gaps": ["activity_coverage_gap"],
            "ranking": [{"name": "Acme", "severity_tier": "amber", "risk_flags": ["single_threaded"],
                         "coverage_gaps": ["activity_coverage_gap"]}],
        }
        return "```json\n" + json.dumps(obj) + "\n```"

    rc, out = run("Confidence: Medium, partial coverage.\n\nComputed inputs:\n" + gap_footer())
    ok &= check("coverage gap without blind section fails",
                rc == 1 and "Where you're blind" in out)

    rc, _ = run("Confidence: Medium, partial coverage.\n\nWhere you're blind: Acme activity data is thin.\n\n"
                "Computed inputs:\n" + gap_footer())
    ok &= check("coverage gap with blind section passes", rc == 0)

    rc, out = run("Confidence: High, all current.\n\nWhere you're blind: Acme activity data is thin.\n\n"
                  "Computed inputs:\n" + gap_footer())
    ok &= check("High + coverage gap fails", rc == 1 and "coverage gap" in out.lower())

    # NW1 anchor guard: a deal flagged email_data_stale must cite its last_touch date.
    def stale_anchor_footer(last_touch="2026-05-26"):
        obj = {
            "schema_version": "pipeline-read.computed-inputs.v1",
            "run": {"mode": "read"},
            "portfolio": {"deal_count": 1, "stale_data_deals": 1},
            "ranking": [{"name": "Northwind", "severity_tier": "red",
                         "risk_flags": ["email_data_stale"], "last_touch": last_touch,
                         "last_touch_source": "call"}],
        }
        return "```json\n" + json.dumps(obj) + "\n```"

    blind = "Where you're blind: Northwind email view is lagging.\n\n"
    rc, out = run("Confidence: Medium, partial coverage.\n\n" + blind +
                  "Northwind has gone quiet since March.\n\nComputed inputs:\n" + stale_anchor_footer())
    ok &= check("stale deal missing last_touch date fails",
                rc == 1 and "2026-05-26" in out)

    rc, _ = run("Confidence: Medium, partial coverage.\n\n" + blind +
                "Northwind's true last touch was a 2026-05-26 call.\n\nComputed inputs:\n" + stale_anchor_footer())
    ok &= check("stale deal citing last_touch date passes", rc == 0)

    # Lenient: a stale-flagged row with null last_touch (older input) skips the anchor check.
    rc, _ = run("Confidence: Medium, partial coverage.\n\n" + blind +
                "Computed inputs:\n" + stale_anchor_footer(last_touch=None))
    ok &= check("stale deal with null last_touch skips anchor check", rc == 0)

    # Hygiene mode: requires the hygiene sections, not the forecast ones, and a stale-data
    # row in another mode's footer never trips the High-confidence guard here.
    hyg_footer = "```json\n" + json.dumps({
        "schema_version": "pipeline-read.computed-inputs.v1",
        "run": {"mode": "hygiene"},
        "portfolio": {"deal_count": 1, "flagged_deals": 1, "clean_deals": 0,
                      "distribution": {"no_contact_roles": 1, "clean": 0}},
        "ranking": [{"name": "Acme", "dominant_flag": "no_contact_roles",
                     "hygiene_flags": ["no_contact_roles"]}],
        "hygiene": {"flag_precedence": ["no_contact_roles"]},
    }) + "\n```"

    good_hyg = ("Pipeline Hygiene — rep.\n\nConfidence: High, Salesforce read cleanly.\n\n"
                "Hygiene distribution:\n- NO CONTACTS: 1\n\nBy deal:\n1. Acme — 0 contact roles.\n\n"
                "Computed inputs:\n" + hyg_footer)
    rc, out = run(good_hyg)
    ok &= check("hygiene brief with required sections passes", rc == 0)

    rc, out = run(good_hyg.replace("By deal:", "Deals:"))
    ok &= check("hygiene brief missing 'By deal' fails", rc == 1 and "By deal" in out)

    # A hygiene brief must NOT be forced to carry forecast-only sections.
    ok &= check("hygiene brief does not demand forecast sections",
                "Category rollup" not in out and "Recommendation changes" not in out)

    # Confidence floor (NW1 regression): when rollup sets portfolio.confidence_floor=Low,
    # a brief claiming Medium/High must fail; Low passes.
    def floor_footer(floor="Low", blocked=("NW1",)):
        obj = {
            "schema_version": "pipeline-read.computed-inputs.v1",
            "run": {"mode": "read"},
            "portfolio": {"deal_count": 2, "stale_data_deals": 1,
                          "confidence_floor": floor,
                          "confidence_blocked_deals": list(blocked)},
            "ranking": [{"name": "NW1", "severity_tier": "red",
                         "risk_flags": ["close_date_slipped", "email_data_stale"],
                         "last_touch": "2026-06-04", "confidence_blocked": True}],
        }
        return "```json\n" + json.dumps(obj) + "\n```"

    blind = "Where you're blind: NW1 last touch 2026-06-04, email view lags.\n\n"
    rc, out = run("Confidence: Medium.\n\n" + blind + "Computed inputs:\n" + floor_footer())
    ok &= check("floor Low + Medium confidence fails", rc == 1 and "confidence_floor" in out.lower())

    rc, out = run("Confidence: High.\n\n" + blind + "Computed inputs:\n" + floor_footer())
    ok &= check("floor Low + High confidence fails", rc == 1 and "confidence_floor" in out.lower())

    rc, out = run("Confidence: Low.\n\n" + blind + "Computed inputs:\n" + floor_footer())
    ok &= check("floor Low + Low confidence passes", rc == 0)

    # No floor (null) leaves confidence to the model — Medium still passes.
    rc, out = run("Confidence: Medium.\n\n" + blind + "Computed inputs:\n" + floor_footer(floor=None, blocked=()))
    ok &= check("no floor + Medium passes", rc == 0)

    # Backward compat: a footer with no confidence_floor key at all is unconstrained.
    rc, out = run("Confidence: Medium, partial coverage.\n\nComputed inputs:\n" + footer(stale=False))
    ok &= check("legacy footer without floor key is unconstrained", rc == 0)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
