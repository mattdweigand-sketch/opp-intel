#!/usr/bin/env python3
"""Deterministic transcript signal extractor.

This is the semantic companion to callstats.py. It reads a Zoom/Gong asset JSON
or a plain transcript and emits capped signal buckets so downstream workflow
steps can use structured excerpts instead of loading raw transcript text into
model context.

Usage:
  python3 transcript_extract.py <asset_or_transcript_file>
  python3 transcript_extract.py             # reads JSON or text on stdin
"""
import json
import os
import re
import sys


MAX_BUCKET = 12
MAX_EXCERPT_CHARS = 240

ACTION_PATTERNS = [
    re.compile(r"\b(i'll|i will|we'll|we will|i'm going to|we're going to|we need to|i need to)\b", re.I),
    re.compile(r"\b(send|share|forward|circulate|loop in|cc|introduce|follow up|circle back|get back)\b", re.I),
    re.compile(r"\b(next step|action item|to-?do|deliverable)\b", re.I),
]

DECISION_PATTERNS = [
    re.compile(r"\b(agreed|decided|sounds good|that works|makes sense|let's do|we'll go|approved)\b", re.I),
    re.compile(r"\b(by|on)\s+(monday|tuesday|wednesday|thursday|friday|next week|this week|eod|cob)\b", re.I),
]

PAIN_PATTERNS = [
    re.compile(r"\b(manual|painful|cumbersome|messy|broken|tedious|slow|clunky|frustrating|fragmented)\b", re.I),
    re.compile(r"\b(takes|spend|spending)\s+(hours|days|weeks)\b", re.I),
    re.compile(r"\b(overwhelmed|swamped|behind on|crazy right now)\b", re.I),
]

TOOL_VOCAB = [
    "SS&C", "SSC", "Allvue", "SEI", "eFront", "Investran", "Carta", "AngelList",
    "Diligence Vault", "Dasseti", "DocSend", "SharePoint", "Dropbox", "Box",
    "Notion", "Slack", "ChatGPT", "Claude", "Gemini", "OpenAI", "Salesforce", "Excel",
]
TOOL_RE = re.compile(r"\b(" + "|".join(re.escape(v) for v in TOOL_VOCAB) + r")\b", re.I)

QUESTION_LEAD_RE = re.compile(
    r"^\s*(how|what|when|where|why|who|which|can|could|would|should|do|does|did|are|is|will|may)\b",
    re.I,
)

TIMESTAMP_SPEAKER_RE = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[|｜]\s*(.+?)\s*$")


def load_input(path=None):
    if path:
        with open(path) as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()
    try:
        return json.loads(raw), raw
    except ValueError:
        return raw, raw


def split_speaker(text):
    if ": " in text:
        speaker, _, utterance = text.partition(": ")
        return speaker.strip(), utterance.strip()
    return None, text.strip()


def extract_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("meeting_transcript"), dict):
            return data["meeting_transcript"].get("transcript_items") or []
        return data.get("transcript_items") or []
    return []


def text_from_item(item):
    if not isinstance(item, dict):
        return str(item)
    text = item.get("text") or item.get("utterance") or item.get("content") or ""
    speaker = item.get("speaker") or item.get("speaker_name")
    if speaker and ": " not in text:
        return f"{speaker}: {text}"
    return text


def turns_from_items(items):
    turns = []
    for idx, item in enumerate(items):
        text = text_from_item(item)
        speaker, utterance = split_speaker(text)
        if not utterance:
            continue
        turns.append({
            "index": idx,
            "speaker": speaker or "Unknown",
            "text": utterance,
            "source_ref": f"transcript_item:{idx + 1}",
        })
    return turns


