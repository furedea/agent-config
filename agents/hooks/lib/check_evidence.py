"""Interpret runner evidence and order summaries independently of execution."""

import re
from dataclasses import dataclass

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TAP_FOOTER = re.compile(r"^\S (pass|fail|cancelled|skipped|todo) (\d+)")
OUTCOME_KIND = {
    "passed": "passed",
    "pass": "passed",
    "failed": "failed",
    "fail": "failed",
    "cancelled": "failed",
    "skipped": "skipped",
    "todo": "skipped",
    "ignored": "skipped",
}
DISPLAY_ORDER = {
    "pytest": 0,
    "rust": 1,
    "go": 1,
    "vitest": 2,
    "jest": 2,
    "node": 2,
    "npm test": 2,
    "pnpm test": 2,
    "yarn test": 2,
    "bun test": 2,
    "javascript_typescript": 2,
    "Bats": 3,
}


@dataclass(frozen=True, slots=True)
class Evidence:
    """A runner summary and the number of actual observations, when knowable."""

    summary: str
    executed: int | None


def ordered_lines(lines: list[str]) -> list[str]:
    """Order language summaries without changing their evidence."""
    return sorted(lines, key=lambda line: DISPLAY_ORDER.get(line.partition(":")[0], -1))


def summarize(label: str, output: str) -> Evidence:
    """Read supported runner output; unrecognized output remains explicitly unknown."""
    lines = ANSI.sub("", output).splitlines()
    if label == "bats":
        return summarize_bats(lines)
    if label == "go":
        return summarize_go(lines)
    if label == "pytest":
        summaries = [
            line
            for line in lines
            if re.match(r"^[= ]*\d+ (passed|failed|skipped|error|xfailed|xpassed|deselected)", line)
        ]
        if not summaries:
            return Evidence("test count unavailable", None)
        summary = re.sub(r" in [0-9.]+s.*$", "", summaries[-1].strip("= "))
        executed = sum(int(count) for count in re.findall(r"(\d+) (?:passed|failed|xfailed|xpassed)\b", summary))
        return Evidence(re.sub(r", 0 (failed|skipped)", "", summary), executed)
    if label == "rust":
        return summarize_rust(lines)
    return summarize_javascript(lines)


@dataclass(frozen=True, slots=True)
class Counts:
    """Outcome totals of one runner invocation, reported as `N passed[, F failed][, S skipped]`."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @classmethod
    def tally(cls, found: list[tuple[str, str]]) -> Counts:
        """Sum (count, outcome) pairs; todo and ignored tests count as skipped."""
        totals = {"passed": 0, "failed": 0, "skipped": 0}
        for count, outcome in found:
            totals[OUTCOME_KIND[outcome]] += int(count)
        return cls(**totals)

    def evidence(self, skipped_word: str = "skipped") -> Evidence:
        """Name the skipped count with the runner's own word; observations are passed plus failed."""
        summary = f"{self.passed} passed"
        if self.failed:
            summary += f", {self.failed} failed"
        if self.skipped:
            summary += f", {self.skipped} {skipped_word}"
        return Evidence(summary, self.passed + self.failed)


def summarize_rust(lines: list[str]) -> Evidence:
    """Sum every `test result:` line; cargo prints one per test binary."""
    results = [line for line in lines if line.startswith("test result:")]
    if not results:
        return Evidence("test count unavailable", None)
    return Counts.tally(
        [pair for line in results for pair in re.findall(r"(\d+) (passed|failed|ignored);", line)]
    ).evidence("ignored")


def summarize_javascript(lines: list[str]) -> Evidence:
    """Sum every vitest/jest `Tests` line or node footer (TAP or spec); repeated runs add up to one count."""
    tests_lines = [line for line in lines if re.match(r"^\s*Tests[:\s]", line)]
    if tests_lines:
        return Counts.tally(
            [pair for line in tests_lines for pair in re.findall(r"(\d+) (passed|failed|skipped|todo)\b", line)]
        ).evidence()
    footer = [(match[2], match[1]) for match in map(TAP_FOOTER.match, lines) if match]
    if any(outcome in {"pass", "fail", "cancelled"} for _, outcome in footer):
        return Counts.tally(footer).evidence()
    if any(re.match(r"^\s*No test (files|suites|tests)?\s*found", line) for line in lines):
        return Evidence("test count unavailable", 0)
    return Evidence("test count unavailable", None)


def summarize_go(lines: list[str]) -> Evidence:
    """Count packages whose tests ran; `go test` without -v reports no per-test counts."""
    tested = untested = 0
    for line in lines:
        if re.match(r"^(ok|FAIL)\s", line) and "[no tests to run]" not in line:
            tested += 1
        elif re.match(r"^(\?|ok)\s", line) and re.search(r"\[no (test files|tests to run)\]", line):
            untested += 1
    if not tested and not untested:
        return Evidence("test count unavailable", None)
    summary = f"{tested} packages tested"
    if untested:
        summary += f", {untested} without tests"
    return Evidence(summary, tested)


def summarize_bats(lines: list[str]) -> Evidence:
    """Count TAP observations, retaining partial-plan and skipped-test information."""
    planned: int | None = None
    passed = failed = skipped = 0
    for line in lines:
        if match := re.match(r"^1\.\.(\d+)", line):
            planned = int(match[1])
        if not re.match(r"^(not )?ok \d+( |$)", line):
            continue
        if re.search(r"#\s*skip(?:\s|$)", line, re.IGNORECASE):
            skipped += 1
        elif line.startswith("not ok"):
            failed += 1
        else:
            passed += 1
    observed = passed + failed + skipped
    if planned is None and not observed:
        return Evidence("test count unavailable", None)
    summary = f"{passed} passed"
    if failed:
        summary += f", {failed} failed"
    if skipped:
        summary += f", {skipped} skipped"
    if planned is not None and planned != observed:
        summary += f" (partial results; {planned} planned)"
    return Evidence(summary, passed + failed)


def first_error(output: str) -> str:
    """Prefer a runner failure line over its banner without exposing unbounded output."""
    lines = [line for line in ANSI.sub("", output).splitlines() if line.strip()]
    failure = next((line for line in lines if re.match(r"^(not ok \d+|FAILED |E\s+)", line)), None)
    return (failure or next(iter(lines), ""))[:240]
