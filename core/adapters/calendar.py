"""Google Calendar planning and normalization contract."""

SOURCE = "google_calendar"
PROFILES = {"deal", "pipeline"}


def plan(profile):
    if profile == "deal":
        return {
            "source": SOURCE,
            "history": "historical_meetings",
            "future": "upcoming_meetings",
            "detail": "titles_attendees_times_and_conference_links",
        }
    if profile == "pipeline":
        return {
            "source": SOURCE,
            "history": "recent_meeting_presence",
            "future": "upcoming_meeting_presence",
            "detail": "metadata_only",
        }
    raise ValueError(f"calendar is off for profile: {profile}")


def normalize(raw):
    return {"calendar_evidence": raw or {}}
