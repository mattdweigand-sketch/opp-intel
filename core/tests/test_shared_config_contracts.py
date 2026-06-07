#!/usr/bin/env python3
"""Phase 2 shared config and contract checks."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE_CONFIG = os.path.join(ROOT, "core", "config")


def load(name):
    with open(os.path.join(CORE_CONFIG, name)) as f:
        return json.load(f)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    model = load("risk-model.json")
    fields = load("sf-fields.json")
    profiles = load("depth-profiles.json")
    contracts = load("source-contracts.json")

    ok &= check("shared risk thresholds exist", model["thresholds"]["email_window_days"] == 90)
    ok &= check("deal legal status preserved", "legal_status" in model)
    ok &= check("pipeline config exists", "pipeline" in model and "flag_severity" in model["pipeline"])
    ok &= check("calendar scoring thresholds exist",
                model["calendar"]["scoring"]["late_stage_days_to_close"] == 30
                and model["calendar"]["scoring"]["recent_stage_movement_days"] == 14)
    ok &= check("hygiene remains SF-only",
                profiles["hygiene"]["email"] == "off"
                and profiles["hygiene"]["calendar"] == "off"
                and profiles["hygiene"]["calls"] == "off")
    ok &= check("deal profile is one opportunity", profiles["deal"]["scope"] == "one_opportunity")
    ok &= check("pipeline profile is many opportunities", profiles["pipeline"]["scope"] == "many_opportunities")
    ok &= check("pipeline internal default remains bounded",
                model["internal_evidence"]["default_by_profile"]["pipeline"] == "auto")
    ok &= check("pipeline internal depth caps are shallower than deal",
                profiles["pipeline"]["slack"]["max_messages"] < profiles["deal"]["slack"]["max_messages"]
                and profiles["pipeline"]["drive"]["max_docs"] < profiles["deal"]["drive"]["max_docs"])
    ok &= check("shared sf fields preserve deal depth", "Decision_Maker__c" in fields["opportunity_fields"])
    ok &= check("shared sf fields include pipeline scope", "pipeline_scope" in fields)
    ok &= check("contact role grounding preserved", {"Role", "IsPrimary"}.issubset(set(fields["contact_fields"])))
    ok &= check("read-only source contract", contracts["read_policy"]["sources_are_read_only"] is True)
    ownership = contracts["source_ownership"]
    ok &= check("source ownership: Salesforce owns only Salesforce truth",
                ownership["salesforce"]["source_of_truth"] == "salesforce"
                and "slack evidence" in ownership["salesforce"]["does_not_own"]
                and "gmail evidence" in ownership["salesforce"]["does_not_own"]
                and "google calendar evidence" in ownership["salesforce"]["does_not_own"])
    ok &= check("source ownership: Gmail owns Gmail truth and requires domain search",
                ownership["gmail"]["source_of_truth"] == "gmail"
                and any("company domains" in rule for rule in ownership["gmail"]["required_search"]))
    ok &= check("source ownership: Slack owns Slack truth via Slack MCP only",
                ownership["slack"]["source_of_truth"] == "slack"
                and ownership["slack"]["connector"] == "slack_mcp"
                and ownership["slack"]["salesforce_role"] == "none")
    ok &= check("source ownership: Calendar owns Calendar truth",
                ownership["google_calendar"]["source_of_truth"] == "google_calendar")
    ok &= check("coverage rules: cross-source substitution disabled",
                contracts["coverage_rules"]["cross_source_substitution_allowed"] is False
                and contracts["coverage_rules"]["missing_connector_read"] == "coverage_gap")
    manifest = contracts["coverage_manifest"]
    ok &= check("coverage manifest: deal expected sources include Slack and Gmail",
                "gmail" in manifest["expected_sources_by_profile"]["deal"]
                and "slack" in manifest["expected_sources_by_profile"]["deal"])
    ok &= check("coverage manifest: hygiene expected sources are Salesforce only",
                manifest["expected_sources_by_profile"]["hygiene"] == ["salesforce"])
    ok &= check("coverage manifest: missing proof hard fails before analysis",
                manifest["missing_expected_source"] == "hard_fail_before_analysis"
                and manifest["clean_source_without_required_proof"] == "hard_fail_before_analysis")
    ok &= check("calendar source contract", contracts["sources"]["calendar"]["profiles"] == ["deal", "pipeline"])
    ok &= check("connector status aliases documented",
                "gmail" in contracts["sources"]["gmail"]["status_key_aliases"]
                and "google_calendar" in contracts["sources"]["calendar"]["status_key_aliases"]
                and "calls_zoom" in contracts["sources"]["calls"]["status_key_aliases"])
    ok &= check("calendar flags excluded from hygiene precedence",
                all(not flag.startswith("calendar_") for flag in model["hygiene"]["flag_precedence"]))
    ok &= check("deal draft confirmation contract",
                contracts["read_policy"]["deal_read_gmail_draft"] == "explicit_user_confirmation_only")

    for surface in ("deal-read", "pipeline-read"):
        local_config = os.path.join(ROOT, surface, "config")
        ok &= check(f"{surface}: no local copied config", not os.path.exists(local_config))

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
