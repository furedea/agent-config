REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
export REPO_ROOT
# Keep bsdtar from adding AppleDouble entries to fixture archives.
export COPYFILE_DISABLE=1

readonly FAKE_AGENT_HARNESS_VERSION="9.9.9"
# Executable entry points the fake agent-harness renders with the source shebang.
readonly RENDERED_ENTRY_POINTS=(
  .claude/hooks/guard_command.py
  .claude/statusline/statusline.py
  .claude/skills/explain-visually/scripts/render.py
  .codex/hooks/hook_adapter.py
  .codex/skills/explain-visually/scripts/render.py
  .devin/hooks/hook_adapter.py
  .hermes/hooks/hook_adapter.py
  .pi/hooks/hook_adapter.py
)

# Offline stand-ins for the release downloads and installers used by
# scripts/bootstrap_server.sh. Every fixture lives under BATS_TEST_TMPDIR.
function create_bootstrap_server_fixtures() {
  HOME_DIR="$BATS_TEST_TMPDIR/home"
  # shellcheck disable=SC2034  # asserted by the .bats file
  BIN_DIR="$HOME_DIR/.local/bin"
  RELEASES="$BATS_TEST_TMPDIR/releases"
  FAKE_PYTHON="$BATS_TEST_TMPDIR/python3.14"
  UV_ARGS_FILE="$BATS_TEST_TMPDIR/uv-args"
  AGENT_HARNESS_ARGS_FILE="$BATS_TEST_TMPDIR/agent-harness-args"
  SANDBOX_TOOLS_DIR="$BATS_TEST_TMPDIR/sandbox-tools"
  mkdir -p "$HOME_DIR" "$RELEASES" "$SANDBOX_TOOLS_DIR"
  write_stub "$FAKE_PYTHON" '#!/bin/sh' "exec '$(command -v python3)' \"\$@\""
  write_stub "$RELEASES/shfmt" '#!/bin/sh' 'exit 0'
  write_stub "$RELEASES/jq" '#!/bin/sh' "exec '$(command -v jq)' \"\$@\""
  write_stub "$SANDBOX_TOOLS_DIR/bwrap" '#!/bin/sh' 'exit 0'
  write_stub "$SANDBOX_TOOLS_DIR/socat" '#!/bin/sh' 'exit 0'
  create_agent_harness_archive
  create_tarball ripgrep.tar.gz ripgrep-14.1.1-x86_64-unknown-linux-musl rg
  create_tarball ruff.tar.gz ruff-x86_64-unknown-linux-musl ruff
  create_tarball shellcheck.tar.xz shellcheck-v0.11.0 shellcheck
  create_dprint_archive
  create_bats_archive
  create_uv_installer
}

# Runs the script with the sandbox tools present unless PATH is overridden.
function bootstrap_server() {
  env -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_CACHE_HOME -u BIN_DIR \
    HOME="$HOME_DIR" \
    PATH="$SANDBOX_TOOLS_DIR:$PATH" \
    BOOTSTRAP_SERVER_MACHINE=x86_64 \
    AGENT_HARNESS_VERSION="$FAKE_AGENT_HARNESS_VERSION" \
    AGENT_HARNESS_URL="file://$RELEASES/agent-harness.tar.xz" \
    SHFMT_URL="file://$RELEASES/shfmt" \
    RIPGREP_URL="file://$RELEASES/ripgrep.tar.gz" \
    JQ_URL="file://$RELEASES/jq" \
    RUFF_URL="file://$RELEASES/ruff.tar.gz" \
    DPRINT_URL="file://$RELEASES/dprint.zip" \
    SHELLCHECK_URL="file://$RELEASES/shellcheck.tar.xz" \
    BATS_URL="file://$RELEASES/bats-core.tar.gz" \
    UV_INSTALLER_URL="file://$RELEASES/uv_install.sh" \
    FAKE_PYTHON="$FAKE_PYTHON" \
    UV_ARGS_FILE="$UV_ARGS_FILE" \
    AGENT_HARNESS_ARGS_FILE="$AGENT_HARNESS_ARGS_FILE" \
    "$@" \
    /bin/bash "$SCRIPT"
}

# Prints a PATH holding only the host commands the script and its fixtures use,
# so tests can observe a host without bubblewrap or socat.
function path_without_sandbox_tools() {
  local _directory="$BATS_TEST_TMPDIR/host-tools" _command
  mkdir -p "$_directory"
  for _command in bash sh env cat curl tar xz gzip install mktemp rm cp mv ln mkdir chmod \
    head tail find dirname uname sha256sum jq python3 grep; do
    ln -sf "$(command -v "$_command")" "$_directory/$_command"
  done
  printf '%s\n' "$_directory"
}

