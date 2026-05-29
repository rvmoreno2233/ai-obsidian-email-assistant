#!/usr/bin/env bash
set -euo pipefail

echo "Post-edit reminder: run narrowest validation for changed areas."

if command -v ruff >/dev/null 2>&1; then
  ruff check . 2>/dev/null || true
fi
