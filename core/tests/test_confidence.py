#!/usr/bin/env python3
"""Pins deterministic confidence ceilings."""

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIDENCE = os.path.join(HERE, "..", "scripts", "confidence.py")


def load_confidence():
    spec = importlib.util.spec_from_file_location("confidence", CONFIDENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    confidence = load_confidence()
    ok = True

    clean = confidence.deal_confidence({"flags": {}, "coverage_gaps": []})
    ok &= check("deal clean: High ceiling", clean["max_label"] == "High")

    stale = confidence.deal_confidence({"flags": {"email_data_stale": True}, "coverage_gaps": []})
    ok &= check("deal stale email: Low ceiling", stale["max_label"] == "Low")
    ok &= check("deal stale email: reason", "email_data_stale" in stale["reason_codes"])

    email_gap = confidence.deal_confidence(
        {"flags": {}, "coverage_gaps": ["email_newest_thread_coverage_gap"]}
    )
    ok &= check("deal email coverage gap: Low ceiling", email_gap["max_label"] == "Low")

    internal_gap = confidence.deal_confidence(
        {"flags": {}, "coverage_gaps": []},
        internal_evidence={"source_gaps": ["deal_room_missing"]},
    )
    ok &= check("deal internal gap: Medium ceiling", internal_gap["max_label"] == "Medium")

    pipeline_stale = confidence.pipeline_confidence(
        "read",
        [{"risk_flags": ["email_data_stale"], "coverage_gaps": []}],
    )
    ok &= check("pipeline stale data: Low ceiling", pipeline_stale["max_label"] == "Low")

    pipeline_gap = confidence.pipeline_confidence(
        "read",
        [{"risk_flags": [], "coverage_gaps": ["calendar_unavailable"]}],
        source_gaps=["calendar_unavailable"],
        coverage_gap_deals=["Acme"],
    )
    ok &= check("pipeline non-email gap: Medium ceiling", pipeline_gap["max_label"] == "Medium")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
