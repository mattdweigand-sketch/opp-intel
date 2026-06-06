#!/usr/bin/env python3
"""Code gate for pipeline-read's machine-checkable output contracts.

Run the drafted brief through this before presenting it. The gate confirms the
Computed inputs footer is rollup.py output, rejects unearned High confidence, and
enforces the stricter forecast-mode sections.

Usage:
  python3 validate_brief.py < brief.md
On success: writes `Validation: PASS` to stdout, exits 0.
On failure: writes reasons to stderr, exits non-zero.
"""
import json
import re
import sys

SCHEMA_VERSION = "pipeline-read.computed-inputs.v1"
CONF_RE = re.compile(r"Confidence:\s*\**\s*(High|Medium|Low)", re.IGNORECASE)
JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)
FORECAST_SECTIONS = [
    "Review scope",
    "Internal evidence",
    "Category rollup",
    "Key movements",
    "Recommendation changes",
    "Highest-risk deals",
    "Evidence gaps",
    "Your move this week",
    "Computed inputs",
]
HYGIENE_SECTIONS = [
    "Hygiene distribution",
    "By deal",
    "Computed inputs",
]


def find_computed_block(text):
    """Return the parsed Computed inputs JSON, or None if absent/empty/unparseable."""
    blocks = JSON_BLOCK_RE.findall(text)
    for raw in reversed(blocks):
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


def has_section(text, heading):
    return re.search(rf"(^|\n)\s*{re.escape(heading)}\s*:", text, re.IGNORECASE) is not None


def any_deal_stale(computed):
    for row in computed.get("ranking", []) or []:
        if "email_data_stale" in (row.get("risk_flags") or []):
            return True
    return bool(computed.get("portfolio", {}).get("stale_data_deals"))


def any_coverage_gap(computed):
    """True when the roll-up reports any connector coverage gap. Backward compatible:
    older inputs without coverage_gaps/coverage_gap_deals read as no gap."""
    if computed.get("source_gaps"):
        return True
    if (computed.get("portfolio") or {}).get("coverage_gap_deals"):
        return True
    for row in computed.get("ranking", []) or []:
        if row.get("coverage_gaps"):
            return True
    return False


def forecast_mode(text, computed):
    run_mode = (computed.get("run") or {}).get("mode") if computed else None
    return run_mode == "forecast" or bool(computed and computed.get("forecast")) or "Forecast Read" in text


def hygiene_mode(text, computed):
    run_mode = (computed.get("run") or {}).get("mode") if computed else None
    return run_mode == "hygiene" or bool(computed and computed.get("hygiene")) or "Pipeline Hygiene" in text


def forecast_gap_reasons(computed):
    reasons = []
    if any_deal_stale(computed):
        reasons.append("stale_data")

    for rec in (computed.get("forecast") or {}).get("recommendations", []) or []:
        for code in rec.get("reason_codes") or []:
            if code in {"unknown_forecast_category", "missing_amount"}:
                reasons.append(code)
            if str(code).startswith("deal_room") or str(code).startswith("linked_doc"):
                reasons.append(code)
            if code in {"checked_no_match", "unavailable"}:
                reasons.append(code)

    movement = computed.get("movement") or {}
    if movement and movement.get("evaluated") is False:
        reasons.append(movement.get("reason") or "movement_not_evaluated")

    internal = computed.get("internal_evidence") or {}
    coverage = internal.get("deal_room_coverage") or {}
    if coverage.get("missing"):
        reasons.append("deal_room_missing")
    if coverage.get("unavailable"):
        reasons.append("deal_room_unavailable")
    if coverage.get("checked_no_match"):
        reasons.append("checked_no_match")
    if internal.get("linked_docs_unavailable"):
        reasons.append("linked_doc_unavailable")
    if internal.get("source_gaps"):
        reasons.append("internal_source_gaps")

    for gap in computed.get("source_gaps") or []:
        reasons.append(str(gap))

    return sorted(set(reasons))


