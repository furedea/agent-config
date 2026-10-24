#!/usr/bin/env bats
# Executable specifications for deploying the agent harness on servers without Nix.

bats_require_minimum_version 1.5.0

setup() {
  load test-helper/setup
  SCRIPT="$REPO_ROOT/scripts/bootstrap_server.sh"
  create_bootstrap_server_fixtures
}

# ============================================================
# Tool installation
# ============================================================

@test "installs the pinned user-space tools into the binary directory" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _tool
  for _tool in agent-harness shfmt rg jq ruff dprint shellcheck bats uv; do
    [ -x "$BIN_DIR/$_tool" ] || {
      echo "missing tool: $_tool"
      return 1
    }
  done
}

@test "reuses installed tools without downloading again" {
  run bootstrap_server
  [ "$status" -eq 0 ]

  run bootstrap_server \
    AGENT_HARNESS_URL="file://$RELEASES/missing.tar.xz" \
    SHFMT_URL="file://$RELEASES/missing" \
    RIPGREP_URL="file://$RELEASES/missing.tar.gz" \
    JQ_URL="file://$RELEASES/missing" \
    RUFF_URL="file://$RELEASES/missing.tar.gz" \
    DPRINT_URL="file://$RELEASES/missing.zip" \
    SHELLCHECK_URL="file://$RELEASES/missing.tar.xz" \
    BATS_URL="file://$RELEASES/missing.tar.gz" \
    UV_INSTALLER_URL="file://$RELEASES/missing.sh"

  [ "$status" -eq 0 ]
}

@test "replaces an installed agent-harness of another version" {
  run bootstrap_server
  [ "$status" -eq 0 ]

  run bootstrap_server AGENT_HARNESS_VERSION=10.0.0 AGENT_HARNESS_URL="file://$RELEASES/missing.tar.xz"

  [ "$status" -ne 0 ]
  [[ "$output" == *"missing.tar.xz"* ]]
}

@test "downloads agent-harness from its release tag" {
  local _curl_log="$BATS_TEST_TMPDIR/curl-urls"
  mkdir -p "$BATS_TEST_TMPDIR/logging-curl"
  write_stub "$BATS_TEST_TMPDIR/logging-curl/curl" \
    '#!/bin/sh' \
    "printf '%s\\n' \"\$*\" >>'$_curl_log'" \
    'exit 22'

  run bootstrap_server PATH="$BATS_TEST_TMPDIR/logging-curl:$SANDBOX_TOOLS_DIR:$PATH" AGENT_HARNESS_URL=

  [ "$status" -ne 0 ]
  grep -Fq "releases/download/agent-harness-v$FAKE_AGENT_HARNESS_VERSION/agent-harness-x86_64-unknown-linux-musl.tar.xz" "$_curl_log"
}

@test "refuses an agent-harness archive that does not match its release checksum" {
  printf '%064d *agent-harness.tar.xz\n' 0 >|"$RELEASES/agent-harness.tar.xz.sha256"

  run bootstrap_server

  [ "$status" -ne 0 ]
  [[ "$output" == *"checksum"* ]]
  [ ! -e "$BIN_DIR/agent-harness" ]
}

@test "installs bats-core under its own prefix and links it into the binary directory" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _prefix="$HOME_DIR/.local/share/bats-core"
  [ "$(readlink "$BIN_DIR/bats")" = "$_prefix/bin/bats" ]
  [ -f "$_prefix/libexec/bats-core/bats" ]
}

@test "installs the requested Python through uv" {
  run bootstrap_server PYTHON_VERSION=3.15

  [ "$status" -eq 0 ]
  run /bin/cat "$UV_ARGS_FILE"
  [ "${lines[0]}" = "python install 3.15" ]
  [[ "$output" == *"python find"*"3.15"* ]]
}

@test "refuses machines without release binaries before downloading anything" {
  run bootstrap_server BOOTSTRAP_SERVER_MACHINE=aarch64

  [ "$status" -ne 0 ]
  [[ "$output" == *"aarch64"* ]]
  [[ "$output" == *"cargo install"* ]]
  [ ! -e "$BIN_DIR" ]
}

# ============================================================
# Linux sandbox components
# ============================================================

