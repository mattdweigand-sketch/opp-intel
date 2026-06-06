#!/usr/bin/env python3
"""Parity checks for Phase 0 baseline fixtures."""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(HERE, "fixtures")


def run_fixture(path):
    with open(path) as f:
        fixture = json.load(f)
    script = os.path.join(ROOT, fixture["surface"], fixture["script"])
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(fixture["input"]),
        capture_output=True,
        text=True,
        cwd=os.path.join(ROOT, fixture["surface"]),
    )
    if proc.returncode != 0:
        raise AssertionError(f"{path} failed: {proc.stderr.strip()}")
    actual = json.loads(proc.stdout)
    if actual != fixture["output"]:
        raise AssertionError(f"{os.path.basename(path)} drifted")


def main():
    ok = True
    for name in sorted(os.listdir(FIXTURES)):
        if not name.endswith(".json"):
            continue
        try:
            run_fixture(os.path.join(FIXTURES, name))
            print("PASS", name)
        except AssertionError as exc:
            ok = False
            print("FAIL", exc)
    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
