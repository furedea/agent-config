"""Respell function body calls with the words of each call, so a caller cannot hand a body a denied option."""

import re
import shlex
from dataclasses import dataclass

from shell_words import PARAMETER_MODIFIERS, UnsupportedSyntaxError, literal_word, nodes, source_text

# $1, ${12}, $@, and $*, which take the words a function is called with.
POSITIONAL = re.compile(r"[1-9][0-9]*|[@*]")


def with_definitions(records: tuple[dict, ...], data: bytes, script: str) -> str:
    """The script behind the definition of each function it names, so an eval or trap script can call one."""
    named = (
        source_text(node, data) + "\n"
        for node in records
        if node.get("Type") == "FuncDecl"
        and re.search(rf"(?<![\w-]){re.escape(node['Name']['Value'])}(?![\w-])", script)
    )
    return "".join(named) + script


def respelled_calls(records: tuple[dict, ...], data: bytes) -> list[str]:
    """Each body call that reads its function's arguments, with the words of each call of that function.

    Every definition of a name counts. A body that shifts its arguments is respelled once for every
    shift, so a word may land in any position.

    Raises:
        UnsupportedSyntaxError: A body reads its arguments in a way the respelling cannot follow.
    """
    bodies: dict[str, list[dict]] = {}
    for node in (node for node in records if node.get("Type") == "FuncDecl"):
        bodies.setdefault(node["Name"]["Value"], []).append(_followed(node["Body"], data))
    respelled = []
    for call in (node for node in records if node.get("Type") == "CallExpr" and node.get("Args")):
        name, dynamic = literal_word(call["Args"][0], data)
        words = call["Args"][1:]
        for body in [] if dynamic else bodies.get(name, []):
            copies = _copies(body)
            shifts = range(len(words) + 1) if _calls(body, data, "shift") else range(1)
            respelled += [
                " ".join(map(_Respelling(words[shift:], data, copies).word, inner["Args"]))
                for inner in _calls(body, data)
                if any(_Respelling.reads(part, copies) for part in nodes(inner["Args"]))
                for shift in shifts
            ]
    return respelled


def _followed(body: dict, data: bytes) -> dict:
    """The body, once it is known to read its arguments only plainly, directly or through a plain copy."""
    copies = _copies(body)
    unfollowed = (
        any(_Respelling.reads(part, copies) and any(map(part.get, PARAMETER_MODIFIERS)) for part in nodes(body))
        or any(part.get("Param", {}).get("Value") == "argv" for part in nodes(body))
        or any(node.get("Type") == "WordIter" and not node.get("InPos") for node in nodes(body))
        or any(_reassigns(call["Args"], data) for call in _calls(body, data))
        or any(_copied(node) is None for node in _assignments(body) if any(map(_is_positional, nodes(node["Value"]))))
    )
    if unfollowed:
        raise UnsupportedSyntaxError("a function reading its arguments this way requires explicit review", "expansion")
    return body


def _reassigns(arguments: list[dict], data: bytes) -> bool:
    """Whether a call replaces the arguments: getopts, or set with an operand or --."""
    words = [source_text(word, data) for word in arguments]
    return words[0] == "getopts" or (
        words[0] == "set" and any(word[:1] not in {"-", "+"} or word == "--" for word in words[1:])
    )


def _assignments(body: dict) -> list[dict]:
    return [
        node for node in nodes(body) if "Type" not in node and "Name" in node and isinstance(node.get("Value"), dict)
    ]


def _copied(assignment: dict) -> str | None:
    """The positional parameter a plain copy such as id=$1 or id="$1" takes, or None."""
    parts = assignment["Value"].get("Parts", [])
    if len(parts) == 1 and parts[0].get("Type") == "DblQuoted":
        parts = parts[0].get("Parts", [])
    return parts[0]["Param"]["Value"] if len(parts) == 1 and _is_positional(parts[0]) else None


def _copies(body: dict) -> dict[str, str]:
    return {node["Name"]["Value"]: name for node in _assignments(body) if (name := _copied(node)) is not None}


def _calls(body: dict, data: bytes, name: str | None = None) -> list[dict]:
    calls = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return [call for call in calls if name is None or source_text(call["Args"][0], data) == name]


def _is_positional(part: dict) -> bool:
    return part.get("Type") == "ParamExp" and POSITIONAL.fullmatch(part.get("Param", {}).get("Value", "")) is not None


@dataclass(frozen=True, slots=True)
class _Respelling:
    """A call's words, standing in for each positional parameter or plain copy of one.

    Inside quotes, the quotes close around the words.
    """

    words: list[dict]
    data: bytes
    copies: dict[str, str]

    @staticmethod
    def reads(part: dict, copies: dict[str, str]) -> bool:
        """Whether a part expands a positional parameter or a plain copy of one."""
        return _is_positional(part) or (part.get("Type") == "ParamExp" and part["Param"]["Value"] in copies)

    def word(self, word: dict) -> str:
        return "".join(self._part(part, quoted=False) for part in word.get("Parts", []))

    def _part(self, part: dict, *, quoted: bool) -> str:
        if self.reads(part, self.copies):
            name = self.copies.get(part["Param"]["Value"], part["Param"]["Value"])
            words = self.words if name in {"@", "*"} else self.words[int(name) - 1 : int(name)]
            value = " ".join(self._spelled(word, quoted=quoted) for word in words) or "''"
            return f'"{value}"' if quoted else value
        if part.get("Type") == "DblQuoted" and not part.get("Dollar"):
            return '"' + "".join(self._part(item, quoted=True) for item in part.get("Parts", [])) + '"'
        return source_text(part, self.data)

    def _spelled(self, word: dict, *, quoted: bool) -> str:
        """The caller's word as written, or, where the expansion is unquoted, each field it splits into, requoted."""
        value, dynamic = literal_word(word, self.data)
        if quoted or dynamic:
            return source_text(word, self.data)
        return " ".join(map(shlex.quote, value.split())) or "''"
