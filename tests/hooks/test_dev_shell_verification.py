"""Verification runs a tool that only the project's flake dev shell provides through that dev shell."""

import json
import os
import sys
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT, StubWriter, load_script_module

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
execution = load_script_module("agents/hooks/lib/check_execution.py", "check_execution")
selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")

FLAKE_WITH_DEV_SHELL = "{ outputs = _: { devShells.aarch64-darwin.default = null; }; }\n"
FLAKE_WITHOUT_DEV_SHELL = "{ outputs = _: { packages.aarch64-darwin.default = null; }; }\n"
GO_STUB = "import sys\nprint('ok  \\texample/a\\t0.01s')\nsys.exit(0)\n"
NIX_STUB = """\
    import json, os, sys
    from pathlib import Path
    with Path(os.environ["NIX_CALLS"]).open("a") as stream:
        stream.write(json.dumps(sys.argv[1:]) + "\\n")
    arguments = sys.argv[1:]
    assert arguments[:3] == ["develop", "--no-write-lock-file", "--command"], arguments
    os.environ["PATH"] = os.pathsep.join([os.environ["DEV_SHELL_BIN"], "/usr/bin", "/bin"])
    os.execvp(arguments[3], arguments[3:])
"""
# A name no machine installs, so a real `go` on the CI runner cannot satisfy the PATH lookup.
TOOL = "dev-shell-only-go"
GO_TEST = selection.Invocation("go", "1 packages", (TOOL, "test", "./a"))


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executable: StubWriter) -> Path:
    """A project whose agent PATH holds only a fake nix; go lives in a separate dev-shell directory."""
    root = tmp_path / "project"
    root.mkdir()
    shell_bin = tmp_path / "dev-shell-bin"
    shell_bin.mkdir()
    executable("nix", NIX_STUB)
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path / "bin"), "/usr/bin", "/bin"]))
    monkeypatch.setenv("DEV_SHELL_BIN", str(shell_bin))
    monkeypatch.setenv("NIX_CALLS", str(tmp_path / "nix_calls"))
    return root


def install_go_in_dev_shell(tmp_path: Path, source: str = GO_STUB) -> None:
    go = tmp_path / "dev-shell-bin" / TOOL
    go.write_text(f"#!{sys.executable} -I\n{source}")
    go.chmod(0o700)


def nix_calls(tmp_path: Path) -> list[list[str]]:
    path = tmp_path / "nix_calls"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_tool_missing_from_path_runs_through_the_flake_dev_shell(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    install_go_in_dev_shell(tmp_path)
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.PASSED
    command = nix_calls(tmp_path)[0]
    assert command[:3] == ["develop", "--no-write-lock-file", "--command"]
    assert command[-3:] == [TOOL, "test", "./a"]


def test_tool_on_path_runs_directly_even_when_a_dev_shell_exists(
    project: Path, tmp_path: Path, executable: StubWriter
) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    executable(TOOL, GO_STUB)
    assert execution.execute(GO_TEST, project, 30).status == execution.Status.PASSED
    assert nix_calls(tmp_path) == []


def test_dev_shell_run_keeps_failure_as_failed(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    install_go_in_dev_shell(tmp_path, "import sys\nprint('FAIL\\texample/a\\t0.01s')\nsys.exit(1)\n")
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.FAILED


def test_dev_shell_run_keeps_the_timeout(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    install_go_in_dev_shell(tmp_path, "import time\ntime.sleep(60)\n")
    result = execution.execute(GO_TEST, project, 1)
    assert result.status == execution.Status.TIMEOUT


def test_dev_shell_run_keeps_the_empty_run_rule(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    install_go_in_dev_shell(tmp_path, "print('?   \\texample/a\\t[no test files]')\n")
    assert execution.execute(GO_TEST, project, 30).status == execution.Status.UNAVAILABLE


def test_tool_missing_without_a_flake_is_a_missing_tool_not_a_failure(project: Path, tmp_path: Path) -> None:
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.MISSING_TOOL
    assert TOOL in result.summary
    assert "not found" in result.summary
    assert nix_calls(tmp_path) == []


def test_flake_without_a_dev_shell_does_not_provide_the_tool(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITHOUT_DEV_SHELL)
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.MISSING_TOOL
    assert nix_calls(tmp_path) == []


def test_dev_shell_that_lacks_the_tool_is_a_missing_tool(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.MISSING_TOOL
    assert "dev shell" in result.summary
    assert len(nix_calls(tmp_path)) == 1


def test_broken_flake_that_nix_cannot_enter_is_a_blocking_failure_with_nix_output(
    project: Path, executable: StubWriter
) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    executable(
        "nix",
        "import sys\nprint('error: syntax error, unexpected end of file in flake.nix')\nsys.exit(1)\n",
    )
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.DEV_SHELL_FAILED
    assert result.failed
    assert "syntax error" in result.output
    assert "syntax error" in result.summary


def test_dev_shell_still_building_when_the_budget_ends_is_unavailable_not_a_timeout(
    project: Path, executable: StubWriter
) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    executable("nix", "import time\ntime.sleep(60)\n")
    result = execution.execute(GO_TEST, project, 1)
    assert result.status == execution.Status.MISSING_TOOL
    assert "did not start within the check budget" in result.summary


def test_failure_with_output_past_the_retained_tail_stays_failed(project: Path, tmp_path: Path) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    noisy = f"import sys\nsys.stdout.write('x' * {execution.OUTPUT_LIMIT_BYTES * 2})\nsys.exit(1)\n"
    install_go_in_dev_shell(tmp_path, noisy)
    assert execution.execute(GO_TEST, project, 30).status == execution.Status.FAILED


def test_dev_shell_without_nix_on_path_names_nix_as_the_missing_tool(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "flake.nix").write_text(FLAKE_WITH_DEV_SHELL)
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path / "empty"), "/usr/bin", "/bin"]))
    result = execution.execute(GO_TEST, project, 30)
    assert result.status == execution.Status.MISSING_TOOL
    assert "nix" in result.summary


def test_missing_tool_is_not_a_blocking_failure() -> None:
    assert not execution.Result(execution.Status.MISSING_TOOL, "go: not found").failed
