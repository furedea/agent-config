"""The values the Stop-time model rules pass between their steps."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Prevented:
    """Why the model rules did not run or did not finish; reported in one line and never blocks Stop."""

    reason: str


@dataclass(frozen=True, slots=True)
class Finding:
    """One reported rule violation, with the score and cutoff the model judged it by."""

    rule: str
    file: str
    line: int
    message: str
    score: float | None = None
    cutoff: float | None = None


@dataclass(frozen=True, slots=True)
class Resumable:
    """A file that one kind of review skipped for the cap and that a later Stop on the same inputs can still judge.

    The commits and the uncommitted changes are separate reviews, each with its own subjects in a file, so the
    skipped file is remembered per review.
    """

    review: str
    file: str


@dataclass(frozen=True, slots=True)
class Plan:
    """What one review will judge: the files to pass (empty means the whole diff) and what the cap left out.

    `cost` counts the subjects the model will be asked about, so those already in the verdict cache are not charged
    against the cap.
    """

    paths: tuple[str, ...]
    subjects: int
    cost: int
    skipped_files: int = 0
    skipped_subjects: int = 0
    resumable: tuple[str, ...] = ()

    @property
    def judged(self) -> int:
        """How many subjects the review will pass to the model, cached ones included."""
        return self.subjects - self.skipped_subjects


@dataclass(frozen=True, slots=True)
class Judgement:
    """The findings of the reviews of one Stop with the work they took.

    `resumable` names the skipped files a later Stop on the same inputs can still judge; a file the cap can never
    admit, or that cannot be passed as an argument, is counted as skipped but is not named.
    """

    findings: tuple[Finding, ...]
    subjects: int = 0
    skipped_files: int = 0
    skipped_subjects: int = 0
    requests: int = 0
    cached: int = 0
    withheld_files: int = 0
    resumable: tuple[Resumable, ...] = ()
    seconds: float = 0.0

    @property
    def judged(self) -> int:
        """How many subjects were passed to the model, cached ones included."""
        return self.subjects - self.skipped_subjects

    def combined(self, other: Judgement) -> Judgement:
        """Add another review's result; a finding at the same rule, file and line is kept once."""
        known = {(finding.rule, finding.file, finding.line) for finding in self.findings}
        added = tuple(item for item in other.findings if (item.rule, item.file, item.line) not in known)
        return Judgement(
            self.findings + added,
            self.subjects + other.subjects,
            self.skipped_files + other.skipped_files,
            self.skipped_subjects + other.skipped_subjects,
            self.requests + other.requests,
            self.cached + other.cached,
            self.withheld_files + other.withheld_files,
            tuple(dict.fromkeys(self.resumable + other.resumable)),
            self.seconds + other.seconds,
        )
