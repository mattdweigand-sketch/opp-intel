#!/usr/bin/env python3
import os
import subprocess
import sys


def main():
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "core", "scripts", "plan.py"))
    env = dict(os.environ)
    env["OPP_INTEL_SURFACE"] = "pipeline-read"
    proc = subprocess.run([sys.executable, core], input=sys.stdin.read(), text=True, env=env)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
