"""Names that tell the inspection which program is a shell, and which shells are not bash."""

import re

SHELLS = frozenset(
    {
        "ash",
        "bash",
        "dash",
        "hush",
        "ksh",
        "mksh",
        "oksh",
        "pdksh",
        "posh",
        "rbash",
        "sh",
        "yash",
        "zsh",
    }
)
# Shells whose syntax is not bash's. However one is invoked, the call asks: the inspection cannot tell
# what such a shell would run, and each option or syntax it adds is another way to hand it a script.
# Its script text, where visible, is read as bash only to find commands to deny.
FOREIGN_SHELLS = frozenset(
    {
        "csh",
        "elvish",
        "es",
        "fish",
        "nu",
        "nushell",
        "powershell",
        "pwsh",
        "pwsh-preview",
        "rc",
        "tcsh",
        "xonsh",
        "ysh",
    }
)
# Names ending in sh that are no listed shell but may be one; they ask only when handed a script, since
# a file extension (run.sh) or ssh is not a shell, and so is any program that merely ends in sh.
SHELL_LOOKALIKE = re.compile(r"(?!ssh$)[a-z0-9_-]*sh")
# Options that hand a script over, in any letter case and abbreviation PowerShell accepts: -c, -Command,
# --commands, nu's -e and --execute, fish's --init-command, or a short bundle holding c such as tcsh's -fc.
FOREIGN_COMMAND_OPTION = re.compile(r"-(-commands?|-execute|-init-command|e|[a-z]*c[a-z]*)(=.*)?", re.IGNORECASE)
VERSION_SUFFIX = re.compile(r"[0-9._-]+$")
