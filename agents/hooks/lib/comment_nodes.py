"""Find comments, and the strings and comments around Rust code, with ast-grep's tree-sitter grammars.

Hand-written lexers miss block scalars, raw strings and similar constructs, and ast-grep itself honors a
suppression only in a comment node, so the same parser decides here.
"""

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

SCANNER = "ast-grep"
# Every scan of one decision shares this, so the scans cannot add up past the 30-second hook timeout.
BUDGET_SECONDS = 20
LANGUAGES = {
    **dict.fromkeys((".py", ".pyi"), "python"),
    **dict.fromkeys((".ts", ".mts", ".cts"), "typescript"),
    ".tsx": "tsx",
    **dict.fromkeys((".js", ".jsx", ".mjs", ".cjs"), "javascript"),
    ".rs": "rust",
    ".go": "go",
    **dict.fromkeys((".sh", ".bash"), "bash"),
    ".lua": "lua",
    ".nix": "nix",
    **dict.fromkeys((".yml", ".yaml"), "yaml"),
}
COMMENT_KINDS = {
    "rust": ("line_comment", "block_comment"),
    **dict.fromkeys(("javascript", "typescript", "tsx"), ("comment", "html_comment")),
}
SUPPRESSION = "ast-grep-ignore"
# Same length as the suppression word, so every offset stays.
STAND_IN = "ast-grep-ign0re"
RUST_INERT_KINDS = ("string_literal", "raw_string_literal", "char_literal", "line_comment", "block_comment")


@dataclass(slots=True)
class _Budget:
    """The deadline the scans of one decision share, and whether a scan ran into it."""

    deadline: float = 0.0
    ran_out: bool = False


_BUDGET = _Budget(time.monotonic() + BUDGET_SECONDS)
# Only found spans are kept: a scan cut short by the budget is unknown for this decision, not for the next.
_SPANS: dict[tuple[str, str, tuple[str, ...]], list[tuple[int, int]]] = {}


def start_budget(seconds: float | None = None) -> None:
    """Give the scans from now on `seconds` in all, BUDGET_SECONDS by default; call it once per decision."""
    _BUDGET.deadline = time.monotonic() + (BUDGET_SECONDS if seconds is None else seconds)
    _BUDGET.ran_out = False


def budget_ran_out() -> bool:
    """Whether a scan since the budget started was cut short, so some comments are unknown."""
    return _BUDGET.ran_out


def comment_spans(text: str, suffix: str) -> list[tuple[int, int]] | None:
    """The start and end offsets of each comment in `text`, or None when they cannot be known.

    None means the suffix has no grammar, the scanner is missing, or it failed; the caller must then fail closed.
    """
    language = LANGUAGES.get(suffix.lower())
    if language is None or shutil.which(SCANNER) is None:
        return None
    return _scan(text, language, COMMENT_KINDS.get(language, ("comment",)))


def inert_spans(text: str, suffix: str) -> list[tuple[int, int]] | None:
    """The offsets of each Rust string or comment, where an attribute cannot apply; the whole text outside Rust.

    Anything else counts, including a macro body, whose attributes take effect once the macro expands. None means
    they cannot be known.
    """
    if LANGUAGES.get(suffix.lower()) != "rust":
        return [(0, len(text) + 1)]
    if shutil.which(SCANNER) is None:
        return None
    return _scan(text, "rust", RUST_INERT_KINDS)


def _scan(text: str, language: str, kinds: tuple[str, ...]) -> list[tuple[int, int]] | None:
    """Scan once per text and node kinds, since every marker kind asks about the same text."""
    key = (text, language, kinds)
    if key not in _SPANS:
        spans = _scan_within_budget(text, language, kinds)
        if spans is None:
            return None
        _SPANS[key] = spans
    return _SPANS[key]


def _scan_within_budget(text: str, language: str, kinds: tuple[str, ...]) -> list[tuple[int, int]] | None:
    remaining = _BUDGET.deadline - time.monotonic()
    if remaining <= 0:
        _BUDGET.ran_out = True
        return None
    try:
        encoded = text.encode()
        # An empty config of its own in a fresh private directory, so ast-grep looks for no sgconfig.yml.
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sgconfig.yml"
            config.write_text("ruleDirs: []\n")
            result = subprocess.run(
                (
                    SCANNER,
                    "scan",
                    "--config",
                    str(config),
                    "--stdin",
                    "--inline-rules",
                    _rule(language, kinds),
                    "--json=stream",
                ),
                # ast-grep would apply the suppressions in the text to this scan too and hide the comments below them.
                input=text.replace(SUPPRESSION, STAND_IN).encode(),
                capture_output=True,
                timeout=remaining,
                check=False,
                cwd=directory,
            )
        records = [json.loads(line) for line in result.stdout.decode().splitlines() if line.strip()]
        offsets = [record["range"]["byteOffset"] for record in records]
        spans = [(_characters(encoded, offset["start"]), _characters(encoded, offset["end"])) for offset in offsets]
    except subprocess.TimeoutExpired:
        _BUDGET.ran_out = True
        return None
    except OSError, ValueError, KeyError, TypeError:
        return None
    return spans if result.returncode == 0 else None


def _rule(language: str, kinds: tuple[str, ...]) -> str:
    matchers = "".join(f"\n    - kind: {kind}" for kind in kinds)
    return f"id: node\nlanguage: {language}\nrule:\n  any:{matchers}\n"


def _characters(encoded: bytes, offset: int) -> int:
    return len(encoded[:offset].decode(errors="replace"))
