"""Recognise a finding the agent was already shown in a session, by its rule and its subject's current text."""

import hashlib
from pathlib import Path

from model_rules_outcome import Finding


def fingerprint(root: Path, finding: Finding) -> str:
    """Identify a finding by rule, file and the text of its subject, so that a moved subject keeps its identity.

    The subject is read from the working tree, so a change anywhere in it makes the finding new again. A subject that
    cannot be read is identified by the rule and file alone.
    """
    digest = hashlib.sha256()
    for part in (finding.rule_key or finding.rule, finding.file, _subject_text(root, finding)):
        digest.update(part.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _subject_text(root: Path, finding: Finding) -> str:
    path = (root / finding.file).resolve()
    try:
        path.relative_to(root.resolve())
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError, ValueError:
        return ""
    return "\n".join(lines[max(finding.line, 1) - 1 : max(finding.end_line, finding.line)])
