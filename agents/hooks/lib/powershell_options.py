"""Read PowerShell's options: which ones hand it code, in what spelling, and how many words they take."""

import re

NAMES = frozenset({"powershell", "pwsh", "pwsh-preview"})
# PowerShell's -e, -ec, -EncodedCommand: a base64 script, which the inspection does not decode.
ENCODED_OPTION = re.compile(r"-(e|ec|en[a-z]*)", re.IGNORECASE)


def _is_powershell(shell: str) -> bool:
    return shell in NAMES


def form(shell: str, argument: str) -> str:
    """The option as written with one dash; PowerShell reads --name and /name as -name."""
    if _is_powershell(shell) and argument.startswith(("/", "--")):
        return "-" + argument.lstrip("/-")
    return argument


def is_encoded(shell: str, argument: str) -> bool:
    """Whether the option carries a base64 script; only PowerShell has one, nu's -e is a plain script."""
    return _is_powershell(shell) and ENCODED_OPTION.fullmatch(form(shell, argument)) is not None


def takes_code(shell: str, argument: str) -> bool:
    """Whether the option is -Command, -CommandWithArgs, or an abbreviation, which takes the next word as code."""
    name = form(shell, argument)[1:].lower()
    return _is_powershell(shell) and bool(name) and ("command".startswith(name) or _is_with_args(name))


def joins_following_words(shell: str, argument: str) -> bool:
    """Whether every word after the option is code.

    After -CommandWithArgs only the first is; the rest are arguments.
    """
    return _is_powershell(shell) and not _is_with_args(form(shell, argument)[1:].lower())


def _is_with_args(name: str) -> bool:
    return name == "cwa" or (len(name) > len("command") and "commandwithargs".startswith(name))
