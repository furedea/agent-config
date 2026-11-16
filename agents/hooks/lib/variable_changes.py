"""Find what may change a variable the hook cannot see: IFS, a name known only at run time, or an export."""

import re

import shell_input
from code_text import NAME_OPTION
from shell_words import literal_word, nodes, source_text

LITERALS = frozenset({"Lit", "SglQuoted"})
EXPANSIONS = frozenset({"ParamExp", "CmdSubst", "ProcSubst", "ArithmExp"})
# Quotes, escapes, braces, and glob characters, which spell a name without writing it plainly.
SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
GLOB_CHARACTERS = re.compile(r"[*?\[]")
# Builtins that may assign a variable named only at run time, or run code that does.
UNSEEN_ASSIGNERS = frozenset({"read", "mapfile", "readarray", "vared", "getopts", "source", ".", "eval", "trap"})
ARITHMETIC = frozenset({"ArithmCmd", "ArithmExp", "LetClause"})
ARITHMETIC_TEST = re.compile(r"\s-(?:eq|ne|lt|le|gt|ge)\s")


def may_change_ifs(records: tuple[dict, ...], data: bytes) -> bool:
    """Whether IFS may be named: however quoted, escaped, or spelled, or by a name known only at run time."""
    if "IFS" in SPELLING.sub("", data.decode()):
        return True
    if any(record.get("Type") in {"SglQuoted", "DblQuoted"} and record.get("Dollar") for record in records):
        return True
    names = (record.get("Name") or record.get("Param") for record in records)
    if any(isinstance(name, dict) and name.get("Value") == "IFS" for name in names):
        return True
    words = (record for record in records if "Type" not in record and isinstance(record.get("Parts"), list))
    if any("IFS" in _literal(word) for word in words):
        return True
    return any(_computed_declaration(record) for record in records if record.get("Type") == "DeclClause")


def _computed_declaration(declaration: dict) -> bool:
    """Whether a declaration names its variable at run time or by a glob, or makes a nameref."""
    naked = [argument for argument in declaration.get("Args", []) if argument.get("Naked")]
    options = "".join(text for argument in naked if (text := _literal(argument.get("Value"))).startswith("-"))
    return "n" in options or any(
        any(part.get("Type") in EXPANSIONS for part in nodes(argument))
        or GLOB_CHARACTERS.search(_literal(argument.get("Value")))
        for argument in naked
    )


def _literal(word: dict | None) -> str:
    return "".join(part.get("Value", "") for part in nodes(word) if part.get("Type") in LITERALS)


def may_export(records: tuple[dict, ...], data: bytes) -> bool:
    """Whether any variable may be exported: by export, allexport, setopt, emulate, or options[...].

    A program named only at run time may be set -a.
    """
    if re.search(r"(?<![\w-])(?:export|allexport|setopt|emulate|options\[)", shell_input.normalized(data.decode())):
        return True
    calls = [node for node in records if node.get("Type") == "CallExpr" and node.get("Args")]
    if any(shell_input.runs_unseen(call, data) for call in calls):
        return True
    return any(
        word[:1] in {"-", "+"} and "a" in word[1:] and word not in {"-o", "+o"}
        for word in shell_input.options_given_to_set(calls, data)
    )


def may_assign_unseen(records: tuple[dict, ...], data: bytes) -> bool:
    """Whether any variable, IFS among them, may take a value the source does not spell out.

    Arithmetic evaluates the text of the variables it names, and these builtins assign or run text
    known only at run time.
    """
    if any(record.get("Type") in ARITHMETIC for record in records):
        return True
    if any(record.get("Type") == "ParamExp" and (record.get("Index") or record.get("Slice")) for record in records):
        return True
    tests = (record for record in records if record.get("Type") == "TestClause")
    if any(ARITHMETIC_TEST.search(source_text(test, data)) for test in tests):
        return True
    calls = (_program(call, data) for call in records if call.get("Type") == "CallExpr" and call.get("Args"))
    return any(
        words[0] in UNSEEN_ASSIGNERS or (words[0] in {"print", "printf"} and any(map(NAME_OPTION.fullmatch, words)))
        for words in calls
    )


def _program(call: dict, data: bytes) -> list[str]:
    """The call's words from the program on, past prefixes, wrappers, options, and assignments."""
    words = [literal_word(word, data)[0] for word in call["Args"]]
    return words[shell_input.program_index(words) :] or [""]


def arithmetic(body: dict, data: bytes) -> list[object]:
    """The arithmetic in the body, which evaluates an argument's text as code.

    That is $(( )), (( )), let, an index or a slice, and a [[ ]] test comparing numbers.
    """
    found: list[object] = [node for node in nodes(body) if node.get("Type") in ARITHMETIC]
    tests = (node for node in nodes(body) if node.get("Type") == "TestClause")
    found += [test for test in tests if ARITHMETIC_TEST.search(source_text(test, data))]
    found += [node.get(key) for node in nodes(body) if node.get("Type") == "ParamExp" for key in ("Index", "Slice")]
    return [item for item in found if item]
