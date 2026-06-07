#!/usr/bin/env python3
"""Guard active docs against stale source-policy language."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

ACTIVE_DOCS = [
    "README.md",
    "SETUP.md",
    "deal-read/SKILL.md",
    "deal-read/README.md",
    "deal-read/CONTEXT.md",
    "pipeline-read/SKILL.md",
    "pipeline-read/README.md",
    "pipeline-read/CONTEXT.md",
    "pipeline-read/commands/pipeline-read/SKILL.md",
    "pipeline-read/commands/pipeline-forecast/SKILL.md",
    "pipeline-read/commands/pipeline-hygiene/SKILL.md",
]

FORBIDDEN = [
    "mapped Slack deal rooms",
    "mapped Slack deal-room",
    "mapped deal-room evidence",
    "mapped rooms",
    "Slack_Channel__c",
    "Deal_Room_URL__c",
]


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def main():
    ok = True
    for rel in ACTIVE_DOCS:
        path = os.path.join(ROOT, rel)
        with open(path) as f:
            text = f.read()
        for needle in FORBIDDEN:
            ok &= check(f"{rel}: excludes {needle}", needle not in text)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
