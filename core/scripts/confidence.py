"""Deterministic confidence ceilings for generated briefs.

The model may choose to sound less certain, but it may not exceed the ceiling
computed here from source freshness and coverage proof.
"""

EMAIL_GAP_PREFIXES = ("email_",)
DEGRADED_SUFFIX = "_connector_degraded"


def unique(items):
    out = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def is_email_gap(gap):
    text = str(gap or "")
    return text == "activity_coverage_gap" or text.startswith(EMAIL_GAP_PREFIXES)


def is_calendar_gap(gap):
    return str(gap or "").startswith("calendar_")


def is_internal_gap(gap):
    text = str(gap or "")
    return (
        text.startswith("slack_")
        or text.startswith("deal_room")
        or text.startswith("linked_doc")
        or text in {"checked_no_match", "unavailable"}
    )


def is_degraded_gap(gap):
    return str(gap or "").endswith(DEGRADED_SUFFIX)


def ceiling(low_reasons, medium_reasons):
    if low_reasons:
        return "Low"
    if medium_reasons:
        return "Medium"
    return "High"


def deal_confidence(deal_metrics, calendar_evidence=None, internal_evidence=None):
    metrics = deal_metrics or {}
    flags = metrics.get("flags") or {}
    metric_gaps = list(metrics.get("coverage_gaps") or [])
    calendar_gaps = list(((metrics.get("calendar") or {}).get("source_gaps")) or [])
    if calendar_evidence:
        calendar_gaps.extend(calendar_evidence.get("source_gaps") or [])
    internal_gaps = list((internal_evidence or {}).get("source_gaps") or [])

    all_gaps = unique([str(g) for g in metric_gaps + calendar_gaps + internal_gaps])
    low = []
    medium = []

    if flags.get("email_data_stale"):
        low.append("email_data_stale")
    if any(is_email_gap(g) for g in all_gaps):
        low.append("email_coverage_gap")
    if any(is_calendar_gap(g) for g in all_gaps):
        medium.append("calendar_gap")
    if any(is_internal_gap(g) for g in all_gaps):
        medium.append("internal_gap")
    if any(is_degraded_gap(g) for g in all_gaps):
        medium.append("connector_degraded")
    if all_gaps and not low and not medium:
        medium.append("coverage_gap")

    return {
        "max_label": ceiling(low, medium),
        "reason_codes": unique(low + medium),
        "coverage_gaps": all_gaps,
    }


def pipeline_confidence(mode, rows, source_gaps=None, coverage_gap_deals=None):
    rows = rows or []
    all_gaps = unique([str(g) for g in (source_gaps or [])])
    for row in rows:
        all_gaps.extend(str(g) for g in (row.get("coverage_gaps") or []))
    all_gaps = unique(all_gaps)

    low = []
    medium = []
    if mode == "hygiene":
        if coverage_gap_deals or all_gaps:
            low.append("salesforce_coverage_gap")
    else:
        if any("email_data_stale" in (row.get("risk_flags") or []) for row in rows):
            low.append("stale_data")
        if any(is_email_gap(g) for g in all_gaps):
            low.append("email_coverage_gap")
        if any(is_calendar_gap(g) for g in all_gaps):
            medium.append("calendar_gap")
        if any(is_internal_gap(g) for g in all_gaps):
            medium.append("internal_gap")
        if any(is_degraded_gap(g) for g in all_gaps):
            medium.append("connector_degraded")
        if (coverage_gap_deals or all_gaps) and not low and not medium:
            medium.append("coverage_gap")

    return {
        "max_label": ceiling(low, medium),
        "reason_codes": unique(low + medium),
        "coverage_gap_deals": sorted(set(coverage_gap_deals or [])),
        "source_gaps": all_gaps,
    }
