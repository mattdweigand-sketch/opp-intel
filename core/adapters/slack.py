"""Slack internal-evidence adapter contract."""

SOURCE = "slack"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile == "deal":
        return {"source": SOURCE, "mode": "channel_name_lookup_default", "max_messages": 80}
    if profile == "pipeline":
        return {"source": SOURCE, "mode": "channel_name_lookup_default", "max_messages": 40}
    raise ValueError(f"slack is off for profile: {profile}")


def normalize(raw):
    return {"internal_evidence": {"deal_room": raw or {}, "source_gaps": []}}
