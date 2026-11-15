"""Find the comments that hold a word with ast-grep's tree-sitter grammars, which know every string form.

Hand-written lexers miss block scalars, raw strings and similar constructs, and ast-grep itself honors a
suppression only in a comment node, so the same parser decides here.
"""

import json
import shutil
import subprocess
import tempfile

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
STAND_IN = "guardcommentmarkerstandin"


def comment_spans(text: str, suffix: str, word: str) -> list[tuple[int, int]] | None:
    """The start and end offsets of each comment in `text` that holds `word`, or None when they cannot be known.

    None means the suffix has no grammar, the scanner is missing, or it failed; the caller must then fail closed.
    """
    language = LANGUAGES.get(suffix)
    if language is None or shutil.which(SCANNER) is None:
        return None
    encoded = text.encode()
    # ast-grep would apply the suppressions in the text to this scan too and hide comments below a marker, so the
    # word is replaced by a stand-in of the same length, which keeps every offset.
    stand_in = STAND_IN[: len(word)].ljust(len(word), "_")
    try:
        # A fresh private directory, so no sgconfig.yml there changes how the rule is read.
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                (SCANNER, "scan", "--stdin", "--inline-rules", _rule(language, stand_in), "--json=stream"),
                input=text.replace(word, stand_in).encode(),
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


def _rule(language: str, word: str) -> str:
    kinds = "".join(f"\n    - kind: {kind}" for kind in COMMENT_KINDS.get(language, ("comment",)))
    return f"id: comment\nlanguage: {language}\nrule:\n  regex: {json.dumps(word)}\n  any:{kinds}\n"


def _characters(encoded: bytes, offset: int) -> int:
    return len(encoded[:offset].decode(errors="replace"))
