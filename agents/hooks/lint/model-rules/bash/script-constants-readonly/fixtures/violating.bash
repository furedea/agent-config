#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="$(dirname "$0")/../data/input"
MAX_RETRY=3
readonly OUTPUT_DIR="$INPUT_DIR/../output"

function fetch_with_retry() {
  local _url="$1"
  local _attempt
  for ((_attempt = 1; _attempt <= MAX_RETRY; _attempt++)); do
    curl -fsSL "$_url" -o "$OUTPUT_DIR/page.html" && return 0
  done
  return 1
}

API_URL="https://api.example.com/v1/status"

fetch_with_retry "$API_URL"
ls "$INPUT_DIR"