@test "stays quiet when bubblewrap and socat are installed" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  ! [[ "$output" == *"bwrap"* ]]
  ! [[ "$output" == *"socat"* ]]
}

@test "warns about missing bubblewrap and socat without stopping" {
  run bootstrap_server PATH="$(path_without_sandbox_tools)"

  [ "$status" -eq 0 ]
  [[ "$output" == *"warning"*"bwrap"* ]]
  [[ "$output" == *"warning"*"socat"* ]]
  [ -x "$BIN_DIR/agent-harness" ]
}

# ============================================================
# Harness rendering
# ============================================================

@test "renders the repository harness into the home directory and verifies it" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  run /bin/cat "$AGENT_HARNESS_ARGS_FILE"
  [[ "$output" == *"install --source $REPO_ROOT/agents --prefix $HOME_DIR"* ]]
  [[ "$output" == *"verify --source $REPO_ROOT/agents --prefix $HOME_DIR"* ]]
}

@test "pins the shebang of every rendered executable to the managed interpreter" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _entry
  for _entry in "${RENDERED_ENTRY_POINTS[@]}"; do
    [ -x "$HOME_DIR/$_entry" ]
    [ "$(head -n 1 "$HOME_DIR/$_entry")" = "#!$FAKE_PYTHON -IB" ] || {
      echo "shebang not pinned: $_entry"
      return 1
    }
  done
  [ "$(head -n 1 "$HOME_DIR/.claude/hooks/lib/policy.py")" = '"""Shared policy."""' ]
  [ "$(head -n 1 "$HOME_DIR/.claude/hooks/lib/not_executable.py")" = '#!/usr/bin/env -S python3 -IB' ]
}

@test "preserves settings Claude Code added while generated keys win" {
  mkdir -p "$HOME_DIR/.claude"
  printf '%s\n' '{"model":"stale","permissions":{"allow":["Bash(ls)"]}}' >|"$HOME_DIR/.claude/settings.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.model' "$HOME_DIR/.claude/settings.json")" = "fable" ]
  [ "$(jq -r '.permissions.allow[0]' "$HOME_DIR/.claude/settings.json")" = "Bash(ls)" ]
}

@test "preserves keys Devin added to its config while generated keys win" {
  mkdir -p "$HOME_DIR/.config/devin"
  printf '%s\n' '{"hooks":{"stale":true},"theme":"dark"}' >|"$HOME_DIR/.config/devin/config.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.theme' "$HOME_DIR/.config/devin/config.json")" = "dark" ]
  [ "$(jq -r '.hooks.managed' "$HOME_DIR/.config/devin/config.json")" = "true" ]
}

@test "keeps a Devin config it cannot sync and fails" {
  mkdir -p "$HOME_DIR/.config/devin"
  printf '%s\n' '{"theme":"dark",}' >|"$HOME_DIR/.config/devin/config.json"

  run bootstrap_server

  [ "$status" -ne 0 ]
  [ "$(cat "$HOME_DIR/.config/devin/config.json")" = '{"theme":"dark",}' ]
}

@test "enables the Hermes hook plugin in the Hermes config while keeping its keys" {
  mkdir -p "$HOME_DIR/.hermes"
  printf '%s\n' 'model: user-model' >|"$HOME_DIR/.hermes/config.yaml"

  run bootstrap_server

  [ "$status" -eq 0 ]
  grep -Fxq 'model: user-model' "$HOME_DIR/.hermes/config.yaml"
  grep -Fq 'agent-harness-hooks' "$HOME_DIR/.hermes/config.yaml"
}

@test "applies the host settings override after rendering" {
  mkdir -p "$HOME_DIR/.config/agent-config"
  printf '%s\n' '{"sandbox":{"enabled":false}}' >|"$HOME_DIR/.config/agent-config/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.sandbox.enabled' "$HOME_DIR/.claude/settings.json")" = "false" ]
  [ "$(jq -r '.sandbox.network.allowedDomains[0]' "$HOME_DIR/.claude/settings.json")" = "api.day.app" ]
  [ "$(jq -r '.model' "$HOME_DIR/.claude/settings.json")" = "fable" ]
}

