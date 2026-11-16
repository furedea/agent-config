"""A notebook cell is code in the notebook's language, so a suppression added to it asks like one in a file."""

import json
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_notebook")


def notebook(tmp_path: Path, source: str, metadata: dict | None = None, cell_type: str = "code") -> Path:
    path = tmp_path / "analysis.ipynb"
    cell = {
        "cell_type": cell_type,
        "id": "c1",
        "metadata": {},
        "source": source,
        "outputs": [],
        "execution_count": None,
    }
    path.write_text(json.dumps({"cells": [cell], "metadata": metadata or {}, "nbformat": 4, "nbformat_minor": 5}))
    return path


def decide(path: Path, **values: object) -> str:
    payload = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(path), **values}}
    return guard.decide(payload).decision


@pytest.mark.parametrize("source", ["x = 1  # noqa", "y = f()  # type: ignore"])
def test_a_suppression_added_to_a_cell_asks(tmp_path: Path, source: str) -> None:
    path = notebook(tmp_path, "x = 1\n")
    assert decide(path, cell_id="c1", new_source=source) == "ask"


def test_an_inserted_cell_with_a_suppression_asks(tmp_path: Path) -> None:
    path = notebook(tmp_path, "x = 1\n")
    assert decide(path, cell_id="c1", edit_mode="insert", cell_type="code", new_source="x = 1  # noqa") == "ask"


def test_editing_a_cell_beside_its_unchanged_suppression_passes(tmp_path: Path) -> None:
    path = notebook(tmp_path, "import os  # noqa: F401\nx = 1\n")
    assert decide(path, cell_id="c1", new_source="import os  # noqa: F401\nx = 2\n") == "allow"


def test_a_cell_is_read_in_the_notebooks_language(tmp_path: Path) -> None:
    path = notebook(tmp_path, "let x = 1;\n", {"language_info": {"name": "rust"}})
    assert decide(path, cell_id="c1", new_source="#[allow(dead_code)]\nlet x = 1;\n") == "ask"


def test_a_markdown_cell_that_mentions_a_marker_passes(tmp_path: Path) -> None:
    path = notebook(tmp_path, "x = 1\n")
    values = {"cell_id": "c1", "edit_mode": "insert", "cell_type": "markdown", "new_source": "Add # noqa sparingly."}
    assert decide(path, **values) == "allow"


def test_turning_a_markdown_cell_that_mentions_a_marker_into_code_asks(tmp_path: Path) -> None:
    """The prose of a markdown cell suppresses nothing, so a marker it held is new once the cell becomes code."""
    path = notebook(tmp_path, "x = 1  # noqa\n", cell_type="markdown")
    assert decide(path, cell_id="c1", cell_type="code", new_source="x = 1  # noqa\n") == "ask"
