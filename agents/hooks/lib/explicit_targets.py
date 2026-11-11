"""Resolve the test paths a project maps to changed files in related_test_extensions.json."""

import fnmatch
import json
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

TARGET_LANGUAGES = {
    ".bats": "bats",
    ".py": "python",
    ".rs": "rust",
    ".go": "go",
    ".js": "javascript_typescript",
    ".jsx": "javascript_typescript",
    ".ts": "javascript_typescript",
    ".tsx": "javascript_typescript",
    ".mts": "javascript_typescript",
    ".cts": "javascript_typescript",
    ".mjs": "javascript_typescript",
    ".cjs": "javascript_typescript",
}


def strings(value: object) -> bool:
    """Recognize arrays of nonempty strings at configuration boundaries."""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def project_targets(
    root: Path, changed: tuple[str, ...]
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str]]:
    """Resolve explicit mappings and track the changed files each language covers.

    Both mappings are keyed by language name and yield an empty set for a language no mapping reaches.
    """
    targets: dict[str, set[str]] = defaultdict(set)
    covered: dict[str, set[str]] = defaultdict(set)
    path = root / ".agents/hooks/rules/related_test_extensions.json"
    if not path.exists():
        return targets, covered, []
    try:
        mappings = json.loads(path.read_text())
        if not isinstance(mappings, dict) or not all(key and strings(value) for key, value in mappings.items()):
            raise ValueError("Expected an object mapping patterns to arrays of nonempty test paths.")
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Invalid configuration: {path}. Expected an object mapping patterns to arrays of nonempty test paths."
        ) from error
    errors: list[str] = []
    for target, matched_files in mapped_targets(mappings, changed):
        language, error = target_language(root, target)
        if error:
            errors.append(error)
            continue
        targets[language].add(target)
        covered[language] |= matched_files
    return targets, covered, errors


def mapped_targets(mappings: dict, changed: tuple[str, ...]) -> Iterator[tuple[str, set[str]]]:
    """Yield each configured test path with the changed files its pattern matches."""
    for pattern, paths in mappings.items():
        matched_files = {filename for filename in changed if fnmatch.fnmatchcase(filename, pattern)}
        if not matched_files:
            continue
        for target in paths:
            yield str(Path(target)), matched_files


def target_language(root: Path, target: str) -> tuple[str, str]:
    """Classify a configured test path as its runner language, or explain why it cannot run."""
    absolute = root / target
    if not absolute.exists():
        return "", f"Configured test target does not exist: {target}"
    if absolute.is_dir():
        return "bats", ""
    if language := TARGET_LANGUAGES.get(absolute.suffix):
        return language, ""
    return "", f"Unsupported configured test target: {target}"
