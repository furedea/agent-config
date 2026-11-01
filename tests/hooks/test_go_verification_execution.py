"""A Go run that executed no tests is unavailable evidence, as it is for Rust."""

from pathlib import Path


from tests.runtime import StubWriter, load_script_module

execution = load_script_module("agents/hooks/lib/check_execution.py", "check_execution")
selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")


def run_go(executable: StubWriter, tmp_path: Path, stdout: str, exit_code: int = 0) -> tuple[str, str]:
    executable("go", f"import sys\nprint({stdout!r})\nsys.exit({exit_code})\n")
    invocation = selection.Invocation("go", "1 packages", ("go", "test", "./a"))
    result = execution.execute(invocation, tmp_path, 30)
    return str(result.status), str(result.output)


def test_go_without_test_files_is_unavailable_not_passed(executable: StubWriter, tmp_path: Path) -> None:
    result = run_go(executable, tmp_path, "?   \texample/a\t[no test files]")
    status, output = result
    assert status == str(execution.Status.UNAVAILABLE)
    assert "No tests executed" in output


def test_go_with_a_tested_package_passes(executable: StubWriter, tmp_path: Path) -> None:
    result = run_go(executable, tmp_path, "ok  \texample/a\t0.01s")
    assert result[0] == str(execution.Status.PASSED)


def test_go_failure_stays_failed(executable: StubWriter, tmp_path: Path) -> None:
    result = run_go(executable, tmp_path, "FAIL\texample/a\t0.01s", exit_code=1)
    assert result[0] == str(execution.Status.FAILED)
