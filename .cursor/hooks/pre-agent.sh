#!/usr/bin/env bash
set -euo pipefail

echo "Pre-agent checks..."

if [[ -f .env ]]; then
  echo "Note: .env present — do not commit secrets."
fi

if git diff --name-only 2>/dev/null | grep -q '^data/catalog/'; then
  echo "Warning: data/catalog/ has uncommitted changes — may contain PII."
fi

echo "Pre-agent checks complete."
