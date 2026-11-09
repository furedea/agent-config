#!/usr/bin/env bash
set -euCo pipefail

function usage() {
  cat <<EOF
Description:
    Refresh the sha256 that scripts/bootstrap_server.sh pins for bats-core. bats-core
    publishes no release assets, only the tag's source archive, so Renovate cannot
    compute its hash. Run this in the PR where Renovate bumped BATS_VERSION.

Usage:
    $0 [--check]

Options:
    --check: change nothing; fail when the pinned sha256 differs from the archive
    --help, -h: print this
EOF
}

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/bootstrap_server.sh"
readonly SCRIPT_PATH
readonly ARCHIVE_URL='https://github.com/bats-core/bats-core/archive/refs/tags/v{v}.tar.gz'
# shellcheck disable=SC2016  # the heads match script text, so the ${...} must stay literal
readonly VERSION_HEAD='readonly BATS_VERSION="${BATS_VERSION:-'
# shellcheck disable=SC2016  # see VERSION_HEAD
readonly SHA256_HEAD='readonly BATS_SHA256="${BATS_SHA256:-'

function main() {
  local _check=false
  case "${1:-}" in
    --help | -h) usage && exit 0 ;;
    --check) _check=true ;;
    "") ;;
    *) usage >&2 && exit 1 ;;
  esac
  local _version _sha256 _current
  _version="$(pinned_value "$VERSION_HEAD")"
  _current="$(pinned_value "$SHA256_HEAD")"
  _sha256="$(archive_sha256 "${ARCHIVE_URL//\{v\}/$_version}")"
  [[ "$_current" == "$_sha256" ]] && return 0
  printf 'BATS_SHA256: %s -> %s\n' "$_current" "$_sha256"
  [[ "$_check" == true ]] && return 1
  replace_pin "$_sha256"
}

# Prints the default value of the assignment that starts with the given head.
function pinned_value() {
  local _head="$1" _line
  while IFS= read -r _line; do
    if [[ "$_line" == "$_head"* ]]; then
      _line="${_line#"$_head"}"
      printf '%s\n' "${_line%\}\"}"
      return 0
    fi
  done <"$SCRIPT_PATH"
  printf 'no %s in %s\n' "$_head" "$SCRIPT_PATH" >&2
  return 1
}

function archive_sha256() {
  local _url="$1" _sri
  _sri="$(nix store prefetch-file --json --hash-type sha256 "$_url" | jq -r .hash)"
  nix hash convert --hash-algo sha256 --to base16 "$_sri"
}

function replace_pin() {
  local _sha256="$1" _line _output=""
  while IFS= read -r _line; do
    [[ "$_line" == "$SHA256_HEAD"* ]] && _line="$SHA256_HEAD$_sha256}\""
    _output+="$_line"$'\n'
  done <"$SCRIPT_PATH"
  printf '%s' "$_output" >|"$SCRIPT_PATH"
}

main "$@"
