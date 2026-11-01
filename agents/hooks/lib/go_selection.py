"""Resolve changed Go files to the packages `go test` must run."""

from pathlib import Path

GO_FULL_SUITE = ("go", "test", "./...")


def go_files(extensions: list[str], changed: tuple[str, ...]) -> set[str]:
    """Return changed Go files, tests included, because a test edit still verifies its package."""
    return {path for path in changed if any(path.endswith(extension) for extension in extensions)}


def go_package_exists(root: Path, filename: str) -> bool:
    """Whether the file sits in a directory the go tool can address as a package."""
    parent = Path(filename).parent
    ignored = any(part == "testdata" or part.startswith((".", "_")) for part in parent.parts)
    return not ignored and (root / parent).is_dir()


def go_test_arguments(files: set[str], *, full: bool) -> tuple[str, ...]:
    """Name the packages holding the files, or the whole module when none are known."""
    directories = sorted({Path(path).parent for path in files})
    if full or not directories:
        return GO_FULL_SUITE
    return ("go", "test", *("." if directory == Path() else f"./{directory}" for directory in directories))
