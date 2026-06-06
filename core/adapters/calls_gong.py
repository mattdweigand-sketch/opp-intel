"""Future call-source adapter contract for Gong.

This file defines the interface only. It does not invent Gong behavior before
there is real connector output to normalize.
"""

SOURCE = "calls"
PROVIDER = "gong"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile not in PROFILES:
        raise ValueError(f"calls are off for profile: {profile}")
    return {"source": SOURCE, "provider": PROVIDER, "status": "contract_only"}


def normalize(raw):
    if raw:
        raise NotImplementedError("Gong normalization needs real connector output fixtures.")
    return {"call_evidence": {"provider": PROVIDER, "calls": [], "source_gaps": ["gong_not_configured"]}}
