"""Gmail planning and normalization contract."""

SOURCE = "gmail"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile == "deal":
        return {"source": SOURCE, "thread_depth": "full_relevant_threads", "sent_freshness": True}
    if profile == "pipeline":
        return {"source": SOURCE, "thread_depth": "bounded_recent_threads", "sent_freshness": True}
    raise ValueError(f"gmail is off for profile: {profile}")


def normalize(raw):
    return {"email_evidence": raw or {}}
