"""Respell function body calls with the words of each call, so a caller cannot hand a body a denied option."""

import re
import shlex
from collections import Counter
from dataclasses import dataclass

from code_text import ASSIGNING_BUILTINS, CODE_BODY, NAME_OPTION
from shell_words import PARAMETER_MODIFIERS, UnsupportedSyntaxError, literal_word, nodes, source_text
from shell_wrappers import WRAPPERS

# $1, ${12}, $@, and $*, which take the words a function is called with.
POSITIONAL = re.compile(r"[1-9][0-9]*|[@*]")
LITERALS = frozenset({"Lit", "SglQuoted"})
EXPANSIONS = frozenset({"ParamExp", "CmdSubst", "ProcSubst", "ArithmExp"})
# A caller's word that an unquoted expansion splits and globs no differently from its plain text.
PLAIN_FIELDS = re.compile(r"[A-Za-z0-9_./:=@%+,\s-]*")
# Builtins and wrappers whose meaning the hook relies on; a function of that name would change it.
RELIED_NAMES = frozenset(
    "echo printf print cd pushd popd shift set getopts builtin command eval trap alias hash source . exec".split()
) | frozenset(WRAPPERS)
# Words before a builtin that still run it, as in builtin shift or command -p shift.
BUILTIN_PREFIXES = frozenset({"builtin", "command"})
# Text eval or trap runs that may read or replace a function's arguments, at any depth of eval, once unquoted.
ARGUMENT_TEXT = re.compile(r"[$`]|(?<![\w-])(?:shift|set|getopts|read|mapfile|readarray|vared|source|\.)(?![\w-])")
# Quotes, escapes, braces, and glob characters, which spell a name without writing it plainly.
SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
# Builtins that may assign a variable named only at run time, or run code that does.
UNSEEN_ASSIGNERS = frozenset({"read", "mapfile", "readarray", "vared", "getopts", "source", ".", "eval", "trap"})
ARITHMETIC = frozenset({"ArithmCmd", "ArithmExp", "LetClause"})
ARITHMETIC_TEST = re.compile(r"\s-(?:eq|ne|lt|le|gt|ge)\s")
GLOB_CHARACTERS = re.compile(r"[*?\[]")


def with_definitions(records: tuple[dict, ...], data: bytes, script: str) -> str:
    """The script behind the definition of each function it names, so an eval or trap script can call one."""
    named = (
        source_text(node, data) + "\n"
        for node in records
        if node.get("Type") == "FuncDecl"
        and node["Name"]["Value"] != CODE_BODY
        and re.search(rf"(?<![\w-]){re.escape(node['Name']['Value'])}(?![\w-])", script)
    )
    return "".join(named) + script


def respelled_calls(records: tuple[dict, ...], data: bytes) -> list[str]:
    """Each body call that reads its function's arguments, with the words of each call of that function.

    Every definition of a name counts. A body that shifts its arguments is respelled once for every
    shift, so a word may land in any position. A redirection of the body itself is respelled too.

    Raises:
        UnsupportedSyntaxError: A body reads its arguments in a way the respelling cannot follow.
    """
    bodies: dict[str, list[dict]] = {}
    for node in (node for node in records if node.get("Type") == "FuncDecl" and node["Name"]["Value"] != CODE_BODY):
        bodies.setdefault(_defined_name(node), []).append(_followed(node["Body"], records, data))
    if bodies and _may_change_ifs(records, data):
        raise UnsupportedSyntaxError("calling a function after changing IFS requires explicit review", "expansion")
    splitting = any(_reads_unquoted(body) for definitions in bodies.values() for body in definitions)
    if splitting and _may_assign_unseen(records, data):
        raise UnsupportedSyntaxError("calling a function after changing IFS requires explicit review", "expansion")
    respelled = []
    for call in (node for node in records if node.get("Type") == "CallExpr" and node.get("Args")):
        name, dynamic = literal_word(call["Args"][0], data)
        words = call["Args"][1:]
        for body in [] if dynamic else bodies.get(name, []):
            respelled += _body_respellings(body, words, data)
    return respelled


