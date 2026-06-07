#!/usr/bin/env python3
"""Pins analyzed-deal and rollup output schema fields."""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMAS = os.path.join(HERE, "..", "schemas")


def load(name):
    with open(os.path.join(SCHEMAS, name)) as f:
        return json.load(f)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    analyzed = load("analyzed-deal.schema.json")
    rollup = load("rollup.schema.json")

    ok &= check("analyzed schema: confidence present", "confidence" in analyzed["properties"])
    ok &= check("analyzed schema: confidence labels",
                analyzed["properties"]["confidence"]["properties"]["max_label"]["enum"] == ["Low", "Medium", "High"])
    ok &= check("rollup schema: confidence present", "confidence" in rollup["properties"])
    ok &= check("rollup schema: confidence carries source gaps",
                "source_gaps" in rollup["properties"]["confidence"]["properties"])

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
