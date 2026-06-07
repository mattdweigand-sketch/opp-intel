#!/usr/bin/env python3
"""Roll per-deal analyze.py outputs up into one deterministic pipeline view.

pipeline-read feeds one analyze.py output per in-scope deal, whether that output
came from the fast bulk-first path or explicit deep search. rollup.py ranks the
deals and computes the
portfolio aggregates so the model never eyeballs "which deal is riskiest" or sums
amounts in its head.

Ranking is by severity of current evidence, not a predictive model: a deal with a
red flag (from risk-model.json pipeline.flag_severity) outranks one with only amber
flags; ties break on flag count, then amount, then days-to-close. Forecast labels
and movement are deterministic output from this script.

Usage: python3 rollup.py        # reads the bundle JSON on stdin
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "config"))
SCHEMA_VERSION = "pipeline-read.computed-inputs.v1"
TIER_RANK = {"red": 0, "amber": 1, "none": 2}
RISK_SCORE = {"none": 0, "amber": 1, "red": 2}


def load(name):
    with open(os.path.join(CONFIG, name)) as f:
        return json.load(f)


def normalize_token(value):
    return str(value or "").strip().lower().replace("-", "_")


def money_value(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return None
    raw = str(value).strip().replace("$", "").replace(",", "")
    if not raw:
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def amount_or_zero(value):
    number = money_value(value)
    return number if number is not None else 0


def first_present(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def deal_flags(deal):
    """The flags dict from this deal's analyze.py output (empty if absent)."""
    return (
        (deal.get("analyze_output") or {})
        .get("deal_metrics", {})
        .get("flags", {})
    ) or {}


def days_to_close(deal):
    return (deal.get("analyze_output") or {}).get("deal_metrics", {}).get("days_to_close")


def deal_metrics(deal):
    """The deal_metrics dict from this deal's analyze.py output (empty if absent)."""
    return (deal.get("analyze_output") or {}).get("deal_metrics", {}) or {}


def coverage_gaps_for(deal):
    """Per-deal coverage_gaps list (compute.py emits these; default []). Metadata only —
    coverage gaps are NOT risk flags and never affect ranking or severity."""
    gaps = deal_metrics(deal).get("coverage_gaps")
    return [str(g) for g in gaps] if isinstance(gaps, list) else []


def calendar_gaps_for(deal):
    calendar = deal_metrics(deal).get("calendar", {}) or {}
    gaps = calendar.get("source_gaps")
    return [str(g) for g in gaps] if isinstance(gaps, list) else []


def freshness_for(deal):
    return deal_metrics(deal).get("freshness", {}) or {}


def last_touch_for(deal):
    """activity_anchor_date / activity_anchor_source, null-safe (None when absent)."""
    freshness = freshness_for(deal)
    return freshness.get("activity_anchor_date"), freshness.get("activity_anchor_source")


def classify(deal, severity):
    """Return (dominant_flag, tier, true_risk_flags) for one deal."""
    flags = deal_flags(deal)
    red = severity.get("red", [])
    amber = severity.get("amber", [])
    true_red = [f for f in red if flags.get(f)]
    true_amber = [f for f in amber if flags.get(f)]
    if true_red:
        return true_red[0], "red", true_red + true_amber
    if true_amber:
        return true_amber[0], "amber", true_amber
    return None, "none", []


def stable_id(deal):
    return first_present(
        deal.get("opportunity_id"),
        deal.get("opp_id"),
        deal.get("id"),
        deal.get("Id"),
    )


def field_value(deal, field_name):
    if not field_name:
        return None
    return deal.get(field_name)


def category_value(deal, category_field):
    return first_present(
        deal.get("forecast_category"),
        deal.get("forecast_category_name"),
        field_value(deal, category_field),
        deal.get("ForecastCategory"),
        deal.get("ForecastCategoryName"),
    )


def category_group(value, convention):
    value_norm = str(value or "").strip().lower()
    for group, names in convention.items():
        if value_norm in {str(n).strip().lower() for n in names}:
            return group
    return "unknown"


