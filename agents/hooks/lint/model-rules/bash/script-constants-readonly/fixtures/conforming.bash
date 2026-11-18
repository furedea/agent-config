#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly SCRIPT_DIR
readonly INPUT_DIR="$SCRIPT_DIR/../data/input"

failed=0
verbose=0
files=()

while getopts "v" option; do
  case "$option" in
    v) verbose=1 ;;
    *) exit 1 ;;
  esac
done

for file in "$INPUT_DIR"/*.csv; do
  files+=("$file")
  if ! csvlint "$file"; then
    failed=$((failed + 1))
  fi
done

if ((verbose)); then
  printf 'checked %s files\n' "${#files[@]}"
fi
exit "$failed"