function write_stub() {
  local _path="$1"
  shift
  printf '%s\n' "$@" >|"$_path"
  chmod 0755 "$_path"
}

# Prints the rendered Codex config as JSON.
function codex_config_json() {
  python3 -c 'import json, sys, tomllib; json.dump(tomllib.load(sys.stdin.buffer), sys.stdout, default=lambda v: v.isoformat().replace("+00:00", "Z"))' \
    <"$HOME_DIR/.codex/config.toml"
}

function write_host_env() {
  mkdir -p "$HOME_DIR/.config/agent-config"
  printf '%s\n' "$@" >|"$HOME_DIR/.config/agent-config/bootstrap_server.env"
}

function create_agent_harness_archive() {
  local _name="agent-harness-x86_64-unknown-linux-musl"
  mkdir -p "$BATS_TEST_TMPDIR/$_name"
  write_fake_agent_harness "$BATS_TEST_TMPDIR/$_name/agent-harness"
  tar -cJf "$RELEASES/agent-harness.tar.xz" -C "$BATS_TEST_TMPDIR" "$_name"
  write_checksum "$RELEASES/agent-harness.tar.xz"
}

# Mirrors the release checksum format: "<sha256> *<asset name>".
function write_checksum() {
  local _archive="$1" _sum
  _sum="$(sha256sum "$_archive")"
  printf '%s *%s\n' "${_sum%% *}" "${_archive##*/}" >|"$_archive.sha256"
}

# Packs one stub binary inside a top-level directory, as the release tarballs do.
function create_tarball() {
  local _archive="$1" _name="$2" _binary="$3"
  mkdir -p "$BATS_TEST_TMPDIR/$_name"
  write_stub "$BATS_TEST_TMPDIR/$_name/$_binary" '#!/bin/sh' 'exit 0'
  tar -caf "$RELEASES/$_archive" -C "$BATS_TEST_TMPDIR" "$_name"
}

# dprint ships its binary at the root of a zip archive.
function create_dprint_archive() {
  mkdir -p "$BATS_TEST_TMPDIR/dprint-release"
  write_stub "$BATS_TEST_TMPDIR/dprint-release/dprint" '#!/bin/sh' 'exit 0'
  (cd "$BATS_TEST_TMPDIR/dprint-release" && python3 -m zipfile -c "$RELEASES/dprint.zip" dprint)
}

# Mimics bats-core's source archive: install.sh lays out bin/ and libexec/ under a prefix.
function create_bats_archive() {
  local _name="bats-core-1.13.0"
  mkdir -p "$BATS_TEST_TMPDIR/$_name"
  write_stub "$BATS_TEST_TMPDIR/$_name/install.sh" \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'mkdir -p "$1/bin" "$1/libexec/bats-core"' \
    "printf '%s\\n' '#!/bin/sh' 'exit 0' >\"\$1/bin/bats\"" \
    'chmod 0755 "$1/bin/bats"' \
    "printf 'fake\\n' >\"\$1/libexec/bats-core/bats\""
  tar -czf "$RELEASES/bats-core.tar.gz" -C "$BATS_TEST_TMPDIR" "$_name"
}

function create_uv_installer() {
  write_fake_uv "$RELEASES/uv"
  write_stub "$RELEASES/uv_install.sh" \
    '#!/bin/sh' \
    'set -eu' \
    'mkdir -p "${UV_UNMANAGED_INSTALL:?}"' \
    "cp '$RELEASES/uv' \"\$UV_UNMANAGED_INSTALL/uv\""
}

function write_fake_uv() {
  /bin/cat >|"$1" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${UV_ARGS_FILE:?}"
case "${1:-} ${2:-}" in
  "python install") ;;
  "python find") printf '%s\n' "${FAKE_PYTHON:?}" ;;
  *) exit 2 ;;
esac
EOF
  chmod 0755 "$1"
}

