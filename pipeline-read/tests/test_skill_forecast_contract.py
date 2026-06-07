#!/usr/bin/env python3
"""Tests that SKILL.md exposes the forecast machinery implemented in config/scripts."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "SKILL.md")


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    with open(SKILL) as f:
        text = f.read()

    required = [
        "--posture conservative|defend-commit|identify-upside",
        "--next-quarter",
        "--window current_quarter|next_quarter|30d",
        "--amount-basis added-arr",
        "--compare <prior-computed-inputs.json>",
        "--internal auto|off|force",
        "Slack",
        "Google Calendar",
        "Google Drive",
        "forecast.category_rollup",
        "forecast.recommendations",
        "internal_evidence",
        "movement",
        "Category rollup:",
        "Recommendation changes:",
        "Evidence gaps:",
        "Review scope:",
        "Internal evidence:",
        "JSQ's fiscal year starts Feb 1",
        "--window next_quarter",
    ]

    ok = True
    for needle in required:
        ok &= check(f"SKILL forecast contract includes {needle}", needle in text)

    ok &= check("SKILL no longer describes forecast as only forecast-realism",
                "forecast-realism view" not in text)
    ok &= check("SKILL routes broad Slack message lookup through force",
                "Broad Slack message-body lookup is allowed only under `internal=force`" in text)
    ok &= check("SKILL does not advertise removed /pipeline-triage command",
                "/pipeline-triage" not in text
                and "pipeline-triage" not in text)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
