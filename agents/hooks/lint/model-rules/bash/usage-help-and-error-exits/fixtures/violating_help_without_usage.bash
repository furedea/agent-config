#!/usr/bin/env bash
set -euo pipefail

function usage() {
  cat <<EOF2
Usage:
    $0 <FILE>
EOF2
}

case "${1:-}" in
  --help)
    echo "see README.md"
    ;;
  "")
    usage
    exit 0
    ;;
esac

wc -l "$1"
