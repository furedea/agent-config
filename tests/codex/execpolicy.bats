#!/usr/bin/env bats
# Check the installed Codex execpolicy rules against the locked Codex CLI's evaluator.

setup_file() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  RULES="$BATS_FILE_TMPDIR/prefix/.codex/rules/default.rules"
  export RULES
  agent-harness install --source "$REPO_ROOT/agents" --prefix "$BATS_FILE_TMPDIR/prefix"
}

setup() {
  CODEX_BIN="${CODEX_BIN:-codex}"
  require_codex_execpolicy
}

function require_codex_execpolicy() {
  if "$CODEX_BIN" execpolicy check --help >/dev/null 2>&1; then
    return 0
  fi
  if [ "${REQUIRE_CODEX_EXECPOLICY:-0}" = "1" ]; then
    echo "Codex execpolicy check is not available: $CODEX_BIN" >&2
    return 1
  fi
  skip "Codex execpolicy check is not available: $CODEX_BIN"
}

function decision_for() {
  local _output
  _output="$("$CODEX_BIN" execpolicy check --rules "$RULES" -- "$@")"
  jq -er '.decision' <<<"$_output"
}

@test "installed rules allow an allow-listed command" {
  [ "$(decision_for git fetch origin)" = "allow" ]
}

@test "installed rules prompt for an ask-listed command" {
  [ "$(decision_for uvx ruff check)" = "prompt" ]
}

@test "installed rules forbid a deny-listed command" {
  [ "$(decision_for brew install ffmpeg)" = "forbidden" ]
}
