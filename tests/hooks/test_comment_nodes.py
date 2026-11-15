"""Comment nodes come from ast-grep's grammars, and ast-grep's own suppressions do not hide any of them."""

import shutil
from pathlib import Path

import pytest
from tests.runtime import load_script_module

comment_nodes = load_script_module("agents/hooks/lib/comment_nodes.py", "comment_nodes_for_tests")
pytestmark = pytest.mark.skipif(shutil.which("ast-grep") is None, reason="ast-grep is provided by the dev shell")


def test_a_comment_right_below_a_bare_marker_is_still_found() -> None:
    text = "# ast-grep-ignore\n# ast-grep-ignore: rule\nx = 1\n"
    assert comment_nodes.comment_spans(text, ".py") == [(0, 17), (18, 41)]


def test_a_project_config_in_the_working_directory_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(comment_nodes.tempfile, "tempdir", None)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    (tmp_path / "sgconfig.yml").write_text("ruleDirs: [missing]\n")
    assert comment_nodes.comment_spans("# ast-grep-ignore\n", ".py") == [(0, 17)]


def test_every_comment_is_found_once_and_strings_are_not_comments() -> None:
    text = 'x = "# not a comment"  # first\n# second\n'
    assert comment_nodes.comment_spans(text, ".py") == [(23, 30), (31, 39)]


def test_text_that_cannot_be_encoded_is_unknown() -> None:
    assert comment_nodes.comment_spans("x = 1  # \ud800\n", ".py") is None


@pytest.mark.parametrize("suffix", [".js", ".ts", ".tsx"])
def test_an_html_like_comment_in_javascript_is_a_comment(suffix: str) -> None:
    assert comment_nodes.comment_spans("<!-- note\nfoo()\n", suffix) == [(0, 9)]
