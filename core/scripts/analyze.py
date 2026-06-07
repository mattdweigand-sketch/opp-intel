#!/usr/bin/env python3
"""One entrypoint for all deterministic deal-read processing.

The model gathers raw data (only it can call the connectors), dumps it into one
bundle, and runs this once. analyze.py orchestrates compute.py + callstats.py and
parses account history, so the model never stitches the pieces together itself.

Usage: python3 analyze.py        # reads the bundle JSON on stdin
Bundle:
  {
    "rep_name": "Matthew Weigand",
    "compute_input": { ... what compute.py expects ... },
    "transcript_file": "/abs/path/to/asset.json",   # optional; enables call_execution + call_extract
    "prior_opps": [ { closed opps on the same account } ],  # optional
    "calendar_evidence": { ... historical + upcoming meetings } # optional
    "internal_evidence": { ... Slack + linked-doc findings } # optional
  }
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run_script(script, args=None, stdin_obj=None):
    p = subprocess.run(
        [sys.executable, os.path.join(HERE, script)] + (args or []),
        input=json.dumps(stdin_obj) if stdin_obj is not None else None,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"{script} failed: {p.stderr.strip()}")
    return json.loads(p.stdout)


def loss_reason(opp):
    for k in ("JSQ_Loss_Notes__c", "JSQ_Loss_Reason__c", "Lost_Reason__c", "Primary_Risk_Lost_Reason__c"):
        if opp.get(k):
            return opp[k]
    return "no reason recorded"


def account_history(prior_opps):
    prior_opps = prior_opps or []
    lost = [
        o for o in prior_opps
        if o.get("IsWon") is False or str(o.get("StageName", "")).lower() in {"lost", "closed lost"}
    ]
    won = [
        o for o in prior_opps
        if o.get("IsWon") is True or str(o.get("StageName", "")).lower() in {"won", "closed won"}
    ]
    most_recent = lost[0] if lost else None  # query is ordered CloseDate DESC
    if not prior_opps:
        summary = "No prior closed deals on this account."
    elif lost:
        summary = (
            f"Lost {len(lost)} time(s) on this account"
            + (f", {len(won)} win(s)" if won else "")
            + f". Most recent loss {most_recent.get('CloseDate')}: {loss_reason(most_recent)}"
        )
    else:
        summary = f"{len(won)} prior win(s), no losses on this account."
    return {
        "prior_losses": len(lost),
        "prior_wins": len(won),
        "most_recent_loss": (
            {"name": most_recent.get("Name"), "close_date": most_recent.get("CloseDate"),
             "reason": loss_reason(most_recent)} if most_recent else None
        ),
        "summary": summary,
    }


def normalize_internal_evidence(raw):
    """Keep only source-backed internal evidence and explicit coverage gaps."""
    raw = raw or {}
    if not raw:
        return None

    deal_room = raw.get("deal_room") or {}
    coverage = deal_room.get("coverage") or raw.get("coverage")

    linked_docs = []
    for doc in raw.get("linked_docs") or []:
        linked_docs.append({
            "source": doc.get("source"),
            "title": doc.get("title"),
            "coverage": doc.get("coverage"),
            "source_ref": doc.get("source_ref"),
        })

    signals = []
    # Workflow-tool signals (derived from the Gmail workflow_signals sweep) are folded in
    # alongside Slack/Drive signals. Same contract: a source_ref is required, or the entry is
    # dropped. Internal-evidence lane only — never ranking or flag_severity.
    for sig in (raw.get("signals") or []) + (raw.get("workflow_signals") or []):
        if not sig.get("source_ref"):
            continue
        signals.append({
            "type": sig.get("type"),
            "summary": sig.get("summary"),
            "source_ref": sig.get("source_ref"),
            "confidence": sig.get("confidence"),
        })

    source_gaps = list(raw.get("source_gaps") or [])
    if coverage in {"deal_room_missing", "checked_no_match", "unavailable"}:
        source_gaps.append(coverage)
    for doc in linked_docs:
        if doc.get("coverage") in {"unavailable", "skipped"}:
            source_gaps.append("linked_doc_" + doc.get("coverage"))

    return {
        "mode": raw.get("mode"),
        "deal_room": {
            "source": deal_room.get("source"),
            "coverage": coverage,
            "source_ref": deal_room.get("source_ref"),
        },
        "linked_docs": linked_docs,
        "signals": signals,
        "source_gaps": sorted(set(source_gaps)),
    }


def normalize_calendar_evidence(raw):
    """Preserve read-only Calendar evidence and explicit coverage gaps."""
    raw = raw or {}
    if not raw:
        return None

    source_gaps = list(raw.get("source_gaps") or [])
    coverage = raw.get("coverage")
    if coverage in {"insufficient_context", "unavailable", "checked_no_match"}:
        source_gaps.append(
            "calendar_context_missing" if coverage == "insufficient_context" else "calendar_" + coverage
        )

    def compact_event(event):
        compact = {
            "title": event.get("title"),
            "start": event.get("start") or event.get("start_time"),
            "end": event.get("end") or event.get("end_time"),
            "attendees": event.get("attendees") or [],
            "organizer": event.get("organizer"),
            "conference_link": event.get("conference_link"),
            "source_ref": event.get("source_ref"),
        }
        if "buyer_attendees" in event:
            compact["buyer_attendees"] = event.get("buyer_attendees") or []
        return compact

    historical = first_list(raw.get("historical_meetings"), raw.get("history"))
    upcoming = first_list(raw.get("upcoming_meetings"), raw.get("future"))

    return {
        "coverage": coverage,
        "historical_meetings": [compact_event(e) for e in historical],
        "upcoming_meetings": [compact_event(e) for e in upcoming],
        "source_gaps": sorted(set(source_gaps)),
    }


def first_list(*values):
    for value in values:
        if isinstance(value, list):
            return value
    return []


def main():
    bundle = json.load(sys.stdin)

    calendar_evidence = normalize_calendar_evidence(bundle.get("calendar_evidence"))
    compute_input = dict(bundle.get("compute_input") or {})
    if calendar_evidence and "calendar_evidence" not in compute_input:
        compute_input["calendar_evidence"] = calendar_evidence
    if bundle.get("connector_status") and "connector_status" not in compute_input:
        compute_input["connector_status"] = bundle.get("connector_status")
    deal_metrics = run_script("compute.py", stdin_obj=compute_input)

    call_execution = None
    call_extract = None
    tf = bundle.get("transcript_file")
    if tf and os.path.exists(tf):
        call_execution = run_script("callstats.py", args=[bundle.get("rep_name", ""), tf])
        call_extract = run_script("transcript_extract.py", args=[tf])

    out = {
        "deal_metrics": deal_metrics,
        "call_execution": call_execution,
        "account_history": account_history(bundle.get("prior_opps")),
        "calendar_evidence": calendar_evidence,
        "internal_evidence": normalize_internal_evidence(bundle.get("internal_evidence")),
    }
    if call_extract is not None:
        out["call_extract"] = call_extract
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
