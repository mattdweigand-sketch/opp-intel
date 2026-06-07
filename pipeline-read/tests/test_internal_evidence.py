#!/usr/bin/env python3
"""Tests for Slack/Drive internal-evidence planning and preservation."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(HERE, "..", "scripts", "plan.py")
ANALYZE = os.path.join(HERE, "..", "scripts", "analyze.py")


def run_script(script, payload):
    p = subprocess.run([sys.executable, script], input=json.dumps(payload),
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    channel = run_script(PLAN, {
        "deal_name": "Acme Growth Fund",
        "account_name": "Acme",
        "forecast": True,
        "internal": "auto",
    })
    ie = channel["internal_evidence"]
    ok &= check("auto channel: slack channel lookup emitted",
                ie["slack"]["query_type"] == "channel_name_lookup")
    ok &= check("auto channel: hyphen channel variant emitted",
                "acme-growth-fund" in ie["slack"]["terms"])
    ok &= check("auto channel: linked docs restricted to deal-room relationship",
                ie["linked_docs"]["relationship"] == "linked_from_deal_room")
    ok &= check("auto channel: linked docs only allowed from explicit context",
                ie["linked_docs"]["allowed_when"] == ["linked_from_deal_room", "explicit_deal_context"])

    missing = run_script(PLAN, {
        "deal_name": "Acme Growth Fund",
        "account_name": "Acme",
        "forecast": True,
        "internal": "auto",
    })
    ok &= check("auto missing: channel-name lookup emitted",
                missing["internal_evidence"]["slack"]["query_type"] == "channel_name_lookup")
    ok &= check("auto missing: no broad slack search",
                missing["internal_evidence"]["broad_search_allowed"] is False
                and missing["internal_evidence"]["slack"]["broad_search_allowed"] is False)

    off = run_script(PLAN, {
        "deal_name": "Acme Growth Fund",
        "account_name": "Acme",
        "forecast": True,
        "internal": "off",
    })
    ok &= check("off: no internal evidence query emitted", "internal_evidence" not in off)

    force = run_script(PLAN, {
        "deal_name": "Acme Growth Fund",
        "account_name": "Acme",
        "forecast": True,
        "internal": "force",
    })
    ok &= check("force: bounded fallback lookup emitted",
                force["internal_evidence"]["slack"]["query_type"] == "bounded_fallback_lookup")
    ok &= check("force: broad lookup is explicitly force-gated",
                force["internal_evidence"]["slack"]["requires_internal_force"] is True)

    analyzed = run_script(ANALYZE, {
        "compute_input": {"today": "2026-06-05"},
        "internal_evidence": {
            "mode": "auto",
            "deal_room": {"source": "slack", "coverage": "found", "source_ref": "C123/1710000000"},
            "linked_docs": [
                {"source": "google_drive", "title": "Proposal", "coverage": "read",
                 "source_ref": "drive/file/abc"},
                {"source": "google_drive", "title": "Missing redlines", "coverage": "unavailable"},
            ],
            "signals": [
                {"type": "legal_blocker", "summary": "Waiting on redlines.",
                 "source_ref": "C123/1710000000", "confidence": "Medium"},
                {"type": "pricing_approval", "summary": "No source ref, must be dropped."},
            ],
        },
    })
    out_ie = analyzed["internal_evidence"]
    ok &= check("analyze: source-backed signal preserved",
                [s["type"] for s in out_ie["signals"]] == ["legal_blocker"])
    ok &= check("analyze: unavailable linked doc becomes gap",
                "linked_doc_unavailable" in out_ie["source_gaps"])

    # --- Workflow-tool signals: source-backed entry survives normalization; bare one is dropped.
    wf = run_script(ANALYZE, {
        "compute_input": {"today": "2026-06-05"},
        "internal_evidence": {
            "mode": "force",
            "workflow_signals": [
                {"type": "clm_stage", "summary": "Ironclad order form at Sign stage.",
                 "source_ref": "gmail/msg/abc123", "confidence": "High"},
                {"type": "call_activity", "summary": "No source ref, must be dropped."},
            ],
        },
    })
    wf_signals = wf["internal_evidence"]["signals"]
    ok &= check("analyze: workflow signal with source_ref preserved",
                [s["type"] for s in wf_signals] == ["clm_stage"])
    ok &= check("analyze: workflow signal source_ref carried through",
                wf_signals[0]["source_ref"] == "gmail/msg/abc123")
    ok &= check("analyze: workflow signal without source_ref dropped",
                all(s["type"] != "call_activity" for s in wf_signals))

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
