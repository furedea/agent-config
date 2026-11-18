#!/usr/bin/env bash
set -euo pipefail

function archive_logs() {
  archive_name="logs-$(date +%Y%m%d).tar.gz"
  tar -czf "$archive_name" logs/
}

function count_failures() {
  local _failures=0
  for report in reports/*.xml; do
    if grep -q '<failure' "$report"; then
      ((_failures++))
    fi
  done
  printf '%s\n' "$_failures"
}

function ask_target() {
  read -r -p "Target host: " target_host
  ssh "$target_host" uptime
}

function publish_release() {
  local _version="$1"
  local _notes_file="$2"
  local _tag="v$_version"
  git fetch --tags origin
  git diff --quiet || {
    echo "working tree is dirty" >&2
    return 1
  }
  npm ci --ignore-scripts
  npm run build
  npm test
  npm pack --dry-run
  echo "build verified"
  git tag -a "$_tag" -F "$_notes_file"
  git push origin "$_tag"
}
