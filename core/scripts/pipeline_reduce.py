#!/usr/bin/env python3
"""Reduce raw per-deal pipeline evidence into an analyze.py bundle.

The pipeline workflow can save connector payloads to files, run this reducer,
then pipe the result to analyze.py. Raw email bodies, full meeting metadata, and
Slack messages stay outside the roll-up context; only dates, participants,
source refs, and compact evidence metadata survive.

Usage:
  python3 pipeline_reduce.py < gather.json
"""
import json
import os
import re
import sys
from datetime import datetime


MAX_EVIDENCE_ITEMS = 8
MAX_SUMMARY_CHARS = 220
INTERNAL_DOMAINS = {"junipersquare.com"}


def read_json_file(path):
    if not path:
        return None
    with open(path) as f:
        return json.load(f)


def load_value(obj, key):
    if key in obj:
        return obj.get(key)
    file_key = key + "_file"
    if file_key in obj:
        return read_json_file(obj.get(file_key))
    return None


def first(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def compact_text(value, limit=MAX_SUMMARY_CHARS):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def parse_date(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def email_from_value(value):
    if not value:
        return None
    text = str(value)
    match = re.search(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", text)
    if match:
        return match.group(0).lower()
    return text.strip().lower() if "@" in text else None


def emails_from_value(value):
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(emails_from_value(item))
        return out
    if isinstance(value, dict):
        return emails_from_value(first(value.get("email"), value.get("address"), value.get("name")))
    return [m.lower() for m in re.findall(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", str(value))]


def domain_of(email):
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].lower()


def is_internal_email(email, internal_domains):
    domain = domain_of(email)
    return bool(domain and domain in internal_domains)


def is_prospect_email(email, internal_domains, prospect_domains):
    domain = domain_of(email)
    if not domain or domain in internal_domains:
        return False
    return not prospect_domains or domain in prospect_domains


def normalize_threads(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("threads", "gmail_threads", "items", "results"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return [raw]
    return []


def messages_from_thread(thread):
    if not isinstance(thread, dict):
        return []
    for key in ("messages", "message_list", "emails"):
        if isinstance(thread.get(key), list):
            return thread[key]
    return [thread] if any(k in thread for k in ("date", "from", "sender", "to", "body", "snippet")) else []


def reduce_emails(raw, internal_domains, prospect_domains):
    emails = []
    observed = set()
    evidence = []

    for thread_idx, thread in enumerate(normalize_threads(raw), start=1):
        thread_id = first(
            thread.get("id") if isinstance(thread, dict) else None,
            thread.get("thread_id") if isinstance(thread, dict) else None,
            f"thread:{thread_idx}",
        )
        subject = thread.get("subject") if isinstance(thread, dict) else None
        for msg_idx, msg in enumerate(messages_from_thread(thread), start=1):
            if not isinstance(msg, dict):
                continue
            date = parse_date(first(msg.get("date"), msg.get("internalDate"), msg.get("timestamp")))
            if not date:
                continue
            sender = email_from_value(first(msg.get("from"), msg.get("sender"), msg.get("from_email")))
            recipients = []
            for field in ("to", "recipients", "cc", "bcc"):
                recipients.extend(emails_from_value(msg.get(field)))
            for email in [sender, *recipients]:
                if is_prospect_email(email, internal_domains, prospect_domains):
                    observed.add(email)

            direction = str(msg.get("direction") or "").strip().lower()
            if direction not in {"in", "out"}:
                if is_prospect_email(sender, internal_domains, prospect_domains):
                    direction = "in"
                elif is_internal_email(sender, internal_domains):
                    direction = "out"
                elif any(is_prospect_email(e, internal_domains, prospect_domains) for e in recipients):
                    direction = "out"
                else:
                    direction = "unknown"
            if direction in {"in", "out"}:
                source_ref = first(msg.get("source_ref"), msg.get("id"), msg.get("message_id"), f"{thread_id}:{msg_idx}")
                emails.append({"direction": direction, "date": date, "source_ref": source_ref})
                if len(evidence) < MAX_EVIDENCE_ITEMS:
                    evidence.append({
                        "type": "email",
                        "date": date,
                        "direction": direction,
                        "subject": compact_text(subject, 120),
                        "source_ref": source_ref,
                    })

    emails.sort(key=lambda item: (item["date"], item.get("source_ref") or ""))
    return {
        "emails": emails,
        "observed_participants": sorted(observed),
        "evidence": evidence,
    }


def reduce_calendar(raw, internal_domains, prospect_domains):
    if not raw:
        return {"calendar_evidence": None, "observed_participants": [], "evidence": []}
    if isinstance(raw, dict):
        source = raw
    else:
        source = {"coverage": "available", "historical_meetings": raw if isinstance(raw, list) else []}

    calendar = {
        "coverage": source.get("coverage") or "available",
        "historical_meetings": [],
        "upcoming_meetings": [],
        "source_gaps": list(source.get("source_gaps") or []),
    }

    observed = set()
    evidence = []
    bucket_pairs = (
        ("historical_meetings", "historical_meetings"),
        ("history", "historical_meetings"),
        ("upcoming_meetings", "upcoming_meetings"),
        ("future", "upcoming_meetings"),
    )
    for source_bucket, target_bucket in bucket_pairs:
        for event in source.get(source_bucket) or []:
            attendees = emails_from_value(event.get("attendees") or event.get("participants") or [])
            buyer_attendees = [
                email for email in attendees
                if is_prospect_email(email, internal_domains, prospect_domains)
            ]
            observed.update(buyer_attendees)
            compact_event = {
                "title": compact_text(event.get("title") or event.get("summary"), 120),
                "start": first(event.get("start"), event.get("start_time")),
                "end": first(event.get("end"), event.get("end_time")),
                "attendees": attendees,
                "buyer_attendees": buyer_attendees,
                "organizer": event.get("organizer"),
                "conference_link": event.get("conference_link"),
                "source_ref": event.get("source_ref") or event.get("id"),
            }
            calendar[target_bucket].append(compact_event)
            if len(evidence) < MAX_EVIDENCE_ITEMS:
                evidence.append({
                    "type": "calendar",
                    "title": compact_event["title"],
                    "start": compact_event["start"],
                    "buyer_attendees": buyer_attendees,
                    "source_ref": compact_event["source_ref"],
                })
    return {"calendar_evidence": calendar, "observed_participants": sorted(observed), "evidence": evidence}


def reduce_internal_evidence(raw):
    if not raw:
        return None

    deal_room = raw.get("deal_room") or {}
    linked_docs = []
    for doc in raw.get("linked_docs") or []:
        linked_docs.append({
            "source": doc.get("source"),
            "title": compact_text(doc.get("title"), 120),
            "coverage": doc.get("coverage"),
            "source_ref": doc.get("source_ref"),
        })

    def compact_signals(items):
        signals = []
        for sig in items or []:
            if not sig.get("source_ref"):
                continue
            signals.append({
                "type": sig.get("type"),
                "summary": compact_text(sig.get("summary"), MAX_SUMMARY_CHARS),
                "source_ref": sig.get("source_ref"),
                "confidence": sig.get("confidence"),
            })
        return signals

    out = {
        "mode": raw.get("mode"),
        "coverage": raw.get("coverage"),
        "deal_room": {
            "source": deal_room.get("source"),
            "coverage": deal_room.get("coverage"),
            "source_ref": deal_room.get("source_ref"),
        },
        "linked_docs": linked_docs,
        "signals": compact_signals(raw.get("signals")),
        "workflow_signals": compact_signals(raw.get("workflow_signals")),
        "source_gaps": list(raw.get("source_gaps") or []),
    }
    return out


def normalize_meetings(raw):
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("meetings", "items", "results", "recordings"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return [raw]
    return []


def reduce_zoom(raw, internal_domains, prospect_domains):
    latest_call_date = None
    observed = set()
    evidence = []
    for idx, meeting in enumerate(normalize_meetings(raw), start=1):
        if not isinstance(meeting, dict):
            continue
        date = parse_date(first(meeting.get("start_time"), meeting.get("start"), meeting.get("date"), meeting.get("created_at")))
        if date and (latest_call_date is None or date > latest_call_date):
            latest_call_date = date
        attendees = emails_from_value(meeting.get("attendees") or meeting.get("participants") or [])
        buyer_attendees = [
            email for email in attendees
            if is_prospect_email(email, internal_domains, prospect_domains)
        ]
        observed.update(buyer_attendees)
        if len(evidence) < MAX_EVIDENCE_ITEMS:
            evidence.append({
                "type": "zoom_meeting",
                "date": date,
                "title": compact_text(first(meeting.get("topic"), meeting.get("title"), meeting.get("summary")), 120),
                "buyer_attendees": buyer_attendees,
                "source_ref": first(meeting.get("source_ref"), meeting.get("uuid"), meeting.get("id"), f"meeting:{idx}"),
            })
    return {"latest_call_date": latest_call_date, "observed_participants": sorted(observed), "evidence": evidence}


def main():
    gather = json.load(sys.stdin)
    internal_domains = set(gather.get("internal_domains") or INTERNAL_DOMAINS)
    prospect_domains = set(gather.get("prospect_domains") or [])

    email = reduce_emails(load_value(gather, "email_threads"), internal_domains, prospect_domains)
    calendar = reduce_calendar(load_value(gather, "calendar_evidence"), internal_domains, prospect_domains)
    zoom = reduce_zoom(load_value(gather, "zoom_meetings"), internal_domains, prospect_domains)
    internal_evidence = reduce_internal_evidence(load_value(gather, "internal_evidence"))

    compute_input = dict(gather.get("compute_input") or {})
    if email["emails"] and "emails" not in compute_input:
        compute_input["emails"] = email["emails"]
    observed = set(compute_input.get("observed_participants") or [])
    observed.update(email["observed_participants"])
    observed.update(calendar["observed_participants"])
    observed.update(zoom["observed_participants"])
    if observed:
        compute_input["observed_participants"] = sorted(observed)
    if zoom["latest_call_date"] and "latest_call_date" not in compute_input:
        compute_input["latest_call_date"] = zoom["latest_call_date"]

    out = {
        "rep_name": gather.get("rep_name"),
        "compute_input": compute_input,
        "prior_opps": gather.get("prior_opps") or [],
        "connector_status": gather.get("connector_status") or {},
        "calendar_evidence": calendar["calendar_evidence"],
        "internal_evidence": internal_evidence,
        "evidence_summary": {
            "emails": email["evidence"],
            "calendar": calendar["evidence"],
            "zoom": zoom["evidence"],
        },
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
