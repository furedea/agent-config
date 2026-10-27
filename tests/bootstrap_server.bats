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

@test "installs Python 3.15.1 through uv by default" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  run /bin/cat "$UV_ARGS_FILE"
  [ "${lines[0]}" = "python install 3.15.1" ]
  [[ "$output" == *"python find"*"3.15.1"* ]]
}

@test "installs the requested Python through uv" {
  run bootstrap_server PYTHON_VERSION=3.16

  [ "$status" -eq 0 ]
  run /bin/cat "$UV_ARGS_FILE"
  [ "${lines[0]}" = "python install 3.16" ]
  [[ "$output" == *"python find"*"3.16"* ]]
}

@test "downloads the uv installer of the pinned version" {
  local _curl_log="$BATS_TEST_TMPDIR/curl-urls"
  mkdir -p "$BATS_TEST_TMPDIR/logging-curl"
  write_stub "$BATS_TEST_TMPDIR/logging-curl/curl" \
    '#!/bin/sh' \
    "printf '%s\\n' \"\$*\" >>'$_curl_log'" \
    'case "$*" in *astral.sh*) exit 22 ;; esac' \
    "exec '$(command -v curl)' \"\$@\""

  run bootstrap_server PATH="$BATS_TEST_TMPDIR/logging-curl:$SANDBOX_TOOLS_DIR:$PATH" UV_INSTALLER_URL=

  [ "$status" -ne 0 ]
  grep -Fq "https://astral.sh/uv/0.13.5/install.sh" "$_curl_log"
}

@test "stops when the installed uv is older than the pinned version" {
  run bootstrap_server FAKE_UV_VERSION=0.13.4

  [ "$status" -ne 0 ]
  [[ "$output" == *"0.13.4"*"0.13.5"* ]]
  [ ! -e "$UV_ARGS_FILE" ]
}

@test "stops when a kept uv is older than the pinned version" {
  run bootstrap_server
  [ "$status" -eq 0 ]

  run bootstrap_server FAKE_UV_VERSION=0.12.9 UV_INSTALLER_URL="file://$RELEASES/missing.sh"

  [ "$status" -ne 0 ]
  [[ "$output" == *"0.12.9"*"0.13.5"* ]]
}

@test "accepts a uv version with a local or pre-release suffix" {
  run bootstrap_server FAKE_UV_VERSION=0.13.5+local

  [ "$status" -eq 0 ]
}

@test "ignores UV_VERSION and PYTHON_VERSION leaking from the caller's environment" {
  UV_VERSION=9.9.9 PYTHON_VERSION=3.99 run bootstrap_server

  [ "$status" -eq 0 ]
  run /bin/cat "$UV_ARGS_FILE"
  [ "${lines[0]}" = "python install 3.15.1" ]
}

@test "accepts a uv newer than the pinned version" {
  run bootstrap_server FAKE_UV_VERSION=0.14.0

  [ "$status" -eq 0 ]
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
  [[ "$output" != *"bwrap"* ]]
  [[ "$output" != *"socat"* ]]
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
  [ "$(jq -r '.sandbox.network.allowedDomains[0]' "$HOME_DIR/.claude/settings.json")" = "pypi.org" ]
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
  [ "$(jq -c '.sandbox.network.allowedDomains' "$_settings")" = '["pypi.org","github.com","api.github.com"]' ]
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
    = '["read","write","write",{"src":"read",".":"write"},"deny"]' ]
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

@test "merges the Codex token settings into the generated workspace roots" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -c '.permissions.guarded.filesystem[":workspace_roots"]')" = '{"src":"read",".":"write"}' ]
}

@test "keeps the user's own Codex settings and comments" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  mkdir -p "$HOME_DIR/.codex"
  printf '%s\n' '# user-config' '# my note' '[projects."/srv"]' 'trust = "x" # inline' >|"$HOME_DIR/.codex/config.toml"

  run bootstrap_server

  [ "$status" -eq 0 ]
  grep -Fxq '# my note' "$HOME_DIR/.codex/config.toml"
  grep -Fxq 'trust = "x" # inline' "$HOME_DIR/.codex/config.toml"
  [ "$(codex_config_json | jq -r '.default_permissions')" = "guarded" ]
}

@test "keeps every generated Codex value across the token merge" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _codex
  _codex="$(codex_config_json)"
  [ "$(jq -r '.developer_instructions' <<<"$_codex")" = "be nice 😀 日本語" ]
  [ "$(jq -r '.created' <<<"$_codex")" = "2026-01-02T03:04:05Z" ]
  [ "$(jq -r '.plugins["documents@openai"].enabled' <<<"$_codex")" = "true" ]
  [ "$(jq -r '.hooks[0].name' <<<"$_codex")" = "first" ]
}

