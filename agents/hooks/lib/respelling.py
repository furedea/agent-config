"""Stand a call's words in for the positional parameters a function body reads."""

import re
import shlex
from dataclasses import dataclass

from shell_words import UnsupportedSyntaxError, literal_word, source_text, spreads

# $1, ${12}, $@, and $*, which take the words a function is called with.
POSITIONAL = re.compile(r"[1-9][0-9]*|[@*]")
# A caller's word that an unquoted expansion splits and globs no differently from its plain text.
PLAIN_FIELDS = re.compile(r"[A-Za-z0-9_./:=@%+,\s-]*")
# The count of a function's arguments: $# and zsh's ARGC.
ARGUMENT_COUNTS = frozenset({"#", "ARGC"})


def redirections(statement: dict) -> list[dict]:
    """The statement's redirections other than heredocs, whose targets a respelling rewrites."""
    return [redirect for redirect in statement.get("Redirs", []) if redirect.get("Word") and "Hdoc" not in redirect]


def counts_arguments(part: dict) -> bool:
    """Whether a part expands the count of the arguments."""
    return part.get("Type") == "ParamExp" and part.get("Param", {}).get("Value") in ARGUMENT_COUNTS


def reads(part: dict, copies: dict[str, str]) -> bool:
    """Whether a part expands a positional parameter, their count, or a plain copy of one."""
    return (
        is_positional(part)
        or counts_arguments(part)
        or (part.get("Type") == "ParamExp" and part["Param"]["Value"] in copies)
    )


def is_positional(part: dict) -> bool:
    """Whether a part expands a positional parameter."""
    return part.get("Type") == "ParamExp" and POSITIONAL.fullmatch(part.get("Param", {}).get("Value", "")) is not None


@dataclass(frozen=True, slots=True)
class Respelling:
    """A call's words, standing in for each positional parameter or plain copy of one.

    A copy taken before the first shift reads the words as they were before it.

    Inside quotes, the quotes close around the words.
    """

    words: list[dict]
    data: bytes
    copies: dict[str, str]
    # The words before any shift, which a copy taken before the first shift holds.
    unshifted: list[dict]
    early: frozenset[str]

    def statement(self, statement: dict) -> str:
        """The statement's assignments, call, and redirections, each word respelled."""
        assigns = [self._assignment(assign) for assign in statement["Cmd"].get("Assigns", [])]
        words = assigns + [self.word(word) for word in statement["Cmd"].get("Args", [])]
        redirects = [
            self.data[redirect["Pos"]["Offset"] : redirect["Word"]["Pos"]["Offset"]].decode()
            + self.word(redirect["Word"])
            for redirect in redirections(statement)
        ]
        return " ".join(words + redirects)

    def _assignment(self, assign: dict) -> str:
        """A prefix assignment such as X=$1, which a child sees, respelled; any other form as written."""
        if not isinstance(assign.get("Value"), dict) or assign.get("Array") or assign.get("Index"):
            return source_text(assign, self.data)
        return self.data[assign["Pos"]["Offset"] : assign["Value"]["Pos"]["Offset"]].decode() + self.word(
            assign["Value"]
        )

    def word(self, word: dict) -> str:
        """The word with each argument read respelled."""
        return "".join(self._part(part, quoted=False) for part in word.get("Parts", []))

    def _part(self, part: dict, *, quoted: bool) -> str:
        if counts_arguments(part):
            if any(spreads(word, self.data) for word in self.words):
                raise UnsupportedSyntaxError("counting function arguments that may split requires explicit review")
            return str(len(self.words))
        if reads(part, self.copies):
            name = self.copies.get(part["Param"]["Value"], part["Param"]["Value"])
            source = self.unshifted if part["Param"]["Value"] in self.early else self.words
            words = source if name in {"@", "*"} else source[int(name) - 1 : int(name)]
            if quoted and name == "*":
                return (
                    '"' + shlex.quote(" ".join(literal_word(word, self.data)[0] for word in self._plain(words))) + '"'
                )
            value = " ".join(filter(None, (self._spelled(word, quoted=quoted) for word in words)))
            value = value or ("''" if quoted else "")
            return f'"{value}"' if quoted else value
        if part.get("Type") == "DblQuoted" and not part.get("Dollar"):
            return '"' + "".join(self._part(item, quoted=True) for item in part.get("Parts", [])) + '"'
        return source_text(part, self.data)

    def _plain(self, words: list[dict]) -> list[dict]:
        """The words, once none is known only at run time or may expand into others."""
        if any(literal_word(word, self.data)[1] or spreads(word, self.data) for word in words):
            raise UnsupportedSyntaxError(
                "passing a function an argument known only at run time requires explicit review"
            )
        return words

    def _spelled(self, word: dict, *, quoted: bool) -> str:
        """The caller's word as the shell hands it over, requoted; unquoted, each field it splits into, or none."""
        value, dynamic = literal_word(word, self.data)
        if dynamic or spreads(word, self.data):
            raise UnsupportedSyntaxError(
                "passing a function an argument known only at run time requires explicit review"
            )
        if quoted:
            return shlex.quote(value)
        if not PLAIN_FIELDS.fullmatch(value):
            raise UnsupportedSyntaxError("passing a glob to an unquoted function argument requires explicit review")
        return " ".join(map(shlex.quote, value.split()))
