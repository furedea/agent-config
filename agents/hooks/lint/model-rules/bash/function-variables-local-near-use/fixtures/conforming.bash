#!/usr/bin/env bash
set -euo pipefail

function archive_logs() {
  local _archive_name
  _archive_name="logs-$(date +%Y%m%d).tar.gz"
  tar -czf "$_archive_name" logs/
}

function count_failures() {
  local _failures=0
  local _report
  for _report in reports/*.xml; do
    if grep -q '<failure' "$_report"; then
      ((_failures++))
    fi
  done
  printf '%s\n' "$_failures"
}

# Sets SELECTED_PROFILE for the caller: the rest of the script reads it.
function select_profile() {
  SELECTED_PROFILE="${PROFILE:-default}"
}

function sorted_names() {
  local _file="$1"
  LC_ALL=C sort -u "$_file"
}

# Prints the agent-config location of a host file, or the legacy one while only that exists.
function host_config_file() {
  local _name="$1"
  if [[ ! -e "$CONFIG_DIR/$_name" && -e "$LEGACY_CONFIG_DIR/$_name" ]]; then
    printf '%s\n' "$LEGACY_CONFIG_DIR/$_name"
  else
    printf '%s\n' "$CONFIG_DIR/$_name"
  fi
}