@test "produces the same Codex config on every run" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  run bootstrap_server
  [ "$status" -eq 0 ]
  cp "$HOME_DIR/.codex/config.toml" "$BATS_TEST_TMPDIR/first.toml"

  run bootstrap_server

  [ "$status" -eq 0 ]
  cmp "$BATS_TEST_TMPDIR/first.toml" "$HOME_DIR/.codex/config.toml"
}

@test "removes the Codex token settings once the host no longer names a GitHub App" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  run bootstrap_server
  [ "$status" -eq 0 ]
  write_host_env 'PYTHON_VERSION=3.16'

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -r '.default_permissions // "unset"')" = "unset" ]
  [ "$(codex_config_json | jq -c '.shell_environment_policy.set | keys')" = '["NVIM_LOG_FILE"]' ]
  [ "$(codex_config_json | jq -r '.permissions.guarded.network // "unset"')" = "unset" ]
}

@test "runs the Codex token merge with the managed Python" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  local _log="$BATS_TEST_TMPDIR/python-calls"
  write_stub "$BATS_TEST_TMPDIR/logging-python" '#!/bin/sh' \
    "printf '%s\\n' \"\$*\" >>'$_log'" \
    "exec '$(command -v python3)' \"\$@\""

  run bootstrap_server FAKE_PYTHON="$BATS_TEST_TMPDIR/logging-python"

  [ "$status" -eq 0 ]
  grep -Eq '^-I - ' "$_log"
}

@test "stops with a clear message when the managed Python cannot read TOML" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"
  write_stub "$BATS_TEST_TMPDIR/old-python" '#!/bin/sh' \
    'case "$*" in *tomllib*) exit 1 ;; esac' \
    "exec '$(command -v python3)' \"\$@\""

  run bootstrap_server FAKE_PYTHON="$BATS_TEST_TMPDIR/old-python" PYTHON_VERSION=3.10

  [ "$status" -ne 0 ]
  [[ "$output" == *"Python 3.11"*"PYTHON_VERSION"* ]]
  ! grep -Fq "github-app-token" "$AGENT_HARNESS_ARGS_FILE"
}

@test "leaves the Codex permissions alone when the host names no GitHub App" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -r '.default_permissions // "unset"')" = "unset" ]
  [ "$(codex_config_json | jq -c '.shell_environment_policy.set | keys')" = '["NVIM_LOG_FILE"]' ]
}

@test "keeps Neovim's log out of the working directory for Claude commands" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.env.NVIM_LOG_FILE' "$HOME_DIR/.claude/settings.json")" = "$HOME_DIR/.local/state/agent-harness/nvim.log" ]
  [ -d "$HOME_DIR/.local/state/agent-harness" ]
}

@test "keeps Neovim's log out of the working directory for Codex commands" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(codex_config_json | jq -r '.shell_environment_policy.set.NVIM_LOG_FILE')" = "$HOME_DIR/.local/state/agent-harness/nvim.log" ]
}

@test "keeps Neovim's log setting beside the GitHub token settings" {
  write_host_env 'AGENT_GITHUB_APP_ID=123' "AGENT_GITHUB_APP_PRIVATE_KEY=$HOME_DIR/app.pem"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.env.NVIM_LOG_FILE' "$HOME_DIR/.claude/settings.json")" = "$HOME_DIR/.local/state/agent-harness/nvim.log" ]
  [ "$(codex_config_json | jq -cS '.shell_environment_policy.set')" \
    = '{"GH_CONFIG_DIR":"'"$HOME_DIR"'/.config/agent-harness/gh","NVIM_LOG_FILE":"'"$HOME_DIR"'/.local/state/agent-harness/nvim.log"}' ]
}

@test "keeps Neovim's log setting over the host settings override" {
  mkdir -p "$HOME_DIR/.config/agent-config"
  printf '%s\n' '{"env":{"NVIM_LOG_FILE":"/elsewhere/nvim.log"}}' >|"$HOME_DIR/.config/agent-config/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [ "$(jq -r '.env.NVIM_LOG_FILE' "$HOME_DIR/.claude/settings.json")" = "$HOME_DIR/.local/state/agent-harness/nvim.log" ]
}

@test "leaves GitHub out of the sandbox when the host names no GitHub App" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  ! grep -Fq "github-app-token" "$AGENT_HARNESS_ARGS_FILE"
  [ "$(jq -c '.sandbox.network.allowedDomains' "$HOME_DIR/.claude/settings.json")" = '["pypi.org"]' ]
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

@test "prints a copy-paste command that appends the snippet when no profile sources it" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *"Add this line"* ]]
  [[ "$output" == *"printf '%s\\n' '. \"\$HOME/.config/agent-config/agent_env.sh\"' >> ~/.profile"* ]]
}

