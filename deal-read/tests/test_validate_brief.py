#!/usr/bin/env python3
"""Tests for validate_brief.py: pins the output-contract gate. Run: python3 test_validate_brief.py"""
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


def footer(flags):
    return "```json\n" + json.dumps({"deal_metrics": {"flags": flags}}) + "\n```"


def footer_with_gaps(gaps):
    return "```json\n" + json.dumps({
        "deal_metrics": {"flags": {"email_data_stale": False}, "coverage_gaps": gaps}
    }) + "\n```"


def full_footer(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


def main():
    ok = True

    # Good brief: confidence present, footer present and parseable, not stale.
    rc, _ = run(
        "Confidence: Low, one call, no email thread.\n\n"
        "Computed inputs:\n" + footer({"email_data_stale": False})
    )
    ok &= check("good brief passes", rc == 0)

    # Missing footer: the audit trail isn't there.
    rc, out = run("Confidence: Medium, partial coverage.\n\nNo computed block here.")
    ok &= check("missing footer fails", rc == 1 and "Computed inputs" in out)

    # Empty json fence counts as missing.
    rc, _ = run("Confidence: Low\n\n```json\n\n```")
    ok &= check("empty footer fails", rc == 1)

    # High confidence on stale data is the contract violation.
    rc, out = run(
        "Confidence: High, corroborated.\n\n"
        "Computed inputs:\n" + footer({"email_data_stale": True})
    )
    ok &= check("High + stale fails", rc == 1 and "email_data_stale" in out)

    # High confidence on fresh data is fine.
    rc, _ = run(
        "Confidence: High, calls and emails current.\n\n"
        "Computed inputs:\n" + footer({"email_data_stale": False})
    )
    ok &= check("High + fresh passes", rc == 0)

    rc, out = run(
        "Confidence: High, calls and emails current.\n\n"
        "Computed inputs:\n" + footer_with_gaps(["email_connector_degraded"])
    )
    ok &= check("High + coverage gap fails", rc == 1 and "coverage gaps" in out)

    ceiling_footer = {
        "deal_metrics": {"flags": {"email_data_stale": False}, "coverage_gaps": []},
        "confidence": {"max_label": "Low", "reason_codes": ["email_coverage_gap"]},
    }
    rc, out = run(
        "Confidence: Medium, partial coverage.\n\n"
        "Computed inputs:\n" + full_footer(ceiling_footer)
    )
    ok &= check("confidence above computed ceiling fails",
                rc == 1 and "cap confidence at Low" in out)

    rc, out = run(
        "Confidence: Medium, no live email thread.\n\n"
        "Computed inputs:\n" + footer_with_gaps(["email_domain_coverage_gap"])
    )
    ok &= check("email absence claim + email gap fails",
                rc == 1 and "email coverage gaps" in out)

    slack_gap_footer = {
        "deal_metrics": {"flags": {"email_data_stale": False}, "coverage_gaps": []},
        "internal_evidence": {"deal_room": {"coverage": "checked_no_match"}, "source_gaps": ["slack_coverage_unproven"]},
    }
    rc, out = run(
        "Confidence: Medium, no Slack room found.\n\n"
        "Computed inputs:\n" + full_footer(slack_gap_footer)
    )
    ok &= check("Slack absence claim without Slack MCP proof fails",
                rc == 1 and "Slack MCP coverage" in out)

    slack_clean_footer = {
        "deal_metrics": {"flags": {"email_data_stale": False}, "coverage_gaps": []},
        "internal_evidence": {
            "deal_room": {
                "coverage": "checked_no_match",
                "slack_mcp_checked": True,
                "slack_channels_searched": ["acme"],
            },
            "source_gaps": ["checked_no_match"],
        },
    }
    rc, _ = run(
        "Confidence: Medium, no Slack room found after Slack MCP channel search.\n\n"
        "Computed inputs:\n" + full_footer(slack_clean_footer)
    )
    ok &= check("Slack absence claim with clean Slack MCP proof passes", rc == 0)

    rc, out = run(
        "Confidence: Medium, Salesforce shows no Slack room.\n\n"
        "Computed inputs:\n" + full_footer(slack_clean_footer)
    )
    ok &= check("Salesforce-as-Slack evidence fails",
                rc == 1 and "Slack/deal-room truth" in out)

    # Missing confidence line fails.
    rc, out = run("Computed inputs:\n" + footer({"email_data_stale": False}))
    ok &= check("missing confidence fails", rc == 1 and "Confidence" in out)

    # Footer that isn't analyze.py output (no deal_metrics) fails.
    rc, out = run("Confidence: Low\n\n```json\n{\"foo\": 1}\n```")
    ok &= check("non-analyze footer fails", rc == 1 and "deal_metrics" in out)

    # On success the gate renders: the raw JSON is gone, replaced by a pass stamp
    # inside a collapsible Computed inputs block.
    rc, out = run(
        "Confidence: Low, one call.\n\n"
        "Computed inputs:\n" + footer({"email_data_stale": False})
    )
    ok &= check("render: passes", rc == 0)
    ok &= check("render: emits pass stamp", "Verified: analyze.py ran" in out)
    ok &= check("render: no emoji", "\u2705" not in out)
    ok &= check("render: keeps Computed inputs disclosure", "<summary>Computed inputs</summary>" in out)
    ok &= check("render: raw JSON redacted", "email_data_stale" not in out and "```json" not in out)
    ok &= check("render: absorbs the label line", "Computed inputs:\n" not in out)
    ok &= check("render: preserves brief body", "Confidence: Low, one call." in out)

    # On failure the gate writes nothing to stdout (only stderr reasons).
    p = subprocess.run([sys.executable, VALIDATE],
                       input="Confidence: Medium\n\nno footer", capture_output=True, text=True)
    ok &= check("fail: no stdout on failure", p.returncode == 1 and p.stdout == "")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