def _body_respellings(body: dict, words: list[dict], data: bytes) -> list[str]:
    """Each statement of one body that reads its arguments, respelled with one call's words, once per shift."""
    if words and _calls(body, data, "source") + _calls(body, data, "."):
        raise UnsupportedSyntaxError(
            "calling a function that sources a file with arguments requires explicit review", "expansion"
        )
    copies = _copies(body)
    shifts = range(len(words) + 1) if _calls(body, data, "shift") else range(1)
    return [
        _Respelling(words[shift:], data, copies).statement(statement)
        for statement in _statements(body)
        if any(_reads(part, copies) for part in nodes(_respelled_nodes(statement)))
        for shift in shifts
    ]


def _defined_name(definition: dict) -> str:
    """The function's name, once neither the name nor a redirection of its body changes what the hook relies on."""
    name = definition["Name"]["Value"]
    if name in RELIED_NAMES:
        raise UnsupportedSyntaxError(
            "defining a function named after a builtin or wrapper requires explicit review", "expansion"
        )
    if definition["Body"].get("Redirs"):
        raise UnsupportedSyntaxError("defining a function with a redirection requires explicit review", "expansion")
    return name


def _may_change_ifs(records: tuple[dict, ...], data: bytes) -> bool:
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


def _may_assign_unseen(records: tuple[dict, ...], data: bytes) -> bool:
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


def _followed(body: dict, records: tuple[dict, ...], data: bytes) -> dict:
    """The body, once it is known to read its arguments only plainly, directly or through a plain copy."""
    copies = _copies(body)
    reading = [node for node in _assignments(body) if any(_reads(part, copies) for part in nodes(node["Value"]))]
    unfollowed = (
        any(_reads(part, copies) and any(map(part.get, PARAMETER_MODIFIERS)) for part in nodes(body))
        or any(part.get("Param", {}).get("Value") == "argv" for part in nodes(body))
        or any(_iterates_arguments(node, copies) for node in nodes(body) if node.get("Type") == "WordIter")
        or any(_reassigns(_program(call, data)) for call in _calls(body, data))
        or any(_copied(node) is None for node in reading)
        or _reassigned(copies, records, data)
    )
    if unfollowed:
        raise UnsupportedSyntaxError("a function reading its arguments this way requires explicit review", "expansion")
    return body


def _iterates_arguments(loop: dict, copies: dict[str, str]) -> bool:
    """Whether a for loop walks the arguments: implicitly, or over an expansion of them or of a copy."""
    return not loop.get("InPos") or any(_reads(part, copies) for part in nodes(loop.get("Items")))


def _reassigns(words: list[str]) -> bool:
    """Whether a call may replace the arguments: getopts, set with an operand or --, or code text."""
    program, arguments = words[0], words[1:]
    if program == "getopts":
        return True
    if program in {"eval", "trap"}:
        return bool(ARGUMENT_TEXT.search(SPELLING.sub("", " ".join(arguments))))
    return program == "set" and any(word[:1] not in {"-", "+"} or word == "--" for word in arguments)


def _reassigned(copies: dict[str, str], records: tuple[dict, ...], data: bytes) -> bool:
    """Whether any copy may be assigned again anywhere in the source, so it may no longer hold its argument."""
    if not copies:
        return False
    assigned = Counter(
        record["Name"].get("Value")
        for record in records
        if isinstance(record.get("Name"), dict) and record.get("Type") in {None, "WordIter"}
    )
    named: set[str] = set()
    for words in (_program(call, data) for call in records if call.get("Type") == "CallExpr" and call.get("Args")):
        if words[0] in ASSIGNING_BUILTINS | {"unset", "let"}:
            named.update(name for word in words[1:] for name in re.findall(r"[A-Za-z_]\w*", word))
    for record in (record for record in records if record.get("Type") in ARITHMETIC):
        named.update(name for part in nodes(record) for name in re.findall(r"[A-Za-z_]\w*", part.get("Value", "")))
    return any(assigned[name] > 1 or name in named for name in copies)


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


