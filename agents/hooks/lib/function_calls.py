"""Respell function body calls with the words of each call, so a caller cannot hand a body a denied option."""

import re
from collections import Counter

import respelling
import shell_input
import variable_changes
from code_text import ASSIGNING_BUILTINS, CODE_BODY, NAME_OPTION
from shell_words import PARAMETER_MODIFIERS, UnsupportedSyntaxError, literal_word, nodes, source_text, spreads
from shell_wrappers import WRAPPERS
from variable_changes import ARITHMETIC, ARITHMETIC_TEST, UNSEEN_ASSIGNERS

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
# Builtins that call a function they are given by name, with arguments the call never shows.
CALLBACK_TAKERS = frozenset(
    "mapfile readarray complete compgen compdef zle add-zsh-hook bind sched zstyle trap zargs zmv".split()
)
# Variables naming functions the shell calls on its own.
HOOK_VARIABLES = re.compile(r"PROMPT_COMMAND|(?:precmd|preexec|chpwd|periodic|zshexit|zshaddhistory)_functions")
# Words before a builtin that still run it, as in builtin shift, command -p shift, or zsh's noglob shift.
BUILTIN_PREFIXES = frozenset({"builtin", "command", "noglob", "nocorrect", "-"})
# Quotes, escapes, braces, and glob characters, which spell a name without writing it plainly.
SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
# Builtins that may assign a variable named only at run time, or run code that does.
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


