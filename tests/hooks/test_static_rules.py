"""ast-grep rules from the project's own sgconfig.yml report findings after formatting and never block."""

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
        def check(_kind: str, path: Path) -> tuple[str, ...]:
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


@pytest.fixture(autouse=True)
def shared_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The deployed shared rules, absent until a test creates them."""
    config = tmp_path / "shared-lint" / "sgconfig.yml"
    monkeypatch.setattr(lint_format.static_rule_scan, "SHARED_CONFIG", config)
    return config


def deploy_shared_rules(config: Path) -> None:
    config.parent.mkdir()
    config.write_text("ruleDirs:\n  - rules\n")


def scanned_configs(scanner_calls: Path) -> list[str]:
    return [json.loads(line)[2] for line in scanner_calls.read_text().splitlines()]


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


@pytest.mark.usefixtures("lint_directory")
def test_the_scanner_sees_the_file_after_formatting(
    hook: Hook, executable: StubWriter, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    hook.formatter(rewrite="\n\nprint('x')\n")
    hook.run(source)
    assert json.loads(scanner_calls.read_text())[-1] == "\n\nprint('x')\n"


@pytest.mark.parametrize("status", [0, 1])
@pytest.mark.usefixtures("lint_directory")
def test_findings_are_never_blocking_whatever_the_scanner_exit_code(
    hook: Hook, executable: StubWriter, source: Path, status: int
) -> None:
    install_scanner(executable, [FINDING], status)
    exit_status, output = hook.run(source)
    assert exit_status == 0
    assert "Static rule no-print" in context_of(output)
    assert "decision" not in json.loads(output)


@pytest.mark.usefixtures("lint_directory")
def test_a_clean_file_stays_silent(hook: Hook, executable: StubWriter, source: Path) -> None:
    install_scanner(executable, [], 0)
    assert hook.run(source) == (0, "")


@pytest.mark.usefixtures("source")
def test_each_file_is_scanned_with_the_nearest_project_config(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path
) -> None:
    nested = lint_directory / "nested"
    nested.mkdir()
    (nested / "sgconfig.yml").write_text("ruleDirs:\n  - rules\n")
    inner = nested / "inner.py"
    inner.write_text("print('y')\n")
    install_scanner(executable, [FINDING])
    hook.run(inner)
    assert json.loads(scanner_calls.read_text())[2] == str(nested / "sgconfig.yml")


def test_shared_rules_run_in_a_project_without_its_own_config(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, shared_config: Path, source: Path
) -> None:
    (lint_directory / "sgconfig.yml").unlink()
    deploy_shared_rules(shared_config)
    install_scanner(executable, [FINDING])
    status, output = hook.run(source)
    assert status == 0
    assert scanned_configs(scanner_calls) == [str(shared_config)]
    assert context_of(output).startswith("Static rule no-print")


def test_shared_and_project_rules_both_run_and_their_findings_are_merged(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, shared_config: Path, source: Path
) -> None:
    deploy_shared_rules(shared_config)
    install_scanner(executable, [FINDING])
    status, output = hook.run(source)
    assert status == 0
    assert scanned_configs(scanner_calls) == [str(shared_config), str(lint_directory / "sgconfig.yml")]
    assert context_of(output).count("Static rule no-print") == 2


def test_a_project_config_that_is_the_shared_config_is_scanned_once(
    hook: Hook,
    executable: StubWriter,
    lint_directory: Path,
    scanner_calls: Path,
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lint_format.static_rule_scan, "SHARED_CONFIG", lint_directory / "sgconfig.yml")
    install_scanner(executable, [FINDING])
    hook.run(source)
    assert scanned_configs(scanner_calls) == [str(lint_directory / "sgconfig.yml")]


@pytest.mark.usefixtures("lint_directory")
def test_a_failing_shared_scan_does_not_hide_project_findings_or_block(
    hook: Hook, executable: StubWriter, shared_config: Path, source: Path
) -> None:
    deploy_shared_rules(shared_config)
    executable(
        "ast-grep",
        RECORD_CALLS
        + f"""
    if sys.argv[3] == {str(shared_config)!r}:
        print("Error: bad shared rule", file=sys.stderr)
        sys.exit(8)
    print(json.dumps({{**{FINDING!r}, "file": sys.argv[-1]}}))
    sys.exit(1)
""",
    )
    status, output = hook.run(source)
    assert status == 0
    assert "Static rules failed" in context_of(output)
    assert "Static rule no-print" in context_of(output)
    assert "decision" not in json.loads(output)


def test_project_without_scanner_config_does_nothing(
    hook: Hook, executable: StubWriter, lint_directory: Path, scanner_calls: Path, source: Path
) -> None:
    (lint_directory / "sgconfig.yml").unlink()
    install_scanner(executable, [FINDING])
    assert hook.run(source) == (0, "")
    assert not scanner_calls.exists()


@pytest.mark.usefixtures("lint_directory")
def test_missing_ast_grep_does_nothing(
    hook: Hook, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: Path
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert hook.run(source) == (0, "")


@pytest.mark.usefixtures("lint_directory")
def test_a_failing_scanner_is_reported_without_blocking(hook: Hook, executable: StubWriter, source: Path) -> None:
    executable("ast-grep", 'import sys\nprint("Error: cannot read sgconfig.yml", file=sys.stderr)\nsys.exit(8)\n')
    status, output = hook.run(source)
    assert status == 0
    assert "Static rules failed" in context_of(output)
    assert "cannot read sgconfig.yml" in context_of(output)


@pytest.mark.usefixtures("lint_directory")
def test_findings_before_an_abnormal_exit_are_kept_with_a_failure_notice(
    hook: Hook, executable: StubWriter, source: Path
) -> None:
    install_scanner(executable, [FINDING], status=8)
    status, output = hook.run(source)
    assert status == 0
    findings, failure = context_of(output).split("\n\n")
    assert findings.startswith("Static rule no-print")
    assert failure.startswith("Static rules failed")


@pytest.mark.usefixtures("lint_directory")
def test_output_cut_at_the_limit_is_reported_instead_of_dropping_findings_silently(
    hook: Hook, executable: StubWriter, source: Path
) -> None:
    executable(
        "ast-grep", 'import json, sys\nprint(json.dumps({"ruleId": "big", "text": "x" * 100000}))\nsys.exit(1)\n'
    )
    status, output = hook.run(source)
    assert status == 0
    assert "Static rule output truncated" in context_of(output)


@pytest.mark.usefixtures("lint_directory")
def test_non_edit_tools_and_missing_files_are_not_scanned(
    hook: Hook, executable: StubWriter, scanner_calls: Path, source: Path
) -> None:
    install_scanner(executable, [FINDING])
    assert hook.run(source, "Read") == (0, "")
    assert not scanner_calls.exists()


@pytest.mark.usefixtures("hook", "lint_directory")
def test_provider_adapters_report_static_findings_with_the_lint_diagnostics(
    executable: StubWriter,
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