@test "stays quiet about the snippet when a profile already sources it" {
  local _snippet="$HOME_DIR/.config/agent-config/agent_env.sh"
  local _spelling
  for _spelling in ". \"$_snippet\"" "source $_snippet" '. "$HOME/.config/agent-config/agent_env.sh"' \
    'source "${HOME}/.config/agent-config/agent_env.sh"' '. ~/.config/agent-config/agent_env.sh'; do
    printf '%s\n' "$_spelling" >|"$HOME_DIR/.bashrc"

    run bootstrap_server

    [ "$status" -eq 0 ]
    ! [[ "$output" == *"Add this line"* ]] || {
      echo "hint printed for: $_spelling"
      return 1
    }
  done
}

@test "asks for the snippet when a profile quotes a path the shell would not expand" {
  local _spelling
  for _spelling in ". '~/.config/agent-config/agent_env.sh'" ". \"~/.config/agent-config/agent_env.sh\"" \
    ". '\$HOME/.config/agent-config/agent_env.sh'"; do
    printf '%s\n' "$_spelling" >|"$HOME_DIR/.bashrc"

    run bootstrap_server

    [ "$status" -eq 0 ]
    [[ "$output" == *"Add this line"* ]] || {
      echo "hint missing for: $_spelling"
      return 1
    }
  done
}

@test "appends to ~/.bash_profile when bash reads it instead of ~/.profile" {
  : >|"$HOME_DIR/.bash_profile"
  : >|"$HOME_DIR/.profile"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *">> ~/.bash_profile"* ]]
  [[ "$output" != *">> ~/.profile"* ]]
}

@test "appends to ~/.bash_login when it is the first profile bash reads" {
  : >|"$HOME_DIR/.bash_login"
  : >|"$HOME_DIR/.profile"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *">> ~/.bash_login"* ]]
}

@test "asks for the snippet when only a profile that bash skips sources it" {
  : >|"$HOME_DIR/.bash_profile"
  printf '%s\n' '. "$HOME/.config/agent-config/agent_env.sh"' >|"$HOME_DIR/.profile"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *"Add this line"* ]]
}

@test "stays quiet when the profile bash reads or ~/.bashrc sources the snippet" {
  local _file
  for _file in .bash_profile .bashrc; do
    : >|"$HOME_DIR/.bash_profile"
    : >|"$HOME_DIR/.bashrc"
    printf '%s\n' '. "$HOME/.config/agent-config/agent_env.sh"' >|"$HOME_DIR/$_file"

    run bootstrap_server

    [ "$status" -eq 0 ]
    [[ "$output" != *"Add this line"* ]] || {
      echo "hint printed with the snippet sourced from $_file"
      return 1
    }
  done
}

@test "detects a profile that sources the snippet without depending on grep" {
  printf '%s\n' '. "$HOME/.config/agent-config/agent_env.sh"' >|"$HOME_DIR/.profile"
  mkdir -p "$BATS_TEST_TMPDIR/failing-grep"
  write_stub "$BATS_TEST_TMPDIR/failing-grep/grep" '#!/bin/sh' 'exit 2'

  run bootstrap_server PATH="$BATS_TEST_TMPDIR/failing-grep:$PATH"

  [ "$status" -eq 0 ]
  [[ "$output" != *"Add this line"* ]]
}

@test "prints an append command that makes the next run quiet" {
  run bootstrap_server
  [ "$status" -eq 0 ]
  local _command
  _command="$(grep -F "printf '%s" <<<"$output" | sed 's/^ *//')"
  HOME="$HOME_DIR" run /bin/bash -c "$_command"
  [ "$status" -eq 0 ]

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" != *"Add this line"* ]]
}

@test "does not ask for the snippet when the legacy snippet is still sourced and gets replaced" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' '# old' >|"$HOME_DIR/.config/dotfiles/agent_env.sh"
  printf '%s\n' '. "$HOME/.config/dotfiles/agent_env.sh"' >|"$HOME_DIR/.profile"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" != *"Add this line"* ]]
  [[ "$output" == *"line 1 of $HOME_DIR/.profile still sources it"* ]]
}

@test "lists the profile change before the rm of the legacy snippet" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' '# old' >|"$HOME_DIR/.config/dotfiles/agent_env.sh"
  printf '%s\n' '. "$HOME/.config/dotfiles/agent_env.sh"' >|"$HOME_DIR/.profile"

  run bootstrap_server

  local _before_rm="${output%%rm -- *}"
  [[ "$_before_rm" == *"still sources it"* ]]
}

