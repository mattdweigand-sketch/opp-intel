"""Salesforce planning and normalization contract."""

SOURCE = "salesforce"
PROFILES = {"deal", "pipeline", "hygiene"}


def plan(profile):
    if profile == "hygiene":
        return {"source": SOURCE, "mode": "portfolio_scope_plus_contact_roles"}
    if profile == "pipeline":
        return {"source": SOURCE, "mode": "portfolio_scope_plus_per_deal_core_fields"}
    if profile == "deal":
        return {"source": SOURCE, "mode": "full_opportunity_history"}
    raise ValueError(f"unknown profile: {profile}")


def normalize(raw):
    return {"salesforce_evidence": raw or {}}
