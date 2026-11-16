"""Read the code cell a notebook edit changes, in the notebook's own language."""

import json
from dataclasses import dataclass
from pathlib import Path

# The suffix of each notebook language whose files the hooks know; a notebook that names none is Python.
LANGUAGE_SUFFIXES = {
    "python": ".py",
    "rust": ".rs",
    "go": ".go",
    "typescript": ".ts",
    "javascript": ".js",
    "bash": ".sh",
    "sh": ".sh",
    "lua": ".lua",
}


@dataclass(frozen=True, slots=True)
class CellEdit:
    """A code cell's source before and after an edit, and the suffix of the notebook's language."""

    before: str
    after: str
    suffix: str


def code_cell_edit(path: str, values: dict) -> CellEdit | None:
    """The code cell a NotebookEdit writes, or None for a markdown cell or a deletion, which add no code.

    An inserted cell had no source, and a cell the notebook does not hold is read as empty. A language the hooks do
    not know gets its own name as suffix, which no hook inspects.
    """
    notebook = _notebook(path)
    cells = [cell for cell in _as_list(notebook.get("cells")) if isinstance(cell, dict)]
    cell = next((cell for cell in cells if cell.get("id") == values.get("cell_id")), {})
    inserted = values.get("edit_mode") == "insert"
    cell_type = values.get("cell_type") or ("code" if inserted else cell.get("cell_type", "code"))
    if cell_type != "code" or values.get("edit_mode") == "delete":
        return None
    after = values.get("new_source")
    return CellEdit(
        "" if inserted else _source(cell), after if isinstance(after, str) else "", _language_suffix(notebook)
    )


def _notebook(path: str) -> dict:
    try:
        notebook = json.loads(Path(path).read_text(errors="replace"))
    except OSError, ValueError:
        return {}
    return _as_dict(notebook)


def _source(cell: dict) -> str:
    """A cell's source, which nbformat stores as one string or as a list of lines."""
    source = cell.get("source", "")
    return "".join(part for part in source if isinstance(part, str)) if isinstance(source, list) else str(source)


def _language_suffix(notebook: dict) -> str:
    metadata = _as_dict(notebook.get("metadata"))
    language = _as_dict(metadata.get("language_info")).get("name") or _as_dict(metadata.get("kernelspec")).get(
        "language"
    )
    name = str(language or "python").lower()
    return LANGUAGE_SUFFIXES.get(name, f".{name}")


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []
