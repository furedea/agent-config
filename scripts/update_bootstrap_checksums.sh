#!/usr/bin/env bash
set -euCo pipefail

function usage() {
  cat <<EOF
Description:
    Refresh the sha256 pins that scripts/bootstrap_server.sh keeps next to each
    release version. Run it in the PR where Renovate bumped a version. The hash
    comes from the digest GitHub records for the release asset (gh api), or, for
    old releases without one, from nix store prefetch-file.

Usage:
    $0 [--check]

Options:
    --check: change nothing; fail when a pinned sha256 differs from the release
    --help, -h: print this
EOF
}

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/bootstrap_server.sh"
readonly SCRIPT_PATH

# Each row: VARIABLE_PREFIX|GitHub repository|tag|asset name. {v} stands for the pinned version.
# Keep the rows in step with the URLs in bootstrap_server.sh.
readonly -a ASSETS=(
  'AGENT_HARNESS|furedea/agent-harness|agent-harness-v{v}|agent-harness-x86_64-unknown-linux-musl.tar.xz'
  'SHFMT|mvdan/sh|v{v}|shfmt_v{v}_linux_amd64'
  'RIPGREP|BurntSushi/ripgrep|{v}|ripgrep-{v}-x86_64-unknown-linux-musl.tar.gz'
  'JQ|jqlang/jq|jq-{v}|jq-linux-amd64'
  'RUFF|astral-sh/ruff|{v}|ruff-x86_64-unknown-linux-musl.tar.gz'
  'DPRINT|dprint/dprint|{v}|dprint-x86_64-unknown-linux-musl.zip'
  'SHELLCHECK|koalaman/shellcheck|v{v}|shellcheck-v{v}.linux.x86_64.tar.xz'
  'UV|astral-sh/uv|{v}|uv-x86_64-unknown-linux-musl.tar.gz'
)
# bats-core is a source archive, which has no release asset digest.
readonly BATS_ARCHIVE_URL='https://github.com/bats-core/bats-core/archive/refs/tags/v{v}.tar.gz'

function main() {
  local _check=false
  case "${1:-}" in
    --help | -h) usage && exit 0 ;;
    --check) _check=true ;;
    "") ;;
    *) usage >&2 && exit 1 ;;
  esac
  local _prefix _repo _tag _asset _row _version _sha256 _failed=false
  for _row in "${ASSETS[@]}"; do
    IFS='|' read -r _prefix _repo _tag _asset <<<"$_row"
    _version="$(pinned_version "$_prefix")"
    _sha256="$(asset_sha256 "$_repo" "${_tag//\{v\}/$_version}" "${_asset//\{v\}/$_version}")"
    apply_pin "$_prefix" "$_sha256" "$_check" || _failed=true
  done
  _version="$(pinned_version BATS)"
  _sha256="$(archive_sha256 "${BATS_ARCHIVE_URL//\{v\}/$_version}")"
  apply_pin BATS "$_sha256" "$_check" || _failed=true
  [[ "$_failed" == false ]]
}

function pinned_version() {
  local _prefix="$1" _line
  while IFS= read -r _line; do
    if [[ "$_line" == "readonly ${_prefix}_VERSION=\"\${${_prefix}_VERSION:-"* ]]; then
      _line="${_line#*:-}"
      printf '%s\n' "${_line%\}\"}"
      return 0
    fi
  done <"$SCRIPT_PATH"
  printf 'no %s_VERSION in %s\n' "$_prefix" "$SCRIPT_PATH" >&2
  return 1
}

function asset_sha256() {
  local _repo="$1" _tag="$2" _asset="$3" _digest
  _digest="$(gh api "repos/$_repo/releases/tags/$_tag" --jq ".assets[] | select(.name == \"$_asset\") | .digest")"
  if [[ "$_digest" == sha256:* ]]; then
    printf '%s\n' "${_digest#sha256:}"
    return 0
  fi
  archive_sha256 "https://github.com/$_repo/releases/download/$_tag/$_asset"
}

function archive_sha256() {
  local _url="$1" _sri
  _sri="$(nix store prefetch-file --json --hash-type sha256 "$_url" | jq -r .hash)"
  nix hash convert --hash-algo sha256 --to base16 "$_sri"
}

# Rewrites the pin, or only reports a stale one with --check.
function apply_pin() {
  local _prefix="$1" _sha256="$2" _check="$3" _line _current _updated
  local _head="readonly ${_prefix}_SHA256=\"\${${_prefix}_SHA256:-"
  local _output="" _found=false
  while IFS= read -r _line; do
    if [[ "$_line" == "$_head"* ]]; then
      _found=true
      _current="${_line#"$_head"}"
      _current="${_current%\}\"}"
      _line="$_head$_sha256}\""
      if [[ "$_current" != "$_sha256" ]]; then
        printf '%s: %s -> %s\n' "$_prefix" "$_current" "$_sha256"
        _updated=true
      fi
    fi
    _output+="$_line"$'\n'
  done <"$SCRIPT_PATH"
  [[ "$_found" == true ]] || {
    printf 'no %s_SHA256 in %s\n' "$_prefix" "$SCRIPT_PATH" >&2
    return 1
  }
  [[ "${_updated:-false}" == true ]] || return 0
  [[ "$_check" == true ]] && return 1
  printf '%s' "$_output" >|"$SCRIPT_PATH"
}

main "$@"
