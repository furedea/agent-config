"""Static registry rules report findings after an edit and never block, whatever the scanner does."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.runtime import REPO_ROOT, CliRunner, StubWriter, load_script_module


hook_adapter = load_script_module("agents/codex/hooks/hook_adapter.py", "codex_hook_adapter_for_static_rules")
SCRIPT = "agents/hooks/static_rules.py"
FINDING = {
    "ruleId": "no-print",
    "severity": "error",
    "message": "Do not call print in library code.",
    "range": {"start": {"line": 3, "column": 0}},
}
RECORD_CALLS = """
    import json, os, sys
    from pathlib import Path
    with Path(os.environ["SCANNER_CALLS"]).open("a") as stream:
        stream.write(json.dumps(sys.argv[1:]) + "\\n")
"""


@pytest.fixture
def lint_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "lint"
    directory.mkdir()
    (directory / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
    monkeypatch.setenv("AGENT_LINT_DIR", str(directory))
    return directory


@pytest.fixture(autouse=True)
def scanner_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    calls = tmp_path / "scanner_calls.jsonl"
    monkeypatch.setenv("SCANNER_CALLS", str(calls))
    return calls


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "work" / "source.py"
    path.parent.mkdir()
    path.write_text("print('x')\n")
    return path


def install_scanner(executable: StubWriter, findings: list[dict], status: int = 1) -> None:
    lines = "\n".join(json.dumps({**finding, "file": "{path}"}) for finding in findings)
    executable(
        "ast-grep",
        RECORD_CALLS
        + f"""
    for line in {lines!r}.splitlines():
        print(line.replace("{{path}}", sys.argv[-1]))
    sys.exit({status})
""",
    )


def edit_payload(path: Path, tool: str = "Write") -> dict:
    return {"tool_name": tool, "cwd": str(path.parent), "tool_input": {"file_path": str(path)}}


def context_of(result: subprocess.CompletedProcess[str]) -> str:
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_findings_are_returned_as_context_with_rule_file_line_and_message(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert result.returncode == 0
    assert context_of(result) == f"Static rule no-print · {source}:4\nDo not call print in library code."
    assert json.loads(scanner_calls.read_text()) == [
        "scan",
        "--config",
        str(lint_directory / "sgconfig.yml"),
        "--json=stream",
        str(source),
    ]


@pytest.mark.parametrize("status", [0, 1])
def test_findings_are_never_blocking_whatever_the_scanner_exit_code(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, source: Path, status: int
) -> None:
    install_scanner(executable, [FINDING], status)
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert result.returncode == 0
    assert "Static rule no-print" in context_of(result)
    assert "decision" not in json.loads(result.stdout)


def test_a_clean_file_stays_silent(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, source: Path
) -> None:
    install_scanner(executable, [], 0)
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_missing_rules_directory_does_nothing(
    run_cli: CliRunner,
    executable: StubWriter,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scanner_calls: Path,
    source: Path,
) -> None:
    install_scanner(executable, [FINDING])
    monkeypatch.setenv("AGENT_LINT_DIR", str(tmp_path / "absent"))
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not scanner_calls.exists()


def test_rules_directory_without_scanner_config_does_nothing(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    (lint_directory / "sgconfig.yml").unlink()
    install_scanner(executable, [FINDING])
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not scanner_calls.exists()


def test_missing_ast_grep_does_nothing(run_cli: CliRunner, lint_directory: Path, tmp_path: Path, source: Path) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    result = run_cli(SCRIPT, payload=edit_payload(source), env={"PATH": str(empty)})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_a_failing_scanner_is_reported_without_blocking(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, source: Path
) -> None:
    executable("ast-grep", 'import sys\nprint("Error: cannot read sgconfig.yml", file=sys.stderr)\nsys.exit(2)\n')
    result = run_cli(SCRIPT, payload=edit_payload(source))
    assert result.returncode == 0
    assert "Static rules failed" in context_of(result)
    assert "cannot read sgconfig.yml" in context_of(result)


def test_non_edit_tools_and_missing_files_are_not_scanned(
    run_cli: CliRunner, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    assert run_cli(SCRIPT, payload=edit_payload(source, "Read")).stdout == ""
    assert run_cli(SCRIPT, payload=edit_payload(source.with_name("missing.py"))).stdout == ""
    assert not scanner_calls.exists()


def test_invalid_input_fails_without_the_blocking_exit_code(run_cli: CliRunner, lint_directory: Path) -> None:
    result = run_cli(SCRIPT, payload="[")
    assert result.returncode == 1


def test_provider_adapters_report_static_findings_with_the_lint_diagnostics(
    executable: StubWriter,
    lint_directory: Path,
    source: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_scanner(executable, [FINDING])
    monkeypatch.chdir(source.parent)
    monkeypatch.setattr(hook_adapter.provider_adapter.lint_format, "check_file", lambda *_: ())
    assert hook_adapter.ADAPTER.lint({"tool_name": "Write", "tool_input": {"file_path": str(source)}}) == 0
    assert "Static rule no-print" in capsys.readouterr().out


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is provided by the dev shell")
def test_real_ast_grep_reports_a_rule_from_the_rules_directory(
    run_cli: CliRunner, lint_directory: Path, source: Path
) -> None:
    (lint_directory / "sgconfig.yml").write_text("ruleDirs:\n  - rules/python\n")
    rules = lint_directory / "rules/python"
    rules.mkdir(parents=True)
    (rules / "no-print.yml").write_text(
        "id: no-print\nlanguage: python\nseverity: error\nmessage: Do not call print in library code.\n"
        "rule:\n  pattern: print($$$ARGS)\n"
    )
    result = run_cli(SCRIPT, payload=edit_payload(source), env=os.environ | {"AGENT_LINT_DIR": str(lint_directory)})
    assert result.returncode == 0
    assert context_of(result) == f"Static rule no-print · {source}:1\nDo not call print in library code."


def test_claude_manifest_runs_the_static_rules_after_every_edit() -> None:
    groups = json.loads((REPO_ROOT / "agents/hooks.json").read_text())["claude"]["PostToolUse"]
    edits = next(group for group in groups if group.get("matcher") == "Write|Edit|NotebookEdit")
    commands = [hook["command"] for hook in edits["hooks"]]
    assert commands == ['"$HOME/.claude/hooks/lint_format.py"', '"$HOME/.claude/hooks/static_rules.py"']
