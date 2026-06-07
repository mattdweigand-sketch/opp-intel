#!/usr/bin/env python3
"""Code gate (and renderer) for the coaching brief's machine-checkable output contracts.

Two rules in SKILL.md were phrased as "required" but enforced only by asking the
model nicely. This turns them into a deterministic check the model runs on its own
drafted brief before presenting it:

  1. The `Computed inputs` JSON block must be present, non-empty, and parseable.
     It is the audit trail proving analyze.py actually ran. A missing or empty
     block means the deterministic steps were skipped and the brief is untrustworthy.
  2. Confidence must not be High when the computed flags show email_data_stale.
     Stale email data means the brief is reasoning on a lagging view, so an
     authoritative rating is unearned. (Low vs Medium stays model judgment; this
     enforces only the machine-grounded floor: no High on stale data.)

The drafted brief still carries analyze.py's verbatim JSON so the gate can verify it,
but the reader should never have to scroll the raw object. On success this script
emits the brief back out with that JSON footer collapsed to a one-line verification
stamp inside a `<details>` block — so the model can present stdout verbatim and the
reader sees only pass/fail. The code owns the redaction; the model cannot fake the
stamp without a real, parseable footer to feed in.

Usage:
  python3 validate_brief.py < brief.md      # reads the drafted brief on stdin
On success: writes the rendered brief (JSON footer → pass stamp) to stdout, exits 0.
On failure: writes reasons to stderr, exits non-zero, writes nothing to stdout.
"""
import json
import re
import sys

CONF_RE = re.compile(r"Confidence:\s*\**\s*(High|Medium|Low)", re.IGNORECASE)
JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)
EMAIL_ABSENCE_RE = re.compile(
    r"\b(no|without|lack(?:s|ing)?|missing)\b.{0,50}\b(email|gmail|thread|inbound|reply|conversation)\b"
    r"|\b(email|gmail|thread|inbound|reply|conversation)\b.{0,50}\b(stale|quiet|silent|no activity|no evidence|missing)\b"
    r"|\bwent quiet\b",
    re.IGNORECASE | re.DOTALL,
)
SLACK_ABSENCE_RE = re.compile(
    r"\b(no|without|lack(?:s|ing)?|missing)\b.{0,60}\b(slack|deal room|deal-room|channel)\b"
    r"|\b(slack|deal room|deal-room|channel)\b.{0,60}\b(not found|missing|absent|no activity|quiet|silent)\b",
    re.IGNORECASE | re.DOTALL,
)
SALESFORCE_SLACK_RE = re.compile(
    r"\bsalesforce\b.{0,80}\b(slack|deal room|deal-room)\b"
    r"|\b(slack|deal room|deal-room)\b.{0,80}\bsalesforce\b",
    re.IGNORECASE | re.DOTALL,
)
# A "Computed inputs" label line immediately preceding the footer fence, so the
# render can absorb it along with the JSON it introduces.
COMPUTED_LABEL_RE = re.compile(
    r"(?:^|\n)[ \t]*\**\s*Computed inputs\s*\**[ \t]*:?[ \t]*\n*\Z", re.IGNORECASE
)

PASS_FOOTER = (
    "<details>\n"
    "<summary>Computed inputs</summary>\n\n"
    "Verified: analyze.py ran; footer present and parseable, "
    "confidence calibrated to evidence.\n\n"
    "</details>\n"
)


def find_computed_block(text):
    """Return the parsed Computed inputs JSON, or None if absent/empty/unparseable."""
    blocks = JSON_BLOCK_RE.findall(text)
    for raw in reversed(blocks):  # the footer is the last json block
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj:
            return obj
    return None


def find_confidence(text):
    m = CONF_RE.search(text)
    return m.group(1).capitalize() if m else None


def deal_metric_gaps(computed):
    metrics = computed.get("deal_metrics") or {}
    gaps = list(metrics.get("coverage_gaps") or [])
    gaps.extend((metrics.get("calendar") or {}).get("source_gaps") or [])
    return gaps


def internal_gaps(computed):
    return list((computed.get("internal_evidence") or {}).get("source_gaps") or [])


def slack_cleanly_checked(computed):
    internal = computed.get("internal_evidence") or {}
    room = internal.get("deal_room") or {}
    source_gaps = set(internal_gaps(computed))
    if source_gaps.intersection({"slack_coverage_unproven", "slack_channel_search_missing", "slack_non_slack_source"}):
        return False
    if room.get("slack_mcp_checked") is not True:
        return False
    if not room.get("slack_channels_searched"):
        return False
    return room.get("coverage") in {"found", "checked_no_match", "deal_room_missing"}


def validate(text):
    errors = []

    computed = find_computed_block(text)
    if computed is None:
        errors.append(
            "Computed inputs block missing, empty, or not valid JSON. Paste analyze.py's "
            "verbatim output under a ```json fence; without it the brief is unverifiable."
        )
    elif "deal_metrics" not in computed:
        errors.append(
            "Computed inputs block has no deal_metrics key. It does not look like analyze.py "
            "output. Paste the whole object, not a fragment."
        )

    confidence = find_confidence(text)
    if confidence is None:
        errors.append("Confidence line missing. Lead the brief with a Confidence rating.")

    if computed and confidence == "High":
        metrics = computed.get("deal_metrics", {})
        stale = metrics.get("flags", {}).get("email_data_stale") is True
        coverage_gaps = metrics.get("coverage_gaps") or []
        calendar_gaps = (metrics.get("calendar") or {}).get("source_gaps") or []
        internal_source_gaps = internal_gaps(computed)
        if stale:
            errors.append(
                "Confidence is High but email_data_stale is true. Stale email data cannot "
                "support a High rating. Lower it and name what you could not see."
            )
        if coverage_gaps or calendar_gaps or internal_source_gaps:
            errors.append(
                "Confidence is High but computed inputs show coverage gaps. Lower it and "
                "name what you could not see."
            )

    if computed:
        gaps = set(deal_metric_gaps(computed))
        email_gaps = {g for g in gaps if str(g).startswith("email_") or g == "activity_coverage_gap"}
        if email_gaps and EMAIL_ABSENCE_RE.search(text):
            errors.append(
                "Brief makes an email absence/staleness claim while computed inputs show email "
                "coverage gaps. Name the Gmail coverage gap instead."
            )
        if SLACK_ABSENCE_RE.search(text) and not slack_cleanly_checked(computed):
            errors.append(
                "Brief makes a Slack/deal-room absence claim without a clean Slack MCP coverage "
                "read in computed inputs."
            )
        if SALESFORCE_SLACK_RE.search(text):
            errors.append(
                "Brief links Slack evidence to Salesforce. Slack/deal-room truth must come from Slack MCP only."
            )

    return errors


def render(text):
    """Collapse the verified Computed inputs JSON footer to a one-line pass stamp.

    Replaces the last ```json fence (and an immediately-preceding "Computed inputs"
    label, if any) with PASS_FOOTER. Call only after validate() returns no errors.
    """
    last = None
    for last in JSON_BLOCK_RE.finditer(text):
        pass  # keep the final match — the footer is the last json block
    if last is None:
        return text
    head = text[: last.start()]
    label = COMPUTED_LABEL_RE.search(head)
    if label:
        head = head[: label.start()]
    return head.rstrip() + "\n\n" + PASS_FOOTER


def main():
    text = sys.stdin.read()
    errors = validate(text)
    if errors:
        for e in errors:
            sys.stderr.write("FAIL: " + e + "\n")
        sys.exit(1)
    sys.stdout.write(render(text))


if __name__ == "__main__":
    main()