def internal_sources_have_refs(computed):
    errors = []
    internal = computed.get("internal_evidence") or {}
    for sig in internal.get("signals") or []:
        if not sig.get("source_ref"):
            errors.append(f"Internal evidence signal lacks source_ref: {sig.get('deal') or sig.get('type')}")
    return errors


def prose_text(text):
    """Brief text with the ```json Computed inputs fences stripped, so a date check tests
    the narrative rather than the audit JSON (where last_touch always literally appears)."""
    return JSON_BLOCK_RE.sub("", text)


def stale_anchor_errors(text, computed):
    """NW1 guard: a deal flagged email_data_stale must cite its true last-touch date in the
    brief prose, so it can't be narrated as gone quiet when a later call exists. Lenient:
    skip rows whose last_touch is null/absent (older inputs lack the field)."""
    errors = []
    prose = prose_text(text)
    for row in computed.get("ranking", []) or []:
        if "email_data_stale" not in (row.get("risk_flags") or []):
            continue
        last_touch = row.get("last_touch")
        if not last_touch:
            continue
        if str(last_touch) not in prose:
            name = row.get("name") or row.get("deal") or "a stale-flagged deal"
            errors.append(
                f"Deal '{name}' is flagged email_data_stale but its last-touch date "
                f"{last_touch} is not cited in the brief. Cite the real last touch instead "
                f"of narrating it as gone quiet."
            )
    return errors


def validate(text):
    errors = []

    computed = find_computed_block(text)
    if computed is None:
        errors.append(
            "Computed inputs block missing, empty, or not valid JSON. Paste rollup.py's "
            "verbatim output under a ```json fence; without it the brief is unverifiable."
        )
    elif "portfolio" not in computed or "ranking" not in computed:
        errors.append(
            "Computed inputs block has no portfolio/ranking keys. It does not look like "
            "rollup.py output. Paste the whole object, not a per-deal fragment."
        )
    elif computed.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Computed inputs missing schema_version {SCHEMA_VERSION}.")

    confidence = find_confidence(text)
    if confidence is None:
        errors.append("Confidence line missing. Lead the brief with a Confidence rating.")

    if not computed:
        return errors

    is_forecast = forecast_mode(text, computed)
    is_hygiene = hygiene_mode(text, computed)
    coverage_gap = any_coverage_gap(computed)
    if confidence == "High" and any_deal_stale(computed):
        errors.append(
            "Confidence is High but the roll-up shows deals with stale email data. Lower it "
            "and name which deals you could not see clearly."
        )
    if confidence == "High" and coverage_gap:
        errors.append(
            "Confidence is High but the roll-up reports coverage gaps (connectors under-collected). "
            "Lower it and name what you could not see."
        )

    if (
        not is_forecast
        and not is_hygiene
        and (any_deal_stale(computed) or coverage_gap)
        and not has_section(text, "Where you're blind")
    ):
        errors.append("Where you're blind section missing while stale data or coverage gaps exist.")

    errors.extend(stale_anchor_errors(text, computed))

    if is_hygiene:
        for heading in HYGIENE_SECTIONS:
            if not has_section(text, heading):
                errors.append(f"Hygiene-mode section missing: {heading}.")

    if is_forecast:
        if "forecast" not in computed:
            errors.append("Forecast-mode brief has no forecast block in Computed inputs.")
        for heading in FORECAST_SECTIONS:
            if not has_section(text, heading):
                errors.append(f"Forecast-mode section missing: {heading}.")

        gaps = forecast_gap_reasons(computed)
        if gaps and not has_section(text, "Evidence gaps"):
            errors.append("Evidence gaps section missing while computed inputs show confidence-limiting gaps.")
        if gaps and confidence == "High":
            errors.append(
                "Confidence is High but forecast computed inputs show evidence gaps: "
                + ", ".join(gaps)
            )
        errors.extend(internal_sources_have_refs(computed))

    return errors


def main():
    text = sys.stdin.read()
    errors = validate(text)
    if errors:
        for e in errors:
            sys.stderr.write("FAIL: " + e + "\n")
        sys.exit(1)
    sys.stdout.write("Validation: PASS\n")


if __name__ == "__main__":
    main()
