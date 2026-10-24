"""Formatter configs resolve from the project, then the home directory, then the hook defaults."""

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from lib import formatter_policy, lint_engine, process_runner


def test_personal_dprint_runs_from_the_target_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "dprint.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    target = project / "config.json"
    steps = formatter_policy.plan("json_toml", target)
    assert all(step.cwd == project for step in steps)
    assert all(str(home / "dprint.json") in step.arguments for step in steps)


def test_personal_configs_in_home_are_not_project_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "dprint.json").write_text("{}")
    (home / ".prettierrc").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    steps = formatter_policy.plan("json_toml", home / "project" / "config.json")
    assert [step.label for step in steps] == ["dprint format", "dprint lint"]
    assert all(str(home / "dprint.json") in step.arguments for step in steps)


def test_personal_configs_behind_a_symlinked_home_are_not_project_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "real-home"
    home.mkdir()
    (home / "dprint.json").write_text("{}")
    (home / ".prettierrc").write_text("{}")
    (tmp_path / "home").symlink_to(home)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    steps = formatter_policy.plan("json_toml", home / "project" / "config.json")
    assert [step.label for step in steps] == ["dprint format", "dprint lint"]


def test_project_declarations_in_the_home_directory_still_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / ".oxfmtrc.json").write_text("{}")
    steps = formatter_policy.plan("js", tmp_path / "file.js")
    assert [step.label for step in steps] == ["oxlint fix", "oxfmt format", "oxlint lint"]


def test_bundled_dprint_config_is_used_without_a_personal_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    steps = formatter_policy.plan("json_toml", tmp_path / "project" / "config.json")
    configs = {step.arguments[step.arguments.index("--config") + 1] for step in steps}
    assert len(configs) == 1
    config = Path(configs.pop())
    assert config.parent.name == "defaults"
    assert json.loads(config.read_text())["plugins"]


def run_prettierd_environment(tmp_path: Path, mocker: MockerFixture) -> dict[str, str]:
    execute = mocker.patch.object(
        process_runner, "run_process", return_value=process_runner.ProcessResult(0), autospec=True
    )
    target = tmp_path / "project" / "file.md"
    target.parent.mkdir(parents=True)
    target.write_text("text\n")
    step = formatter_policy.Step("prettierd format", ("prettierd", str(target)), writes_stdout=True, mutates=True)
    lint_engine.run_step(step, target)
    return execute.call_args.args[2]


def test_prettierd_prefers_the_personal_prettier_config(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".prettierrc").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    assert run_prettierd_environment(tmp_path, mocker)["PRETTIERD_DEFAULT_CONFIG"] == str(home / ".prettierrc")


def test_prettierd_uses_the_bundled_config_without_a_personal_config(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = Path(run_prettierd_environment(tmp_path, mocker)["PRETTIERD_DEFAULT_CONFIG"])
    assert config.parent.name == "defaults"
    assert json.loads(config.read_text())["proseWrap"] == "preserve"
