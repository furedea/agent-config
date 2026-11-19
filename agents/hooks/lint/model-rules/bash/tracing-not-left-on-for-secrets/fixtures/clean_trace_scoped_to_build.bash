#!/usr/bin/env bash
set -euo pipefail

readonly TOKEN="${PUBLISH_TOKEN:?PUBLISH_TOKEN is required}"

function build() {
  set -x
  npm ci --ignore-scripts
  npm run build
  set +x
}

build
npm publish --access public --//registry.npmjs.org/:_authToken="$TOKEN"
