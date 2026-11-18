#!/usr/bin/env bash
set -euCo pipefail

function usage() {
  cat <<USAGE >&2
Usage:
    $0
USAGE
  exit 1
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly REPO_ROOT
readonly HARNESS_PREFIX="${HOME:?}"

[[ "$#" -eq 0 ]] || usage
cd "$REPO_ROOT"
agent-harness install --source agents --prefix "$HARNESS_PREFIX"
