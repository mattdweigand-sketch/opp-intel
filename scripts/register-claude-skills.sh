#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skills_dir="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
force="false"

if [[ "${1:-}" == "--force" ]]; then
  force="true"
fi

mkdir -p "$skills_dir"

register_skill() {
  local name="$1"
  local source="$2"
  local target="$skills_dir/$name"

  if [[ -e "$target" && ! -L "$target" && "$force" != "true" ]]; then
    printf 'SKIP %s: %s exists and is not a symlink. Re-run with --force to replace it.\n' "$name" "$target"
    return 0
  fi

  rm -rf "$target"
  ln -s "$source" "$target"
  printf 'OK   %s -> %s\n' "$target" "$source"
}

register_skill "deal-read" "$repo_root/deal-read"
register_skill "pipeline-triage" "$repo_root/pipeline-read/commands/pipeline-triage"
register_skill "pipeline-forecast" "$repo_root/pipeline-read/commands/pipeline-forecast"
register_skill "pipeline-hygiene" "$repo_root/pipeline-read/commands/pipeline-hygiene"
