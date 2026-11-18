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
      exit 0
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -*)
      usage >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ "$#" -ne 1 ]]; then
  usage >&2
  exit 1
fi

echo "deploying to $1 (dry run: $dry_run)"
