#!/usr/bin/env bash
set -euo pipefail

readonly TARGET="${1:?target is required}"

set +e
rsync -a dist/ "$TARGET:/srv/app/"
ssh "$TARGET" systemctl restart app
ssh "$TARGET" systemctl is-active app
echo "deployed to $TARGET"