# Mimics the agent-harness CLI surface the script relies on, including the
# behaviour verified against agent-harness 0.9.7: `install` renders every
# provider with the source shebang, replaces the Devin config, and writes the
# Hermes managed config without enabling it in config.yaml; the sync commands
# let generated keys win; `github-app-token refresh` writes the gh config.
function write_fake_agent_harness() {
  {
    printf '#!/usr/bin/env bash\n'
    printf 'readonly VERSION=%q\n' "$FAKE_AGENT_HARNESS_VERSION"
    printf 'readonly ENTRY_POINTS=(%s)\n' "${RENDERED_ENTRY_POINTS[*]}"
    /bin/cat <<'EOF'
set -euo pipefail
printf '%s\n' "$*" >>"${AGENT_HARNESS_ARGS_FILE:?}"

option_value() {
  local _flag="$1"
  shift
  while [[ "$#" -gt 1 ]]; do
    if [[ "$1" == "$_flag" ]]; then
      printf '%s\n' "$2"
      return 0
    fi
    shift
  done
  return 1
}

render() {
  local _prefix="$1" _entry
  for _entry in "${ENTRY_POINTS[@]}"; do
    mkdir -p "$(dirname "$_prefix/$_entry")"
    printf '%s\n' '#!/usr/bin/env -S python3 -IB' 'print("hook")' >|"$_prefix/$_entry"
    chmod 0755 "$_prefix/$_entry"
  done
  mkdir -p "$_prefix/.claude/hooks/lib" "$_prefix/.config/devin" "$_prefix/.hermes"
  printf '%s\n' '"""Shared policy."""' >|"$_prefix/.claude/hooks/lib/policy.py"
  printf '%s\n' '#!/usr/bin/env -S python3 -IB' >|"$_prefix/.claude/hooks/lib/not_executable.py"
  printf '%s\n' \
    '{"model":"fable","sandbox":{"enabled":true,"excludedCommands":["gh *","herdr *"],"network":{"allowedDomains":["api.day.app"]}}}' \
    >|"$_prefix/.claude/settings.json"
  printf '%s\n' '{"hooks":{"managed":true}}' >|"$_prefix/.config/devin/config.json"
  mkdir -p "$_prefix/.codex"
  write_codex_baseline "$_prefix/.codex/baseline.toml"
  merge_codex_config "$_prefix/.codex/baseline.toml" "$_prefix/.codex/config.toml"
  rm "$_prefix/.codex/baseline.toml"
  printf '%s\n' 'plugins:' '  enabled:' '    - agent-harness-hooks' >|"$_prefix/.hermes/managed-config.yaml"
}

write_codex_baseline() {
  printf '%s\n' \
    'model = "gpt"' \
    'developer_instructions = "be nice 😀 日本語"' \
    'created = 2026-01-02T03:04:05Z' \
    'shell_environment_policy = {}' \
    '' \
    '[permissions.guarded.filesystem]' \
    '"~/.codex/config.toml" = "read"' \
    '' \
    '[permissions.guarded.filesystem.":workspace_roots"]' \
    '"src" = "read"' \
    '' \
    '[plugins."documents@openai"]' \
    'enabled = true' \
    '' \
    '[[hooks]]' \
    'name = "first"' >|"$1"
}

# Like the real sync: the source owns what it names, and everything the user wrote
# below the marker line stays as written, comments included.
merge_codex_config() {
  local _source="$1" _target="$2" _user=""
  if [[ -f "$_target" ]]; then
    _user="$(sed -n '/^# user-config$/,$p' "$_target")"
  fi
  {
    /bin/cat "$_source"
    [[ -z "$_user" ]] || printf '\n%s\n' "$_user"
  } >|"$_target.new"
  mv "$_target.new" "$_target"
}

merge_json() {
  local _source="$1" _target="$2" _merged
  _merged="$(jq -s '.[1] + .[0]' "$_source" "$_target")"
  printf '%s\n' "$_merged" >|"$_target"
}

case "${1:-}" in
  --version)
    printf 'agent-harness %s\n' "$VERSION"
    ;;
  install)
    render "$(option_value --prefix "$@")"
    ;;
  sync-claude-settings | sync-devin-config)
    merge_json "$(option_value --source "$@")" "$(option_value --target "$@")"
    ;;
  generate-codex-config-source)
    write_codex_baseline "$(option_value --output "$@")"
    ;;
  sync-codex-config)
    merge_codex_config "$(option_value --source "$@")" "$(option_value --target "$@")"
    ;;
  sync-hermes-config)
    /bin/cat "$(option_value --source "$@")" >>"$(option_value --target "$@")"
    ;;
  github-app-token)
    config_dir="$(option_value --config-dir "$@")"
    mkdir -p "$config_dir"
    printf '%s\n' 'github.com:' '    oauth_token: fake' >|"$config_dir/hosts.yml"
    ;;
  verify)
    exit "${FAKE_VERIFY_STATUS:-0}"
    ;;
  *)
    exit 2
    ;;
esac
EOF
  } >|"$1"
  chmod 0755 "$1"
}
