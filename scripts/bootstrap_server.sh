#!/usr/bin/env bash
set -euCo pipefail

function usage() {
  cat <<EOF >&2
Description:
    Deploy the agents/ harness on a Linux server without Nix. Installs pinned
    user-space release binaries and a uv-managed Python under the home
    directory, renders the harness with agent-harness, pins hook shebangs to
    that interpreter, and writes a shell snippet for the login shell.

Usage:
    $0

Options:
    --help, -h: print this

Host-specific settings, from the environment or
\$XDG_CONFIG_HOME/agent-config/bootstrap_server.env:
    BIN_DIR                        user-space binaries (default: ~/.local/bin)
    BATS_PREFIX                    bats-core installation (default: ~/.local/share/bats-core)
    PYTHON_VERSION                 uv-managed interpreter (default: 3.15.1)
    UV_PYTHON_INSTALL_DIR          interpreter location (uv default: ~/.local/share/uv/python)
    UV_CACHE_DIR                   uv cache (uv default: ~/.cache/uv)
    XDG_CACHE_HOME                 hook cache (default: ~/.cache)
    AGENT_GITHUB_APP_ID            GitHub App that mints the agent GitHub token (optional)
    AGENT_GITHUB_APP_PRIVATE_KEY   absolute path of that App's private key
    AGENT_GITHUB_APP_INSTALLATION_ID
                                   App installation (default: the App's only installation)

Hook state stays in ~/.local/state, the location the Claude Code sandbox lets hooks write.
EOF
  exit 1
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly REPO_ROOT
readonly HARNESS_PREFIX="${HOME:?}"
readonly CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
readonly CONFIG_DIR="$CONFIG_HOME/agent-config"
# TODO: Stop reading the dotfiles location after the release that introduced CONFIG_DIR.
readonly LEGACY_CONFIG_DIR="$CONFIG_HOME/dotfiles"
readonly ENV_SNIPPET="$CONFIG_DIR/agent_env.sh"
readonly SOURCE_SHEBANG="#!/usr/bin/env -S python3"
readonly DEFAULT_STATE_HOME="$HOME/.local/state"
readonly AGENT_GITHUB_TOKEN_CONFIG_DIR="$CONFIG_HOME/agent-harness/gh"
readonly CLAUDE_SETTINGS="$HARNESS_PREFIX/.claude/settings.json"
readonly CODEX_CONFIG="$HARNESS_PREFIX/.codex/config.toml"
# Neovim cannot write its default log under the sandbox, so it would leave nvim.log in the working directory.
readonly NVIM_LOG_FILE_PATH="$DEFAULT_STATE_HOME/agent-harness/nvim.log"

# Prints the agent-config location of a host file, or the legacy one while only that exists.
function host_config_file() {
  local _name="$1"
  if [[ ! -e "$CONFIG_DIR/$_name" && -e "$LEGACY_CONFIG_DIR/$_name" ]]; then
    printf '%s\n' "$LEGACY_CONFIG_DIR/$_name"
  else
    printf '%s\n' "$CONFIG_DIR/$_name"
  fi
}

HOST_ENV_FILE="${BOOTSTRAP_SERVER_ENV:-$(host_config_file bootstrap_server.env)}"
readonly HOST_ENV_FILE
CLAUDE_SETTINGS_OVERRIDE="${CLAUDE_SETTINGS_OVERRIDE:-$(host_config_file claude_settings_override.json)}"
readonly CLAUDE_SETTINGS_OVERRIDE

function load_host_env() {
  [[ -f "$HOST_ENV_FILE" ]] || return 0
  set -a
  # shellcheck source=/dev/null
  source "$HOST_ENV_FILE"
  set +a
}
load_host_env

readonly BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
readonly PYTHON_VERSION="${PYTHON_VERSION:-3.15.1}"
MACHINE="${BOOTSTRAP_SERVER_MACHINE:-$(uname -m)}"
readonly MACHINE
# Renovate updates the versions below from the release named on each comment.
# renovate: datasource=github-releases depName=furedea/agent-harness extractVersion=^agent-harness-v(?<version>.+)$
readonly AGENT_HARNESS_VERSION="${AGENT_HARNESS_VERSION:-0.9.7}"
# renovate: datasource=github-releases depName=mvdan/sh extractVersion=^v(?<version>.+)$
readonly SHFMT_VERSION="${SHFMT_VERSION:-3.13.1}"
# renovate: datasource=github-releases depName=BurntSushi/ripgrep
readonly RIPGREP_VERSION="${RIPGREP_VERSION:-14.1.1}"
# renovate: datasource=github-releases depName=jqlang/jq extractVersion=^jq-(?<version>.+)$
readonly JQ_VERSION="${JQ_VERSION:-1.8.1}"
# renovate: datasource=github-releases depName=astral-sh/ruff
readonly RUFF_VERSION="${RUFF_VERSION:-0.17.0}"
# renovate: datasource=github-releases depName=dprint/dprint
readonly DPRINT_VERSION="${DPRINT_VERSION:-0.64.1}"
# renovate: datasource=github-releases depName=koalaman/shellcheck extractVersion=^v(?<version>.+)$
readonly SHELLCHECK_VERSION="${SHELLCHECK_VERSION:-0.11.0}"
# renovate: datasource=github-releases depName=bats-core/bats-core extractVersion=^v(?<version>.+)$
readonly BATS_VERSION="${BATS_VERSION:-1.13.0}"
readonly BATS_PREFIX="${BATS_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/bats-core}"
# Older uv cannot install the managed CPython this script requests.
# renovate: datasource=github-releases depName=astral-sh/uv
readonly UV_VERSION="${UV_VERSION:-0.13.5}"
readonly UV_INSTALLER_URL="${UV_INSTALLER_URL:-https://astral.sh/uv/${UV_VERSION}/install.sh}"
readonly AGENT_HARNESS_URL="${AGENT_HARNESS_URL:-https://github.com/furedea/agent-harness/releases/download/agent-harness-v${AGENT_HARNESS_VERSION}/agent-harness-x86_64-unknown-linux-musl.tar.xz}"
readonly SHFMT_URL="${SHFMT_URL:-https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_linux_amd64}"
readonly RIPGREP_URL="${RIPGREP_URL:-https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep-${RIPGREP_VERSION}-x86_64-unknown-linux-musl.tar.gz}"
readonly JQ_URL="${JQ_URL:-https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-amd64}"
readonly RUFF_URL="${RUFF_URL:-https://github.com/astral-sh/ruff/releases/download/${RUFF_VERSION}/ruff-x86_64-unknown-linux-musl.tar.gz}"
readonly DPRINT_URL="${DPRINT_URL:-https://github.com/dprint/dprint/releases/download/${DPRINT_VERSION}/dprint-x86_64-unknown-linux-musl.zip}"
readonly SHELLCHECK_URL="${SHELLCHECK_URL:-https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}/shellcheck-v${SHELLCHECK_VERSION}.linux.x86_64.tar.xz}"
readonly BATS_URL="${BATS_URL:-https://github.com/bats-core/bats-core/archive/refs/tags/v${BATS_VERSION}.tar.gz}"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bootstrap_server.XXXXXX")"
readonly WORK_DIR
trap 'rm -rf "$WORK_DIR"' EXIT

function main() {
  [[ "$#" -eq 0 ]] || usage
  require_release_binaries
  require_default_state_home
  require_complete_github_app
  mkdir -p "$BIN_DIR" "$CONFIG_DIR"
  install_agent_harness
  install_tool shfmt "$SHFMT_URL"
  install_tool rg "$RIPGREP_URL" rg
  install_tool jq "$JQ_URL"
  install_tool ruff "$RUFF_URL" ruff
  install_tool shellcheck "$SHELLCHECK_URL" shellcheck
  install_bats
  install_uv
  local _python
  _python="$(install_python)"
  install_dprint "$_python"
  render_harness
  pin_python_shebangs "$_python"
  apply_claude_settings_override
  require_toml_python "$_python"
  configure_nvim_log_file
  configure_agent_github_token
  render_codex_config "$_python"
  write_env_snippet
  verify_harness
  warn_missing_sandbox_tools
  report_legacy_config_dir
}

function require_release_binaries() {
  [[ "$MACHINE" == x86_64 ]] && return 0
  cat <<EOF >&2
Release binaries are published only for x86_64 Linux; this machine is $MACHINE.
Build agent-harness from source instead:
    cargo install --locked --git https://github.com/furedea/agent-harness agent-harness
EOF
  exit 1
}

# The Claude Code sandbox lets hooks write their state only under the default location.
function require_default_state_home() {
  [[ -z "${XDG_STATE_HOME:-}" || "$XDG_STATE_HOME" == "$DEFAULT_STATE_HOME" ]] && return 0
  printf 'XDG_STATE_HOME=%s is unsupported: hooks keep their state in %s, which the sandbox lets them write.\n' \
    "$XDG_STATE_HOME" "$DEFAULT_STATE_HOME" >&2
  exit 1
}

function require_complete_github_app() {
  [[ -z "${AGENT_GITHUB_APP_ID:-}" ]] && return 0
  [[ "${AGENT_GITHUB_APP_PRIVATE_KEY:-}" == /* ]] && return 0
  printf 'AGENT_GITHUB_APP_ID needs AGENT_GITHUB_APP_PRIVATE_KEY set to the absolute path of the App private key.\n' >&2
  exit 1
}

# agent-harness renders this repository, so an installed binary of another version is replaced.
function install_agent_harness() {
  local _binary="$BIN_DIR/agent-harness"
  if [[ -x "$_binary" && "$("$_binary" --version)" == "agent-harness $AGENT_HARNESS_VERSION" ]]; then
    printf 'keep %s\n' "$_binary"
    return 0
  fi
  local _download="$WORK_DIR/agent-harness.download"
  download "$AGENT_HARNESS_URL" "$_download"
  require_release_checksum "$AGENT_HARNESS_URL" "$_download"
  install -m 0755 "$(extract_member "$_download" agent-harness)" "$_binary"
  printf 'install %s\n' "$_binary"
}

# The checksum shares the archive's origin: it catches a damaged download, not a forged release.
function require_release_checksum() {
  local _url="$1" _download="$2" _expected _asset _actual
  download "$_url.sha256" "$WORK_DIR/release.sha256"
  read -r _expected _asset <"$WORK_DIR/release.sha256"
  _actual="$(sha256sum "$_download")"
  [[ "${_actual%% *}" == "$_expected" ]] && return 0
  printf 'checksum mismatch for %s\n' "$_url" >&2
  exit 1
}

# Installs a release binary, or the named member of a release archive, into BIN_DIR.
function install_tool() {
  local _name="$1" _url="$2" _member="${3:-}"
  if [[ -x "$BIN_DIR/$_name" ]]; then
    printf 'keep %s\n' "$BIN_DIR/$_name"
    return 0
  fi
  local _download="$WORK_DIR/$_name.download"
  download "$_url" "$_download"
  if [[ -n "$_member" ]]; then
    _download="$(extract_member "$_download" "$_member")"
  fi
  install -m 0755 "$_download" "$BIN_DIR/$_name"
  printf 'install %s\n' "$BIN_DIR/$_name"
}

function download() {
  local _url="$1" _destination="$2"
  curl --retry 3 --retry-delay 2 -fsSL "$_url" -o "$_destination"
}

function extract_member() {
  local _archive="$1" _member="$2"
  printf '%s/%s\n' "$(extract_archive "$_archive")" "$_member"
}

function extract_archive() {
  local _archive="$1" _directory
  _directory="$(mktemp -d "$WORK_DIR/extract.XXXXXX")"
  tar -xf "$_archive" -C "$_directory" --strip-components=1
  printf '%s\n' "$_directory"
}

# dprint ships a zip archive, which tar cannot read; Python's zipfile module can.
function install_dprint() {
  local _python="$1"
  if [[ -x "$BIN_DIR/dprint" ]]; then
    printf 'keep %s\n' "$BIN_DIR/dprint"
    return 0
  fi
  local _download="$WORK_DIR/dprint.download" _directory
  download "$DPRINT_URL" "$_download"
  _directory="$(mktemp -d "$WORK_DIR/extract.XXXXXX")"
  "$_python" -m zipfile -e "$_download" "$_directory"
  install -m 0755 "$_directory/dprint" "$BIN_DIR/dprint"
  printf 'install %s\n' "$BIN_DIR/dprint"
}

# bats-core is plain Bash; its installer lays out bin/ and libexec/ under one prefix.
function install_bats() {
  if [[ -x "$BIN_DIR/bats" ]]; then
    printf 'keep %s\n' "$BIN_DIR/bats"
    return 0
  fi
  local _download="$WORK_DIR/bats.download" _source
  download "$BATS_URL" "$_download"
  _source="$(extract_archive "$_download")"
  bash "$_source/install.sh" "$BATS_PREFIX" >/dev/null
  ln -sf "$BATS_PREFIX/bin/bats" "$BIN_DIR/bats"
  printf 'install %s\n' "$BIN_DIR/bats"
}

function install_uv() {
  if [[ -x "$BIN_DIR/uv" ]]; then
    printf 'keep %s\n' "$BIN_DIR/uv"
  else
    download "$UV_INSTALLER_URL" "$WORK_DIR/uv_install.sh"
    UV_UNMANAGED_INSTALL="$BIN_DIR" sh "$WORK_DIR/uv_install.sh"
    printf 'install %s\n' "$BIN_DIR/uv"
  fi
  require_uv_version
}

# An installed uv is never replaced, so one older than the pin stops the run.
function require_uv_version() {
  local _output _found
  _output="$("$BIN_DIR/uv" --version)"
  _found="${_output#uv }"
  _found="${_found%% *}"
  _found="${_found%%[!0-9.]*}"
  version_at_least "$_found" "$UV_VERSION" && return 0
  printf '%s is uv %s, but %s or newer is required; remove it and run again.\n' \
    "$BIN_DIR/uv" "$_found" "$UV_VERSION" >&2
  exit 1
}

# Compares dotted numeric versions field by field.
function version_at_least() {
  local -a _found _required
  IFS=. read -ra _found <<<"$1"
  IFS=. read -ra _required <<<"$2"
  local _index _have _need
  for _index in "${!_required[@]}"; do
    _have="${_found[_index]:-0}"
    _need="${_required[_index]}"
    ((_have == _need)) && continue
    ((_have > _need))
    return
  done
}

# Prints the absolute path of the managed interpreter.
function install_python() {
  "$BIN_DIR/uv" python install "$PYTHON_VERSION" >&2
  "$BIN_DIR/uv" python find --managed-python "$PYTHON_VERSION"
}

# Runs the same syncs as the agent-harness Home Manager module: `install` replaces the
# Devin config and leaves the Hermes config alone, while the agents edit both at runtime.
function render_harness() {
  local _devin_config="$HARNESS_PREFIX/.config/devin/config.json"
  stash_runtime_config "$CLAUDE_SETTINGS"
  stash_runtime_config "$_devin_config"
  "$BIN_DIR/agent-harness" install --source "$REPO_ROOT/agents" --prefix "$HARNESS_PREFIX"
  sync_runtime_config sync-claude-settings "$CLAUDE_SETTINGS"
  sync_runtime_config sync-devin-config "$_devin_config"
  "$BIN_DIR/agent-harness" sync-hermes-config \
    --source "$HARNESS_PREFIX/.hermes/managed-config.yaml" \
    --target "$HARNESS_PREFIX/.hermes/config.yaml"
}

function stash_runtime_config() {
  local _config="$1"
  [[ -f "$_config" ]] || return 0
  cp "$_config" "$(stashed_config_path "$_config")"
}

# Merges the freshly rendered keys into the stashed runtime copy, then restores it.
# A copy the sync rejects goes back unchanged, so the agent's own edits are never lost.
function sync_runtime_config() {
  local _command="$1" _config="$2" _stashed
  _stashed="$(stashed_config_path "$_config")"
  [[ -f "$_stashed" ]] || return 0
  local _merged="$_stashed.merged"
  cp "$_stashed" "$_merged"
  if ! "$BIN_DIR/agent-harness" "$_command" --source "$_config" --target "$_merged"; then
    install -m 0600 "$_stashed" "$_config"
    printf 'restored %s, which %s could not merge; fix it and run again.\n' "$_config" "$_command" >&2
    exit 1
  fi
  install -m 0600 "$_merged" "$_config"
}

function stashed_config_path() {
  printf '%s/%s.previous\n' "$WORK_DIR" "${1//\//_}"
}

# Mirrors Nix's patchShebangs, which rewrites executables only, so hooks never depend on
# which python3 PATH resolves.
function pin_python_shebangs() {
  local _python="$1" _directory _file
  for _directory in .claude/hooks .claude/statusline .claude/skills .codex/hooks .codex/skills \
    .devin/hooks .hermes/hooks .pi/hooks; do
    [[ -d "$HARNESS_PREFIX/$_directory" ]] || continue
    while IFS= read -r -d '' _file; do
      pin_python_shebang "$_python" "$_file"
    done < <(find "$HARNESS_PREFIX/$_directory" -type f -perm -u+x -print0)
  done
}

function pin_python_shebang() {
  local _python="$1" _file="$2" _first_line
  _first_line="$(head -n 1 "$_file")"
  [[ "$_first_line" == "$SOURCE_SHEBANG"* ]] || return 0
  local _pinned="$WORK_DIR/pinned.py"
  {
    printf '#!%s%s\n' "$_python" "${_first_line#"$SOURCE_SHEBANG"}"
    tail -n +2 "$_file"
  } >|"$_pinned"
  install -m 0755 "$_pinned" "$_file"
}

# Matches the agent-harness Home Manager token module: gh and git push in the Claude sandbox
# authenticate with a GitHub App token, and the App key stays unreadable there. It runs after
# the host override, whose arrays would otherwise replace these entries.
function configure_agent_github_token() {
  [[ -n "${AGENT_GITHUB_APP_ID:-}" ]] || return 0
  local _refresh=("$BIN_DIR/agent-harness" github-app-token refresh --app-id "$AGENT_GITHUB_APP_ID")
  if [[ -n "${AGENT_GITHUB_APP_INSTALLATION_ID:-}" ]]; then
    _refresh+=(--installation-id "$AGENT_GITHUB_APP_INSTALLATION_ID")
  fi
  _refresh+=(--private-key "$AGENT_GITHUB_APP_PRIVATE_KEY" --config-dir "$AGENT_GITHUB_TOKEN_CONFIG_DIR")
  "${_refresh[@]}"
  allow_agent_github_token
  report_token_refresh "${_refresh[@]}"
}

# Matches the agent-harness Home Manager module: agent commands log Neovim into the harness state
# directory, which both sandboxes let them write. Neovim does not create the directory itself.
function configure_nvim_log_file() {
  local _merged="$WORK_DIR/nvim_settings.json"
  mkdir -p "${NVIM_LOG_FILE_PATH%/*}"
  # shellcheck disable=SC2016  # $path is a jq variable
  "$BIN_DIR/jq" --arg path "$NVIM_LOG_FILE_PATH" '.env.NVIM_LOG_FILE = $path' "$CLAUDE_SETTINGS" >|"$_merged"
  install -m 0600 "$_merged" "$CLAUDE_SETTINGS"
}

function allow_agent_github_token() {
  local _merged="$WORK_DIR/token_settings.json"
  # shellcheck disable=SC2016  # $config_dir and $key are jq variables
  "$BIN_DIR/jq" \
    --arg config_dir "$AGENT_GITHUB_TOKEN_CONFIG_DIR" \
    --arg key "$AGENT_GITHUB_APP_PRIVATE_KEY" '
    def append_unique($items): reduce $items[] as $item (. // []; if index([$item]) then . else . + [$item] end);
    .env.GH_CONFIG_DIR = $config_dir
    | .sandbox.enableWeakerNetworkIsolation = true
    | .sandbox.network.allowedDomains |= append_unique(["github.com", "api.github.com"])
    | if .sandbox | has("excludedCommands") then .sandbox.excludedCommands -= ["gh *"] else . end
    | .permissions.deny |= append_unique(["Read(/" + $key + ")"])
    | .sandbox.filesystem.denyRead |= append_unique([$key])
  ' "$CLAUDE_SETTINGS" >|"$_merged"
  install -m 0600 "$_merged" "$CLAUDE_SETTINGS"
}

# Matches the Home Manager module for Codex: shell commands log Neovim into the harness state
# directory and, when the host names a GitHub App, read its token while the guarded profile
# writes what Claude may write, reaches the network, and hides the App key.
# The settings go into the generated Codex source, which agent-harness then syncs into the
# user's config: its comments and own keys stay, and the settings vanish with the App.
function render_codex_config() {
  local _python="$1"
  local _generated="$WORK_DIR/codex_generated.toml"
  local _merged="$WORK_DIR/codex_config.toml"
  "$BIN_DIR/agent-harness" generate-codex-config-source --source "$REPO_ROOT/agents" --output "$_generated"
  local _config_dir="" _private_key=""
  if [[ -n "${AGENT_GITHUB_APP_ID:-}" ]]; then
    _config_dir="$AGENT_GITHUB_TOKEN_CONFIG_DIR"
    _private_key="$AGENT_GITHUB_APP_PRIVATE_KEY"
  fi
  "$_python" -I - "$_generated" "$CLAUDE_SETTINGS" "$NVIM_LOG_FILE_PATH" "$_config_dir" \
    "$_private_key" >|"$_merged" <<'PY'
import json
import sys
import tomllib

sys.stdout.reconfigure(encoding="utf-8")
config_path, claude_settings_path, nvim_log_file, config_dir, private_key = sys.argv[1:]
with open(config_path, "rb") as file:
    config = tomllib.load(file)
with open(claude_settings_path, encoding="utf-8") as file:
    claude_settings = json.load(file)

environment = config.setdefault("shell_environment_policy", {}).setdefault("set", {})
environment["NVIM_LOG_FILE"] = nvim_log_file

if config_dir:
    environment["GH_CONFIG_DIR"] = config_dir
    # Relative allowWrite entries name Claude's working directory, which :workspace_roots covers.
    cache_writes = [
        path
        for path in claude_settings.get("sandbox", {}).get("filesystem", {}).get("allowWrite", [])
        if path.startswith(("/", "~/"))
    ]
    config["default_permissions"] = "guarded"
    guarded = config.setdefault("permissions", {}).setdefault("guarded", {})
    filesystem = guarded.setdefault("filesystem", {})
    workspace_roots = {**filesystem.get(":workspace_roots", {}), ".": "write"}
    filesystem.update(
        {path: "write" for path in cache_writes}
        | {
            ":root": "read",
            ":tmpdir": "write",
            ":slash_tmp": "write",
            ":workspace_roots": workspace_roots,
            "~/.config/gh/hosts.yml": "deny",
            private_key: "deny",
        }
    )
    guarded.setdefault("network", {})["enabled"] = True


def key(name):
    return json.dumps(name, ensure_ascii=False)


def inline(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key(k)} = {inline(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(inline(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return value.isoformat() if hasattr(value, "isoformat") else repr(value)


def is_table_array(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def emit(table, path):
    nested = {k: v for k, v in table.items() if isinstance(v, dict) or is_table_array(v)}
    for name, value in table.items():
        if name not in nested:
            print(f"{key(name)} = {inline(value)}")
    for name, value in nested.items():
        child = [*path, key(name)]
        for item in value if isinstance(value, list) else [value]:
            print()
            print(("[[" if isinstance(value, list) else "[") + ".".join(child) + ("]]" if isinstance(value, list) else "]"))
            emit(item, child)


emit(config, [])
PY
  "$_python" -I -c 'import sys, tomllib; tomllib.load(open(sys.argv[1], "rb"))' "$_merged"
  "$BIN_DIR/agent-harness" sync-codex-config --source "$_merged" --target "$CODEX_CONFIG"
}

# The Codex config render reads the generated Codex source with the standard-library TOML parser.
function require_toml_python() {
  local _python="$1"
  "$_python" -I -c 'import tomllib' 2>/dev/null && return 0
  printf 'The Codex config settings need Python 3.11 or newer (tomllib); %s is older. Set PYTHON_VERSION to 3.11 or newer.\n' \
    "$_python" >&2
  exit 1
}

# The token expires after an hour; scheduling its refresh is left to the host owner.
function report_token_refresh() {
  local _command
  printf -v _command '%q ' "$@"
  _command="${_command% }"
  cat <<EOF
The agent GitHub token expires in one hour. Refresh it every 5 minutes with either:
    crontab -e, then add:  */5 * * * * $_command
    systemd-run --user --on-calendar='*:0/5' --unit agent-harness-github-app-token $_command   (until reboot)
EOF
}

function apply_claude_settings_override() {
  [[ -f "$CLAUDE_SETTINGS_OVERRIDE" ]] || return 0
  local _merged="$WORK_DIR/settings.json"
  "$BIN_DIR/jq" -s '.[0] * .[1]' "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS_OVERRIDE" >|"$_merged"
  install -m 0600 "$_merged" "$CLAUDE_SETTINGS"
  printf 'override %s\n' "$CLAUDE_SETTINGS"
}

# Hooks run inside the agent's environment, so the login shell must export the same locations.
function write_env_snippet() {
  {
    printf '%s\n' \
      '# Generated by scripts/bootstrap_server.sh; source this file from the login shell.' \
      "case \":\$PATH:\" in" \
      "  *\":$BIN_DIR:\"*) ;;" \
      "  *) export PATH=\"$BIN_DIR:\$PATH\" ;;" \
      'esac'
    write_env_exports XDG_CONFIG_HOME XDG_CACHE_HOME
    printf '%s\n' 'export DEVIN_PERMISSION_MODE=smart'
  } >|"$ENV_SNIPPET"
  printf 'Add this line to the login shell profile (~/.profile or ~/.bashrc):\n    . "%s"\n' "$ENV_SNIPPET"
}

function write_env_exports() {
  local _name
  for _name in "$@"; do
    if [[ -n "${!_name:-}" ]]; then
      printf 'export %s="%s"\n' "$_name" "${!_name}"
    fi
  done
}

function verify_harness() {
  PATH="$BIN_DIR:$PATH" "$BIN_DIR/agent-harness" verify --source "$REPO_ROOT/agents" --prefix "$HARNESS_PREFIX"
}

# Claude Code's Linux sandbox needs both; without them it cannot isolate agent commands.
function warn_missing_sandbox_tools() {
  local _command
  for _command in bwrap socat; do
    command -v "$_command" >/dev/null && continue
    printf 'warning: %s not found; install it so the Claude Code sandbox can run on Linux.\n' "$_command" >&2
  done
}

function report_legacy_config_dir() {
  local _name
  for _name in bootstrap_server.env claude_settings_override.json; do
    [[ -e "$LEGACY_CONFIG_DIR/$_name" ]] || continue
    printf 'notice: %s/%s is read for one more release; move it to %s/.\n' \
      "$LEGACY_CONFIG_DIR" "$_name" "$CONFIG_DIR" >&2
  done
  [[ -e "$LEGACY_CONFIG_DIR/agent_env.sh" ]] || return 0
  printf 'notice: %s/agent_env.sh is no longer updated; source %s from the login shell instead.\n' \
    "$LEGACY_CONFIG_DIR" "$ENV_SNIPPET" >&2
}

main "$@"
