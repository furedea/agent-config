"""Respell function body calls with the words of each call, so a caller cannot hand a body a denied option."""

import re
from dataclasses import dataclass

from shell_words import nodes, source_text

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

    A body that shifts its arguments is respelled once for every shift, so a word may land in any position.
    """
    bodies = {node["Name"]["Value"]: node["Body"] for node in records if node.get("Type") == "FuncDecl"}
    respelled = []
    for call in (node for node in records if node.get("Type") == "CallExpr" and node.get("Args")):
        body = bodies.get(source_text(call["Args"][0], data))
        if body is None:
            continue
        words = [source_text(word, data) for word in call["Args"][1:]]
        shifts = range(len(words) + 1) if _shifts(body, data) else range(1)
        respelled += [
            " ".join(map(_Respelling(words[shift:], data).word, inner["Args"]))
            for inner in _reading_calls(body)
            for shift in shifts
        ]
    return respelled


def _reading_calls(body: dict) -> list[dict]:
    calls = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return [call for call in calls if any(_is_positional(part) for part in nodes(call["Args"]))]


def _shifts(body: dict, data: bytes) -> bool:
    calls = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return any(source_text(call["Args"][0], data) in {"shift", "set"} for call in calls)


def _is_positional(part: dict) -> bool:
    return part.get("Type") == "ParamExp" and POSITIONAL.fullmatch(part.get("Param", {}).get("Value", "")) is not None


@dataclass(frozen=True, slots=True)
class _Respelling:
    """A call's words, standing in for each positional parameter; inside quotes, the quotes close around them."""

    words: list[str]
    data: bytes

    def word(self, word: dict) -> str:
        return "".join(self._part(part, quoted=False) for part in word.get("Parts", []))

    def _part(self, part: dict, *, quoted: bool) -> str:
        if _is_positional(part):
            name, words = part["Param"]["Value"], self.words
            value = (
                " ".join(words) if name in {"@", "*"} else (words[int(name) - 1] if int(name) <= len(words) else "''")
            )
            return f'"{value}"' if quoted else value
        if part.get("Type") == "DblQuoted" and not part.get("Dollar"):
            return '"' + "".join(self._part(item, quoted=True) for item in part.get("Parts", [])) + '"'
        return source_text(part, self.data)