def amount_for_basis(deal, amount_basis, amount_field):
    # Added_ARR__c is the only reliable ARR source in this org. Do not fall back
    # to aliases or alternate Salesforce amount fields; a missing value is a
    # missing_amount signal, not permission to use a different basis.
    return money_value(field_value(deal, amount_field))


def internal_for_deal(deal):
    return first_present(
        deal.get("internal_evidence"),
        (deal.get("analyze_output") or {}).get("internal_evidence"),
    ) or {}


def source_gaps_for(deal):
    gaps = list(coverage_gaps_for(deal))
    gaps.extend(calendar_gaps_for(deal))

    internal = internal_for_deal(deal)
    gaps.extend(internal.get("source_gaps") or [])
    coverage = first_present(
        internal.get("coverage"),
        (internal.get("deal_room") or {}).get("coverage"),
    )
    if coverage in {"deal_room_missing", "checked_no_match", "unavailable"}:
        gaps.append(coverage)
    for doc in internal.get("linked_docs") or []:
        if doc.get("coverage") in {"unavailable", "skipped"}:
            gaps.append("linked_doc_" + doc.get("coverage"))
    return sorted(set(gaps))


def internal_signals_for(deal):
    internal = internal_for_deal(deal)
    return [s for s in (internal.get("signals") or []) if s.get("source_ref")]


def build_rows(deals, severity, amount_basis, amount_field, category_field, convention):
    rows = []
    for deal in deals:
        dominant, tier, true_flags = classify(deal, severity)
        amount = amount_for_basis(deal, amount_basis, amount_field)
        acv = amount
        category = category_value(deal, category_field)
        group = category_group(category, convention)
        last_touch, last_touch_source = last_touch_for(deal)
        rows.append({
            "opportunity_id": stable_id(deal),
            "name": first_present(deal.get("name"), deal.get("Name")),
            "stage": first_present(deal.get("stage"), deal.get("StageName")),
            "acv": acv,
            "amount": amount,
            "amount_basis": amount_basis,
            "forecast_category": category,
            "forecast_category_group": group,
            "close_date": first_present(deal.get("close_date"), deal.get("CloseDate")),
            "days_to_close": days_to_close(deal),
            "dominant_flag": dominant,
            "severity_tier": tier,
            "flag_count": len(true_flags),
            "risk_flags": true_flags,
            "last_touch": last_touch,
            "last_touch_source": last_touch_source,
            "coverage_gaps": source_gaps_for(deal),
        })
    return rows


def sort_ranking(rows):
    big = float("inf")
    return sorted(
        rows,
        key=lambda r: (
            TIER_RANK[r["severity_tier"]],
            -r["flag_count"],
            -amount_or_zero(r["amount"] if r.get("amount") is not None else r.get("acv")),
            r["days_to_close"] if r["days_to_close"] is not None else big,
        ),
    )


def coverage_gap_deals_for(deals):
    """Sorted names of deals carrying any coverage_gap. Pure metadata."""
    names = [
        first_present(d.get("name"), d.get("Name"))
        for d in deals
        if source_gaps_for(d)
    ]
    return sorted(n for n in names if n)


def aggregate_coverage_gaps(deals):
    """Union of every in-scope deal's source gaps (dedup, sorted)."""
    gaps = set()
    for d in deals:
        gaps.update(source_gaps_for(d))
    return sorted(gaps)