@test "fails when the harness verification fails" {
  run bootstrap_server FAKE_VERIFY_STATUS=3

  [ "$status" -ne 0 ]
  grep -Fq "verify --source" "$AGENT_HARNESS_ARGS_FILE"
}

# ============================================================
# Agent GitHub token
# ============================================================

@test "mints the agent GitHub token when the host names a GitHub App" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _config_dir="$HOME_DIR/.config/agent-harness/gh"
  grep -Fq "github-app-token refresh --app-id 123 --private-key $HOME_DIR/app.pem --config-dir $_config_dir" \
    "$AGENT_HARNESS_ARGS_FILE"
  [ -f "$_config_dir/hosts.yml" ]
  [[ "$output" == *"crontab"*"github-app-token refresh"* ]]
}

@test "lets Claude Code reach GitHub with the agent token and hides the App key" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _settings="$HOME_DIR/.claude/settings.json"
  [ "$(jq -r '.env.GH_CONFIG_DIR' "$_settings")" = "$HOME_DIR/.config/agent-harness/gh" ]
  [ "$(jq -c '.sandbox.network.allowedDomains' "$_settings")" = '["api.day.app","github.com","api.github.com"]' ]
  [ "$(jq -r '.sandbox.enableWeakerNetworkIsolation' "$_settings")" = "true" ]
  [ "$(jq -c '.sandbox.excludedCommands' "$_settings")" = '["herdr *"]' ]
  [ "$(jq -r '.permissions.deny | index("Read(/'"$HOME_DIR"'/app.pem)") != null' "$_settings")" = "true" ]
  [ "$(jq -r '.sandbox.filesystem.denyRead | index("'"$HOME_DIR"'/app.pem") != null' "$_settings")" = "true" ]
}

@test "keeps GitHub access and the App key denial over the host settings override" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  printf '%s\n' '{"permissions":{"deny":["Read(~/notes)"]},"sandbox":{"network":{"allowedDomains":["example.com"]},"filesystem":{"denyRead":["~/notes"]}}}' \
    >|"$HOME_DIR/.config/agent-config/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _settings="$HOME_DIR/.claude/settings.json"
  [ "$(jq -c '.sandbox.network.allowedDomains' "$_settings")" = '["example.com","github.com","api.github.com"]' ]
  [ "$(jq -c '.permissions.deny' "$_settings")" = '["Read(~/notes)","Read(/'"$HOME_DIR"'/app.pem)"]' ]
  [ "$(jq -c '.sandbox.filesystem.denyRead' "$_settings")" = '["~/notes","'"$HOME_DIR"'/app.pem"]' ]
}

@test "points Codex shell commands at the agent token and lets its sandbox reach GitHub" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _codex
  _codex="$(codex_config_json)"
  [ "$(jq -r '.shell_environment_policy.set.GH_CONFIG_DIR' <<<"$_codex")" = "$HOME_DIR/.config/agent-harness/gh" ]
  [ "$(jq -r '.default_permissions' <<<"$_codex")" = "guarded" ]
  [ "$(jq -r '.permissions.guarded.network.enabled' <<<"$_codex")" = "true" ]
  [ "$(jq -c '.permissions.guarded.filesystem | [.[":root"], .[":tmpdir"], .[":slash_tmp"], .[":workspace_roots"], .["~/.config/gh/hosts.yml"]]' <<<"$_codex")" \
    = '["read","write","write",{".":"write"},"deny"]' ]
  [ "$(jq -r '.permissions.guarded.filesystem["~/.codex/config.toml"]' <<<"$_codex")" = "read" ]
  [ "$(jq -r '.model' <<<"$_codex")" = "gpt" ]
}

@test "lets Codex write the cache directories Claude may write and hides the App key" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  printf '%s\n' '{"sandbox":{"filesystem":{"allowWrite":["~/.cache/uv","/var/cache/tools","relative/dir"]}}}' \
    >|"$HOME_DIR/.config/agent-config/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _filesystem
  _filesystem="$(codex_config_json | jq -c '.permissions.guarded.filesystem')"
  [ "$(jq -r '.["~/.cache/uv"]' <<<"$_filesystem")" = "write" ]
  [ "$(jq -r '.["/var/cache/tools"]' <<<"$_filesystem")" = "write" ]
  [ "$(jq -r 'has("relative/dir")' <<<"$_filesystem")" = "false" ]
  [ "$(jq -r '.["'"$HOME_DIR"'/app.pem"]' <<<"$_filesystem")" = "deny" ]
}

