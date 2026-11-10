"""What the shell cannot expand into paths is asked about, never skipped."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

paths = load_script_module("agents/hooks/lib/shell_paths.py", "shell_paths_home_test")


def test_glob_of_an_unknown_home_directory_cannot_be_expanded_so_the_command_is_reviewed() -> None:
    with pytest.raises(paths.UnexpandableGlob):
        paths.command_paths("cat ~/.ssh/id_rsa ~no-such-user-for-agent-config/*")


def test_plain_path_of_an_unknown_home_directory_is_reviewed_like_a_glob() -> None:
    with pytest.raises(paths.UnexpandableGlob):
        paths.command_paths("cat ~no-such-user-for-agent-config/.aws/credentials")


def test_plain_path_of_another_users_home_stays_named_by_its_user() -> None:
    assert "~root/.aws/credentials" in paths.command_paths("cat ~root/.aws/credentials")


def test_glob_in_another_users_home_names_its_matches_by_that_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".aws").mkdir()
    (tmp_path / ".aws" / "credentials").touch()
    monkeypatch.setattr(paths.Path, "expanduser", lambda self: tmp_path if str(self) == "~root" else self)
    assert "~root/.aws/credentials" in paths.command_paths("cat ~root/.aws/*")
