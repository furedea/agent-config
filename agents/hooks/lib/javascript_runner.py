"""Identify the package manager and test runner a JavaScript project uses."""

from pathlib import Path
import re


RUNNER_PREFIXES = {
    "pnpm": ("pnpm", "exec"),
    "npm": ("npm", "exec", "--"),
    "yarn": ("yarn", "exec"),
    "bun": ("bun", "x"),
}
LOCKFILE_MANAGERS = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
)


def package_manager(root: Path, package: dict) -> str:
    """Prefer the declared package manager, then the lockfile present, then npm."""
    manager = package.get("packageManager", "").split("@", 1)[0]
    if manager:
        return manager
    return next((name for lock, name in LOCKFILE_MANAGERS if (root / lock).is_file()), "npm")


def javascript_runner(package: dict, test_script: str) -> str:
    """Name the JavaScript test runner the project depends on, or an empty string when none is known."""
    dependencies = dict(package.get("dependencies") or {}, **(package.get("devDependencies") or {}))
    runner = next((name for name in ("vitest", "jest") if dependencies.get(name) is not None), "")
    if not runner and re.search(r"(^|\s)node\s+--test(\s|$)", test_script):
        return "node"
    return runner


def runner_arguments(manager: str, runner: str) -> tuple[str, ...]:
    """Invoke the runner through the package manager, or Node directly for its built-in runner."""
    return ("node", "--test") if runner == "node" else (*RUNNER_PREFIXES.get(manager, ("false",)), runner)
