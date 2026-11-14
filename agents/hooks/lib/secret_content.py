"""Find secrets in text with the PCRE2 patterns of secret_content_patterns.json, without logging the text."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SecretMatch:
    """The pattern that matched and the message it reports."""

    name: str
    message: str


def first_match(text: str, path: Path) -> SecretMatch | None:
    """The first pattern, in name order, that matches the text; none when the text is empty or the file is missing."""
    if not text or not path.is_file():
        return None
    rules = json.loads(path.read_text())
    for name in sorted(rules):
        rule = rules[name]
        if not rule.get("pattern"):
            continue
        result = subprocess.run(
            ["rg", "--pcre2", "-q", "-e", rule["pattern"], "-"],
            input=text + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode > 1:
            raise ValueError(f"invalid sensitive content rule: {name}")
        if result.returncode == 0:
            return SecretMatch(name, rule.get("message", "Sensitive information detected"))
    return None
