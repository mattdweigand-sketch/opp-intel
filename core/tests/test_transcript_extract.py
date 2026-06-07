#!/usr/bin/env python3
"""Tests for transcript_extract.py and analyze.py transcript reduction."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE_SCRIPTS = os.path.join(ROOT, "core", "scripts")


def run_script(script, payload=None, args=None):
    proc = subprocess.run(
        [sys.executable, os.path.join(CORE_SCRIPTS, script)] + (args or []),
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip())
    return json.loads(proc.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def write_asset(payload):
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(payload, handle)
        handle.close()
        return handle.name
    except Exception:
        handle.close()
        os.unlink(handle.name)
        raise


def main():
    ok = True
    asset = {
        "meeting_transcript": {
            "transcript_items": [
                {"text": "Matt: What is your budget and decision process?"},
                {"text": "Buyer: Our process is manual and painful in Excel."},
                {"text": "Buyer: We also looked at Allvue and SS&C."},
                {"text": "Matt: I will send the follow-up by Friday."},
                {"text": "Buyer: Sounds good, that works."},
            ],
        },
        "attendees": [
            {"name": "Buyer One", "email": "buyer@example.com"},
            {"name": "Matt Weigand", "email": "matt@junipersquare.com"},
        ],
    }
    path = write_asset(asset)
    try:
        extracted = run_script("transcript_extract.py", args=[path])
        ok &= check("extract: zoom json detected", extracted["source_format"] == "zoom_json")
        ok &= check("extract: turn count", extracted["stats"]["turn_count"] == 5)
        ok &= check("extract: question bucket", "decision process" in extracted["questions_raised"][0]["text"])
        ok &= check("extract: pain bucket", "manual and painful" in extracted["pain_signals"][0]["text"])
        ok &= check("extract: tool bucket", any("Allvue" in s["text"] for s in extracted["competitive_mentions"]))
        ok &= check("extract: internal attendees filtered", len(extracted["contact_candidates"]) == 1)
        ok &= check("extract: action bucket", "follow-up" in extracted["action_items"][0]["text"])
        ok &= check("extract: decision bucket", any("works" in s["text"] for s in extracted["decision_points"]))
        ok &= check("extract: no raw transcript field", "raw" not in extracted)

        analyzed = run_script("analyze.py", {
            "rep_name": "Matt",
            "transcript_file": path,
            "compute_input": {},
        })
        ok &= check("analyze: call execution emitted", analyzed["call_execution"]["turns"] == 4)
        ok &= check("analyze: call extract emitted", analyzed["call_extract"]["stats"]["turn_count"] == 5)
        ok &= check("analyze: call extract omits raw transcript", "raw" not in analyzed["call_extract"])
    finally:
        os.unlink(path)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
