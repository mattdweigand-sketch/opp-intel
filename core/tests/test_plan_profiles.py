#!/usr/bin/env python3
"""Phase 4 plan profile and adapter contract checks."""

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CORE_PLAN = os.path.join(ROOT, "core", "scripts", "plan.py")
ADAPTERS = os.path.join(ROOT, "core", "adapters")


def run_plan(payload, surface="pipeline-read"):
    env = dict(os.environ)
    env["OPP_INTEL_SURFACE"] = surface
    proc = subprocess.run(
        [sys.executable, CORE_PLAN],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip())
    return json.loads(proc.stdout)


def load_adapter(name):
    path = os.path.join(ADAPTERS, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    deal = run_plan({"deal_name": "Acme", "opp_id": "006X", "account_id": "001X"}, surface="deal-read")
    ok &= check("deal plan: contact read fields preserved", "read_fields" in deal["salesforce"]["contact_roles"])
    ok &= check("deal plan: no pipeline contact query", "account_contacts" not in deal["salesforce"])

    pipeline = run_plan({"deal_name": "Acme", "opp_id": "006X", "account_id": "001X"}, surface="pipeline-read")
    ok &= check("pipeline per-deal plan: contact query preserved", "account_contacts" in pipeline["salesforce"])

    hygiene = run_plan({"mode": "pipeline", "hygiene": True, "today": "2026-06-04", "owner_id": "005XX"})
    ok &= check("hygiene plan: Salesforce only", hygiene["per_deal_connectors"] == ["Salesforce"])

    zoom = load_adapter("calls_zoom")
    gong = load_adapter("calls_gong")
    ok &= check("zoom adapter: current provider", zoom.plan("deal")["provider"] == "zoom")
    ok &= check("gong adapter: contract only", gong.plan("pipeline")["status"] == "contract_only")
    ok &= check("gmail off for hygiene", raises(lambda: load_adapter("gmail").plan("hygiene")))

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    main()