@test "applies the Codex token settings again on a repeated run" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  run bootstrap_server
  [ "$status" -eq 0 ]

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -r '.shell_environment_policy.set.GH_CONFIG_DIR')" = "$HOME_DIR/.config/agent-harness/gh" ]
}

@test "leaves the Codex config alone when the host names no GitHub App" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -r '.default_permissions // "unset"')" = "unset" ]
  [ "$(codex_config_json | jq -c '.shell_environment_policy')" = "{}" ]
}

@test "leaves GitHub out of the sandbox when the host names no GitHub App" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  ! grep -Fq "github-app-token" "$AGENT_HARNESS_ARGS_FILE"
  [ "$(jq -c '.sandbox.network.allowedDomains' "$HOME_DIR/.claude/settings.json")" = '["api.day.app"]' ]
  [ "$(jq -r '.env.GH_CONFIG_DIR // "unset"' "$HOME_DIR/.claude/settings.json")" = "unset" ]
}

@test "refuses a GitHub App without its private key before downloading anything" {
  write_host_env 'AGENT_GITHUB_APP_ID=123'

  run bootstrap_server

  [ "$status" -ne 0 ]
  [[ "$output" == *"AGENT_GITHUB_APP_PRIVATE_KEY"* ]]
  [ ! -e "$BIN_DIR" ]
}

# ============================================================
# Host-specific locations
# ============================================================

@test "loads host locations from the agent-config config directory" {
  write_host_env "BIN_DIR=\"$BATS_TEST_TMPDIR/tools\""

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ -x "$BATS_TEST_TMPDIR/tools/agent-harness" ]
  [ ! -e "$BIN_DIR" ]
}

@test "reads the legacy dotfiles config directory and asks to move it" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' "BIN_DIR=\"$BATS_TEST_TMPDIR/tools\"" >|"$HOME_DIR/.config/dotfiles/bootstrap_server.env"
  printf '%s\n' '{"sandbox":{"enabled":false}}' >|"$HOME_DIR/.config/dotfiles/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ -x "$BATS_TEST_TMPDIR/tools/agent-harness" ]
  [ "$(jq -r '.sandbox.enabled' "$HOME_DIR/.claude/settings.json")" = "false" ]
  [[ "$output" == *"$HOME_DIR/.config/dotfiles"*"$HOME_DIR/.config/agent-config"* ]]
  [ -f "$HOME_DIR/.config/agent-config/agent_env.sh" ]
}

@test "refuses a relocated hook state directory before downloading anything" {
  write_host_env "XDG_STATE_HOME=\"$BATS_TEST_TMPDIR/state\""

  run bootstrap_server

  [ "$status" -ne 0 ]
  [[ "$output" == *"XDG_STATE_HOME"* ]]
  [ ! -e "$BIN_DIR" ]
}

@test "writes a shell snippet that puts the tools on PATH" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _snippet="$HOME_DIR/.config/agent-config/agent_env.sh"
  [[ "$output" == *"$_snippet"* ]]
  run env -i PATH=/usr/bin:/bin /bin/bash -c "source '$_snippet' && command -v rg"
  [ "$status" -eq 0 ]
  [ "$output" = "$BIN_DIR/rg" ]
}

@test "exports the shared agent environment from the shell snippet" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _snippet="$HOME_DIR/.config/agent-config/agent_env.sh" _expected
  _expected="$(jq -er '.DEVIN_PERMISSION_MODE' "$REPO_ROOT/agent_environment.json")"
  run env -i PATH=/usr/bin:/bin /bin/bash -c "source '$_snippet' && printenv DEVIN_PERMISSION_MODE"
  [ "$status" -eq 0 ]
  [ "$output" = "$_expected" ]
}

@test "prints usage for --help" {
  run /bin/bash "$SCRIPT" --help

  [ "$status" -eq 1 ]
  [[ "$output" == *"Usage:"* ]]
}
