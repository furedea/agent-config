"""Walk a function body: the calls it makes, the programs they run, and the assignments in it."""

import re
from pathlib import Path

import respelling
import shell_input
from code_text import NAME_OPTION, PARAMETER_SETTERS
from shell_words import literal_word, nodes, source_text
from variable_changes import ARITHMETIC_TEST

# Words before a builtin that still run it, as in builtin shift, command -p shift, or zsh's noglob shift.
BUILTIN_PREFIXES = frozenset({"builtin", "command", "noglob", "nocorrect", "-"})
# What a simple body may hold: commands, lists, pipes, branches, loops, subshells, tests, and words. Anything else,
# such as arithmetic, a nested definition, or a declaration other than local, evaluates text again or is not followed.
SIMPLE_NODES = frozenset(
    "Block CallExpr BinaryCmd IfClause WhileClause ForClause WordIter CaseClause Subshell TestClause DeclClause Lit "
    "SglQuoted DblQuoted ParamExp CmdSubst ProcSubst UnaryTest BinaryTest ParenTest Word".split()
)
# A test of whether a name is set, or is a nameref, which evaluates the name's subscript as code.
NAME_TEST = re.compile(r"(?<!\S)-[vR](?!\S)")
# Programs that evaluate text again, assign or remove a parameter by name, or change what a name runs.
REEVALUATING = (
    frozenset(
        "unset eval trap let source . alias unalias builtin command hash read mapfile readarray vared getopts "
        "zparseopts declare typeset export readonly enable emulate setopt unsetopt noglob nocorrect - exec".split()
    )
    | PARAMETER_SETTERS
)
# A program name that runs a shell, which may read its script's data from its input.
SHELL_NAME = re.compile(r"\w*sh|fish|pwsh")


def program_words(call: dict, data: bytes) -> list[tuple[str, bool]]:
    """The call's decoded words with their run-time flags, from the program on, past builtin and command."""
    words = [literal_word(word, data) for word in call["Args"]]
    while len(words) > 1 and words[0][0] in BUILTIN_PREFIXES:
        words = words[1:]
        while len(words) > 1 and words[0][0][:1] == "-":
            words = words[1:]
    return words


def program(call: dict, data: bytes) -> list[str]:
    """The call's words as the shell runs them, from the program on, past builtin, command, and command's options."""
    return [value for value, _ in program_words(call, data)]


def calls(body: dict, data: bytes, name: str | None = None) -> list[dict]:
    """The body's calls, or only those running the named program."""
    found = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return [call for call in found if name is None or program(call, data)[0] == name]


def assignments(body: dict) -> list[dict]:
    """The body's assignments of a single value."""
    return [
        node for node in nodes(body) if "Type" not in node and "Name" in node and isinstance(node.get("Value"), dict)
    ]


def statements(body: dict) -> list[dict]:
    """The statements of the body that run one call, together with their redirections."""
    return [
        node for node in nodes(body) if isinstance(node.get("Cmd"), dict) and node["Cmd"].get("Type") == "CallExpr"
    ]


def respelled_nodes(statement: dict) -> list[dict]:
    """The call's assignments, words, and the targets of its redirections other than heredocs."""
    return [
        *statement["Cmd"].get("Assigns", []),
        *statement["Cmd"].get("Args", []),
        *(redirect["Word"] for redirect in respelling.redirections(statement)),
    ]


def may_run_shell(call: dict, data: bytes) -> bool:
    """Whether the call may run a shell: a word names one, or the program is known only at run time."""
    words = program_words(call, data)
    index = shell_input.program_index([value for value, _ in words])
    if index < len(words) and words[index][1]:
        return True
    # A wrapper's option operand may sit where the program seems to be, so any word naming a shell counts.
    return any(SHELL_NAME.fullmatch(Path(value).name) for value, _ in words)


def feeds_a_shell(body: dict, copies: dict[str, str], data: bytes) -> bool:
    """Whether the arguments flow into a shell's input, by a pipe or a redirection, where its script reads them."""
    shells = [call for call in calls(body, data) if may_run_shell(call, data)]
    if not shells:
        return False
    pipes = (node for node in nodes(body) if node.get("Type") == "BinaryCmd" and shell_input.is_pipe(node, data))
    if any(respelling.reads(part, copies) for pipe in pipes for part in nodes(pipe["X"])):
        return True
    statements = (node for node in nodes(body) if node.get("Cmd") in shells)
    return any(
        respelling.reads(part, copies)
        for statement in statements
        for redirect in statement.get("Redirs", [])
        for part in nodes(redirect)
    )


def is_simple(body: dict, data: bytes) -> bool:
    """Whether a body holds only what the hook can judge word by word with each caller's words.

    That excludes a heredoc, a nested definition, arithmetic and subscripts, a test of a name with -v or -R, an
    append, a declaration other than a plain local, and every builtin that evaluates text again or assigns by name.
    """
    for node in nodes(body):
        kind = node.get("Type")
        if kind is not None and kind not in SIMPLE_NODES:
            return False
        if kind == "TestClause" and (
            ARITHMETIC_TEST.search(source_text(node, data)) or NAME_TEST.search(source_text(node, data))
        ):
            return False
        if kind == "ParamExp" and (node.get("Index") or node.get("Slice")):
            return False
        if kind == "DeclClause" and not _plain_local(node, data):
            return False
        if kind is None and (node.get("Hdoc") or node.get("Append") or node.get("Index")):
            return False
    return not any(_reevaluates(call, data) for call in calls(body, data))


def _plain_local(declaration: dict, data: bytes) -> bool:
    """Whether a declaration is local with literal names and no options."""
    if declaration.get("Variant", {}).get("Value") != "local":
        return False
    return all(_plain_name(argument, data) for argument in declaration.get("Args", []))


def _plain_name(argument: dict, data: bytes) -> bool:
    """Whether a declaration word names a variable plainly: an assignment, or a bare literal name, not an option."""
    if not argument.get("Naked"):
        return isinstance(argument.get("Name"), dict)
    value, dynamic = literal_word(argument["Value"], data)
    return not dynamic and re.fullmatch(r"[A-Za-z_]\w*", value) is not None


def _reevaluates(call: dict, data: bytes) -> bool:
    words = [literal_word(word, data)[0] for word in call["Args"]]
    if words[0] in {"test", "["} and not {"-v", "-R"}.isdisjoint(words[1:]):
        return True
    return words[0] in REEVALUATING or (words[0] in {"print", "printf"} and any(map(NAME_OPTION.fullmatch, words)))
