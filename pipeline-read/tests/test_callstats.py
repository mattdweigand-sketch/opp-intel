#!/usr/bin/env python3
"""Tests for callstats.py — pins call-execution metrics against fixtures.

No pytest needed. Run: python3 test_callstats.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CALLSTATS = os.path.join(HERE, "..", "scripts", "callstats.py")


def run(rep_name, items):
    p = subprocess.run(
        [sys.executable, CALLSTATS, rep_name],
        input=json.dumps({"transcript_items": items}),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True

    # Fixture 1: rep dominates. Hand-computed: rep 17 / total 21 = 0.81,
    # 1 question, longest monologue 14 words (items 3+4 are one consecutive turn).
    r = run("Matthew Weigand", [
        {"text": "Matthew Weigand: Good afternoon, Stephanie."},
        {"text": "Stephanie Smith: Hey, how are you?"},
        {"text": "Matthew Weigand: Doing well. What is your budget?"},
        {"text": "Matthew Weigand: I can keep going on and on here."},
    ])
    ok &= check("F1: rep_talk_ratio 0.81", r["rep_talk_ratio"] == 0.81)
    ok &= check("F1: rep_questions 1", r["rep_questions"] == 1)
    ok &= check("F1: longest_rep_monologue_words 14", r["longest_rep_monologue_words"] == 14)
    ok &= check("F1: turns 3", r["turns"] == 3)
    ok &= check("F1: talk_ratio_high True", r["flags"]["talk_ratio_high"] is True)

    # Fixture 2: rep lets the prospect talk. Ratio well under threshold.
    r = run("Matthew Weigand", [
        {"text": "Matthew Weigand: Tell me about the fund?"},
        {"text": "John Mejia: We just launched a five hundred million dollar real estate development fund deploying capital nationally."},
        {"text": "John Mejia: It blends LP money and letters of credit."},
    ])
    ok &= check("F2: talk_ratio_high False", r["flags"]["talk_ratio_high"] is False)
    ok &= check("F2: rep_questions 1", r["rep_questions"] == 1)

    # Fixture 3: empty transcript is null-safe.
    r = run("Matthew Weigand", [])
    ok &= check("F3: rep_talk_ratio None", r["rep_talk_ratio"] is None)
    ok &= check("F3: talk_ratio_high False", r["flags"]["talk_ratio_high"] is False)

    # Fixture 4: speaker with no "Name:" prefix counts as Unknown, no crash.
    r = run("Matthew Weigand", [{"text": "just some text without a speaker prefix"}])
    ok &= check("F4: Unknown speaker handled", "Unknown" in r["speakers"])

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
