#!/usr/bin/env bash
# Pre-commit hook: lint the project that runs it with the rules bundled next to this script.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

(cd "$SCRIPT_DIR" && ast-grep test --skip-snapshot-tests)
ast-grep scan --config "$SCRIPT_DIR/sgconfig.yml" .
