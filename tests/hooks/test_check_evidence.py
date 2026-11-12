"""Runner output is evidence only for observations it actually reports."""

import pytest
from tests.runtime import load_script_module

output = load_script_module("agents/hooks/lib/check_evidence.py", "check_evidence")


@pytest.mark.parametrize(
    ("label", "text", "executed"),
    [
        ("bats", "1..1\nok 1 skipped # skip unavailable service", 0),
        ("bats", "1..2\nok 1 first\nnot ok 2 second", 2),
        ("bats", "1..0", 0),
        ("pytest", "2 passed, 3 skipped in 0.1s", 2),
        ("pytest", "3 skipped in 0.1s", 0),
        ("rust", "test result: ok. 2 passed; 0 failed;\ntest result: ok. 0 passed; 0 failed;", 2),
        ("rust", "test result: ok. 0 passed; 0 failed; 12 filtered out;", 0),
        ("go", "ok  \texample/a\t0.01s\n?   \texample/b\t[no test files]", 1),
        ("go", "ok  \texample/a\t(cached)\nFAIL\texample/b\t0.02s", 2),
        ("go", "?   \texample/a\t[no test files]", 0),
        ("go", "?   \texample/a\t[no test files]\n?   \texample/b\t[no test files]", 0),
        ("go", "ok  \texample/a\t0.01s [no tests to run]", 0),
        ("go", "go: updates to go.mod needed", None),
        ("vitest", "No test files found", 0),
        ("vitest", "Tests  3 passed (3)", 3),
        ("node", "# pass 2\n# fail 1", 3),
        ("pytest", "unrecognized runner output", None),
    ],
)
def test_executed_count_distinguishes_absence_from_unknown(label: str, text: str, executed: int | None) -> None:
    assert output.summarize(label, text).executed == executed


CARGO_TWO_BINARIES = """\
running 3 tests
test result: ok. 3 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s

running 2 tests
test result: FAILED. 2 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
"""
NODE_TAP_FOOTER = """\
# tests 5
# suites 0
# pass 3
# fail 1
# cancelled 0
# skipped 1
# todo 0
# duration_ms 52.1
"""
NODE_TAP_ALL_PASS = "# tests 2\n# suites 0\n# pass 2\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n"
VITEST_OUTPUT = (
    " Test Files  2 passed (2)\n      Tests  1 failed | 2 skipped | 1 todo | 9 passed (13)\n   Duration  1.2s"
)
VITEST_ALL_PASS = " Test Files  1 passed (1)\n      Tests  12 passed (12)"
JEST_OUTPUT = "Test Suites: 1 failed, 1 total\nTests:       1 failed, 2 skipped, 1 todo, 4 passed, 8 total"
JEST_ALL_PASS = "Tests:       5 passed, 5 total"


@pytest.mark.parametrize(
    ("label", "text", "summary"),
    [
        ("rust", CARGO_TWO_BINARIES, "5 passed, 1 failed, 1 ignored"),
        ("rust", "test result: ok. 312 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out", "312 passed"),
        ("node", NODE_TAP_FOOTER, "3 passed, 1 failed, 1 skipped"),
        ("node", NODE_TAP_ALL_PASS, "2 passed"),
        ("npm test", NODE_TAP_FOOTER, "3 passed, 1 failed, 1 skipped"),
        ("bun test", NODE_TAP_ALL_PASS, "2 passed"),
        ("vitest", VITEST_OUTPUT, "9 passed, 1 failed, 3 skipped"),
        ("vitest", VITEST_ALL_PASS, "12 passed"),
        ("jest", JEST_OUTPUT, "4 passed, 1 failed, 3 skipped"),
        ("jest", JEST_ALL_PASS, "5 passed"),
        ("go", "ok  \texample/a\t0.01s\nok  \texample/b\t0.02s", "2 packages tested"),
        ("pytest", "= 4 passed, 1 skipped in 0.1s =", "4 passed, 1 skipped"),
        ("bats", "1..2\nok 1 a\nnot ok 2 b", "1 passed, 1 failed"),
    ],
)
def test_every_runner_reports_one_count_line(label: str, text: str, summary: str) -> None:
    assert output.summarize(label, text).summary == summary


@pytest.mark.parametrize(
    ("label", "text", "executed"),
    [
        ("rust", CARGO_TWO_BINARIES, 6),
        ("node", NODE_TAP_FOOTER, 4),
        ("vitest", VITEST_OUTPUT, 10),
        ("jest", JEST_OUTPUT, 5),
    ],
)
def test_executed_excludes_skipped_and_ignored_tests(label: str, text: str, executed: int) -> None:
    assert output.summarize(label, text).executed == executed


@pytest.mark.parametrize("label", ["rust", "node", "npm test", "vitest", "jest"])
def test_unrecognized_runner_output_stays_unavailable(label: str) -> None:
    assert output.summarize(label, "smoke: ok\nall scripts passed") == output.Evidence("test count unavailable", None)


def test_partial_bats_plan_is_visible() -> None:
    assert output.summarize("bats", "1..3\nok 1 first").summary == "1 passed (partial results; 3 planned)"


def test_bats_summary_preserves_skipped_tests() -> None:
    assert output.summarize("bats", "1..3\nok 1 a\nok 2 b\nok 3 c # SKIP offline").summary == "2 passed, 1 skipped"


def test_diagnostic_prefers_actual_failure_over_runner_banner() -> None:
    assert output.first_error("starting runner\nFAILED test_example\nmore details") == "FAILED test_example"


@pytest.mark.parametrize("runner", ["vitest", "jest", "node", "npm test", "pnpm test", "yarn test", "bun test"])
def test_javascript_runner_summaries_follow_rust_and_precede_bats(runner: str) -> None:
    lines = [
        "Bats: 50 passed · 11 targets · 33.8s",
        f"{runner}: 3 passed · full suite · 0.5s",
        "rust: 2 passed · full suite · 0.3s",
        "pytest: 989 passed · 38 files · 140.0s",
    ]
    assert output.ordered_lines(lines) == [lines[3], lines[2], lines[1], lines[0]]
    assert lines[0].startswith("Bats:")


def test_display_order_preserves_multiple_results_and_configuration_errors() -> None:
    lines = [
        "configuration: unavailable · project test rules",
        "Bats: 1 passed · 1 targets · 0.1s",
        "rust: 2 passed · unit filter first · 0.2s",
        "pytest: 3 passed · 1 files · 0.3s",
        "rust: 4 passed · integration target second · 0.4s",
    ]
    assert output.ordered_lines(lines) == [lines[0], lines[3], lines[2], lines[4], lines[1]]
