#!/usr/bin/env python3
"""Checks that thin command frontends stay aligned with the shared engine."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMMANDS = os.path.join(HERE, "..", "commands")


def read(name):
    with open(os.path.join(COMMANDS, name, "SKILL.md")) as f:
        return f.read()


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    triage = read("pipeline-triage")
    forecast = read("pipeline-forecast")
    hygiene = read("pipeline-hygiene")

    for name, text in {
        "triage": triage,
        "forecast": forecast,
        "hygiene": hygiene,
    }.items():
        ok &= check(f"{name}: no personal absolute repo path", "/Users/matthewweigand/Code/opp-intel" not in text)

    ok &= check("triage: Calendar connector named", "Google Calendar" in triage)
    ok &= check("forecast: Calendar connector named", "Google Calendar" in forecast)
    ok &= check("hygiene: Calendar explicitly excluded", "no Gmail, Calendar, Zoom, Slack, or Drive" in hygiene)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
