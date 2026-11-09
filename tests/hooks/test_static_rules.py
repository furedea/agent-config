"""Static registry rules report findings after formatting and never block, whatever the scanner does."""

import io
import json
from pathlib import Path
import shutil

import pytest

from tests.runtime import StubWriter, load_script_module


lint_format = load_script_module("agents/hooks/lint_format.py", "lint_format_for_static_rules")
hook_adapter = load_script_module("agents/codex/hooks/hook_adapter.py", "codex_hook_adapter_for_static_rules")
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
        stream.write(json.dumps([*sys.argv[1:], Path(sys.argv[-1]).read_text()]) + "\\n")
"""


class Hook:
    """One PostToolUse run of the lint dispatcher, with the formatters replaced by a fake."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        self.monkeypatch = monkeypatch
        self.capsys = capsys

    def formatter(self, rewrite: str | None = None) -> None:
        def check(kind: str, path: Path, readonly: bool = False) -> tuple[str, ...]:
            if rewrite is not None:
                path.write_text(rewrite)
            return ()

        self.monkeypatch.setattr(lint_format, "check_file", check)

    def run(self, path: Path, tool: str = "Write") -> tuple[int, str]:
        payload = {"tool_name": tool, "cwd": str(path.parent), "tool_input": {"file_path": str(path)}}
        self.monkeypatch.setattr(lint_format.sys, "stdin", io.StringIO(json.dumps(payload)))
        status = lint_format.main([])
        return status, self.capsys.readouterr().out


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Hook:
    result = Hook(monkeypatch, capsys)
    result.formatter()
    return result


@pytest.fixture
def lint_directory(tmp_path: Path) -> Path:
    """The project root that owns the ast-grep rules, with the edited file below it."""
    directory = tmp_path / "work"
    directory.mkdir()
    (directory / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
    return directory


@pytest.fixture(autouse=True)
def scanner_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    calls = tmp_path / "scanner_calls.jsonl"
    monkeypatch.setenv("SCANNER_CALLS", str(calls))
    return calls


@pytest.fixture
def source(lint_directory: Path) -> Path:
    path = lint_directory / "src" / "source.py"
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


def context_of(output: str) -> str:
    return json.loads(output)["hookSpecificOutput"]["additionalContext"]


def test_findings_are_returned_as_context_with_rule_file_line_and_message(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    status, output = hook.run(source)
    assert status == 0
    assert context_of(output) == f"Static rule no-print · {source}:4\nDo not call print in library code."
    assert json.loads(scanner_calls.read_text())[:-1] == [
        "scan",
        "--config",
        str(lint_directory / "sgconfig.yml"),
        "--json=stream",
        str(source),
    ]


def test_the_scanner_sees_the_file_after_formatting(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    hook.formatter(rewrite="\n\nprint('x')\n")
    hook.run(source)
    assert json.loads(scanner_calls.read_text())[-1] == "\n\nprint('x')\n"


@pytest.mark.parametrize("status", [0, 1])
def test_findings_are_never_blocking_whatever_the_scanner_exit_code(
    hook: Hook, executable: StubWriter, lint_directory: Path, source: Path, status: int
) -> None:
    install_scanner(executable, [FINDING], status)
    exit_status, output = hook.run(source)
    assert exit_status == 0
    assert "Static rule no-print" in context_of(output)
    assert "decision" not in json.loads(output)


def test_a_clean_file_stays_silent(hook: Hook, executable: StubWriter, lint_directory: Path, source: Path) -> None:
    install_scanner(executable, [], 0)
    assert hook.run(source) == (0, "")


def test_each_file_is_scanned_with_the_nearest_project_config(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    nested = lint_directory / "nested"
    nested.mkdir()
    (nested / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
    inner = nested / "inner.py"
    inner.write_text("print('y')\n")
    install_scanner(executable, [FINDING])
    hook.run(inner)
    assert json.loads(scanner_calls.read_text())[2] == str(nested / "sgconfig.yml")


def test_project_without_scanner_config_does_nothing(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    (lint_directory / "sgconfig.yml").unlink()
    install_scanner(executable, [FINDING])
    assert hook.run(source) == (0, "")
    assert not scanner_calls.exists()


def test_missing_ast_grep_does_nothing(
    hook: Hook, lint_directory: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: Path
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert hook.run(source) == (0, "")


def test_a_failing_scanner_is_reported_without_blocking(
    hook: Hook, executable: StubWriter, lint_directory: Path, source: Path
) -> None:
    executable("ast-grep", 'import sys\nprint("Error: cannot read sgconfig.yml", file=sys.stderr)\nsys.exit(8)\n')
    status, output = hook.run(source)
    assert status == 0
    assert "Static rules failed" in context_of(output)
    assert "cannot read sgconfig.yml" in context_of(output)


def test_non_edit_tools_and_missing_files_are_not_scanned(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    assert hook.run(source, "Read") == (0, "")
    assert not scanner_calls.exists()


def test_provider_adapters_report_static_findings_with_the_lint_diagnostics(
    hook: Hook,
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
class TestRealAstGrep:
    def test_a_rule_from_the_rules_directory_is_reported(self, hook: Hook, lint_directory: Path, source: Path) -> None:
        (lint_directory / "sgconfig.yml").write_text("ruleDirs:\n  - rules/python\n")
        rules = lint_directory / "rules/python"
        rules.mkdir(parents=True)
        (rules / "no-print.yml").write_text(
            "id: no-print\nlanguage: python\nseverity: error\nmessage: Do not call print in library code.\n"
            "rule:\n  pattern: print($$$ARGS)\n"
        )
        status, output = hook.run(source)
        assert status == 0
        assert context_of(output) == f"Static rule no-print · {source}:1\nDo not call print in library code."

    def test_a_broken_scanner_config_is_reported_not_silent(
        self, hook: Hook, lint_directory: Path, source: Path
    ) -> None:
        (lint_directory / "sgconfig.yml").write_text("ruleDirs: [unterminated\n")
        status, output = hook.run(source)
        assert status == 0
        assert "Static rules failed" in context_of(output)
