"""What the shell cannot expand into paths is asked about, never skipped."""

import pytest
from tests.runtime import load_script_module

paths = load_script_module("agents/hooks/lib/shell_paths.py", "shell_paths")


def test_glob_of_an_unknown_home_directory_cannot_be_expanded_so_the_command_is_reviewed() -> None:
    with pytest.raises(paths.UnexpandableGlob):
        paths.command_paths("cat ~/.ssh/id_rsa ~no-such-user-for-agent-config/*")
