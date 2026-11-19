#!/usr/bin/env bash
# Pre-commit hook: format the staged files of the project that runs it.
set -euo pipefail

cd "$(dirname "$0")"

mapfile -t staged < <(git diff --cached --name-only --diff-filter=ACM -- '*.py')
ruff format "${staged[@]}"
git add -- "${staged[@]}"
