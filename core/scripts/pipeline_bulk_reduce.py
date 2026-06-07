#!/usr/bin/env python3
"""Build per-deal analyze.py bundles from a fast pipeline bulk Salesforce pass.

The standard pipeline path gathers portfolio rows, then bulk Salesforce result
sets keyed by OpportunityId/AccountId. This reducer groups those rows into the
same compact analyze.py bundle shape that the deep-search per-deal workers
return, without pushing raw source payloads into the rollup context.

Usage:
  python3 pipeline_bulk_reduce.py < bulk-gather.json
"""
import json
import sys
from collections import defaultdict


DEFERRED_PRIMARY_STATUS = {
    "email": "partial",
    "calendar": "partial",
    "zoom": "partial",
}


def first(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def key(row, *names):
    for name in names:
        if name in row:
            return row.get(name)
    return None


def account_name(row):
    account = row.get("Account")
    if isinstance(account, dict):
        return account.get("Name")
    return row.get("Account.Name") or row.get("account_name")


def group_by(rows, *keys):
    out = defaultdict(list)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = key(row, *keys)
        if value:
            out[str(value)].append(row)
    return out


def sorted_by_created(rows):
    return sorted(rows or [], key=lambda row: str(first(row.get("CreatedDate"), row.get("created_date"), "")))


def close_date_history(history_rows, current_close):
    values = []
    for row in sorted_by_created(history_rows):
        close = first(row.get("CloseDate"), row.get("close_date"))
        if close and close not in values:
            values.append(close)
    if current_close and (not values or values[-1] != current_close):
        values.append(current_close)
    return values


def stage_entered_date(history_rows, current_stage):
    if not current_stage:
        return None
    current = str(current_stage).strip().lower()
    entered = None
    for row in sorted_by_created(history_rows):
        stage = first(row.get("StageName"), row.get("stage_name"))
        if str(stage or "").strip().lower() == current:
            entered = first(row.get("CreatedDate"), row.get("created_date"))
    return str(entered)[:10] if entered else None


def contact_email(row):
    contact = row.get("Contact")
    if isinstance(contact, dict):
        return contact.get("Email")
    return first(row.get("Contact.Email"), row.get("Email"), row.get("email"))


def contact_name(row):
    contact = row.get("Contact")
    if isinstance(contact, dict):
        return contact.get("Name")
    return first(row.get("Contact.Name"), row.get("Name"), row.get("name"))


def role_value(row):
    return first(row.get("Role"), row.get("role"))


def build_deal(row, roles_by_opp, contacts_by_account, tasks_by_opp, history_by_opp, defaults):
    opp_id = str(first(row.get("Id"), row.get("opportunity_id"), row.get("OpportunityId")) or "")
    account_id = first(row.get("AccountId"), row.get("account_id"))
    role_rows = roles_by_opp.get(opp_id, [])
    contact_rows = contacts_by_account.get(str(account_id), [])
    task_rows = tasks_by_opp.get(opp_id, [])
    history_rows = history_by_opp.get(opp_id, [])

    role_emails = sorted({
        str(email).strip().lower()
        for email in (contact_email(role) for role in role_rows)
        if email and str(email).strip()
    })
    account_emails = sorted({
        str(first(c.get("Email"), c.get("email"))).strip().lower()
        for c in contact_rows
        if first(c.get("Email"), c.get("email"))
    })
    roles = [str(r).strip() for r in (role_value(role) for role in role_rows) if r and str(r).strip()]
    current_stage = first(row.get("StageName"), row.get("stage"), row.get("stage_name"))
    current_close = first(row.get("CloseDate"), row.get("close_date"))

    connector_status = dict(defaults.get("connector_status") or {})
    connector_status.setdefault("salesforce", "ok")
    if defaults.get("mark_deferred_primary", True):
        for source, status in DEFERRED_PRIMARY_STATUS.items():
            connector_status.setdefault(source, status)

    compute_input = {
        "today": defaults.get("today"),
        "opportunity": {
            "created_date": first(row.get("CreatedDate"), row.get("created_date")),
            "close_date": current_close,
            "last_activity_date": first(row.get("LastActivityDate"), row.get("last_activity_date")),
            "stage": current_stage,
            "next_step": first(row.get("NextStep"), row.get("next_step")),
            "next_step_last_modified_date": first(
                row.get("Next_Steps_Last_Modified_Date__c"),
                row.get("next_step_last_modified_date"),
            ),
            "legal_status": first(row.get("Legal_Status__c"), row.get("legal_status")),
            "close_date_history": close_date_history(history_rows, current_close),
            "stage_entered_date": stage_entered_date(history_rows, current_stage),
        },
        "logged_contact_roles": len(role_rows),
        "roles": roles,
        "observed_participants": role_emails,
        "connector_status": connector_status,
    }

    analyze_bundle = {
        "rep_name": defaults.get("rep_name"),
        "compute_input": compute_input,
        "connector_status": connector_status,
        "prior_opps": [],
    }

    return {
        "opportunity_id": opp_id,
        "name": first(row.get("Name"), row.get("name")),
        "stage": current_stage,
        "Added_ARR__c": first(row.get("Added_ARR__c"), row.get("added_arr"), row.get("amount")),
        "forecast_category": first(row.get("ForecastCategoryName"), row.get("ForecastCategory")),
        "close_date": current_close,
        "account_id": account_id,
        "account_name": account_name(row),
        "contact_emails": sorted(set(role_emails + account_emails)),
        "analyze_bundle": analyze_bundle,
        "evidence_summary": {
            "salesforce": {
                "contact_roles": [
                    {
                        "name": contact_name(role),
                        "email": contact_email(role),
                        "role": role_value(role),
                        "is_primary": first(role.get("IsPrimary"), role.get("is_primary")),
                    }
                    for role in role_rows
                ],
                "recent_tasks": [
                    {
                        "subject": first(task.get("Subject"), task.get("subject")),
                        "activity_date": first(task.get("ActivityDate"), task.get("activity_date")),
                        "status": first(task.get("Status"), task.get("status")),
                    }
                    for task in task_rows[:5]
                ],
                "history_rows": len(history_rows),
                "deferred_primary_sources": (
                    sorted(DEFERRED_PRIMARY_STATUS)
                    if defaults.get("mark_deferred_primary", True)
                    else []
                ),
            }
        },
    }


def main():
    payload = json.load(sys.stdin)
    portfolio = payload.get("portfolio") or payload.get("opportunities") or []
    roles_by_opp = group_by(payload.get("contact_roles") or payload.get("bulk_contact_roles"), "OpportunityId", "opportunity_id")
    contacts_by_account = group_by(payload.get("account_contacts") or payload.get("bulk_account_contacts"), "AccountId", "account_id")
    tasks_by_opp = group_by(payload.get("tasks") or payload.get("bulk_tasks"), "WhatId", "OpportunityId", "opportunity_id")
    history_by_opp = group_by(payload.get("history") or payload.get("bulk_history"), "OpportunityId", "opportunity_id")

    defaults = {
        "today": payload.get("today"),
        "rep_name": payload.get("rep_name"),
        "connector_status": payload.get("connector_status") or {},
        "mark_deferred_primary": payload.get("mark_deferred_primary", True),
    }
    deals = [
        build_deal(row, roles_by_opp, contacts_by_account, tasks_by_opp, history_by_opp, defaults)
        for row in portfolio
        if isinstance(row, dict)
    ]
    json.dump(
        {
            "run_depth": "fast",
            "execution_strategy": "bulk_first",
            "deals": deals,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
