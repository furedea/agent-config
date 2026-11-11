"""Describe a judgement to the agent in a bounded, advisory message."""

from model_rules_outcome import Finding, Judgement

MAX_FINDINGS = 10
MESSAGE_LIMIT_CHARS = 400


def describe(judgement: Judgement) -> str:
    """List the findings with where they are and how far past the cutoff they scored, then what the cap left out."""
    lines = [
        f"Model rules (advisory) · {len(judgement.findings)} finding(s) in this session's changes. "
        "Fix each one, or say why it does not apply."
    ]
    lines += [_line(finding) for finding in judgement.findings[:MAX_FINDINGS]]
    if len(judgement.findings) > MAX_FINDINGS:
        lines.append(f"... and {len(judgement.findings) - MAX_FINDINGS} more")
    lines.append(_footer(judgement))
    return "\n".join(lines)


def describe_clean(judgement: Judgement) -> str:
    """The one-line result of a review that reported nothing."""
    return f"Model rules · no findings · {_footer(judgement)}"


def _line(finding: Finding) -> str:
    score = (
        ""
        if finding.score is None or finding.cutoff is None
        else f" (score {finding.score:.2f}, cutoff {finding.cutoff:.2f})"
    )
    message = finding.message.strip().replace("\n", " ")[:MESSAGE_LIMIT_CHARS]
    return f"- {finding.rule} · {finding.file}:{finding.line}{score}\n  {message}"


def _footer(judgement: Judgement) -> str:
    parts = [
        f"judged {judgement.judged} of {judgement.subjects} subject(s) in {judgement.seconds:.1f}s",
        f"{judgement.requests} request(s)",
        f"{judgement.cached} cached",
    ]
    if judgement.skipped_subjects:
        skipped = (
            f"{judgement.skipped_subjects} subject(s) in {judgement.skipped_files} file(s) skipped by the cap of 20"
        )
        parts.append(f"{skipped}, judged at the next Stop" if judgement.resumable else skipped)
    if judgement.withheld_files:
        parts.append(f"{judgement.withheld_files} file(s) withheld: links or outside the repository")
    return ", ".join(parts)
