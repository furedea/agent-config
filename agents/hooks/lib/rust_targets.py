"""Resolve Rust integration test files to Cargo test targets."""

from pathlib import Path
import tomllib


def rust_test_target(root: Path, filename: str) -> str:
    """Resolve an integration test file to its declared or auto-discovered Cargo target."""
    try:
        manifest = tomllib.loads((root / "Cargo.toml").read_text())
    except OSError, tomllib.TOMLDecodeError:
        return ""
    path = Path(filename)
    entries = [entry for entry in manifest.get("test", []) if "path" in entry and "name" in entry]
    for entry in sorted(entries, key=lambda entry: len(Path(entry["path"]).parent.parts), reverse=True):
        declared = Path(entry["path"])
        if path == declared or (
            declared.parent != Path("tests")
            and declared.parent.is_relative_to("tests")
            and path.is_relative_to(declared.parent)
        ):
            return entry["name"]
    if len(path.parts) > 2 and (root / "tests" / path.parts[1] / "main.rs").is_file():
        return path.parts[1]
    return path.stem if len(path.parts) == 2 else ""
