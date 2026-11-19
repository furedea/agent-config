#!/usr/bin/env bash
set -euo pipefail

function usage() {
  cat <<EOF2
Usage:
    $0 [--dry-run] <TARGET>
EOF2
}

dry_run=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 1
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${TARGET:-}" ]]; then
  echo "TARGET is required"
  exit 0
fi

echo "deploying to $TARGET (dry run: $dry_run)"
