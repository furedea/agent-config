"""Read the registry's YAML rule files. PyYAML is a development dependency, so hooks never import this module."""

from pathlib import Path

import yaml

from agents.lint.registry import Registry, Rule
from tests.runtime import REPO_ROOT

RULES_DIRECTORY = REPO_ROOT / "agents/lint/rules"


def rule_files(directory: Path = RULES_DIRECTORY) -> list[Path]:
    return sorted(directory.glob("*/*.yml"))


def load_rule(path: Path) -> Rule:
    return Rule.from_mapping(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_registry(directory: Path = RULES_DIRECTORY) -> Registry:
    return Registry.from_rules([load_rule(path) for path in rule_files(directory)])
