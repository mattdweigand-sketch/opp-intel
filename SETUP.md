# Setup

Use this file for local machine setup. The repo-level product and architecture overview lives in `README.md`.

## 1. Clone the repo

Clone `opp-intel` wherever you keep team projects:

```bash
git clone git@github.com:mattdweigand-sketch/opp-intel.git
cd opp-intel
```

The setup scripts resolve paths from the current checkout. They do not require a specific user directory.

## 2. Run local setup

Run the setup script from the repo root:

```bash
scripts/setup.sh
```

The script does two things:

- installs the local Claude slash commands from this checkout
- prompts you to install and authorize the required connectors

Slash commands are registered as symlinks under `~/.claude/skills`:

```text
~/.claude/skills/deal-read -> <repo>/deal-read
~/.claude/skills/pipeline-read -> <repo>/pipeline-read/commands/pipeline-read
~/.claude/skills/pipeline-forecast -> <repo>/pipeline-read/commands/pipeline-forecast
~/.claude/skills/pipeline-hygiene -> <repo>/pipeline-read/commands/pipeline-hygiene
```

Required connectors:

- Salesforce: opportunity truth, CRM fields, and hygiene mode
- Gmail: email freshness and thread evidence
- Google Calendar: historical and future meeting context, plus deterministic meeting-cadence flags
- Zoom: current implemented call provider
- Slack: Slack MCP channel/message evidence only; Salesforce is never Slack evidence
- Google Drive: linked proposal and deal-room documents

All source access should remain read-only. `deal-read` may only create a Gmail draft after explicit confirmation.
If Google Calendar is unavailable, the repo records a source gap instead of creating Calendar risk flags.

If Claude skills live somewhere else on your machine, set `CLAUDE_SKILLS_DIR`:

```bash
CLAUDE_SKILLS_DIR="$HOME/.config/claude/skills" scripts/setup.sh
```

The script will not replace an existing non-symlink skill folder unless run with `--force`:

```bash
scripts/setup.sh --force
```

For non-interactive setup, pass `--yes` to skip the connector confirmation prompt:

```bash
scripts/setup.sh --yes
```

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
scripts/setup.sh
```

If a teammate already has a real folder at one of the command paths, the script will skip that command. Review the existing folder first. Then run:

```bash
scripts/setup.sh --force
```

If tests fail, start with the first failing suite in the `scripts/test.sh` output. The repo has no `pytest` dependency; tests are plain Python files.
