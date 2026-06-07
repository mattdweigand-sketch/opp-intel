#!/usr/bin/env python3
"""Tests for forecast-mode brief validation. Run: python3 test_validate_forecast_brief.py"""
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


def computed(gaps=False, include_forecast=True, signal_ref=True):
    obj = {
        "schema_version": "pipeline-read.computed-inputs.v1",
        "run": {
            "rep_name": "Matthew Weigand",
            "mode": "forecast",
            "posture": "conservative",
            "amount_basis": "acv",
            "internal_evidence": "auto",
        },
        "portfolio": {"deal_count": 1, "stale_data_deals": 0},
        "ranking": [{"name": "Acme", "severity_tier": "none", "risk_flags": []}],
        "internal_evidence": {
            "mode": "auto",
            "deal_room_coverage": {"mapped": 1, "missing": 0, "unavailable": 0, "checked_no_match": 0},
            "linked_docs_read": 1,
            "linked_docs_unavailable": 0,
            "signals": [
                {
                    "deal": "Acme",
                    "type": "legal_blocker",
                    "summary": "Legal has redlines in motion.",
                    "confidence": "Medium",
                    **({"source_ref": "C123/1710000000"} if signal_ref else {}),
                }
            ],
            "source_gaps": [],
        },
    }
    if include_forecast:
        obj["forecast"] = {
            "amount_basis": "acv",
            "posture": "conservative",
            "category_rollup": {
                "commit": {"count": 1, "amount": 100000, "amount_at_risk": 0},
                "upside": {"count": 0, "amount": 0, "amount_at_risk": 0},
                "pipeline": {"count": 0, "amount": 0, "amount_at_risk": 0},
                "unknown": {"count": 0, "amount": 0, "amount_at_risk": 0},
            },
            "recommendations": [
                {"deal": "Acme", "recommendation": "keep",
                 "reason_codes": ["no_current_risk_flags"], "confidence": "Medium"}
            ],
        }
    if gaps:
        obj["forecast"]["recommendations"][0]["reason_codes"] = ["unknown_forecast_category", "deal_room_missing"]
        obj["internal_evidence"]["deal_room_coverage"]["mapped"] = 0
        obj["internal_evidence"]["deal_room_coverage"]["missing"] = 1
        obj["internal_evidence"]["source_gaps"] = [{"deal": "Acme", "gap": "deal_room_missing"}]
        obj["movement"] = {
            "source": "deliverables/prior-computed-inputs.json",
            "evaluated": False,
            "reason": "compare_file_missing",
            "deals": [],
            "summary": {},
        }
    return obj


def brief(obj, confidence="High", include_gap_section=True, omit_heading=None):
    sections = [
        f"Forecast Read - Matthew Weigand, 1 deals closing by 2026-06-30. Run 2026-06-05.\n",
        f"Confidence: {confidence} - current read.\n",
        "Review scope: Salesforce, Gmail, Calendar, Zoom, amount basis acv, posture conservative.\n",
        "Internal evidence: auto; Slack room found for Acme.\n",
        "Category rollup: Commit 1, $100000, $0 at risk.\n",
        "Key movements: Movement was not evaluated.\n",
        "Recommendation changes: Acme - keep. Computed reason: no_current_risk_flags.\n",
        "Highest-risk deals: Acme - no current red flags.\n",
    ]
    if include_gap_section:
        sections.append("Evidence gaps: None.\n")
    sections.extend([
        "Your move this week: Keep Acme moving through legal.\n",
        "Computed inputs:\n```json\n" + json.dumps(obj) + "\n```\n",
    ])
    text = "\n".join(sections)
    if omit_heading:
        text = re_remove_section(text, omit_heading)
    return text


def re_remove_section(text, heading):
    lines = []
    for line in text.splitlines():
        if line.lower().startswith(heading.lower() + ":"):
            continue
        lines.append(line)
    return "\n".join(lines)


def main():
    ok = True

    rc, _ = run(brief(computed(), confidence="Medium"))
    ok &= check("forecast good brief passes", rc == 0)

    rc, out = run(brief(computed(), confidence="Medium", omit_heading="Category rollup"))
    ok &= check("forecast missing required section fails",
                rc == 1 and "Category rollup" in out)

    rc, out = run(brief(computed(include_forecast=False), confidence="Medium"))
    ok &= check("forecast missing computed forecast block fails",
                rc == 1 and "forecast block" in out.lower())

    rc, out = run(brief(computed(gaps=True), confidence="Medium", include_gap_section=False))
    ok &= check("forecast gaps without evidence section fail",
                rc == 1 and "Evidence gaps" in out)

    rc, out = run(brief(computed(gaps=True), confidence="High", include_gap_section=True))
    ok &= check("forecast High confidence with gaps fails",
                rc == 1 and "Confidence is High" in out)

    rc, out = run(brief(computed(signal_ref=False), confidence="Medium"))
    ok &= check("forecast internal signal without source_ref fails",
                rc == 1 and "source_ref" in out)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
