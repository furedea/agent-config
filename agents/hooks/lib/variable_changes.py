"""Find what may change a variable the hook cannot see: IFS, a name known only at run time, or an export."""

import re

import shell_input
from shell_words import nodes

LITERALS = frozenset({"Lit", "SglQuoted"})
EXPANSIONS = frozenset({"ParamExp", "CmdSubst", "ProcSubst", "ArithmExp"})
# Quotes, escapes, braces, and glob characters, which spell a name without writing it plainly.
SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
GLOB_CHARACTERS = re.compile(r"[*?\[]")


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
    """Whether any variable may be exported: export, allexport by set -a or -o, setopt, emulate, or options[...]."""
    if re.search(r"(?<![\w-])(?:export|allexport|setopt|emulate|options\[)", shell_input.normalized(data.decode())):
        return True
    calls = [node for node in records if node.get("Type") == "CallExpr" and node.get("Args")]
    return any(
        word[:1] in {"-", "+"} and "a" in word[1:] and word not in {"-o", "+o"}
        for word in shell_input.set_options(calls, data)
    )
