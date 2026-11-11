"""Find the variables that a command assigned as plain scalars before a call, so zsh runs `$name` there as one word."""

# Environment variables zsh never makes an array.
ENVIRONMENT_NAMES = frozenset({"HOME", "PWD", "TMPDIR", "USER"})
SEQUENTIAL_OPERATORS = ("&&", "||")
PIPE_OPERATORS = ("|&", "|")


def one_word_names(tree: dict, data: bytes) -> dict[int, frozenset[str]]:
    """Map each call to the names its unquoted expansion may rely on being one word, by the call's `id`.

    A call counts only when every statement before its own is a plain scalar assignment, and it is the
    statement's first command or part of its pipeline, so nothing between the assignments and the call
    can retarget a name, change an option, or skip an assignment. Another call gets no entry.
    """
    names: dict[int, frozenset[str]] = {}
    assigned: set[str] = set()
    for statement in tree.get("Stmts", []):
        for call in _reached_calls(statement, data):
            names[id(call)] = frozenset(assigned) | ENVIRONMENT_NAMES
        plain = _assigned_names(statement)
        if plain is None:
            break
        assigned |= plain
    return names


def _reached_calls(statement: dict, data: bytes) -> list[dict]:
    if statement.get("Background") or statement.get("Coprocess"):
        return []
    command = statement.get("Cmd") or {}
    if command.get("Type") == "CallExpr":
        return [command] if command.get("Args") else []
    if command.get("Type") != "BinaryCmd":
        return []
    operator = _operator(command, data)
    if operator in PIPE_OPERATORS:
        return _reached_calls(command["X"], data) + _reached_calls(command["Y"], data)
    return _reached_calls(command["X"], data) if operator in SEQUENTIAL_OPERATORS else []


def _operator(command: dict, data: bytes) -> str:
    offset = command["OpPos"]["Offset"]
    return data[offset : offset + 2].decode().rstrip(" \t\n\\")


def _assigned_names(statement: dict) -> set[str] | None:
    """The names assigned, or None unless every part is a plain `name=value` (or `export name=value`)."""
    if statement.get("Background") or statement.get("Coprocess") or statement.get("Negated"):
        return None
    command = statement.get("Cmd") or {}
    if command.get("Type") == "CallExpr" and not command.get("Args"):
        assigns = command.get("Assigns") or []
    elif command.get("Type") == "DeclClause" and command.get("Variant", {}).get("Value") == "export":
        assigns = command.get("Args") or []
    else:
        return None
    if not assigns or not all(_is_scalar_assignment(assign) for assign in assigns):
        return None
    return {assign["Name"]["Value"] for assign in assigns if not assign.get("Naked")}


def _is_scalar_assignment(assign: dict) -> bool:
    name = assign.get("Name")
    return bool(name) and not assign.get("Array") and not assign.get("Index")
