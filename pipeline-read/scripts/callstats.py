#!/usr/bin/env python3
"""Deterministic call-execution metrics from a Zoom transcript.

Coaches HOW the rep ran the call (talk ratio, questions, monologuing) — the
counting half. Discovery-topic coverage is a semantic judgment left to the model.

Usage:
  python3 callstats.py "<rep name>" <asset_or_transcript.json>
  python3 callstats.py "<rep name>"            # reads JSON on stdin

The input JSON may be a full get_meeting_assets object (has
meeting_transcript.transcript_items), a {"transcript_items": [...]} object, or a
bare list of items. Each item is {"start","end","text"} where text is
"Speaker Name: utterance". Speaker has no own field; it's the prefix before the
first ": ".

A turn is "rep" if rep_name (case-insensitive) appears in the speaker label.
Thresholds come from the sibling risk-model.json call_execution block.
"""
import json
import os
import sys


def load_thresholds():
    path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core", "config", "risk-model.json"))
    try:
        with open(path) as f:
            return json.load(f).get("call_execution", {})
    except (OSError, ValueError):
        return {}


def extract_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "meeting_transcript" in data:
            return (data.get("meeting_transcript") or {}).get("transcript_items", []) or []
        return data.get("transcript_items", []) or []
    return []


def split_speaker(text):
    if ": " in text:
        speaker, _, utterance = text.partition(": ")
        return speaker.strip(), utterance.strip()
    return "Unknown", text.strip()


def main():
    rep_name = sys.argv[1] if len(sys.argv) > 1 else ""
    if len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    items = extract_items(data)
    thresholds = load_thresholds()
    ratio_max = thresholds.get("rep_talk_ratio_max", 0.6)
    rep_key = rep_name.lower().strip()

    words = {}            # speaker -> word count
    rep_questions = 0
    longest_rep_monologue = 0
    cur_speaker = None
    cur_turn_words = 0
    turns = 0

    def is_rep(speaker):
        return bool(rep_key) and rep_key in speaker.lower()

    for item in items:
        speaker, utterance = split_speaker(item.get("text", ""))
        n = len(utterance.split())
        words[speaker] = words.get(speaker, 0) + n
        if is_rep(speaker):
            rep_questions += utterance.count("?")
        # group consecutive same-speaker items into one turn
        if speaker != cur_speaker:
            turns += 1
            cur_speaker = speaker
            cur_turn_words = n
        else:
            cur_turn_words += n
        if is_rep(speaker):
            longest_rep_monologue = max(longest_rep_monologue, cur_turn_words)

    total_words = sum(words.values())
    rep_words = sum(n for s, n in words.items() if is_rep(s))
    rep_talk_ratio = round(rep_words / total_words, 2) if total_words else None

    json.dump(
        {
            "rep_name": rep_name,
            "turns": turns,
            "speakers": sorted(words.keys()),
            "words_by_speaker": words,
            "total_words": total_words,
            "rep_words": rep_words,
            "rep_talk_ratio": rep_talk_ratio,
            "rep_questions": rep_questions,
            "longest_rep_monologue_words": longest_rep_monologue,
            "flags": {
                "talk_ratio_high": rep_talk_ratio is not None and rep_talk_ratio > ratio_max,
            },
            "thresholds_used": {"rep_talk_ratio_max": ratio_max},
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
