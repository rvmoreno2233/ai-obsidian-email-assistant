#!/usr/bin/env bash
set -euo pipefail

COMMAND="${1:-}"

BLOCKED_PATTERNS=(
  "rm -rf /"
  "rm -rf data/catalog"
  "rm -rf vault"
  "git push --force"
  "git reset --hard"
  "chmod -R 777"
)

for pattern in "${BLOCKED_PATTERNS[@]}"; do
  if [[ "$COMMAND" == *"$pattern"* ]]; then
    echo "Blocked risky command: $pattern"
    exit 1
  fi
done
