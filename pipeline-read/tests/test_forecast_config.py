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

    amount = sf["amount_basis"]
    allowed = set(sf["opportunity_fields"]) | set(sf["pipeline_scope"]["fields"])
    ok &= check("amount: default is acv", amount["default"] == "acv")
    ok &= check("amount: acv maps to Added_ARR__c",
                amount["fields"]["acv"] == "Added_ARR__c")
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
    ok &= check("internal: default force", internal["default"] == "force")
    ok &= check("internal: force-required fallback configured",
                sf["internal_sources"]["slack_deal_room"]["fallback_requires_internal_force"] is True)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
