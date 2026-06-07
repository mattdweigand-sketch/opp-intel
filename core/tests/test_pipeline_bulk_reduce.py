#!/usr/bin/env python3
"""Tests for fast-mode pipeline bulk Salesforce reduction."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE_SCRIPTS = os.path.join(ROOT, "core", "scripts")


def run(script, payload):
    proc = subprocess.run(
        [sys.executable, os.path.join(CORE_SCRIPTS, script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip())
    return json.loads(proc.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    reduced = run("pipeline_bulk_reduce.py", {
        "today": "2026-06-06",
        "rep_name": "Matt",
        "portfolio": [
            {
                "Id": "006A",
                "Name": "Acme",
                "StageName": "Validate",
                "CloseDate": "2026-06-30",
                "CreatedDate": "2026-04-01",
                "LastActivityDate": "2026-06-01",
                "NextStep": "commercials",
                "Added_ARR__c": 125000,
                "ForecastCategoryName": "Commit",
                "AccountId": "001A",
                "Account.Name": "Acme Capital",
            }
        ],
        "contact_roles": [
            {
                "OpportunityId": "006A",
                "Role": "Champion",
                "IsPrimary": True,
                "Contact.Name": "Buyer One",
                "Contact.Email": "buyer@acme.com",
            }
        ],
        "account_contacts": [
            {"AccountId": "001A", "Name": "Buyer Two", "Email": "second@acme.com"}
        ],
        "tasks": [
            {"WhatId": "006A", "Subject": "Call", "ActivityDate": "2026-06-01", "Status": "Completed"}
        ],
        "history": [
            {"OpportunityId": "006A", "StageName": "Discover", "CloseDate": "2026-06-15", "CreatedDate": "2026-04-01"},
            {"OpportunityId": "006A", "StageName": "Validate", "CloseDate": "2026-06-30", "CreatedDate": "2026-05-15"},
        ],
    })

    deal = reduced["deals"][0]
    bundle = deal["analyze_bundle"]
    compute_input = bundle["compute_input"]
    ok &= check("bulk reduce: fast strategy emitted", reduced["execution_strategy"] == "bulk_first")
    ok &= check("bulk reduce: deal identity preserved", deal["opportunity_id"] == "006A" and deal["name"] == "Acme")
    ok &= check("bulk reduce: contact union preserved",
                deal["contact_emails"] == ["buyer@acme.com", "second@acme.com"])
    ok &= check("bulk reduce: role count preserved", compute_input["logged_contact_roles"] == 1)
    ok &= check("bulk reduce: roles preserved", compute_input["roles"] == ["Champion"])
    ok &= check("bulk reduce: close history preserved",
                compute_input["opportunity"]["close_date_history"] == ["2026-06-15", "2026-06-30"])
    ok &= check("bulk reduce: stage entered date preserved",
                compute_input["opportunity"]["stage_entered_date"] == "2026-05-15")
    ok &= check("bulk reduce: primary deferred statuses",
                compute_input["connector_status"]["email"] == "partial"
                and compute_input["connector_status"]["calendar"] == "partial"
                and compute_input["connector_status"]["zoom"] == "partial")
    ok &= check("bulk reduce: no raw task body shape",
                "recent_tasks" in deal["evidence_summary"]["salesforce"])

    analyzed = run("analyze.py", bundle)
    gaps = analyzed["deal_metrics"]["coverage_gaps"]
    ok &= check("analyze fast bundle: deferred email is coverage gap",
                "email_connector_degraded" in gaps)
    ok &= check("analyze fast bundle: deferred email neutralizes stale flag",
                analyzed["deal_metrics"]["flags"]["email_data_stale"] is False)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
