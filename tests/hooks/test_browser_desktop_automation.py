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


@pytest.fixture(autouse=True)
def session_temporary(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin the session's temporary directory, so /tmp counts as outside on every platform."""
    temporary = tmp_path_factory.mktemp("session-tmp").resolve()
    for name in ("TMPDIR", "CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.setenv(name, str(temporary))
    monkeypatch.setattr("tempfile.tempdir", str(temporary))
    return temporary


@pytest.fixture
def outside(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory outside both the project and the session's temporary directory."""
    directory = tmp_path_factory.mktemp("outside").resolve()
    (directory / ".zshrc").write_text("")
    return directory


@pytest.mark.parametrize("command", ["agent-browser screenshot", "agent-browser screenshot --full"])
def test_a_screenshot_the_browser_names_itself_runs(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser screenshot page.png",
        "agent-browser screenshot @e1",
        "agent-browser screenshot -f",
        "agent-browser screenshot --full page.png",
        "agent-browser screenshot --annotate",
        "agent-browser --json screenshot",
        "agent-browser 'screenshot' --full x",
        "agent-browser pdf",
        "agent-browser pdf out.pdf",
        "agent-browser pdf --full",
        "agent-browser trace stop",
        "agent-browser trace stop trace.zip",
        "agent-browser trace --json stop out.zip",
        "agent-browser profiler stop profile.json",
        "agent-browser profiler --headed stop out.json",
        "agent-browser network har stop capture.har",
        "agent-browser network --user-agent x har stop .zshrc",
        "agent-browser open https://example.com --screenshot-dir shots",
        "agent-browser open https://example.com --screenshot-dir=shots",
        "agent-browser --session review open https://example.com --action-policy policy.json",
        "agent-browser open https://example.com --action-policy=policy.json",
        "agent-browser open https://example.com --ca-cert ca.pem",
    ],
)
def test_a_file_the_browser_daemon_reads_or_writes_asks(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command", ["agent-browser trace start", "agent-browser profiler start", "agent-browser network requests"]
)
def test_forms_that_write_no_file_still_run(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "allow"


def test_a_browser_project_config_in_the_working_directory_asks(git_project: Path) -> None:
    (git_project / "agent-browser.json").write_text('{"executablePath": "./payload"}')
    assert decision(git_project, "agent-browser open https://example.com") == "ask"
    assert decision(git_project, "agent-desktop list-apps") == "allow"


@pytest.mark.parametrize(
    "command", ["agent-desktop screenshot --app Finder out", "agent-desktop screenshot --app Finder --path=out"]
)
def test_a_path_through_a_symlink_to_outside_asks(git_project: Path, outside: Path, command: str) -> None:
    (git_project / "out").symlink_to(outside / ".zshrc")
    assert decision(git_project, command) == "ask"


def test_an_output_under_a_symlinked_parent_directory_asks(git_project: Path, outside: Path) -> None:
    (git_project / "shots").symlink_to(outside)
    assert decision(git_project, "agent-desktop screenshot --app Finder shots/page.png") == "ask"


def test_a_dangling_symlink_asks(git_project: Path) -> None:
    (git_project / "out").symlink_to(git_project / "missing.png")
    assert decision(git_project, "agent-desktop screenshot --app Finder out") == "ask"


def test_a_symlink_loop_asks(git_project: Path) -> None:
    (git_project / "a").symlink_to(git_project / "b")
    (git_project / "b").symlink_to(git_project / "a")
    assert decision(git_project, "agent-desktop screenshot --app Finder a/page.png") == "ask"


def test_a_browser_argument_through_a_symlink_to_outside_asks(git_project: Path, outside: Path) -> None:
    (git_project / "page.html").symlink_to(outside / ".zshrc")
    assert decision(git_project, "agent-browser open page.html") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "agent-desktop screenshot --app Finder page.png",
        "agent-desktop screenshot --app Finder shots/page.png",
        "agent-browser open https://example.com/a/b",
        "agent-browser fill @e1 'path a/b in text'",
    ],
)
def test_a_path_inside_the_worktree_runs(git_project: Path, command: str) -> None:
    (git_project / "shots").mkdir()
    assert decision(git_project, command) == "allow"


def test_a_symlink_that_stays_inside_the_worktree_runs(git_project: Path) -> None:
    (git_project / "shots").mkdir()
    (git_project / "latest").symlink_to(git_project / "shots")
    assert decision(git_project, "agent-desktop screenshot --app Finder latest/page.png") == "allow"


def test_an_output_in_the_session_temporary_directory_runs(git_project: Path, session_temporary: Path) -> None:
    (git_project / "scratch").symlink_to(session_temporary)
    assert decision(git_project, "agent-desktop screenshot --app Finder scratch/page.png") == "allow"
    assert decision(session_temporary, "agent-desktop screenshot --app Finder page.png") == "allow"


def test_an_output_without_a_known_working_directory_asks(git_project: Path) -> None:
    payload = {"session_id": "session-a", "tool_name": "Bash", "tool_input": {"command": "agent-browser snapshot"}}
    assert guard.decide("allowed", payload).decision == "ask"


def test_a_working_directory_outside_any_worktree_asks(git_project: Path, outside: Path) -> None:
    assert decision(outside, "agent-desktop screenshot --app Finder page.png") == "ask"


def test_text_too_long_to_name_a_file_runs(git_project: Path) -> None:
    assert decision(git_project, "agent-browser fill @e1 '" + "word " * 100 + "'") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser --session work --json get title",
        "agent-browser --headed open https://example.com",
        "agent-browser click @e1 --new-tab",
        "agent-browser snapshot -i -c -d 3",
        "agent-browser snapshot --interactive --depth=3",
        "agent-browser type @e1 hello --delay 50",
        "agent-browser wait --text Done --timeout 5000",
        "agent-browser cookies set name value --domain example.com --secure",
        "agent-browser network route https://example.com/api --body ok",
        "agent-desktop snapshot --app Finder -i --compact",
        "agent-desktop find --app Finder --role button --first",
        "agent-desktop move-window --app Finder --x=-100 --y=20",
        "agent-desktop click @s8f3k2p9:e8 --timeout-ms 500 --wait-for button:OK",
        "agent-desktop wait --app Finder --text Done --timeout 1000",
        "agent-desktop list-windows --app Finder --session work",
        "agent-desktop --help",
    ],
)
def test_an_allowlisted_option_runs(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser open https://example.com --user-agent x",
        "agent-browser open https://example.com --action-policy policy.json",
        "agent-browser open https://example.com --ca-cert ca.pem",
        "agent-browser open https://example.com --proxy http://localhost:8080",
        "agent-browser click @e1 --frobnicate",
        "agent-browser eval --stdin",
        "agent-desktop snapshot --app Finder --trace out.jsonl",
        "agent-desktop snapshot --app Finder --debug --screenshot out.html",
        "agent-desktop clipboard-get --out shot.png",
        "agent-desktop clipboard-set --image shot.png",
        "agent-desktop clipboard-set --file-url notes.txt",
        "agent-desktop list-apps --agent-id helper",
        "agent-desktop close-app Finder --force",
    ],
)
def test_an_unknown_option_asks(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser click @e1 -i",
        "agent-browser snapshot --new-tab",
        "agent-browser fill @e1 hello --delay 50",
        "agent-desktop list-apps --compact",
        "agent-desktop type @e1 hello --direction up",
        "agent-desktop get @e1 --wait-for button:OK",
    ],
)
def test_an_allowlisted_option_on_another_subcommand_asks(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "agent-browser open https://example.com --user-agent=x",
        "agent-browser open https://example.com --action-policy=policy.json",
        "agent-desktop snapshot --app Finder --trace=out.jsonl",
        "agent-desktop clipboard-get --out=shot.png",
    ],
)
def test_an_unknown_option_with_an_attached_value_asks(git_project: Path, command: str) -> None:
    assert decision(git_project, command) == "ask"


def test_a_text_value_starting_with_a_dash_asks(git_project: Path) -> None:
    assert decision(git_project, "agent-browser fill @e1 -5") == "ask"