def turns_from_plain(raw):
    turns = []
    current = None
    for line_no, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        match = TIMESTAMP_SPEAKER_RE.match(stripped)
        if match:
            if current:
                turns.append(current)
            speaker = match.group(2).strip().rstrip(":")
            current = {
                "index": len(turns),
                "speaker": speaker,
                "text": "",
                "source_ref": f"line:{line_no}",
            }
            continue
        speaker, utterance = split_speaker(stripped)
        if speaker:
            if current:
                turns.append(current)
            current = {
                "index": len(turns),
                "speaker": speaker,
                "text": utterance,
                "source_ref": f"line:{line_no}",
            }
        elif current:
            current["text"] = (current["text"] + " " + stripped).strip()
        else:
            turns.append({
                "index": len(turns),
                "speaker": "Unknown",
                "text": stripped,
                "source_ref": f"line:{line_no}",
            })
    if current:
        turns.append(current)
    return [t for t in turns if t["text"]]


def extract_attendees(data):
    if not isinstance(data, dict):
        return []
    candidates = []
    for key in ("attendees", "participants", "meeting_participants"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    if isinstance(data.get("meeting"), dict):
        for key in ("attendees", "participants"):
            value = data["meeting"].get(key)
            if isinstance(value, list):
                candidates.extend(value)

    out = []
    seen = set()
    for item in candidates:
        if isinstance(item, str):
            name = item.strip()
            email = None
            org = None
        elif isinstance(item, dict):
            name = (item.get("name") or item.get("display_name") or item.get("email") or "").strip()
            email = item.get("email")
            org = item.get("org") or item.get("organization") or item.get("company")
        else:
            continue
        if not name:
            continue
        internal_text = " ".join(str(v or "") for v in (name, email, org)).lower()
        if "juniper square" in internal_text or "@junipersquare.com" in internal_text:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        contact = {"name": name, "source": "meeting_attendees"}
        if email:
            contact["email"] = email
        out.append(contact)
    return out[:MAX_BUCKET]


def excerpt(text):
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= MAX_EXCERPT_CHARS:
        return clean
    return clean[: MAX_EXCERPT_CHARS - 3].rstrip() + "..."


def span(turn):
    return {
        "text": excerpt(turn["text"]),
        "speaker": turn["speaker"],
        "source_ref": turn["source_ref"],
    }


def add_unique(bucket_name, bucket, seen, turn):
    text_key = excerpt(turn["text"]).lower()
    key = (bucket_name, turn["speaker"].lower(), text_key)
    if key in seen:
        return
    seen.add(key)
    bucket.append(span(turn))


def bucketize(turns):
    buckets = {
        "action_items": [],
        "decision_points": [],
        "questions_raised": [],
        "pain_signals": [],
        "competitive_mentions": [],
    }
    seen = set()

    for turn in turns:
        text = turn["text"]
        if any(p.search(text) for p in ACTION_PATTERNS):
            add_unique("action_items", buckets["action_items"], seen, turn)
        if any(p.search(text) for p in DECISION_PATTERNS):
            add_unique("decision_points", buckets["decision_points"], seen, turn)
        if "?" in text or QUESTION_LEAD_RE.search(text):
            add_unique("questions_raised", buckets["questions_raised"], seen, turn)
        if any(p.search(text) for p in PAIN_PATTERNS):
            add_unique("pain_signals", buckets["pain_signals"], seen, turn)
        if TOOL_RE.search(text):
            add_unique("competitive_mentions", buckets["competitive_mentions"], seen, turn)

    for key in buckets:
        buckets[key] = buckets[key][:MAX_BUCKET]
    return buckets


def estimate_tokens(raw):
    return int((len(raw or "") + 3) / 4)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    data, raw = load_input(path)
    items = extract_items(data)
    if items:
        turns = turns_from_items(items)
        source_format = "zoom_json"
    else:
        turns = turns_from_plain(raw if isinstance(raw, str) else "")
        source_format = "plain_text"

    buckets = bucketize(turns)
    out = {
        "source_format": source_format,
        "stats": {
            "turn_count": len(turns),
            "raw_token_estimate": estimate_tokens(raw),
            "bucket_cap": MAX_BUCKET,
        },
        "contact_candidates": extract_attendees(data),
        **buckets,
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
