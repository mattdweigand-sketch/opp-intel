#!/usr/bin/env python3
"""Direct Phase 5 checks for core rollup and validators."""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ROLLUP = os.path.join(ROOT, "core", "scripts", "rollup.py")
DEAL_VALIDATE = os.path.join(ROOT, "core", "validators", "validate_deal_brief.py")
PIPELINE_VALIDATE = os.path.join(ROOT, "core", "validators", "validate_pipeline_brief.py")


def run_json(script, payload):
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip())
    return json.loads(proc.stdout)


def run_text(script, text):
    return subprocess.run([sys.executable, script], input=text, capture_output=True, text=True)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    rollup = run_json(ROLLUP, {
        "mode": "read",
        "deals": [
            {
                "name": "Acme",
                "acv": 100000,
                "analyze_output": {
                    "deal_metrics": {
                        "days_to_close": 10,
                        "flags": {"single_threaded": True, "stale_activity": True}
                    }
                }
            }
        ],
    })
    ok &= check("core rollup: ranking emitted", rollup["ranking"][0]["name"] == "Acme")
    ok &= check("core rollup: mode preserved", rollup["run"]["mode"] == "read")

    deal_brief = (
        "Confidence: Medium\n\nComputed inputs:\n```json\n"
        + json.dumps({"deal_metrics": {"flags": {"email_data_stale": False}}})
        + "\n```\n"
    )
    ok &= check("core deal validator passes", run_text(DEAL_VALIDATE, deal_brief).returncode == 0)

    pipeline_brief = (
        "Confidence: Medium\nWhere you're blind: None.\nComputed inputs:\n```json\n"
        + json.dumps({
            "schema_version": "pipeline-read.computed-inputs.v1",
            "run": {"mode": "read"},
            "portfolio": {"stale_data_deals": 0},
            "ranking": []
        })
        + "\n```\n"
    )
    ok &= check("core pipeline validator passes", run_text(PIPELINE_VALIDATE, pipeline_brief).returncode == 0)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
