#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
assume_yes="false"
register_args=()

usage() {
  cat <<'EOF'
Usage: scripts/setup.sh [--force] [--yes]

Options:
  --force  Replace existing non-symlink Claude skill folders.
  --yes    Skip the connector confirmation prompt.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      register_args+=("--force")
      shift
      ;;
    --yes)
      assume_yes="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

printf '==> Registering Claude slash commands\n'
if [[ "${#register_args[@]}" -gt 0 ]]; then
  "$repo_root/scripts/register-claude-skills.sh" "${register_args[@]}"
else
  "$repo_root/scripts/register-claude-skills.sh"
fi

cat <<'EOF'

==> Connector requirements

Install and authorize these connectors in the Claude or agent client before using opp-intel:

- Salesforce: opportunity truth, CRM fields, and hygiene mode
- Gmail: email freshness and thread evidence
- Google Calendar: historical and future meeting context
- Zoom: current implemented call provider
- Slack: mapped deal-room evidence
- Google Drive: linked proposal and deal-room documents

All source access should remain read-only. deal-read may only create a Gmail draft after explicit confirmation.
EOF

if [[ "$assume_yes" == "true" ]]; then
  printf '\nConnector confirmation skipped because --yes was passed.\n'
  exit 0
fi

printf '\nHave these connectors been installed and authorized for this agent client? [y/N] '
read -r reply

case "$reply" in
  y|Y|yes|YES)
    printf 'Connector readiness confirmed.\n'
    ;;
  *)
    cat <<'EOF'
Connector setup is incomplete.

Open the Claude or agent client, install and authorize the listed connectors, then rerun:

  scripts/setup.sh

EOF
    exit 1
    ;;
esac
