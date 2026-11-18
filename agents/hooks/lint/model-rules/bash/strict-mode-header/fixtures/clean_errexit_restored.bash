#!/usr/bin/env bash
set -Eeuo pipefail

readonly TARGET="${1:?target is required}"

# grep exits 1 when nothing matches, which is an answer here, not a failure.
set +e
grep -q '^ready$' "/var/run/$TARGET.state"
ready=$?
set -e

if ((ready == 0)); then
  systemctl restart "$TARGET"
fi
