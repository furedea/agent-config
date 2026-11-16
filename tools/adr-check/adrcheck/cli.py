"""Command line of adr-check: exit 0 when clean, 1 for findings, 2 when the check could not run."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from adrcheck import directory
from adrcheck.history import BaseUnreadableError

CLEAN = 0
FINDINGS = 1
UNUSABLE = 2


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the check and print one line per finding."""
    options = _parser().parse_args(arguments)
    if not options.directory.is_dir():
        print(f"adr-check: {options.directory} is not a directory", file=sys.stderr)
        return UNUSABLE
    try:
        findings = directory.check(options.directory, options.base)
    except BaseUnreadableError as error:
        print(f"adr-check: cannot read ADRs at the base commit: {error}", file=sys.stderr)
        return UNUSABLE
    for finding in findings:
        print(f"{options.directory / finding.file_name}: {finding.message}")
    return FINDINGS if findings else CLEAN


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adr-check", description="Check the MADR ADRs in a directory.")
    parser.add_argument("directory", type=Path, help="the directory holding the ADR files, usually docs/adr")
    parser.add_argument(
        "--base", metavar="REV", help="also fail when an ADR accepted at REV was removed, renumbered, or rewritten"
    )
    return parser
