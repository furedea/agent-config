"""A word the shell would expand from an unknown home directory is reported, never guessed."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

words = load_script_module("agents/hooks/lib/shell_words.py", "shell_words_home_test")


def test_an_unknown_home_directory_is_unsupported_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    def unknown_home() -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", unknown_home)
    with pytest.raises(words.UnsupportedSyntaxError, match="home directory is unknown"):
        words.home_directory()
