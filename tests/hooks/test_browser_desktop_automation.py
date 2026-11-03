"""Browser and desktop automation run outside the sandbox without asking; a few forms stay denied or asking."""

from pathlib import Path

import pytest

from tests.runtime import load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")


def decision(project: Path, command: str, kind: str = "allowed") -> str:
    payload = {"cwd": str(project), "session_id": "session-a", "tool_name": "Bash", "tool_input": {"command": command}}
    return guard.decide(kind, payload).decision


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser open https://example.com",
        "agent-browser snapshot -i",
        "agent-browser --session work fill @e1 'hello world'",
        "agent-browser --json get title",
        "agent-desktop snapshot --app Finder -i",
        "agent-desktop snapshot --app 'Visual Studio Code' -i",
        "agent-desktop click @s8f3k2p9:e8",
        "agent-desktop list-apps",
        "agent-browser screenshot page.png",
        "agent-browser snapshot -d 3",
    ],
)
def test_ordinary_automation_runs_from_the_first_call(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "allow"
    assert decision(git_project, command, kind="forbidden") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser --cdp 9222 open https://example.com",
        "agent-browser open https://example.com --cdp=9222",
        "agent-browser --auto-connect snapshot",
        "agent-browser --profile Default open https://example.com",
        "agent-browser --state ./auth.json open https://example.com",
        "agent-browser --args --user-data-dir=/Users/kaito/Library open https://example.com",
        "agent-browser --config ./other.json open https://example.com",
        "agent-browser --executable-path ./chrome open https://example.com",
        "agent-browser --extension ./ext open https://example.com",
        "agent-browser --init-script ./hook.js open https://example.com",
        "agent-browser --allow-file-access open https://example.com",
        "agent-browser --download-path /tmp open https://example.com",
        "agent-browser connect 9222",
        "agent-browser upload @e1 /Users/kaito/.ssh/id_ed25519",
        "agent-browser download @e1 /tmp/file",
        "agent-browser open https://example.com && agent-browser snapshot",
        "agent-browser open $URL",
        "agent-browser open https://example.com > out.txt",
        "AGENT_BROWSER_PROFILE=Default agent-browser open https://example.com",
        "env agent-browser open https://example.com",
        "agent-browser open fi''le:///etc/passwd",
        "agent-browser 'connect' 9222",
        "agent-browser plugins add @someone/plugin",
        "agent-browser plugin add @someone/plugin",
        "agent-browser mcp call agent_browser_connect '{}'",
        "agent-browser chat 'open my bank'",
        "agent-browser auth login bank",
        "agent-browser batch 'open https://example.com'",
        "agent-browser state load ./auth.json",
        "agent-browser install",
        "agent-browser --provider browserbase open https://example.com",
        "agent-browser open https://example.com --restore=bank-login",
        "agent-browser --session-name bank open https://example.com",
        "agent-browser open https://example.com --provider browserbase",
        "agent-browser open https://example.com -p browserbase",
        "agent-browser diff snapshot --baseline /Users/kaito/.ssh/id_ed25519",
        "agent-browser diff snapshot --baseline id_ed25519",
        "agent-browser pdf /Users/kaito/.zshrc",
        "agent-browser screenshot ~/.zshrc",
        "agent-browser screenshot ../../.zshrc",
        "agent-browser screenshot --path=/tmp/x.png",
        "agent-browser trace stop /tmp/trace.zip",
        "agent-browser wait --download /Users/kaito/Downloads/payload",
        "agent-browser wait -d payload",
        "agent-browser doctor --fix",
    ],
)
def test_browser_forms_that_reach_existing_sessions_files_or_hide_words_ask(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser open file:///Users/kaito/.ssh/id_ed25519",
        "agent-browser open 'FILE:///etc/passwd'",
        "agent-browser open fi''le:///etc/passwd",
        "agent-browser tab new chrome://settings",
        "agent-browser eval \"location.href = 'file:///etc/passwd'\"",
        "env agent-browser open file:///etc/passwd",
    ],
)
def test_local_file_and_browser_internal_urls_are_denied(git_project: Path, command: str) -> None:
    assert decision(git_project, command, kind="forbidden") == "deny"


@pytest.mark.parametrize(
    "command",
    ["agent-browser fill @e1 'profile: public'", "agent-browser open https://example.com/files"],
)
def test_words_that_only_contain_a_scheme_name_are_not_denied(git_project: Path, command: str) -> None:
    assert decision(git_project, command, kind="forbidden") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "agent-desktop snapshot --app Ghostty -i",
        "agent-desktop snapshot --app terminal",
        "agent-desktop launch com.apple.Terminal",
        "agent-desktop launch /System/Applications/Utilities/Terminal.app",
        "agent-desktop focus-window --app iTerm2",
        "agent-desktop snapshot --app 'System Settings'",
        'agent-desktop launch "Keychain Access"',
        "agent-desktop snapshot --app 1Password",
        "agent-desktop launch 'Script Editor'",
        "agent-desktop launch x-apple.systempreferences:com.apple.preference.security",
        "agent-desktop find --app Gho''stty --role button",
        "agent-desktop snapshot --app システム設定 -i",
        "agent-desktop snapshot --app ターミナル",
        "agent-desktop launch キーチェーンアクセス",
    ],
)
def test_terminals_settings_and_credential_apps_are_denied(git_project: Path, command: str) -> None:
    assert decision(git_project, command, kind="forbidden") == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "agent-desktop snapshot -i",
        "agent-desktop snapshot --window-id w-204749 -i",
        "agent-desktop press cmd+v",
        "agent-desktop mouse-click --x 10 --y 10",
        "agent-desktop --headed click @s8f3k2p9:e8",
        "agent-desktop batch '[]'",
        "agent-desktop launch Finder",
        "agent-desktop launch /tmp/Helper.app",
        "agent-desktop launch Finder --arg /tmp",
        "agent-desktop launch Finder --env A=B",
        "agent-desktop permissions --guide",
        "agent-desktop 'press' cmd+v",
        "agent-desktop snapshot 'x --app Finder'",
    ],
)
def test_desktop_targets_the_arguments_cannot_name_ask(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"
