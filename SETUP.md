# Setup

Use this file for local machine setup. The repo-level product and architecture overview lives in `README.md`.

## 1. Clone the repo

Clone `opp-intel` wherever you keep team projects:

```bash
git clone git@github.com:mattdweigand-sketch/opp-intel.git
cd opp-intel
```

The setup scripts resolve paths from the current checkout. They do not require a specific user directory.

## 2. Register Claude commands

Register the local Claude commands from this checkout:

```bash
scripts/register-claude-skills.sh
```

The script creates symlinks under `~/.claude/skills`:

```text
~/.claude/skills/deal-read -> <repo>/deal-read
~/.claude/skills/pipeline-triage -> <repo>/pipeline-read/commands/pipeline-triage
~/.claude/skills/pipeline-forecast -> <repo>/pipeline-read/commands/pipeline-forecast
~/.claude/skills/pipeline-hygiene -> <repo>/pipeline-read/commands/pipeline-hygiene
```

If Claude skills live somewhere else on your machine, set `CLAUDE_SKILLS_DIR`:

```bash
CLAUDE_SKILLS_DIR="$HOME/.config/claude/skills" scripts/register-claude-skills.sh
```

The script will not replace an existing non-symlink skill folder unless run with `--force`.

## 3. Verify the repo

Run the full local gate:

```bash
scripts/test.sh
```

The gate runs shared core tests, the `deal-read` surface tests, and the `pipeline-read` surface tests.

## 4. Start points

Claude can start at `CLAUDE.md`, which is a thin pointer back to `AGENTS.md`.

For repo-wide rules, read:

- `AGENTS.md`
- `CLAUDE.md`

For surface-specific behavior, read:

- `deal-read/README.md`
- `deal-read/AGENTS.md`
- `deal-read/SKILL.md`
- `pipeline-read/README.md`
- `pipeline-read/AGENTS.md`
- `pipeline-read/SKILL.md`

## Troubleshooting

If a command is missing, rerun:

```bash
scripts/register-claude-skills.sh
```

If a teammate already has a real folder at one of the command paths, the script will skip that command. Review the existing folder first. Then run:

```bash
scripts/register-claude-skills.sh --force
```

If tests fail, start with the first failing suite in the `scripts/test.sh` output. The repo has no `pytest` dependency; tests are plain Python files.
