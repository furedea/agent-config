#!/usr/bin/env bash
# Usage: lint.sh [DIR]: lint DIR (default: the current directory) with the bundled config.
set -euo pipefail

readonly TARGET="${1:-.}"

cd "$(dirname "${BASH_SOURCE[0]}")"
shellcheck --rcfile=shellcheckrc "$TARGET"/*.sh
