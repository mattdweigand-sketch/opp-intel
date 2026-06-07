#!/usr/bin/env python3
"""Pins source-read manifest enforcement before analyze.py trusts a bundle."""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE = os.path.join(HERE, "..", "scripts", "analyze.py")


def run(bundle):
    return subprocess.run(
        [sys.executable, ANALYZE],
        input=json.dumps(bundle),
        capture_output=True,
        text=True,
    )


def source_reads(**overrides):
    base = {
        "salesforce": {"status": "ok", "source_refs": ["sf:006"]},
        "gmail": {"status": "ok", "source_refs": ["gmail:thread-1"]},
        "google_calendar": {"status": "empty"},
        "zoom": {"status": "empty"},
        "slack": {"status": "ok", "source_refs": ["slack:C123"]},
        "google_drive": {"status": "empty"},
    }
    base.update(overrides)
    return base


def valid_bundle(**overrides):
    bundle = {
        "profile": "deal",
        "compute_input": {
            "today": "2026-06-06",
            "opportunity": {"last_activity_date": "2026-06-05"},
        },
        "source_reads": source_reads(),
        "email_coverage": {
            "searched_emails": ["vanda@nw1.com"],
            "contact_union_emails": ["vanda@nw1.com"],
            "searched_domains": ["nw1.com"],
            "contact_domains": ["nw1.com"],
            "newest_domain_thread_id": "gmail:thread-1",
            "domain_thread_search_status": "found",
        },
        "calendar_evidence": {"coverage": "available", "historical_meetings": [], "upcoming_meetings": []},
        "internal_evidence": {
            "mode": "auto",
            "slack_mcp_checked": True,
            "slack_channels_searched": ["nw1", "nw1-partners"],
            "slack_channel_matches": ["nw1"],
            "deal_room": {"source": "slack", "coverage": "found", "source_ref": "slack:C123"},
            "linked_docs": [],
            "source_gaps": [],
        },
    }
    bundle.update(overrides)
    return bundle


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    p = run({"profile": "deal", "compute_input": {}})
    ok &= check("missing source_reads fails", p.returncode != 0)
    ok &= check("missing source_reads names source", "source_reads missing expected source: salesforce" in p.stderr)

    p = run(valid_bundle())
    ok &= check("valid manifest passes", p.returncode == 0)
    out = json.loads(p.stdout)
    ok &= check("manifest output preserved", out["coverage_manifest"]["expected_sources"][0] == "salesforce")
    ok &= check("manifest connector status reaches compute",
                out["coverage_manifest"]["connector_status"]["email"] == "ok")

    degraded = valid_bundle(source_reads=source_reads(gmail={"status": "timeout", "retries": 2}))
    degraded.pop("email_coverage")
    p = run(degraded)
    ok &= check("degraded gmail can omit gmail proof", p.returncode == 0)
    out = json.loads(p.stdout)
    ok &= check("degraded gmail becomes coverage gap",
                "email_connector_degraded" in out["deal_metrics"]["coverage_gaps"])

    bad_gmail = valid_bundle()
    bad_gmail["email_coverage"].pop("newest_domain_thread_id")
    bad_gmail["email_coverage"]["domain_thread_search_status"] = None
    p = run(bad_gmail)
    ok &= check("clean gmail missing newest-domain proof fails", p.returncode != 0)
    ok &= check("clean gmail failure is explicit",
                "newest_domain_thread_id" in p.stderr and "domain_thread_search_status=no_match" in p.stderr)

    bad_slack = valid_bundle()
    bad_slack["internal_evidence"]["slack_mcp_checked"] = False
    p = run(bad_slack)
    ok &= check("clean slack without MCP proof fails", p.returncode != 0)
    ok &= check("clean slack failure is explicit", "slack_mcp_checked" in p.stderr)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
