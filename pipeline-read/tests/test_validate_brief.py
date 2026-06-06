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
        "run": {"mode": "triage"},
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
    ok &= check("triage stale without blind section fails",
                rc == 1 and "Where you're blind" in out)

    rc, _ = run("Confidence: Medium, partial coverage.\n\nWhere you're blind: Acme email data is stale.\n\nComputed inputs:\n" + footer(stale=True))
    ok &= check("triage stale with blind section passes", rc == 0)

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

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