def portfolio_for(deals, rows):
    total_acv = sum(amount_or_zero(r.get("acv")) for r in rows)
    at_risk_rows = [r for r in rows if r["severity_tier"] == "red"]
    acv_at_risk = sum(amount_or_zero(r.get("acv")) for r in at_risk_rows)

    by_dominant = {}
    for r in rows:
        key = r["dominant_flag"] or "none"
        by_dominant[key] = by_dominant.get(key, 0) + 1

    def count(pred):
        return sum(1 for d in deals if pred(deal_flags(d)))

    return {
        "deal_count": len(deals),
        "total_acv": total_acv,
        "acv_at_risk": acv_at_risk,
        "acv_at_risk_pct": round(acv_at_risk / total_acv, 2) if total_acv else None,
        "deals_at_risk": len(at_risk_rows),
        "by_dominant_flag": by_dominant,
        "single_threaded": count(lambda f: f.get("single_threaded")),
        "slipped_or_overdue": count(lambda f: f.get("close_date_slipped") or f.get("overdue_close")),
        "stalled_in_stage": count(lambda f: f.get("stalled_in_stage")),
        "stale_data_deals": count(lambda f: f.get("email_data_stale")),
        "coverage_gap_deals": coverage_gap_deals_for(deals),
    }


def row_primary_blind(row):
    """True when a deal's PRIMARY evidence is blind: its email view is provably stale,
    or a primary connector under-collected (activity_coverage_gap / *_connector_degraded).
    Optional internal-evidence gaps (deal_room_missing, checked_no_match, linked_doc_*) are
    color, not primary evidence, and deliberately do NOT count here."""
    if "email_data_stale" in (row.get("risk_flags") or []):
        return True
    for gap in row.get("coverage_gaps") or []:
        if gap == "activity_coverage_gap" or str(gap).endswith("_connector_degraded"):
            return True
    return False


def apply_confidence_gate(rows, total_acv, gate_cfg):
    """Fail-loud, dollar-weighted confidence floor. A material deal (>= pct of in-scope
    ACV, or among the top-N by amount) whose PRIMARY evidence is blind forces the
    portfolio confidence_floor to Low and marks that row confidence_blocked. Mutates rows
    in place (ranking shares the same objects) and returns (floor, blocked_deal_names).
    No material+blind deal -> floor None, the model keeps its discretion."""
    pct = gate_cfg.get("material_deal_acv_pct", 0.25)
    top_n = gate_cfg.get("material_top_n_by_amount", 1)
    by_amount = sorted(rows, key=lambda r: amount_or_zero(r.get("acv")), reverse=True)
    top_objs = by_amount[:top_n] if top_n else []
    blocked = []
    for row in rows:
        acv = amount_or_zero(row.get("acv"))
        is_material = (
            (total_acv and pct and acv / total_acv >= pct)
            or any(row is t for t in top_objs)
        )
        if is_material and row_primary_blind(row):
            row["confidence_blocked"] = True
            row["confidence_block_reason"] = (
                "email_data_stale"
                if "email_data_stale" in (row.get("risk_flags") or [])
                else "primary_connector_coverage_gap"
            )
            if row.get("name"):
                blocked.append(row["name"])
        else:
            row["confidence_blocked"] = False
    return ("Low" if blocked else None), sorted(set(blocked))


def build_hygiene_rows(deals, precedence, amount_basis, amount_field):
    """One row per deal for the hygiene (CRM data-quality) view.

    Reuses the same per-deal flags compute.py emits on a hygiene run
    (no_contact_roles, no_champion, missing_next_step, single_threaded, stale_activity,
    overdue_close) and adds missing_amount, which only this script can know because it
    owns the amount basis. The dominant flag is the first match in the configured
    precedence — one flag per row, like the old pipeline-health.
    """
    rows = []
    for deal in deals:
        flags = dict(deal_flags(deal))
        amount = amount_for_basis(deal, amount_basis, amount_field)
        acv = amount
        if "missing_amount" in precedence:
            flags["missing_amount"] = amount is None
        metrics = (deal.get("analyze_output") or {}).get("deal_metrics", {})
        true_flags = [f for f in precedence if flags.get(f)]
        dominant = true_flags[0] if true_flags else None
        rows.append({
            "opportunity_id": stable_id(deal),
            "name": first_present(deal.get("name"), deal.get("Name")),
            "stage": first_present(deal.get("stage"), deal.get("StageName")),
            "acv": acv,
            "amount": amount,
            "amount_basis": amount_basis,
            "close_date": first_present(deal.get("close_date"), deal.get("CloseDate")),
            "days_to_close": days_to_close(deal),
            "contacts": metrics.get("contacts_engaged"),
            "has_champion": (not flags.get("no_champion")) if "no_champion" in flags else None,
            "next_step_present": (not flags.get("missing_next_step")) if "missing_next_step" in flags else None,
            "days_since_last_activity": metrics.get("days_since_last_activity"),
            "dominant_flag": dominant,
            "hygiene_flags": true_flags,
            "flag_count": len(true_flags),
            "severity_tier": "flagged" if dominant else "clean",
        })
    return rows


