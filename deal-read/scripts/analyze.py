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
    "transcript_file": "/abs/path/to/asset.json",   # optional; enables call_execution
    "prior_opps": [ { closed opps on the same account } ],  # optional
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
    for sig in raw.get("signals") or []:
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


def main():
    bundle = json.load(sys.stdin)

    deal_metrics = run_script("compute.py", stdin_obj=bundle.get("compute_input", {}))

    call_execution = None
    tf = bundle.get("transcript_file")
    if tf and os.path.exists(tf):
        call_execution = run_script("callstats.py", args=[bundle.get("rep_name", ""), tf])

    out = {
        "deal_metrics": deal_metrics,
        "call_execution": call_execution,
        "account_history": account_history(bundle.get("prior_opps")),
        "internal_evidence": normalize_internal_evidence(bundle.get("internal_evidence")),
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
