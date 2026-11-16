"""An edit under docs/adr runs adr-check on that directory and reports its findings without blocking."""

import io
import json
from pathlib import Path

import pytest
from tests.runtime import StubWriter, load_script_module

lint_format = load_script_module("agents/hooks/lint_format.py", "lint_format_for_adr_check")
RECORD_CALLS = """
    import json, os, sys
    from pathlib import Path
    with Path(os.environ["ADR_CHECK_CALLS"]).open("a") as stream:
        stream.write(json.dumps([*sys.argv[1:], str(Path.cwd())]) + "\\n")
"""


@pytest.fixture(autouse=True)
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    record = tmp_path / "adr_check_calls.jsonl"
    monkeypatch.setenv("ADR_CHECK_CALLS", str(record))
    monkeypatch.setattr(lint_format, "check_file", lambda _kind, _path: ())
    return record


@pytest.fixture
def adr_file(tmp_path: Path) -> Path:
    directory = tmp_path / "project" / "docs" / "adr"
    directory.mkdir(parents=True)
    path = directory / "0001_first.md"
    path.write_text("# Title\n")
    return path


def install(executable: StubWriter, output: str, status: int) -> None:
    executable(
        "adr-check",
        RECORD_CALLS
        + f"""
    print({output!r})
    sys.exit({status})
""",
    )


def run_hook(path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, str]:
    payload = {"tool_name": "Write", "cwd": str(path.parent), "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(lint_format.sys, "stdin", io.StringIO(json.dumps(payload)))
    status = lint_format.main([])
    return status, capsys.readouterr().out


def context_of(output: str) -> str:
    return json.loads(output)["hookSpecificOutput"]["additionalContext"]


def test_findings_are_returned_as_context_and_the_hook_still_succeeds(
    executable: StubWriter, adr_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    finding = f"{adr_file}: date: '01/01/2026' is not a 'date'"
    install(executable, finding, 1)
    status, output = run_hook(adr_file, capsys, monkeypatch)
    assert status == 0
    assert context_of(output) == f"ADR check\n{finding}"


def test_the_whole_directory_is_checked_from_inside_it(
    executable: StubWriter,
    adr_file: Path,
    calls: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(executable, "", 0)
    run_hook(adr_file, capsys, monkeypatch)
    assert json.loads(calls.read_text()) == [str(adr_file.parent), str(adr_file.parent.resolve())]


def test_a_clean_directory_is_silent(
    executable: StubWriter, adr_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    install(executable, "", 0)
    assert run_hook(adr_file, capsys, monkeypatch) == (0, "")


def test_a_failed_run_is_reported_as_a_failure(
    executable: StubWriter, adr_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    install(executable, "adr-check: cannot read ADRs", 2)
    _, output = run_hook(adr_file, capsys, monkeypatch)
    assert context_of(output) == "ADR check failed\nadr-check: cannot read ADRs"


def test_long_output_is_cut_with_a_count(executable: StubWriter, adr_file: Path) -> None:
    install(executable, "\n".join(f"finding {n}" for n in range(30)), 1)
    message = lint_format.adr_check_scan.check(adr_file.parent)
    assert "finding 23" in message
    assert "finding 24" not in message
    assert message.endswith("[6 more lines omitted]")


@pytest.mark.parametrize(
    "relative", ["docs/other/0001_first.md", "docs/adr/nested/0001_first.md", "docs/adr/0001_first.txt"]
)
def test_files_outside_the_adr_directory_do_not_run_the_command(
    executable: StubWriter, tmp_path: Path, calls: Path, relative: str
) -> None:
    install(executable, "finding", 1)
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("x\n")
    assert lint_format.adr_check_scan.diagnostics([path]) == ()
    assert not calls.exists()


def test_two_edits_in_one_directory_run_the_command_once(executable: StubWriter, adr_file: Path, calls: Path) -> None:
    install(executable, "finding", 1)
    other = adr_file.with_name("0002_second.md")
    other.write_text("# Title\n")
    assert len(lint_format.adr_check_scan.diagnostics([adr_file, other])) == 1
    assert len(calls.read_text().splitlines()) == 1


def test_missing_command_is_silent(adr_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    assert lint_format.adr_check_scan.diagnostics([adr_file]) == ()
