#!/usr/bin/env bash
set -euo pipefail

echo "Running repo quality gate..."

if command -v ruff >/dev/null 2>&1; then
  ruff check .
fi

if command -v black >/dev/null 2>&1; then
  black --check .
fi

if command -v pytest >/dev/null 2>&1; then
  pytest
fi

echo "Quality gate passed."
