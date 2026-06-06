#!/usr/bin/env python3
"""Deterministic metrics for the deal-read skill.

Reads a deal snapshot as JSON on stdin, reads thresholds from the sibling
risk-model.json, and writes computed metrics + threshold flags as JSON on stdout.
The model should consume these numbers rather than doing date arithmetic itself.

Input shape (all dates ISO yyyy-mm-dd, all fields optional):
  {
    "today": "2026-06-03",
    "opportunity": {
      "created_date": "...", "close_date": "...", "last_activity_date": "..."
    },
    "contacts_engaged": 1,
    "emails": [ {"direction": "out", "date": "..."}, {"direction": "in", "date": "..."} ]
  }
"out" = rep -> prospect, "in" = prospect -> rep.
"""
import json
import os
import sys
from datetime import date, datetime
from statistics import median


def parse(d):
    return date.fromisoformat(d) if d else None


def parse_calendar_date(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def days_between(later, earlier):
    if later is None or earlier is None:
        return None
    return (later - earlier).days


DEGRADED_STATUSES = {"timeout", "error", "partial"}


def main():
    snap = json.load(sys.stdin)
    is_hygiene = bool(snap.get("hygiene"))

    # Per-connector execution status (optional). A connector that did not run
    # cleanly cannot assert a negative finding: its silence is a coverage gap,
    # not evidence the prospect went quiet. Absent/unknown/"ok"/"empty" are NOT
    # degraded; only "timeout"/"error"/"partial" are. See source-contracts.json.
    connector_status = snap.get("connector_status") or {}
    degraded_connectors = [
        name
        for name in ("email", "zoom", "calendar", "salesforce")
        if str(connector_status.get(name) or "").strip().lower() in DEGRADED_STATUSES
    ]
    email_degraded = "email" in degraded_connectors

    model_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core", "config", "risk-model.json"))
    with open(model_path) as f:
        model = json.load(f)
    thresholds = model["thresholds"]
    calendar_scoring = model.get("calendar", {}).get("scoring", {})
    legal_not_started = {
        str(v).strip().lower() for v in model.get("legal_status", {}).get("not_started_values", [])
    }

    today = parse(snap.get("today")) or date.today()
    opp = snap.get("opportunity", {}) or {}
    created = parse(opp.get("created_date"))
    close = parse(opp.get("close_date"))
    last_activity = parse(opp.get("last_activity_date"))
    stage_name = str(opp.get("stage") or opp.get("stage_name") or opp.get("StageName") or "").strip().lower()
    is_closed = bool(opp.get("is_closed") or opp.get("IsClosed")) or stage_name in {
        "closed won",
        "closed lost",
        "won",
        "lost",
    }

    deal_age_days = days_between(today, created)
    days_to_close = days_between(close, today)
    days_since_last_activity = days_between(today, last_activity)

    # Stage velocity: how long the deal has sat in its current stage
    stage_entered = parse(opp.get("stage_entered_date"))
    days_in_current_stage = days_between(today, stage_entered)

    # Close-date slippage: how often the close date has been pushed later.
    # close_date_history is the chronological sequence of CloseDate values the
    # opp has held (oldest first), including the current one.
    history = [parse(d) for d in (opp.get("close_date_history") or []) if d]
    close_date_slippage = None
    if history:
        original = history[0]
        current = history[-1]
        close_date_slippage = {
            "original": original.isoformat(),
            "current": current.isoformat(),
            "times_pushed": sum(1 for a, b in zip(history, history[1:]) if b > a),
            "total_slip_days": (current - original).days,
        }

    # Email engagement
    emails = sorted(
        [e for e in snap.get("emails", []) if e.get("date")],
        key=lambda e: e["date"],
    )
    count_out = sum(1 for e in emails if e.get("direction") == "out")
    count_in = sum(1 for e in emails if e.get("direction") == "in")

    last_inbound = max((parse(e["date"]) for e in emails if e.get("direction") == "in"), default=None)
    days_since_last_inbound = days_between(today, last_inbound)

    # Trailing rep emails after the last inbound = unanswered
    unanswered_rep_emails = 0
    for e in reversed(emails):
        if e.get("direction") == "in":
            break
        unanswered_rep_emails += 1

    # Prospect response latency: each rep email followed in time by an inbound
    latencies = []
    for i, e in enumerate(emails):
        if e.get("direction") != "out":
            continue
        nxt = next((n for n in emails[i + 1:] if n.get("direction") == "in"), None)
        if nxt:
            latencies.append((parse(nxt["date"]) - parse(e["date"])).days)
    median_response_latency_days = median(latencies) if latencies else None

    # Contacts engaged: prefer an explicit count, else derive it deterministically.
    # The model extracts the prospect-side people it observed (Zoom attendees, email
    # senders/recipients on the prospect domain); the dedup and the logged-role floor
    # are mechanical, so they run here, not in the model's head.
    contacts_engaged = snap.get("contacts_engaged")
    if contacts_engaged is None:
        observed = snap.get("observed_participants") or []
        distinct = len({str(p).strip().lower() for p in observed if str(p).strip()})
        logged = snap.get("logged_contact_roles") or 0
        if observed or snap.get("logged_contact_roles") is not None:
            contacts_engaged = max(distinct, logged)

    # Freshness guard: detect when the email view lags other activity (connectors
    # drop recent mail), and when the rep emailed very recently (a new draft would
    # be redundant). emails is sorted ascending, so the last item is newest.
    newest_email = parse(emails[-1]["date"]) if emails else None
    last_outbound = max(
        (parse(e["date"]) for e in emails if e.get("direction") == "out"), default=None
    )
    latest_call = parse(snap.get("latest_call_date"))
    activity_anchor = max([d for d in (last_activity, latest_call) if d], default=None)

    # Salesforce-as-witness coverage check. When Salesforce's LastActivityDate is
    # materially newer than anything the connectors actually retrieved (newest email,
    # last inbound, latest call), that contradiction means the connectors under-
    # collected — not that the deal went quiet. Surface it as a coverage gap, never a
    # risk flag: it drives confidence/blindness downstream, never ranking.
    coverage_gaps = []
    gathered_latest = max(
        [d for d in (newest_email, last_inbound, latest_call) if d], default=None
    )
    activity_coverage_gap = (
        last_activity is not None
        and gathered_latest is not None
        and (last_activity - gathered_latest).days > thresholds["freshness_gap_days"]
    )
    if activity_coverage_gap:
        coverage_gaps.append("activity_coverage_gap")

    # A degraded connector (timeout/error/partial) produces a coverage gap, never a
    # finding. Coverage gaps are NOT risk flags: they drive confidence/blindness
    # downstream, never ranking or severity.
    for name in degraded_connectors:
        coverage_gaps.append(f"{name}_connector_degraded")

    # Which date won activity_anchor — labels the freshness anchor for downstream rollup.
    if activity_anchor is None:
        activity_anchor_source = None
    elif activity_anchor == latest_call:
        activity_anchor_source = "call"
    elif activity_anchor in (newest_email, last_inbound):
        activity_anchor_source = "email"
    elif activity_anchor == last_activity:
        activity_anchor_source = "activity"
    else:
        activity_anchor_source = None

    email_data_stale = activity_anchor is not None and (
        newest_email is None
        or (activity_anchor - newest_email).days > thresholds.get("freshness_gap_days", 5)
    )
    days_since_last_outbound = days_between(today, last_outbound)
    recent_rep_outbound = (
        days_since_last_outbound is not None
        and days_since_last_outbound <= thresholds.get("recent_outbound_days", 3)
    )

    # Email-derived NEGATIVE assertions are only trustworthy when the email
    # connector actually ran. When email is degraded, absence is not evidence of
    # silence: null the inbound/unanswered counts and refuse to assert staleness.
    # The coverage gap (email_connector_degraded) carries the uncertainty instead.
    if email_degraded:
        days_since_last_inbound = None
        unanswered_rep_emails = None
        email_data_stale = False

    # MEDDPICC grounding from structured fields, so the economic_buyer, champion, and
    # paper_timeline dimensions don't rely on title-guessing or eyeballing a picklist.
    # roles = the OpportunityContactRole.Role values the model saw; legal_status = the
    # Opportunity.Legal_Status__c picklist value. All optional — absent means "not asserted".
    roles = {str(r).strip().lower() for r in (snap.get("roles") or []) if str(r).strip()}
    economic_buyer_named = "economic buyer" in roles or bool(opp.get("economic_buyer_named"))
    champion_identified = "champion" in roles
    legal_status = opp.get("legal_status")
    paper_not_started = (
        legal_status is not None
        and str(legal_status).strip().lower() in legal_not_started
    )

    calendar_evidence = snap.get("calendar_evidence") or {}
    calendar_coverage = calendar_evidence.get("coverage")
    calendar_available = calendar_coverage == "available" and not is_hygiene
    historical_meetings = calendar_evidence.get("historical_meetings") or []
    upcoming_meetings = calendar_evidence.get("upcoming_meetings") or []
    historical_dates = [
        parse_calendar_date(m.get("start") or m.get("start_time"))
        for m in historical_meetings
        if isinstance(m, dict)
    ]
    upcoming_dates = [
        parse_calendar_date(m.get("start") or m.get("start_time"))
        for m in upcoming_meetings
        if isinstance(m, dict)
    ]
    last_calendar_meeting = max((d for d in historical_dates if d), default=None)
    next_calendar_meeting = min((d for d in upcoming_dates if d and d >= today), default=None)

    def has_buyer_attendee(meeting):
        buyer_attendees = meeting.get("buyer_attendees")
        if isinstance(buyer_attendees, list):
            return len([a for a in buyer_attendees if str(a).strip()]) > 0
        attendees = meeting.get("attendees")
        if not isinstance(attendees, list):
            return False
        for attendee in attendees:
            if isinstance(attendee, dict):
                if attendee.get("is_buyer") is True or attendee.get("external") is True:
                    return True
                if attendee.get("is_internal") is False:
                    return True
            elif str(attendee).strip():
                return True
        return False

    next_meeting = None
    if upcoming_meetings:
        dated = [
            (parse_calendar_date(m.get("start") or m.get("start_time")), m)
            for m in upcoming_meetings
            if isinstance(m, dict)
        ]
        future_dated = [(d, m) for d, m in dated if d and d >= today]
        if future_dated:
            next_meeting = sorted(future_dated, key=lambda item: item[0])[0][1]
        elif dated:
            next_meeting = dated[0][1]

    calendar_no_upcoming_late_stage = (
        calendar_available
        and not is_closed
        and days_to_close is not None
        and 0 <= days_to_close <= calendar_scoring.get("late_stage_days_to_close", 30)
        and not next_calendar_meeting
    )
    calendar_no_recent_meeting_after_stage_move = (
        calendar_available
        and stage_entered is not None
        and days_in_current_stage is not None
        and days_in_current_stage <= calendar_scoring.get("recent_stage_movement_days", 14)
        and (last_calendar_meeting is None or last_calendar_meeting < stage_entered)
    )
    calendar_next_meeting_no_buyer_attendees = (
        calendar_available
        and next_meeting is not None
        and not has_buyer_attendee(next_meeting)
    )

    # single_threaded normally fires off contacts_engaged. But when the email
    # connector is degraded, email-observed participants may be undercounted, so a
    # low contacts_engaged could be a coverage artifact rather than a real thin
    # thread. In that case only let the flag stand if it is independently supported
    # by the SF-sourced logged_contact_roles; otherwise rely on the coverage gap.
    single_thread_max = thresholds["single_thread_max_contacts"]
    single_threaded = (
        contacts_engaged is not None and contacts_engaged <= single_thread_max
    )
    if email_degraded and single_threaded:
        logged_roles = snap.get("logged_contact_roles")
        single_threaded = (
            logged_roles is not None and logged_roles <= single_thread_max
        )

    flags = {
        "stale_activity": days_since_last_activity is not None
        and days_since_last_activity > thresholds["stale_activity_days"],
        "single_threaded": single_threaded,
        "overdue_close": days_to_close is not None and days_to_close < 0,
        "close_date_slipped": close_date_slippage is not None
        and close_date_slippage["times_pushed"] > 0,
        "stalled_in_stage": days_in_current_stage is not None
        and days_in_current_stage > thresholds.get("stalled_in_stage_days", 60),
        "email_data_stale": email_data_stale,
        "recent_rep_outbound": recent_rep_outbound,
        "economic_buyer_named": economic_buyer_named,
        "champion_identified": champion_identified,
        "paper_not_started": paper_not_started,
        "calendar_no_upcoming_late_stage": calendar_no_upcoming_late_stage,
        "calendar_no_recent_meeting_after_stage_move": calendar_no_recent_meeting_after_stage_move,
        "calendar_next_meeting_no_buyer_attendees": calendar_next_meeting_no_buyer_attendees,
    }

    if is_hygiene:
        hygiene = model.get("hygiene", {})
        hygiene_stale_days = hygiene.get("stale_activity_days", 30)
        logged_roles = snap.get("logged_contact_roles")
        champion_roles = snap.get("champion_contact_roles")
        next_step = snap.get("next_step")
        flags["no_contact_roles"] = (logged_roles or 0) == 0
        flags["no_champion"] = (champion_roles or 0) == 0
        flags["missing_next_step"] = not (next_step and str(next_step).strip())
        flags["stale_activity"] = (
            days_since_last_activity is not None
            and days_since_last_activity > hygiene_stale_days
        )

    json.dump(
        {
            "deal_age_days": deal_age_days,
            "days_to_close": days_to_close,
            "days_since_last_activity": days_since_last_activity,
            "days_in_current_stage": days_in_current_stage,
            "close_date_slippage": close_date_slippage,
            "contacts_engaged": contacts_engaged,
            "engagement_roles": snap.get("roles") or [],
            "legal_status": legal_status,
            "freshness": {
                "newest_email_date": newest_email.isoformat() if newest_email else None,
                "activity_anchor_date": activity_anchor.isoformat() if activity_anchor else None,
                "activity_anchor_source": activity_anchor_source,
                "last_outbound_date": last_outbound.isoformat() if last_outbound else None,
            },
            "email": {
                "count_out": count_out,
                "count_in": count_in,
                "days_since_last_inbound": days_since_last_inbound,
                "unanswered_rep_emails": unanswered_rep_emails,
                "median_response_latency_days": median_response_latency_days,
            },
            "calendar": {
                "coverage": calendar_coverage,
                "last_meeting_date": last_calendar_meeting.isoformat() if last_calendar_meeting else None,
                "next_meeting_date": next_calendar_meeting.isoformat() if next_calendar_meeting else None,
                "source_gaps": sorted(set(calendar_evidence.get("source_gaps") or [])),
            },
            "flags": flags,
            "coverage_gaps": coverage_gaps,
            "thresholds_used": thresholds,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