def sort_hygiene(rows, precedence):
    """Rank by dominant-flag precedence (clean last), then flag count, amount, days-to-close."""
    rank = {f: i for i, f in enumerate(precedence)}
    big = float("inf")
    return sorted(
        rows,
        key=lambda r: (
            rank.get(r["dominant_flag"], big),
            -r["flag_count"],
            -amount_or_zero(r["amount"] if r.get("amount") is not None else r.get("acv")),
            r["days_to_close"] if r["days_to_close"] is not None else big,
        ),
    )


def hygiene_portfolio(rows, precedence):
    distribution = {f: 0 for f in precedence}
    distribution["clean"] = 0
    for r in rows:
        key = r["dominant_flag"] or "clean"
        distribution[key] = distribution.get(key, 0) + 1
    flagged = sum(1 for r in rows if r["dominant_flag"])
    total_acv = sum(amount_or_zero(r.get("acv")) for r in rows)
    return {
        "deal_count": len(rows),
        "total_acv": total_acv,
        "flagged_deals": flagged,
        "clean_deals": len(rows) - flagged,
        "distribution": distribution,
    }


def category_rollup(rows):
    out = {
        "commit": {"count": 0, "amount": 0, "amount_at_risk": 0},
        "upside": {"count": 0, "amount": 0, "amount_at_risk": 0},
        "pipeline": {"count": 0, "amount": 0, "amount_at_risk": 0},
        "unknown": {"count": 0, "amount": 0, "amount_at_risk": 0},
    }
    for row in rows:
        group = row.get("forecast_category_group") or "unknown"
        if group not in out:
            group = "unknown"
        amount = amount_or_zero(row.get("amount"))
        out[group]["count"] += 1
        out[group]["amount"] += amount
        if row.get("severity_tier") == "red":
            out[group]["amount_at_risk"] += amount
    return out


def confidence_for(row, reason_codes):
    if (
        "email_data_stale" in row.get("risk_flags", [])
        or "unknown_forecast_category" in reason_codes
        or "missing_amount" in reason_codes
        or "unavailable" in reason_codes
        or "checked_no_match" in reason_codes
    ):
        return "Low"
    if row.get("severity_tier") == "red" or any(c.startswith("internal_signal:") for c in reason_codes):
        return "Medium"
    if "deal_room_missing" in reason_codes or any(c.startswith("linked_doc_") for c in reason_codes):
        return "Medium"
    return "High"


def recommendation_for(row, deal):
    flags = row.get("risk_flags") or []
    source_gaps = source_gaps_for(deal)
    internal_signals = internal_signals_for(deal)
    reason_codes = list(flags)

    if row.get("forecast_category_group") == "unknown":
        reason_codes.append("unknown_forecast_category")
    if row.get("amount") is None:
        reason_codes.append("missing_amount")
    reason_codes.extend(source_gaps)
    reason_codes.extend("internal_signal:" + str(sig.get("type")) for sig in internal_signals)
    reason_codes = sorted(set(reason_codes))

    stale = "email_data_stale" in flags or "stale_activity" in flags
    if stale or "unknown_forecast_category" in reason_codes or "missing_amount" in reason_codes:
        label = "inspect"
    elif row.get("forecast_category_group") == "commit" and row.get("severity_tier") == "red":
        label = "downgrade"
    elif (
        row.get("forecast_category_group") in {"upside", "pipeline"}
        and row.get("severity_tier") == "none"
    ):
        label = "possible_upside"
    elif row.get("forecast_category_group") in {"commit", "upside"} and row.get("severity_tier") == "none":
        label = "keep"
    else:
        label = "inspect"

    return {
        "deal": row.get("name"),
        "opportunity_id": row.get("opportunity_id"),
        "current_category": row.get("forecast_category"),
        "category_group": row.get("forecast_category_group"),
        "recommendation": label,
        "reason_codes": reason_codes or ["no_current_risk_flags"],
        "confidence": confidence_for(row, reason_codes),
    }


