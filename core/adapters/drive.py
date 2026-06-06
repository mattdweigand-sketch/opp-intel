"""Google Drive linked-document adapter contract."""

SOURCE = "google_drive"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile == "deal":
        return {"source": SOURCE, "linked_docs": "read_content", "max_docs": 5}
    if profile == "pipeline":
        return {"source": SOURCE, "linked_docs": "coverage_plus_titles", "max_docs": 3}
    raise ValueError(f"drive is off for profile: {profile}")


def normalize(raw):
    return {"internal_evidence": {"linked_docs": raw or [], "source_gaps": []}}
