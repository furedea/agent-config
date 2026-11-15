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
    "echo printf print cd pushd popd shift set getopts builtin command eval trap alias hash source . exec noglob "
    "nocorrect -".split()
) | frozenset(WRAPPERS)
# Names the parser reads as declarations, arithmetic, or keywords rather than calls, so their calls go unseen.
KEYWORD_NAMES = frozenset("declare local export typeset readonly nameref integer float let time coproc".split())
# Functions bash or zsh call on their own, with words that never follow the function's name.
SHELL_HOOKS = re.compile(
    r"command_not_found_handler?|precmd|preexec|chpwd|periodic|zshexit|zshaddhistory|TRAP[A-Z0-9]+"
)
# Parameters holding a function's arguments: zsh's argv, bash's BASH_ARGV and BASH_ARGC under extdebug, and $_,
# the last word of the call.
ARGUMENT_ARRAYS = frozenset({"argv", "BASH_ARGV", "BASH_ARGC", "_"})
# zsh precommand modifiers, which run the function named after them; builtin and command skip functions.
FUNCTION_MODIFIERS = frozenset({"noglob", "nocorrect", "-"})
# Builtins that assign a parameter named by an operand or an option, which may hold or replace the arguments.
NAME_ASSIGNERS = ASSIGNING_BUILTINS | frozenset({"zformat", "zstyle", "zregexparse", "zparseopts", "getln", "popln"})
# Words before a builtin that still run it, as in builtin shift, command -p shift, or zsh's noglob shift.
BUILTIN_PREFIXES = frozenset({"builtin", "command", "noglob", "nocorrect", "-"})
# Text eval or trap runs that may read or replace a function's arguments, at any depth of eval, once unquoted.
ARGUMENT_TEXT = re.compile(r"[$`]|(?<![\w-])(?:shift|set|getopts|read|mapfile|readarray|vared|source|\.)(?![\w-])")
# Quotes, escapes, braces, and glob characters, which spell a name without writing it plainly.
SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
# Builtins that may assign a variable named only at run time, or run code that does.
UNSEEN_ASSIGNERS = frozenset({"read", "mapfile", "readarray", "vared", "getopts", "source", ".", "eval", "trap"})
# Programs a caller's word may name that change the arguments or run code, when a body runs that word.
ARGUMENT_CHANGERS = (
    RELIED_NAMES
    | KEYWORD_NAMES
    | UNSEEN_ASSIGNERS
    | frozenset(
        "unset noglob nocorrect - zparseopts fc enable disable emulate setopt unsetopt shopt autoload functions "
        "zmodload".split()
    )
)
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
    code_bodies = [
        node["Body"] for node in records if node.get("Type") == "FuncDecl" and node["Name"]["Value"] == CODE_BODY
    ]
    wrapped = [node for node in records if node.get("Type") == "FuncDecl" and node["Name"]["Value"] == CODE_BODY]
    if any(node["End"]["Offset"] != len(data) for node in wrapped):
        raise UnsupportedSyntaxError("closing the eval or trap text early requires explicit review", "expansion")
    if any(node.get("Type") == "FuncDecl" for body in code_bodies for node in nodes(body)):
        raise UnsupportedSyntaxError("defining a function in eval or trap text requires explicit review", "expansion")
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
        start = _modifier_count(call, data)
        name, dynamic = literal_word(call["Args"][start], data) if start < len(call["Args"]) else ("", True)
        words = call["Args"][start + 1 :]
        for body in [] if dynamic else bodies.get(name, []):
            respelled += _body_respellings(body, words, data)
    return respelled


def unpassed(scripts: list[str], passed: tuple[str, ...]) -> list[str]:
    """The scripts a shell runs, unless one may read the arguments the shell is handed after them.

    Raises:
        UnsupportedSyntaxError: A script reads arguments that the nested judgement cannot see.
    """
    if passed and any(ARGUMENT_TEXT.search(SPELLING.sub("", script)) for script in scripts):
        raise UnsupportedSyntaxError(
            "running a shell script that reads arguments passed to it requires explicit review"
        )
    return scripts