def internal_rollup(deals, mode):
    coverage = {"mapped": 0, "missing": 0, "unavailable": 0, "checked_no_match": 0}
    linked_docs_read = 0
    linked_docs_unavailable = 0
    signals = []
    source_gaps = []

    for deal in deals:
        internal = internal_for_deal(deal)
        room = internal.get("deal_room") or {}
        room_coverage = first_present(internal.get("coverage"), room.get("coverage"))
        if room_coverage == "mapped":
            coverage["mapped"] += 1
        elif room_coverage == "deal_room_missing":
            coverage["missing"] += 1
            source_gaps.append({"deal": first_present(deal.get("name"), deal.get("Name")), "gap": "deal_room_missing"})
        elif room_coverage == "unavailable":
            coverage["unavailable"] += 1
            source_gaps.append({"deal": first_present(deal.get("name"), deal.get("Name")), "gap": "deal_room_unavailable"})
        elif room_coverage == "checked_no_match":
            coverage["checked_no_match"] += 1
            source_gaps.append({"deal": first_present(deal.get("name"), deal.get("Name")), "gap": "checked_no_match"})

        for doc in internal.get("linked_docs") or []:
            if doc.get("coverage") == "read":
                linked_docs_read += 1
            elif doc.get("coverage") in {"unavailable", "skipped"}:
                linked_docs_unavailable += 1
                source_gaps.append({
                    "deal": first_present(deal.get("name"), deal.get("Name")),
                    "gap": "linked_doc_" + doc.get("coverage"),
                    "source_ref": doc.get("source_ref"),
                })

        for sig in internal_signals_for(deal):
            signals.append({
                "deal": first_present(deal.get("name"), deal.get("Name")),
                "type": sig.get("type"),
                "summary": sig.get("summary"),
                "source_ref": sig.get("source_ref"),
                "confidence": sig.get("confidence"),
            })

    return {
        "mode": mode,
        "deal_room_coverage": coverage,
        "linked_docs_read": linked_docs_read,
        "linked_docs_unavailable": linked_docs_unavailable,
        "signals": signals,
        "source_gaps": source_gaps,
    }


def compact_row(row):
    return {
        "opportunity_id": row.get("opportunity_id"),
        "name": row.get("name") or row.get("deal"),
        "amount": first_present(row.get("amount"), row.get("acv")),
        "close_date": row.get("close_date"),
        "severity_tier": row.get("severity_tier"),
        "risk_flags": row.get("risk_flags") or [],
    }


def match_key(row):
    oid = row.get("opportunity_id")
    if oid:
        return ("id", str(oid))
    name = row.get("name") or row.get("deal")
    if name:
        return ("name", str(name).strip().lower())
    return None


def movement_labels(previous, current):
    labels = []
    prev_amount = money_value(first_present(previous.get("amount"), previous.get("acv")))
    curr_amount = money_value(first_present(current.get("amount"), current.get("acv")))
    if prev_amount != curr_amount:
        labels.append("amount_changed")
    if previous.get("close_date") != current.get("close_date"):
        labels.append("close_date_changed")
    if (
        previous.get("severity_tier") != current.get("severity_tier")
        or sorted(previous.get("risk_flags") or []) != sorted(current.get("risk_flags") or [])
    ):
        labels.append("risk_changed")
    return labels or ["unchanged"]


