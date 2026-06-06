#!/usr/bin/env python3
"""Tests for portable Claude skill registration. Run: python3 test_register_claude_skills.py"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REGISTER = os.path.join(ROOT, "scripts", "register-claude-skills.sh")


def run(skills_dir, *args):
    env = dict(os.environ)
    env["CLAUDE_SKILLS_DIR"] = skills_dir
    return subprocess.run([REGISTER, *args], env=env, capture_output=True, text=True)


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    return cond


def link_target(skills_dir, name):
    return os.readlink(os.path.join(skills_dir, name))


def main():
    ok = True

    with tempfile.TemporaryDirectory() as skills_dir:
        stale_target = "/tmp/old-opp-intel/pipeline-read/commands/pipeline-triage"
        os.symlink(stale_target, os.path.join(skills_dir, "pipeline-triage"))

        p = run(skills_dir)
        ok &= check("register: exits zero", p.returncode == 0)
        ok &= check("register: deal-read symlink",
                    link_target(skills_dir, "deal-read") == os.path.join(ROOT, "deal-read"))
        ok &= check("register: pipeline-read symlink",
                    link_target(skills_dir, "pipeline-read") == os.path.join(ROOT, "pipeline-read", "commands", "pipeline-read"))
        ok &= check("register: forecast symlink",
                    link_target(skills_dir, "pipeline-forecast") == os.path.join(ROOT, "pipeline-read", "commands", "pipeline-forecast"))
        ok &= check("register: hygiene symlink",
                    link_target(skills_dir, "pipeline-hygiene") == os.path.join(ROOT, "pipeline-read", "commands", "pipeline-hygiene"))
        ok &= check("register: stale triage symlink removed",
                    not os.path.exists(os.path.join(skills_dir, "pipeline-triage")))

    with tempfile.TemporaryDirectory() as skills_dir:
        existing = os.path.join(skills_dir, "pipeline-read")
        os.makedirs(existing)
        p = run(skills_dir)
        ok &= check("register: existing folder skipped without force",
                    p.returncode == 0 and os.path.isdir(existing) and not os.path.islink(existing))

        p = run(skills_dir, "--force")
        ok &= check("register: force replaces existing folder",
                    p.returncode == 0 and os.path.islink(existing)
                    and link_target(skills_dir, "pipeline-read") == os.path.join(ROOT, "pipeline-read", "commands", "pipeline-read"))

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
