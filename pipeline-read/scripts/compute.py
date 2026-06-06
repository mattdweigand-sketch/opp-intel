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
from datetime import date
from statistics import median


def parse(d):
    return date.fromisoformat(d) if d else None


def days_between(later, earlier):
    if later is None or earlier is None:
        return None
    return (later - earlier).days


def main():
    snap = json.load(sys.stdin)

    model_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core", "config", "risk-model.json"))
    with open(model_path) as f:
        model = json.load(f)
    thresholds = model["thresholds"]

    today = parse(snap.get("today")) or date.today()
    opp = snap.get("opportunity", {}) or {}
    created = parse(opp.get("created_date"))
    close = parse(opp.get("close_date"))
    last_activity = parse(opp.get("last_activity_date"))

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
    email_data_stale = activity_anchor is not None and (
        newest_email is None
        or (activity_anchor - newest_email).days > thresholds.get("freshness_gap_days", 5)
    )
    days_since_last_outbound = days_between(today, last_outbound)
    recent_rep_outbound = (
        days_since_last_outbound is not None
        and days_since_last_outbound <= thresholds.get("recent_outbound_days", 3)
    )

    flags = {
        "stale_activity": days_since_last_activity is not None
        and days_since_last_activity > thresholds["stale_activity_days"],
        "single_threaded": contacts_engaged is not None
        and contacts_engaged <= thresholds["single_thread_max_contacts"],
        "overdue_close": days_to_close is not None and days_to_close < 0,
        "close_date_slipped": close_date_slippage is not None
        and close_date_slippage["times_pushed"] > 0,
        "stalled_in_stage": days_in_current_stage is not None
        and days_in_current_stage > thresholds.get("stalled_in_stage_days", 60),
        "email_data_stale": email_data_stale,
        "recent_rep_outbound": recent_rep_outbound,
    }

    # Hygiene flags: CRM data-quality, only emitted on a hygiene run so triage/forecast
    # flag dicts stay byte-identical. SF-only inputs; no email/Zoom needed. 'stale_activity'
    # is recomputed here against the looser hygiene threshold (it never coexists with a
    # risk run, so there is no conflict). missing_amount is added later by rollup.py, which
    # owns the amount basis.
    if snap.get("hygiene"):
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
            "freshness": {
                "newest_email_date": newest_email.isoformat() if newest_email else None,
                "activity_anchor_date": activity_anchor.isoformat() if activity_anchor else None,
                "last_outbound_date": last_outbound.isoformat() if last_outbound else None,
            },
            "email": {
                "count_out": count_out,
                "count_in": count_in,
                "days_since_last_inbound": days_since_last_inbound,
                "unanswered_rep_emails": unanswered_rep_emails,
                "median_response_latency_days": median_response_latency_days,
            },
            "flags": flags,
            "thresholds_used": thresholds,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