def compare_prior(prior, rows, source):
    prior_rows = prior.get("ranking") or []
    prior_index = {}
    for row in prior_rows:
        key = match_key(compact_row(row))
        if key:
            prior_index[key] = compact_row(row)

    current_index = {}
    for row in rows:
        key = match_key(row)
        if key:
            current_index[key] = compact_row(row)

    deals = []
    summary = {
        "new_deals": 0,
        "removed_deals": 0,
        "risk_increased": 0,
        "risk_decreased": 0,
        "amount_changed": 0,
        "close_date_changed": 0,
    }

    for key, current in current_index.items():
        previous = prior_index.get(key)
        if previous is None:
            summary["new_deals"] += 1
            deals.append({
                "deal": current.get("name"),
                "movement": ["new"],
                "match_basis": key[0],
                "previous": None,
                "current": current,
            })
            continue

        labels = movement_labels(previous, current)
        if "amount_changed" in labels:
            summary["amount_changed"] += 1
        if "close_date_changed" in labels:
            summary["close_date_changed"] += 1
        if "risk_changed" in labels:
            prev_score = RISK_SCORE.get(previous.get("severity_tier"), 0)
            curr_score = RISK_SCORE.get(current.get("severity_tier"), 0)
            if curr_score > prev_score:
                summary["risk_increased"] += 1
            elif curr_score < prev_score:
                summary["risk_decreased"] += 1
        deals.append({
            "deal": current.get("name"),
            "movement": labels,
            "match_basis": key[0],
            "previous": previous,
            "current": current,
        })

    for key, previous in prior_index.items():
        if key in current_index:
            continue
        summary["removed_deals"] += 1
        deals.append({
            "deal": previous.get("name"),
            "movement": ["removed"],
            "match_basis": key[0],
            "previous": previous,
            "current": None,
        })

    return {
        "source": source,
        "evaluated": True,
        "deals": deals,
        "summary": summary,
    }


def validate_prior(obj):
    return isinstance(obj, dict) and isinstance(obj.get("ranking"), list) and "portfolio" in obj


def load_prior(bundle):
    if "prior_rollup" in bundle:
        prior = bundle.get("prior_rollup")
        if not validate_prior(prior):
            raise ValueError("prior_rollup must be a prior Computed inputs JSON object with portfolio/ranking")
        return prior, bundle.get("prior_rollup_source", "prior_rollup"), None

    path = first_present(bundle.get("compare_file"), bundle.get("prior_computed_inputs_path"))
    if not path:
        return None, None, None
    if not os.path.exists(path):
        return None, path, "compare_file_missing"
    try:
        with open(path) as f:
            prior = json.load(f)
    except ValueError as e:
        raise ValueError(f"invalid compare JSON: {e}")
    if not validate_prior(prior):
        raise ValueError("compare file must be a prior Computed inputs JSON object with portfolio/ranking")
    return prior, path, None


def missing_movement(source, reason):
    return {
        "source": source,
        "evaluated": False,
        "reason": reason,
        "deals": [],
        "summary": {
            "new_deals": 0,
            "removed_deals": 0,
            "risk_increased": 0,
            "risk_decreased": 0,
            "amount_changed": 0,
            "close_date_changed": 0,
        },
    }


