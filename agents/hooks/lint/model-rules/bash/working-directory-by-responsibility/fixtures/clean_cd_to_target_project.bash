#!/usr/bin/env bash
# Usage: update.sh <PROJECT_DIR>: update the lock file of PROJECT_DIR.
set -euo pipefail

readonly PROJECT_DIR="${1:?PROJECT_DIR is required}"

cd "$PROJECT_DIR"
uv lock --upgrade
git diff --stat -- uv.lock
