#!/usr/bin/env bash
# Install pre-commit hooks for local governance checks.
# See docs/decisions/ADR-016-pre-commit-hooks-governance.md for rationale.
set -euo pipefail

pip install pre-commit
pre-commit install

echo "Pre-commit hooks installed. They will run on every 'git commit'."
echo "To run manually: pre-commit run --all-files"
echo "To bypass (emergency only): git commit --no-verify"
