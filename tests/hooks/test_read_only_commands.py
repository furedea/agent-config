"""Which calls the words alone show to write no file and run no other program (#255)."""

import shlex
import sys

import pytest
from tests.runtime import load_script_module

load_script_module("agents/hooks/guard_command.py", "guard_command")
read_only_commands = sys.modules["read_only_commands"]


def writes_nothing(line: str) -> bool:
    words = shlex.split(line)
    return read_only_commands.writes_nothing(words, [False] * len(words))


@pytest.mark.parametrize(
    "line",
    [
        "sort -t , -k 2 notes.txt",
        "sort -t -o notes.txt",
        "sort -rn",
        "uniq -c",
        "awk -v x=1 -F: '{print $1}' notes.txt",
        "sed -n -e 1p -e '/a/,/b/p' notes.txt",
        "sed 's/a/b/g'",
        "base64 -d",
    ],
)
def test_a_reading_call_writes_nothing(line: str) -> None:
    assert writes_nothing(line)


@pytest.mark.parametrize(
    "line",
    [
        "sort -o out notes.txt",
        "sort -t , -o out",
        "sort --output=out",
        "uniq in out",
        "awk -f prog.awk",
        "awk '{print > \"out\"}'",
        "sed -e p -e 'w out'",
        "sed 's/a/b/w out'",
        "sed -i s/a/b/ notes.txt",
        "git log --oneline -3",
        "git status",
        "base64 -o out",
        "tee out",
    ],
)
def test_a_call_that_may_write_or_run_a_program_is_not_read_only(line: str) -> None:
    assert not writes_nothing(line)


def test_a_word_known_only_at_run_time_is_read_only_only_for_a_filter() -> None:
    assert read_only_commands.writes_nothing(["head", "$N"], [False, True])
    assert not read_only_commands.writes_nothing(["printf", "$OPT", "PATH", "/tmp"], [False, True, False, False])
    assert not read_only_commands.writes_nothing(["echo", "$WORDS"], [False, True])
    assert not read_only_commands.writes_nothing(["sort", "$OPTIONS"], [False, True])


@pytest.mark.parametrize(
    "format_",
    [
        "x%n",
        "x%5n",
        "x%-n",
        "x%#0 +'n",
        "x%.3n",
        "x%*n",
        "x%.*n",
        "x%hhn",
        "x%lln",
        "x%Ln",
        "x%zn",
        "x%1$n",
        "x%%%n",
        r"x\u0025n",
        r"x\U00000025n",
        r"x%\x6e",
        r"x%l\156",
    ],
)
def test_a_printf_format_assigning_a_count_with_n_is_not_read_only(format_: str) -> None:
    """bash and zsh store the count of printed characters into the variable an operand names."""
    assert not read_only_commands.writes_nothing(["printf", format_, "PATH"], [False] * 3)
    assert not read_only_commands.writes_nothing(["printf", "--", format_, "PATH"], [False] * 4)


@pytest.mark.parametrize("format_", ["%s\\n", "x%%n", "100%%", "%d items", r"x\045n", "%s", "-n"])
def test_a_printf_format_without_an_n_conversion_writes_nothing(format_: str) -> None:
    assert read_only_commands.writes_nothing(["printf", format_, "n"], [False] * 3)


def test_a_printf_format_with_an_escape_beyond_unicode_is_still_judged() -> None:
    assert read_only_commands.writes_nothing(["printf", r"\UFFFFFFFF"], [False] * 2)
