"""Read one ADR file into its front matter and body, and validate the front matter against the schema."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

DELIMITER = "---"
FILE_NAME = re.compile(r"^(?P<number>[0-9]{4})_.+\.md$")
SCHEMA_PATH = Path(__file__).with_name("front_matter.schema.json")
VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text()), format_checker=Draft202012Validator.FORMAT_CHECKER
)


@dataclass(frozen=True, slots=True)
class Document:
    """An ADR file split at its front matter; `front_matter` is whatever the YAML held."""

    number: str
    front_matter: object
    body: str


class InvalidDocumentError(Exception):
    """The file does not have the shape of an ADR file."""


def adr_number(file_name: str) -> str | None:
    """The four-digit ID of an ADR file name, or None when the name is not `NNNN_words.md`."""
    match = FILE_NAME.match(file_name)
    return match["number"] if match else None


def parse(file_name: str, text: str) -> Document:
    """Split `text` into front matter and body; raise InvalidDocumentError when there is no readable front matter."""
    number = adr_number(file_name)
    if number is None:
        raise InvalidDocumentError("file name must be NNNN_words.md")
    lines = text.split("\n")
    if lines[0] != DELIMITER or DELIMITER not in lines[1:]:
        raise InvalidDocumentError("front matter is missing: the file must start with a --- block")
    end = lines.index(DELIMITER, 1)
    return Document(number, _load_yaml("\n".join(lines[1:end])), "\n".join(lines[end + 1 :]))


def shape_errors(front_matter: object) -> tuple[str, ...]:
    """Every way `front_matter` departs from the schema, one sentence each, in a stable order."""
    errors = sorted(VALIDATOR.iter_errors(front_matter), key=lambda error: [str(part) for part in error.path])
    return tuple(_describe(error) for error in errors)


def _describe(error: ValidationError) -> str:
    location = ".".join(str(part) for part in error.path) or "front matter"
    return f"{location}: {error.message}"


def _load_yaml(text: str) -> object:
    """Parse YAML 1.2 with duplicate keys refused and dates kept as the strings written."""
    yaml = YAML(typ="safe", pure=True)
    yaml.constructor.add_constructor("tag:yaml.org,2002:timestamp", type(yaml.constructor).construct_yaml_str)
    try:
        return yaml.load(text)
    except YAMLError as error:
        problem = getattr(error, "problem", None) or "invalid syntax"
        raise InvalidDocumentError(f"front matter is not valid YAML: {problem}") from error