def with_definitions(records: tuple[dict, ...], data: bytes, script: str) -> str:
    """The script behind the definition of each function it names however quoted or escaped, so it can call one."""
    plain = re.sub(r"\\\n|[\\'\"]", "", script)
    named = (
        source_text(node, data) + "\n"
        for node in records
        if node.get("Type") == "FuncDecl"
        and node["Name"]["Value"] != CODE_BODY
        and re.search(rf"(?<![\w-]){re.escape(node['Name']['Value'])}(?![\w-])", plain)
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
    if any(_named_as_word(name, records, data) for name, defined in bodies.items() if any(map(_reads_any, defined))):
        raise UnsupportedSyntaxError(
            "naming a function that reads its arguments other than as a command requires explicit review", "expansion"
        )
    if bodies and variable_changes.may_change_ifs(records, data):
        raise UnsupportedSyntaxError("calling a function after changing IFS requires explicit review", "expansion")
    splitting = any(_reads_unquoted(body) for definitions in bodies.values() for body in definitions)
    if splitting and variable_changes.may_assign_unseen(records, data):
        raise UnsupportedSyntaxError("calling a function after changing IFS requires explicit review", "expansion")
    respelled = []
    for call in (node for node in records if node.get("Type") == "CallExpr" and node.get("Args")):
        start = _modifier_count(call, data)
        program = call["Args"][start] if start < len(call["Args"]) else {}
        if (
            bodies
            and program
            and spreads(program, data)
            and not any(respelling.reads(part, {}) for part in nodes(program))
        ):
            raise UnsupportedSyntaxError(
                "calling a program whose name may expand requires explicit review", "expansion"
            )
        name, dynamic = literal_word(call["Args"][start], data) if start < len(call["Args"]) else ("", True)
        words = call["Args"][start + 1 :]
        for body in [] if dynamic else bodies.get(name, []):
            respelled += _body_respellings(body, words, data)
    return respelled


def _modifier_count(call: dict, data: bytes) -> int:
    """How many zsh precommand modifiers, which still run a function, lead the call."""
    count = 0
    while count < len(call["Args"]) and literal_word(call["Args"][count], data)[0] in FUNCTION_MODIFIERS:
        count += 1
    return count


def _body_respellings(body: dict, words: list[dict], data: bytes) -> list[str]:
    """Each statement of one body that reads its arguments, respelled with one call's words, once per shift."""
    reading = any(respelling.reads(part, _copies(body)) for part in nodes(body))
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
    shift_calls = _calls(body, data, "shift")
    loops = any(node.get("Type") in {"ForClause", "WhileClause"} for node in nodes(body))
    if copies and (len(shift_calls) > 1 or (shift_calls and loops)):
        raise UnsupportedSyntaxError("a function reading its arguments this way requires explicit review", "expansion")
    first = min((call["Pos"]["Offset"] for call in shift_calls), default=len(data))
    early = frozenset(node["Name"]["Value"] for node in _assignments(body) if node["Pos"]["Offset"] < first)
    shifts = range(len(words) + 1) if shift_calls else range(1)
    return [
        respelling.Respelling(words[shift:], data, copies, words, early & copies.keys()).statement(statement)
        for statement in _statements(body)
        if any(respelling.reads(part, copies) for part in nodes(_respelled_nodes(statement)))
        for shift in shifts
    ]


def _reads_any(body: dict) -> bool:
    copies = _copies(body)
    return any(respelling.reads(part, copies) for part in nodes(body))


def _named_as_word(name: str, records: tuple[dict, ...], data: bytes) -> bool:
    """Whether a word other than a command name, or an assigned value, names the function: a callback may call it.

    Fails closed beside a hook variable, a callback builtin given a word known only at run time, or a program
    named only at run time, which may be such a builtin.
    """
    token = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
    calls = [node for node in records if node.get("Type") == "CallExpr" and node.get("Args")]
    # eval and trap text is judged with the definitions in front of it, so a call there is respelled.
    judged = (call for call in calls if _program(call, data)[0] not in {"eval", "trap"})
    words = [word for call in judged for word in call["Args"][_modifier_count(call, data) + 1 :]]
    values = [record for record in records if "Type" not in record and isinstance(record.get("Value"), dict)]
    texts = [literal_word(word, data)[0] for word in words + [value["Value"] for value in values]]
    # An option may carry the name attached, as mapfile -Cf does.
    if any(token.search(re.sub(r"^-[A-Za-z]*?(?=" + re.escape(name) + ")", "", text)) for text in texts):
        return True
    if HOOK_VARIABLES.search(SPELLING.sub("", data.decode())):
        return True
    callbacks = (call for call in calls if _program(call, data)[0] in CALLBACK_TAKERS)
    if any(literal_word(word, data)[1] for call in callbacks for word in call["Args"]):
        return True
    return any(
        shell_input.runs_unseen(call, data) and not _names_by_arguments(call, _program_words(call, data), {})
        for call in calls
    )


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


def _followed(body: dict, records: tuple[dict, ...], data: bytes) -> dict:
    """The body, once it is known to read its arguments only plainly, directly or through a plain copy."""
    copies = _copies(body)
    # Any assignment that reads the arguments, an array or an element among them, unless it is a plain copy.
    reading = [
        node
        for node in nodes(body)
        if "Type" not in node
        and isinstance(node.get("Name"), dict)
        and any(
            respelling.reads(part, copies) for key, value in node.items() if key != "Name" for part in nodes(value)
        )
    ]
    unfollowed = (
        any(
            part.get("Type") == "ParamExp"
            and any(map(part.get, PARAMETER_MODIFIERS))
            and any(respelling.reads(inner, copies) or respelling.counts_arguments(inner) for inner in nodes(part))
            for part in nodes(body)
        )
        or any(part.get("Param", {}).get("Value") in ARGUMENT_ARRAYS for part in nodes(body))
        or any(respelling.reads(part, copies) for context in _arithmetic(body, data) for part in nodes(context))
        or any(
            respelling.reads(part, copies)
            for node in nodes(body)
            if node.get("Type") == "CmdSubst"
            for part in nodes(node)
        )
        or any(
            "Type" not in node and isinstance(node.get("Name"), dict) and node["Name"].get("Value") in ARGUMENT_ARRAYS
            for node in nodes(body)
        )
        or (
            any(respelling.reads(part, copies) for part in nodes(body))
            and any(_assigns_parameter(statement, data) for statement in _statements(body))
        )
        or any(part.get("Type") == "ParamExp" and part.get("Excl") for part in nodes(body))
        or any(_runs_unseen(call, copies, data) for call in _calls(body, data))
        or any(_iterates_arguments(node, copies) for node in nodes(body) if node.get("Type") == "WordIter")
        or any(_reassigns(_program(call, data)) for call in _calls(body, data))
        or any(
            not isinstance(node.get("Value"), dict) or node.get("Array") or node.get("Index") or _copied(node) is None
            for node in reading
        )
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
    return variable_changes.may_export(records, data)


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


def _arithmetic(body: dict, data: bytes) -> list[object]:
    """The arithmetic in the body, which evaluates an argument's text as code.

    That is $(( )), (( )), let, an index or a slice, and a [[ ]] test comparing numbers.
    """
    found: list[object] = [node for node in nodes(body) if node.get("Type") in ARITHMETIC]
    tests = (node for node in nodes(body) if node.get("Type") == "TestClause")
    found += [test for test in tests if ARITHMETIC_TEST.search(source_text(test, data))]
    found += [node.get(key) for node in nodes(body) if node.get("Type") == "ParamExp" for key in ("Index", "Slice")]
    return [item for item in found if item]


def _iterates_arguments(loop: dict, copies: dict[str, str]) -> bool:
    """Whether a for loop walks the arguments: implicitly, or over an expansion of them or of a copy."""
    return not loop.get("InPos") or any(respelling.reads(part, copies) for part in nodes(loop.get("Items")))


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
        return bool(shell_input.ARGUMENT_TEXT.search(SPELLING.sub("", " ".join(arguments))))
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
        if words[0] in ASSIGNING_BUILTINS | {"unset", "let", "eval", "trap"}:
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
    return parts[0]["Param"]["Value"] if len(parts) == 1 and respelling.is_positional(parts[0]) else None


def _copies(body: dict) -> dict[str, str]:
    return {node["Name"]["Value"]: name for node in _assignments(body) if (name := _copied(node)) is not None}


def _reads_unquoted(body: dict) -> bool:
    """Whether the body expands an argument outside double quotes, where IFS splits it."""
    copies = _copies(body)
    words = (node for node in nodes(body) if "Type" not in node and isinstance(node.get("Parts"), list))
    return any(respelling.reads(part, copies) for word in words for part in word["Parts"])


def _program(call: dict, data: bytes) -> list[str]:
    """The call's words as the shell runs them, from the program on, past builtin, command, and command's options."""
    return [value for value, _ in _program_words(call, data)]


def _runs_unseen(call: dict, copies: dict[str, str], data: bytes) -> bool:
    """Whether the program is known only at run time, and not from the arguments a respelling supplies."""
    words = _program_words(call, data)
    return words[0][1] and not _names_by_arguments(call, words, copies)


def _names_by_arguments(call: dict, words: list[tuple[str, bool]], copies: dict[str, str]) -> bool:
    program = call["Args"][len(call["Args"]) - len(words)]
    return any(respelling.reads(part, copies) for part in nodes(program))


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
    """The call's assignments, words, and the targets of its redirections other than heredocs."""
    return [
        *statement["Cmd"].get("Assigns", []),
        *statement["Cmd"].get("Args", []),
        *(redirect["Word"] for redirect in respelling.redirections(statement)),
    ]
