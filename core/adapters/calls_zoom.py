"""Current call-source adapter contract for Zoom."""

SOURCE = "calls"
PROVIDER = "zoom"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile == "deal":
        return {"source": SOURCE, "provider": PROVIDER, "detail": "summary_plus_transcript"}
    if profile == "pipeline":
        return {"source": SOURCE, "provider": PROVIDER, "detail": "summary_first"}
    raise ValueError(f"calls are off for profile: {profile}")


def normalize(raw):
    return {"call_evidence": {"provider": PROVIDER, "calls": raw or [], "source_gaps": []}}
