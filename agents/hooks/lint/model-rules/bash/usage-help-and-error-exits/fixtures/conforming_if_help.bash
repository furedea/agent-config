#!/usr/bin/env bash
set -euo pipefail

function usage() {
  cat <<EOF2
Usage:
    $0 <FILE>
EOF2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

wc -l "${1:?FILE is required}"