@test "still asks for the snippet when a profile only mentions it in a comment" {
  printf '%s\n' '# . "$HOME/.config/agent-config/agent_env.sh"' >|"$HOME_DIR/.profile"

  run bootstrap_server

  [[ "$output" == *"Add this line"* ]]
}

@test "prints nothing about profiles or legacy files when everything is already migrated" {
  printf '%s\n' '. "$HOME/.config/agent-config/agent_env.sh"' >|"$HOME_DIR/.profile"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" != *"Add this line"* ]]
  [[ "$output" != *"notice:"* ]]
}

@test "suggests the mv that moves each legacy host file into agent-config" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' "BIN_DIR=\"$BIN_DIR\"" >|"$HOME_DIR/.config/dotfiles/bootstrap_server.env"
  printf '%s\n' '{}' >|"$HOME_DIR/.config/dotfiles/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  local _legacy="$HOME_DIR/.config/dotfiles" _current="$HOME_DIR/.config/agent-config"
  [[ "$output" == *"mv -- $_legacy/bootstrap_server.env $_current/bootstrap_server.env"* ]]
  [[ "$output" == *"mv -- $_legacy/claude_settings_override.json $_current/claude_settings_override.json"* ]]
  [ -f "$_legacy/bootstrap_server.env" ]
}

@test "quotes a suggested mv so that a path with spaces is safe to paste" {
  mkdir -p "$HOME_DIR/my config/dotfiles"
  printf '%s\n' '{}' >|"$HOME_DIR/my config/dotfiles/claude_settings_override.json"

  run bootstrap_server XDG_CONFIG_HOME="$HOME_DIR/my config"

  [ "$status" -eq 0 ]
  [[ "$output" == *"mv -- ${HOME_DIR}/my\\ config/dotfiles/claude_settings_override.json "* ]]
}

@test "does not suggest mv over a host file that already exists in agent-config" {
  mkdir -p "$HOME_DIR/.config/dotfiles" "$HOME_DIR/.config/agent-config"
  printf '%s\n' '{"old":true}' >|"$HOME_DIR/.config/dotfiles/claude_settings_override.json"
  printf '%s\n' '{"new":true}' >|"$HOME_DIR/.config/agent-config/claude_settings_override.json"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" != *"mv -- "* ]]
  [[ "$output" == *"$HOME_DIR/.config/dotfiles/claude_settings_override.json is ignored"* ]]
  [[ "$output" == *"already reads $HOME_DIR/.config/agent-config/claude_settings_override.json"* ]]
  [[ "$output" == *"rm -- $HOME_DIR/.config/dotfiles/claude_settings_override.json"* ]]
  [[ "$output" == *"mv -f -- $HOME_DIR/.config/dotfiles/claude_settings_override.json $HOME_DIR/.config/agent-config/claude_settings_override.json"* ]]
  [ -f "$HOME_DIR/.config/dotfiles/claude_settings_override.json" ]
}

@test "suggests the rm of the legacy snippet" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' '# old' >|"$HOME_DIR/.config/dotfiles/agent_env.sh"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *"rm -- $HOME_DIR/.config/dotfiles/agent_env.sh"* ]]
  [[ "$output" != *"still sources it"* ]]
  [ -f "$HOME_DIR/.config/dotfiles/agent_env.sh" ]
}

@test "names the profile line that still sources the legacy snippet" {
  mkdir -p "$HOME_DIR/.config/dotfiles"
  printf '%s\n' '# old' >|"$HOME_DIR/.config/dotfiles/agent_env.sh"
  printf '%s\n' 'export A=1' '. "$HOME/.config/dotfiles/agent_env.sh"' >|"$HOME_DIR/.bashrc"

  run bootstrap_server

  [ "$status" -eq 0 ]
  [[ "$output" == *"line 2 of $HOME_DIR/.bashrc still sources it"* ]]
  [[ "$output" == *'. "$HOME/.config/agent-config/agent_env.sh"'* ]]
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
  [ -f "$_snippet" ]
  run env -i PATH=/usr/bin:/bin /bin/bash -c "source '$_snippet' && command -v rg"
  [ "$status" -eq 0 ]
  [ "$output" = "$BIN_DIR/rg" ]
}

@test "exports the Devin permission mode from the shell snippet" {
  run bootstrap_server

  [ "$status" -eq 0 ]
  local _snippet="$HOME_DIR/.config/agent-config/agent_env.sh"
  run env -i PATH=/usr/bin:/bin /bin/bash -c "source '$_snippet' && printenv DEVIN_PERMISSION_MODE"
  [ "$status" -eq 0 ]
  [ "$output" = "smart" ]
}

@test "prints usage for --help" {
  run /bin/bash "$SCRIPT" --help

  [ "$status" -eq 1 ]
  [[ "$output" == *"Usage:"* ]]
}