def operands(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """The words a shell takes as arguments: from its first non-option word, or after a - or -- ending options."""
    for index, argument in enumerate(arguments[1:], 1):
        if argument in {"-", "--"}:
            return arguments[index + 1 :]
        if argument[:1] not in {"-", "+"}:
            return arguments[index:]
    return ()


def _modifier_count(call: dict, data: bytes) -> int:
    """How many zsh precommand modifiers, which still run a function, lead the call."""
    count = 0
    while count < len(call["Args"]) and literal_word(call["Args"][count], data)[0] in FUNCTION_MODIFIERS:
        count += 1
    return count


def _body_respellings(body: dict, words: list[dict], data: bytes) -> list[str]:
    """Each statement of one body that reads its arguments, respelled with one call's words, once per shift."""
    reading = any(_reads(part, _copies(body)) for part in nodes(body))
    if (words or reading) and _calls(body, data, "source") + _calls(body, data, "."):
        raise UnsupportedSyntaxError(
            "calling a function that sources a file and passes or reads arguments requires explicit review",
            "expansion",
        )
    copies = _copies(body)
    named = any(_names_by_arguments(call, _program_words(call, data), copies) for call in _calls(body, data))
    if named and not {literal_word(word, data)[0] for word in words}.isdisjoint(ARGUMENT_CHANGERS):
        raise UnsupportedSyntaxError(
            "calling a function that runs its argument as a builtin changing arguments requires explicit review",
            "expansion",
        )
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
    if name in RELIED_NAMES | KEYWORD_NAMES or SHELL_HOOKS.fullmatch(name):
        raise UnsupportedSyntaxError(
            "defining a function named after a builtin, keyword, wrapper, or shell hook requires explicit review",
            "expansion",
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
        or any(part.get("Param", {}).get("Value") in ARGUMENT_ARRAYS for part in nodes(body))
        or any(
            "Type" not in node and isinstance(node.get("Name"), dict) and node["Name"].get("Value") in ARGUMENT_ARRAYS
            for node in nodes(body)
        )
        or (
            any(_reads(part, copies) for part in nodes(body))
            and any(_assigns_parameter(statement, data) for statement in _statements(body))
        )
        or any(part.get("Type") == "ParamExp" and part.get("Excl") for part in nodes(body))
        or any(_runs_unseen(call, copies, data) for call in _calls(body, data))
        or any(_iterates_arguments(node, copies) for node in nodes(body) if node.get("Type") == "WordIter")
        or any(_reassigns(_program(call, data)) for call in _calls(body, data))
        or any(_copied(node) is None for node in reading)
        or _reassigned(copies, records, data)
        or not _attributed(body, data).isdisjoint(copies)
        or _leaks(body, records, data)
    )
    if unfollowed:
        raise UnsupportedSyntaxError("a function reading its arguments this way requires explicit review", "expansion")
    return body


def _assigns_parameter(statement: dict, data: bytes) -> bool:
    """Whether a builtin such as printf -v or read assigns a parameter, which may take the arguments by any path."""
    if not statement["Cmd"].get("Args"):
        return False
    words = _program(statement["Cmd"], data)
    assigning = words[0] in NAME_ASSIGNERS - {"print", "printf"} or (
        words[0] in {"print", "printf"} and any(map(NAME_OPTION.fullmatch, words))
    )
    return assigning


def _leaks(body: dict, records: tuple[dict, ...], data: bytes) -> bool:
    """Whether a copy may outlive the call: named outside the body, however spelled, or exported to children.

    Only a heredoc body with no expansion is left out, as it names nothing.
    """
    copies = _copies(body)
    if not copies:
        return False
    spans = [(body["Pos"]["Offset"], body["End"]["Offset"])] + [
        (record["Hdoc"]["Pos"]["Offset"], record["Hdoc"]["End"]["Offset"])
        for record in records
        if isinstance(record.get("Hdoc"), dict) and all(part.get("Type") == "Lit" for part in record["Hdoc"]["Parts"])
    ]
    outside = bytearray(data)
    for start, end in spans:
        outside[start:end] = b" " * (end - start)
    text = SPELLING.sub("", re.sub(r"\\\n", "", outside.decode()))
    if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) for name in copies):
        return True
    exporting = re.search(r"(?<![\w-])(?:export|allexport)(?![\w-])|\bset\s+[-+]\w*a", SPELLING.sub("", data.decode()))
    return exporting is not None


def _attributed(body: dict, data: bytes) -> set[str]:
    """Names a declaration in the body gives an attribute, such as -l or -u, which may change a value assigned.

    An option word counts however it is quoted or escaped, and so does any word known only at run time.
    """
    declarations = (node for node in nodes(body) if node.get("Type") == "DeclClause")
    return {
        argument["Name"]["Value"]
        for declaration in declarations
        if any(
            argument.get("Naked") and _option_like(argument.get("Value"), data)
            for argument in declaration.get("Args", [])
        )
        for argument in declaration.get("Args", [])
        if isinstance(argument.get("Name"), dict)
    }


def _option_like(word: dict | None, data: bytes) -> bool:
    value, dynamic = literal_word(word, data) if word else ("", False)
    return dynamic or value[:1] in {"-", "+"}


def _iterates_arguments(loop: dict, copies: dict[str, str]) -> bool:
    """Whether a for loop walks the arguments: implicitly, or over an expansion of them or of a copy."""
    return not loop.get("InPos") or any(_reads(part, copies) for part in nodes(loop.get("Items")))


def _reassigns(words: list[str]) -> bool:
    """Whether a call may replace the arguments: getopts, zparseopts, set, code text, or assigning argv."""
    program, arguments = words[0], words[1:]
    if program in {"getopts", "zparseopts"}:
        return True
    if program in NAME_ASSIGNERS and any(
        not ARGUMENT_ARRAYS.isdisjoint(re.findall(r"[A-Za-z_]\w*", word)) for word in arguments
    ):
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
    """The call's words as the shell runs them, from the program on, past builtin, command, and command's options."""
    return [value for value, _ in _program_words(call, data)]


def _runs_unseen(call: dict, copies: dict[str, str], data: bytes) -> bool:
    """Whether the program is known only at run time, and not from the arguments a respelling supplies."""
    words = _program_words(call, data)
    return words[0][1] and not _names_by_arguments(call, words, copies)


def _names_by_arguments(call: dict, words: list[tuple[str, bool]], copies: dict[str, str]) -> bool:
    program = call["Args"][len(call["Args"]) - len(words)]
    return any(_reads(part, copies) for part in nodes(program))


def _program_words(call: dict, data: bytes) -> list[tuple[str, bool]]:
    words = [literal_word(word, data) for word in call["Args"]]
    while len(words) > 1 and words[0][0] in BUILTIN_PREFIXES:
        words = words[1:]
        while len(words) > 1 and words[0][0][:1] == "-":
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
        """The caller's word as the shell hands it over, requoted; unquoted, each field it splits into."""
        value, dynamic = literal_word(word, self.data)
        if dynamic:
            raise UnsupportedSyntaxError(
                "passing a function an argument known only at run time requires explicit review"
            )
        if quoted:
            return shlex.quote(value)
        if not PLAIN_FIELDS.fullmatch(value):
            raise UnsupportedSyntaxError("passing a glob to an unquoted function argument requires explicit review")
        return " ".join(map(shlex.quote, value.split())) or "''"
