"""Validate per-source read proof before analysis trusts a bundle.

The model still performs connector calls, but the result must arrive as data:
one source-read record per expected connector. Missing read proof is a gather
contract failure, not something downstream prose can repair.
"""

DEGRADED_STATUSES = {"timeout", "error", "partial"}
OK_STATUSES = {"ok", "empty"}
ALLOWED_STATUSES = OK_STATUSES | DEGRADED_STATUSES | {"skipped"}

SOURCE_ALIASES = {
    "email": "gmail",
    "calendar": "google_calendar",
    "calls": "zoom",
    "calls_zoom": "zoom",
    "zoom_calls": "zoom",
    "drive": "google_drive",
}

CONNECTOR_STATUS_KEYS = {
    "gmail": "email",
    "google_calendar": "calendar",
    "zoom": "zoom",
    "salesforce": "salesforce",
    "slack": "slack",
    "google_drive": "drive",
}

DEFAULT_EXPECTED = {
    "deal": ["salesforce", "gmail", "google_calendar", "zoom", "slack", "google_drive"],
    "pipeline": ["salesforce", "gmail", "google_calendar", "zoom", "slack", "google_drive"],
    "hygiene": ["salesforce"],
}


def normalize_source(source):
    key = str(source or "").strip().lower()
    return SOURCE_ALIASES.get(key, key)


def normalize_status(status):
    return str(status or "").strip().lower()


def as_list(value):
    return value if isinstance(value, list) else []


def source_read_records(bundle):
    manifest = bundle.get("coverage_manifest") or {}
    raw = bundle.get("source_reads")
    if raw is None:
        raw = manifest.get("source_reads")
    if raw is None:
        return []

    records = []
    if isinstance(raw, dict):
        for source, value in raw.items():
            record = dict(value or {}) if isinstance(value, dict) else {"status": value}
            record["source"] = source
            records.append(record)
        return records
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    return []


def expected_sources_for(bundle):
    manifest = bundle.get("coverage_manifest") or {}
    profile = bundle.get("profile") or manifest.get("profile")
    expected = manifest.get("expected_sources") or bundle.get("expected_sources")
    if expected is None:
        expected = DEFAULT_EXPECTED.get(profile, [])
    expected = [normalize_source(s) for s in expected if str(s).strip()]

    internal = normalize_status(
        bundle.get("internal")
        or manifest.get("internal")
        or bundle.get("internal_evidence_mode")
    )
    if internal == "off":
        expected = [s for s in expected if s not in {"slack", "google_drive"}]
    return profile, expected


def strict_required(bundle):
    manifest = bundle.get("coverage_manifest") or {}
    return bool(
        bundle.get("coverage_manifest_required")
        or manifest.get("required")
        or bundle.get("profile")
        or manifest.get("profile")
        or source_read_records(bundle)
    )


def email_coverage_for(bundle):
    return bundle.get("email_coverage") or (bundle.get("compute_input") or {}).get("email_coverage") or {}


def validate_gmail(bundle, errors):
    coverage = email_coverage_for(bundle)
    if not isinstance(coverage, dict) or not coverage:
        errors.append("gmail source_read is clean but email_coverage is missing")
        return
    for field in ("searched_emails", "contact_union_emails", "searched_domains", "contact_domains"):
        if field not in coverage or not isinstance(coverage.get(field), list):
            errors.append(f"gmail email_coverage.{field} must be recorded as a list")
    contact_domains = [d for d in as_list(coverage.get("contact_domains")) if str(d).strip()]
    domain_status = normalize_status(coverage.get("domain_thread_search_status"))
    if contact_domains and not coverage.get("newest_domain_thread_id") and domain_status != "no_match":
        errors.append(
            "gmail domain search must record newest_domain_thread_id or "
            "domain_thread_search_status=no_match"
        )


def validate_slack(bundle, errors):
    internal = bundle.get("internal_evidence") or {}
    room = internal.get("deal_room") or {}
    slack_checked = bool(internal.get("slack_mcp_checked") or room.get("slack_mcp_checked"))
    searched = as_list(internal.get("slack_channels_searched") or room.get("slack_channels_searched"))
    coverage = room.get("coverage") or internal.get("coverage")
    if slack_checked is not True:
        errors.append("slack source_read is clean but slack_mcp_checked is not true")
    if not searched:
        errors.append("slack source_read is clean but slack_channels_searched is empty")
    if coverage not in {"found", "checked_no_match", "deal_room_missing", "unavailable"}:
        errors.append("slack deal_room.coverage must be found, checked_no_match, deal_room_missing, or unavailable")
    if coverage == "found":
        if room.get("source") != "slack":
            errors.append("slack deal_room.source must be slack when coverage=found")
        if not str(room.get("source_ref") or "").startswith("slack:"):
            errors.append("slack deal_room.source_ref must start with slack: when coverage=found")


def validate_calendar(bundle, errors):
    calendar = bundle.get("calendar_evidence") or (bundle.get("compute_input") or {}).get("calendar_evidence") or {}
    if not isinstance(calendar, dict) or not calendar.get("coverage"):
        errors.append("google_calendar source_read is clean but calendar_evidence.coverage is missing")


def validate_clean_source(bundle, source, errors):
    if source == "gmail":
        validate_gmail(bundle, errors)
    elif source == "slack":
        validate_slack(bundle, errors)
    elif source == "google_calendar":
        validate_calendar(bundle, errors)


def validate_bundle_coverage(bundle):
    """Return normalized manifest details, or raise ValueError with reasons."""
    profile, expected = expected_sources_for(bundle)
    records = source_read_records(bundle)
    strict = strict_required(bundle)
    if not strict:
        return {
            "profile": profile,
            "expected_sources": expected,
            "source_reads": [],
            "connector_status": {},
        }

    errors = []
    by_source = {}
    for record in records:
        source = normalize_source(record.get("source"))
        status = normalize_status(record.get("status"))
        if not source:
            errors.append("source_read missing source")
            continue
        if status not in ALLOWED_STATUSES:
            errors.append(f"{source} source_read has invalid status: {record.get('status')}")
            continue
        normalized = dict(record)
        normalized["source"] = source
        normalized["status"] = status
        normalized["retries"] = int(record.get("retries") or 0)
        by_source[source] = normalized

    for source in expected:
        if source not in by_source:
            errors.append(f"source_reads missing expected source: {source}")
            continue
        status = by_source[source]["status"]
        if status == "skipped":
            errors.append(f"{source} source_read cannot be skipped when expected")
        if status in OK_STATUSES:
            validate_clean_source(bundle, source, errors)

    if errors:
        raise ValueError("coverage manifest invalid: " + "; ".join(errors))

    connector_status = {}
    for source, record in by_source.items():
        key = CONNECTOR_STATUS_KEYS.get(source)
        if key:
            connector_status[key] = record["status"]

    return {
        "profile": profile,
        "expected_sources": expected,
        "source_reads": [by_source[s] for s in sorted(by_source)],
        "connector_status": connector_status,
    }
