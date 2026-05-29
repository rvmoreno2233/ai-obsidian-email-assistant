#!/usr/bin/env bash
set -euo pipefail

# Fail if .env is staged for commit
if git diff --cached --name-only 2>/dev/null | grep -q '^\.env$'; then
  echo "Blocked: .env must not be committed."
  exit 1
fi

# Warn on large catalog commits
if git diff --cached --name-only 2>/dev/null | grep -q '^data/catalog/'; then
  echo "Warning: staging data/catalog/ — review for PII before commit."
fi
