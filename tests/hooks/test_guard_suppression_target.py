"""A suppression that keeps its place but names other or fewer rules suppresses something new, so it asks."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_target")


def decide_edit(target: Path, old: str, new: str) -> str:
    values = {"file_path": str(target), "old_string": old, "new_string": new}
    return guard.decide({"tool_name": "Edit", "tool_input": values}).decision


@pytest.mark.parametrize(
    "name,before,old,new",
    [
        ("user.go", "f() //nolint:errcheck // read-only\n", "//nolint:errcheck", "//nolint"),
        ("user.go", "f() //nolint:errcheck // read-only\n", "//nolint:errcheck", "//nolint:govet"),
        ("app.py", "x = 1  # noqa: E501\n", "# noqa: E501", "# noqa"),
        ("app.py", "x = 1  # noqa: E501\n", "# noqa: E501", "# noqa: E731"),
        ("app.py", "x = f()  # type: ignore[attr-defined]\n", "[attr-defined]", ""),
        ("app.ts", "// eslint-disable-next-line no-console\nfoo()\n", " no-console", ""),
        ("app.ts", "/* eslint-disable\n  no-console\n*/\nfoo()\n", "no-console", "no-console, no-alert"),
        ("lib.rs", "#[allow(dead_code)]\nfn a() {}\n", "dead_code", "dead_code, unused"),
        ("lib.rs", "#[allow(\n    dead_code,\n)]\nfn a() {}\n", "dead_code,", "dead_code,\n    unused,"),
        ("lib.rs", "#[expect(clippy::too_many_lines)]\nfn a() {}\n", "clippy::too_many_lines", "clippy::all"),
        ("run.sh", "# shellcheck disable=SC2086\necho $x\n", "SC2086", "SC2086,SC2046"),
        ("lib.rs", "#[allow(a, /* #[allow( */ b)]\nfn f() {}\n", "b)]", "b, c)]"),
        ("lib.rs", "#[allow(a /* ] */, b)]\nfn f() {}\n", "b)]", "b, c)]"),
        ("lib.rs", '#[allow(a, b = "]", c)]\nfn f() {}\n', "c)]", "c, d)]"),
        ("lib.rs", "#[allow(a,\n    b,\n", "b,", "b, c,"),
    ],
    ids=[
        "nolint loses its linter",
        "nolint names another linter",
        "noqa loses its code",
        "noqa names another code",
        "type ignore loses its code",
        "eslint directive loses its rule",
        "eslint block comment gains a rule on another line",
        "allow gains a lint",
        "multi-line allow gains a lint on its own line",
        "expect names another lint",
        "shellcheck gains a code",
        "allow gains a lint after a marker in its comment",
        "allow gains a lint after a bracket in its comment",
        "allow gains a lint after a bracket in its string",
        "unclosed allow gains a lint below",
    ],
)
def test_changing_what_a_suppression_names_asks(tmp_path: Path, name: str, before: str, old: str, new: str) -> None:
    target = tmp_path / name
    target.write_text(before)
    assert decide_edit(target, old, new) == "ask"


@pytest.mark.parametrize(
    "name,before,old,new",
    [
        ("lib.rs", "#[allow(dead_code)] fn a() {}\n", "fn a()", "fn b()"),
        ("user.go", "f() //nolint:errcheck // read-only\n", "f()", "g()"),
        ("app.py", "x = 1  # noqa: E501\ny = 2\n", "x = 1  # noqa: E501\ny = 2", "y = 2\nx = 1  # noqa: E501"),
        ("app.py", "x = 1  # noqa: E501\ny = 2  # noqa: E731\n", "  # noqa: E731", ""),
    ],
    ids=["code after an attribute", "code before a nolint", "a marker moved", "a marker removed"],
)
def test_keeping_what_every_suppression_names_passes(
    tmp_path: Path, name: str, before: str, old: str, new: str
) -> None:
    target = tmp_path / name
    target.write_text(before)
    assert decide_edit(target, old, new) == "allow"


@pytest.mark.parametrize(
    "name,before,old,new",
    [
        ("user.go", "f() //nolint:errcheck // clsoe file\n", "clsoe", "close"),
        ("app.py", "x = 1  # noqa: E501 long url, clsoe\n", "clsoe", "close"),
        ("app.ts", "// eslint-disable-next-line no-console -- clsoe\nfoo()\n", "clsoe", "close"),
        ("app.ts", "// biome-ignore lint/style: clsoe\nfoo()\n", "clsoe", "close"),
        ("app.ts", "// @ts-expect-error clsoe\nfoo()\n", "clsoe", "close"),
        ("lib.rs", '#[allow(dead_code, reason = "clsoe")]\nfn a() {}\n', "clsoe", "close"),
        ("run.sh", "# shellcheck disable=SC2086 # clsoe\necho $x\n", "clsoe", "close"),
        ("app.py", "x = f()  # type: ignore[attr-defined]  clsoe\n", "clsoe", "close"),
    ],
    ids=["nolint", "noqa", "eslint", "biome", "ts-expect-error", "allow", "shellcheck", "type ignore"],
)
def test_fixing_the_reason_beside_a_suppression_passes(
    tmp_path: Path, name: str, before: str, old: str, new: str
) -> None:
    target = tmp_path / name
    target.write_text(before)
    assert decide_edit(target, old, new) == "allow"
