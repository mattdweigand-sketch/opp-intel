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
    read_cmd = read("pipeline-read")
    forecast = read("pipeline-forecast")
    hygiene = read("pipeline-hygiene")
    ok &= check("old pipeline-triage command folder absent",
                not os.path.exists(os.path.join(COMMANDS, "pipeline-triage")))

    for name, text in {
        "read": read_cmd,
        "forecast": forecast,
        "hygiene": hygiene,
    }.items():
        ok &= check(f"{name}: no personal absolute repo path", "/Users/matthewweigand/Code/opp-intel" not in text)

    ok &= check("read: Calendar connector named", "Google Calendar" in read_cmd)
    ok &= check("forecast: Calendar connector named", "Google Calendar" in forecast)
    ok &= check("hygiene: Calendar explicitly excluded", "no Gmail, Calendar, Zoom, Slack, or Drive" in hygiene)
    ok &= check("frontends: old /pipeline-triage command absent",
                "/pipeline-triage" not in read_cmd
                and "/pipeline-triage" not in forecast
                and "/pipeline-triage" not in hygiene)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
