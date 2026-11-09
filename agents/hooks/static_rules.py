#!/usr/bin/env -S python3 -IB
"""Return the registry's static rule findings for edited files as hook feedback, never as a block."""

import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(SCRIPT.parent / "lib"))

from lib import hook_input, static_rule_scan
import lint_format


def main(arguments: list[str]) -> int:
    """Report findings for the files one provider payload edited; exit 1 only for unreadable input."""
    if arguments:
        print("Usage: static_rules.py", file=sys.stderr)
        return 1
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise TypeError("hook payload must be an object")
        lint_format.emit(static_rule_scan.diagnostics(hook_input.target_paths(payload)))
    except (ValueError, TypeError, OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
