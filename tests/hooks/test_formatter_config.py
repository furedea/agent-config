"""Formatter configs resolve from the project, then the home directory, then the hook defaults."""

import json
import re
import shutil
from pathlib import Path

import pytest
from lib import formatter_policy, lint_engine


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
    (tmp_path / "home").symlink_to(home)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    steps = formatter_policy.plan("json_toml", home / "project" / "config.json")
    assert [step.label for step in steps] == ["dprint format", "dprint lint"]


@pytest.mark.parametrize("kind", ["json_toml", "md"])
def test_leftover_personal_prettierrc_does_not_shadow_dprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".prettierrc").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    steps = formatter_policy.plan(kind, home / "project" / "file.md")
    assert all(step.policy_error is None for step in steps)
    assert "dprint format" in [step.label for step in steps]


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


def test_bundled_dprint_config_formats_markdown_with_four_space_lists_and_kept_wrapping() -> None:
    config = json.loads((formatter_policy.BUNDLED_CONFIG_DIRECTORY / "dprint.json").read_text())
    assert config["markdown"] == {"listIndentKind": "pythonMarkdown", "textWrap": "maintain"}
    assert "md" in config["includes"][0]
    assert any("markdown" in plugin for plugin in config["plugins"])


def test_every_bundled_dprint_plugin_is_pinned_to_its_content_hash() -> None:
    plugins = json.loads((formatter_policy.BUNDLED_CONFIG_DIRECTORY / "dprint.json").read_text())["plugins"]
    unpinned = [
        plugin
        for plugin in plugins
        if not re.fullmatch(r"https://plugins\.dprint\.dev/\S+\.wasm@[0-9a-f]{64}", plugin)
    ]
    assert unpinned == []


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("dprint") is None, reason="dprint is not installed")
def test_bundled_dprint_config_formats_markdown_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    target = tmp_path / "project" / "file.md"
    target.parent.mkdir(parents=True)
    target.write_text("- a\n  - b\n\nline one\nline two\n")
    assert lint_engine.check_file("md", target, readonly=False) == ()
    assert target.read_text() == "- a\n    - b\n\nline one\nline two\n"


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("dprint") is None, reason="dprint is not installed")
def test_project_dprint_config_without_markdown_plugin_leaves_markdown_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()
    plugins = [
        plugin
        for plugin in json.loads((formatter_policy.BUNDLED_CONFIG_DIRECTORY / "dprint.json").read_text())["plugins"]
        if "json" in plugin
    ]
    (project / "dprint.json").write_text(json.dumps({"includes": ["**/*.json"], "plugins": plugins}))
    target = project / "file.md"
    target.write_text("- a\n  - b\n")
    assert lint_engine.check_file("md", target, readonly=False) == ()
    assert target.read_text() == "- a\n  - b\n"
