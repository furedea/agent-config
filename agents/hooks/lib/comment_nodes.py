"""Find the comments in source text with ast-grep's tree-sitter grammars, which know every string form.

Hand-written lexers miss block scalars, raw strings and similar constructs, and ast-grep itself honors a
suppression only in a comment node, so the same parser decides here.
"""

import functools
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

SCANNER = "ast-grep"
TIMEOUT_SECONDS = 10
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
COMMENT_KINDS = {"rust": ("line_comment", "block_comment")}
SUPPRESSION = "ast-grep-ignore"
# Same length as the suppression word, so every offset stays.
STAND_IN = "ast-grep-ign0re"


def comment_spans(text: str, suffix: str) -> list[tuple[int, int]] | None:
    """The start and end offsets of each comment in `text`, or None when they cannot be known.

    None means the suffix has no grammar, the scanner is missing, or it failed; the caller must then fail closed.
    """
    language = LANGUAGES.get(suffix)
    if language is None or shutil.which(SCANNER) is None:
        return None
    return _scan(text, language, SCANNER)


@functools.cache
def _scan(text: str, language: str, scanner: str) -> list[tuple[int, int]] | None:
    """Scan once per text, since every marker kind asks about the same text."""
    encoded = text.encode()
    try:
        # An empty config of its own in a fresh private directory, so ast-grep looks for no sgconfig.yml.
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sgconfig.yml"
            config.write_text("ruleDirs: []\n")
            result = subprocess.run(
                (
                    scanner,
                    "scan",
                    "--config",
                    str(config),
                    "--stdin",
                    "--inline-rules",
                    _rule(language),
                    "--json=stream",
                ),
                # ast-grep would apply the suppressions in the text to this scan too and hide the comments below them.
                input=text.replace(SUPPRESSION, STAND_IN).encode(),
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
                cwd=directory,
            )
        records = [json.loads(line) for line in result.stdout.decode().splitlines() if line.strip()]
        offsets = [record["range"]["byteOffset"] for record in records]
        spans = [(_characters(encoded, offset["start"]), _characters(encoded, offset["end"])) for offset in offsets]
    except OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError:
        return None
    return spans if result.returncode == 0 else None


def _rule(language: str) -> str:
    kinds = "".join(f"\n    - kind: {kind}" for kind in COMMENT_KINDS.get(language, ("comment",)))
    return f"id: comment\nlanguage: {language}\nrule:\n  any:{kinds}\n"


def _characters(encoded: bytes, offset: int) -> int:
    return len(encoded[:offset].decode(errors="replace"))
