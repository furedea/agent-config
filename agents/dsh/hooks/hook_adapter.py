#!/usr/bin/env -S python3 -IB
"""Translate DeepSeek Harness (dsh) hook payloads at the boundary to shared hook implementations."""

import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
# Deployed adapters live in ~/.<provider>/hooks beside ~/.claude/hooks; the source tree keeps agents/hooks.
COMMON = SCRIPT.parents[2] / (".claude/hooks" if SCRIPT.parent.parent.name.startswith(".") else "hooks")
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(COMMON / "lib"))

import provider_adapter

ADAPTER = provider_adapter.Adapter(
    provider_adapter.Profile(
        name="dsh",
        tools={
            "bash": "Bash",
            "read": "Read",
            "read_image": "Read",
            "write": "Write",
            "edit": "Edit",
            "str_replace_editor": "Edit",
            "apply_patch": "apply_patch",
            "glob": "Glob",
            "grep": "Grep",
            "web_fetch": "WebFetch",
            "web_search": "WebSearch",
        },
        lint_output=provider_adapter.system_message_output,
        manifest_env="AGENT_HARNESS_DSH_MANIFEST",
        manifest_default=".dsh/hooks.json",
    )
)


if __name__ == "__main__":
    sys.exit(ADAPTER.main(sys.argv[1:]))
