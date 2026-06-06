#!/usr/bin/env python3
import os
import subprocess
import sys
import json


def main():
    raw = sys.stdin.read()
    if raw.strip():
        try:
            ctx = json.loads(raw)
        except ValueError:
            sys.stderr.write("invalid JSON input\n")
            sys.exit(1)
        if ctx.get("mode") == "pipeline":
            sys.stderr.write("deal-read plan.py does not emit pipeline portfolio plans\n")
            sys.exit(1)
    else:
        raw = ""
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "core", "scripts", "plan.py"))
    env = dict(os.environ)
    env["OPP_INTEL_SURFACE"] = "deal-read"
    proc = subprocess.run([sys.executable, core], input=raw, text=True, env=env)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
