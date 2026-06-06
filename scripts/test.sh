#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_python_tests() {
  local label="$1"
  local dir="$2"

  printf '\n==> %s\n' "$label"
  cd "$dir"
  for test_file in tests/test_*.py; do
    python3 "$test_file"
  done
}

run_core_tests() {
  printf '\n==> core\n'
  cd "$repo_root"
  for test_file in core/tests/test_*.py; do
    python3 "$test_file"
  done
}

run_core_tests
run_python_tests "deal-read" "$repo_root/deal-read"
run_python_tests "pipeline-read" "$repo_root/pipeline-read"

printf '\nAll tests passed.\n'
