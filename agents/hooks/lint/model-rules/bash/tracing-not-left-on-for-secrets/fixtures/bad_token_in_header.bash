#!/usr/bin/env bash
set -euo pipefail
set -x

readonly API_URL="https://api.example.com/v1/deployments"
readonly TOKEN="${DEPLOY_TOKEN:?DEPLOY_TOKEN is required}"

curl -fsS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"ref":"main"}' \
  "$API_URL"