def main():
    try:
        bundle = json.load(sys.stdin)
        model = load("risk-model.json")
        fields = load("sf-fields.json")

        # Mode is set explicitly by the command that built the bundle:
        # /pipeline-read -> read, /pipeline-forecast -> forecast,
        # /pipeline-hygiene -> hygiene. Accept legacy "triage" input at the
        # boundary, but new outputs always use "read".
        mode = normalize_token(bundle.get("mode"))
        if mode == "triage":
            mode = "read"
        hygiene_requested = mode == "hygiene"
        forecast_requested = bool(
            bundle.get("forecast")
            or mode == "forecast"
        ) and not hygiene_requested
        forecast_cfg = model.get("forecast", {})
        amount_cfg = fields.get("amount_basis", {})
        category_cfg = fields.get("forecast_category", {})
        severity = model.get("pipeline", {}).get("flag_severity", {})

        posture = normalize_token(bundle.get("posture") or forecast_cfg.get("default_posture", "conservative"))
        amount_basis = normalize_token(bundle.get("amount_basis") or amount_cfg.get("default", "acv"))
        amount_field = amount_cfg.get("fields", {}).get(amount_basis)
        if not amount_field:
            raise ValueError(f"unknown amount_basis: {bundle.get('amount_basis')}")
        internal_cfg = model.get("internal_evidence", {})
        internal_mode = normalize_token(
            bundle.get("internal") or bundle.get("internal_evidence_mode")
            or (internal_cfg.get("default_by_profile") or {}).get("pipeline")
            or internal_cfg.get("default")
            or "off"
        )
        if internal_mode not in {"auto", "off", "force"}:
            raise ValueError(f"unknown internal mode: {bundle.get('internal')}")

        deals = bundle.get("deals", []) or []

        if hygiene_requested:
            precedence = model.get("hygiene", {}).get("flag_precedence", [])
            rows = build_hygiene_rows(deals, precedence, amount_basis, amount_field)
            ranking = sort_hygiene(rows, precedence)
            portfolio = hygiene_portfolio(rows, precedence)
            out = {
                "schema_version": SCHEMA_VERSION,
                "run": {
                    "rep_name": bundle.get("rep_name"),
                    "run_date": (bundle.get("window") or {}).get("today") or bundle.get("run_date"),
                    "mode": "hygiene",
                    "posture": None,
                    "amount_basis": amount_basis,
                    "internal_evidence": "off",
                },
                "rep_name": bundle.get("rep_name"),
                "window": bundle.get("window"),
                "portfolio": portfolio,
                "ranking": ranking,
                "hygiene": {
                    "flag_precedence": precedence,
                    "stale_activity_days": model.get("hygiene", {}).get("stale_activity_days"),
                    "distribution": portfolio["distribution"],
                },
            }
        else:
            rows = build_rows(
                deals,
                severity,
                amount_basis,
                amount_field,
                category_cfg.get("field"),
                category_cfg.get("convention", {}),
            )
            ranking = sort_ranking(rows)
            portfolio = portfolio_for(deals, rows)

            gate_cfg = model.get("pipeline", {}).get("confidence_gate", {})
            floor, blocked_deals = apply_confidence_gate(rows, portfolio.get("total_acv"), gate_cfg)
            portfolio["confidence_floor"] = floor
            portfolio["confidence_blocked_deals"] = blocked_deals

            out = {
                "schema_version": SCHEMA_VERSION,
                "run": {
                    "rep_name": bundle.get("rep_name"),
                    "run_date": (bundle.get("window") or {}).get("today") or bundle.get("run_date"),
                    "mode": "forecast" if forecast_requested else "read",
                    "posture": posture if forecast_requested else None,
                    "amount_basis": amount_basis,
                    "internal_evidence": internal_mode,
                },
                "rep_name": bundle.get("rep_name"),
                "window": bundle.get("window"),
                "portfolio": portfolio,
                "ranking": ranking,
                "source_gaps": aggregate_coverage_gaps(deals),
                "severity_tiers_used": severity,
            }

            if forecast_requested:
                recommendations = [recommendation_for(row, deal) for row, deal in zip(rows, deals)]
                recommendations.sort(key=lambda r: [row.get("name") for row in ranking].index(r["deal"]))
                out["forecast"] = {
                    "amount_basis": amount_basis,
                    "amount_field": amount_field,
                    "posture": posture,
                    "category_convention": category_cfg.get("convention", {}),
                    "category_rollup": category_rollup(rows),
                    "recommendations": recommendations,
                }

            if internal_mode != "off":
                out["internal_evidence"] = internal_rollup(deals, internal_mode)

            prior, source, reason = load_prior(bundle)
            if prior is not None:
                out["movement"] = compare_prior(prior, rows, source)
            elif source is not None:
                out["movement"] = missing_movement(source, reason)

    except (ValueError, OSError) as e:
        sys.stderr.write(str(e) + "\n")
        sys.exit(1)

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
