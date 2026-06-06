#!/usr/bin/env python3
import os
import subprocess
import sys


def main():
    core = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "core", "scripts", "rollup.py"))
    proc = subprocess.run([sys.executable, core, *sys.argv[1:]], input=sys.stdin.read(), text=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
