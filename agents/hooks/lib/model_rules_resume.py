"""Keep the part of a Stop run that completed in the receipt, so a failed later review is retried alone."""

from dataclasses import asdict

from model_rules_outcome import Finding, Judgement, Resume

_COUNTS = ("subjects", "skipped_files", "skipped_subjects", "requests", "cached")


def dump(resume: Resume) -> dict:
    """The receipt form of a resume: plain JSON values."""
    part = resume.judgement
    return {
        "completed": resume.completed,
        "spent": resume.spent,
        "part": {
            "findings": [asdict(finding) for finding in part.findings],
            "usd": part.usd,
            **{name: getattr(part, name) for name in _COUNTS},
        },
    }


def load(record: object) -> Resume | None:
    """The resume a receipt holds, or None when it holds none or what it holds cannot be trusted."""
    if not isinstance(record, dict):
        return None
    try:
        part = record["part"]
        findings = tuple(_finding(item) for item in part["findings"])
        judgement = Judgement(
            findings,
            _integer(part["subjects"]),
            _integer(part["skipped_files"]),
            _integer(part["skipped_subjects"]),
            _integer(part["requests"]),
            _integer(part["cached"]),
            usd=_number(part["usd"]),
        )
        return Resume(_integer(record["completed"]), _integer(record["spent"]), judgement)
    except KeyError, TypeError, ValueError:
        return None


def _finding(item: dict) -> Finding:
    if not isinstance(item, dict):
        raise TypeError("reading a resume from the receipt: a finding must be an object")
    rule, file, message = item["rule"], item["file"], item["message"]
    if not all(isinstance(text, str) for text in (rule, file, message)):
        raise TypeError("reading a resume from the receipt: finding fields must be strings")
    scores = tuple(None if item[key] is None else _number(item[key]) for key in ("score", "cutoff"))
    return Finding(rule, file, _integer(item["line"]), message, *scores)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"reading a resume from the receipt: expected an integer, got {value!r}")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"reading a resume from the receipt: expected a number, got {value!r}")
    return float(value)
