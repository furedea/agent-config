"""Describe a judgement as one result line, like a test line, and as the instruction a block gives the agent."""

from model_rules_outcome import Finding, Judgement

MAX_FINDINGS = 10
INSTRUCTION = "Fix each one, or say why it does not apply."
PREFIX = "jev-lint"


def describe_line(judgement: Judgement) -> str:
    """The result line: findings, subjects judged, the state, the cost and the seconds taken."""
    parts = [
        _counted(len(judgement.findings), "finding"),
        _subjects(judgement),
        "advisory" if judgement.findings else "passed",
        f"${judgement.usd:.4f}",
        f"{judgement.seconds:.1f}s",
    ]
    if judgement.withheld_files:
        parts.append(f"{judgement.withheld_files} withheld: links or outside the repository")
    return _line(parts)


def describe_details(judgement: Judgement) -> str:
    """What only a block reason carries: the instruction and one `- rule · file:line` per finding."""
    if not judgement.findings:
        return ""
    lines = [INSTRUCTION, *(_finding_line(finding) for finding in judgement.findings[:MAX_FINDINGS])]
    if len(judgement.findings) > MAX_FINDINGS:
        lines.append(f"... and {len(judgement.findings) - MAX_FINDINGS} more")
    return "\n".join(lines)


def describe_unchanged(findings: int) -> str:
    """The line for inputs that were judged before and are not judged again."""
    return _line([_counted(findings, "finding"), "unchanged; not rerun"])


def describe_skipped(reason: str) -> str:
    """The line for a review that did not run or did not finish."""
    return _line(["skipped", reason])


def _line(parts: list[str]) -> str:
    return f"{PREFIX}: {' · '.join(parts)}"


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _subjects(judgement: Judgement) -> str:
    if judgement.skipped_subjects:
        return f"{judgement.judged}/{_counted(judgement.subjects, 'subject')}"
    return _counted(judgement.subjects, "subject")


def _finding_line(finding: Finding) -> str:
    return f"- {finding.rule} · {finding.file}:{finding.line}"