def _reads_unquoted(body: dict) -> bool:
    """Whether the body expands an argument outside double quotes, where IFS splits it."""
    copies = _copies(body)
    words = (node for node in nodes(body) if "Type" not in node and isinstance(node.get("Parts"), list))
    return any(_reads(part, copies) for word in words for part in word["Parts"])


def _program(call: dict, data: bytes) -> list[str]:
    """The call's words from the program it runs, past builtin, command, and the options command takes."""
    words = [source_text(word, data) for word in call["Args"]]
    while len(words) > 1 and words[0] in BUILTIN_PREFIXES:
        words = words[1:]
        while len(words) > 1 and words[0][:1] == "-":
            words = words[1:]
    return words


def _calls(body: dict, data: bytes, name: str | None = None) -> list[dict]:
    calls = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return [call for call in calls if name is None or _program(call, data)[0] == name]


def _statements(body: dict) -> list[dict]:
    """The statements of the body that run one call, together with their redirections."""
    return [
        node for node in nodes(body) if isinstance(node.get("Cmd"), dict) and node["Cmd"].get("Type") == "CallExpr"
    ]


def _respelled_nodes(statement: dict) -> list[dict]:
    """The call's words and the targets of its redirections other than heredocs."""
    return [*statement["Cmd"].get("Args", []), *(redirect["Word"] for redirect in _redirections(statement))]


def _redirections(statement: dict) -> list[dict]:
    return [redirect for redirect in statement.get("Redirs", []) if redirect.get("Word") and "Hdoc" not in redirect]


def _reads(part: dict, copies: dict[str, str]) -> bool:
    """Whether a part expands a positional parameter or a plain copy of one."""
    return _is_positional(part) or (part.get("Type") == "ParamExp" and part["Param"]["Value"] in copies)


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

    def statement(self, statement: dict) -> str:
        """The statement's call and redirections, each word respelled."""
        words = [self.word(word) for word in statement["Cmd"].get("Args", [])]
        redirects = [
            self.data[redirect["Pos"]["Offset"] : redirect["Word"]["Pos"]["Offset"]].decode()
            + self.word(redirect["Word"])
            for redirect in _redirections(statement)
        ]
        return " ".join(words + redirects)

    def word(self, word: dict) -> str:
        return "".join(self._part(part, quoted=False) for part in word.get("Parts", []))

    def _part(self, part: dict, *, quoted: bool) -> str:
        if _reads(part, self.copies):
            name = self.copies.get(part["Param"]["Value"], part["Param"]["Value"])
            words = self.words if name in {"@", "*"} else self.words[int(name) - 1 : int(name)]
            value = " ".join(self._spelled(word, quoted=quoted) for word in words) or "''"
            return f'"{value}"' if quoted else value
        if part.get("Type") == "DblQuoted" and not part.get("Dollar"):
            return '"' + "".join(self._part(item, quoted=True) for item in part.get("Parts", [])) + '"'
        return source_text(part, self.data)

    def _spelled(self, word: dict, *, quoted: bool) -> str:
        """The caller's word as the shell hands it over, requoted; unquoted, each field it splits into.

        A word known only at run time keeps its source text.
        """
        value, dynamic = literal_word(word, self.data)
        if dynamic:
            return source_text(word, self.data)
        if quoted:
            return shlex.quote(value)
        if not PLAIN_FIELDS.fullmatch(value):
            raise UnsupportedSyntaxError("passing a glob to an unquoted function argument requires explicit review")
        return " ".join(map(shlex.quote, value.split())) or "''"
