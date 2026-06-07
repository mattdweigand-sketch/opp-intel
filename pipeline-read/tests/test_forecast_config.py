#!/usr/bin/env python3
"""Tests for forecast-owned config. Run: python3 test_forecast_config.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "..", "core", "config"))


def load(name):
    with open(os.path.join(CONFIG, name)) as f:
        return json.load(f)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def category_group(value, convention):
    for group, names in convention.items():
        if value in names:
            return group
    return "unknown"


def main():
    ok = True
    model = load("risk-model.json")
    sf = load("sf-fields.json")
    profiles = load("depth-profiles.json")

    forecast = model["forecast"]
    ok &= check("forecast: postures configured",
                forecast["postures"] == ["conservative", "defend_commit", "identify_upside"])
    ok &= check("forecast: default posture configured",
                forecast["default_posture"] == "conservative")
    ok &= check("forecast: recommendation labels configured",
                set(forecast["recommendation_labels"]) == {"keep", "downgrade", "inspect", "possible_upside"})

    scope = model["pipeline"]["scope"]
    ok &= check("pipeline scope: default current quarter", scope["close_window"] == "current_quarter")
    ok &= check("pipeline scope: next quarter option configured",
                "next_quarter" in scope["allowed_close_windows"])
    ok &= check("pipeline scope: JSQ fiscal year starts Feb 1",
                scope["fiscal_year_start_month"] == 2 and scope["fiscal_year_start_day"] == 1)
    severity = model["pipeline"]["flag_severity"]
    ok &= check("pipeline severity: Calendar no-upcoming is red",
                "calendar_no_upcoming_late_stage" in severity["red"])
    ok &= check("pipeline severity: Calendar attendee/stage flags are amber",
                "calendar_no_recent_meeting_after_stage_move" in severity["amber"]
                and "calendar_next_meeting_no_buyer_attendees" in severity["amber"])

    amount = sf["amount_basis"]
    allowed = set(sf["opportunity_fields"]) | set(sf["pipeline_scope"]["fields"])
    ok &= check("amount: default is acv", amount["default"] == "acv")
    ok &= check("amount: acv maps to Added_ARR__c",
                amount["fields"]["acv"] == "Added_ARR__c")
    ok &= check("amount: Added ARR is the only supported amount basis",
                amount["fields"] == {"acv": "Added_ARR__c"})
    ok &= check("amount: every basis maps to a configured SF field",
                all(field in allowed for field in amount["fields"].values()))
    ok &= check("amount: bare Amount is not default",
                amount["fields"][amount["default"]] != "Amount")

    cat = sf["forecast_category"]
    ok &= check("category: field configured", cat["field"] in allowed)
    ok &= check("category: Commit groups to commit",
                category_group("Commit", cat["convention"]) == "commit")
    ok &= check("category: Best Case groups to upside",
                category_group("Best Case", cat["convention"]) == "upside")
    ok &= check("category: unknown stays unknown",
                category_group("Omitted", cat["convention"]) == "unknown")

    internal = model["internal_evidence"]
    ok &= check("internal: default auto", internal["default"] == "auto")
    ok &= check("internal: pipeline default auto", internal["default_by_profile"]["pipeline"] == "auto")
    ok &= check("internal: auto channel fallback configured",
                sf["internal_sources"]["slack_deal_room"]["channel_lookup_in_auto"] is True)
    ok &= check("internal: force-required message search configured",
                sf["internal_sources"]["slack_deal_room"]["message_search_requires_internal_force"] is True)

    ok &= check("run depth: fast profile configured",
                profiles["pipeline_fast"]["run_depth"] == "fast"
                and profiles["pipeline_fast"]["execution_strategy"] == "bulk_first")
    ok &= check("run depth: deep search profile configured",
                profiles["pipeline_deep_search"]["run_depth"] == "deep_search"
                and profiles["pipeline_deep_search"]["execution_strategy"] == "per_deal_search_agents")
    ok &= check("run depth: deep search worker budget configured",
                profiles["pipeline_deep_search"]["worker_budget"]["max_tool_calls_per_deal"] == 12)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
