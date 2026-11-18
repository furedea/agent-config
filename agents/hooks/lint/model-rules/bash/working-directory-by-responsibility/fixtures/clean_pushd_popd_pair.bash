#!/usr/bin/env bash
# Packages the current project with the vendored helper that ships next to this script.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

pushd "$SCRIPT_DIR/vendor/helper" >/dev/null
make
popd >/dev/null
"$SCRIPT_DIR/vendor/helper/bin/pack" --out dist/ .
