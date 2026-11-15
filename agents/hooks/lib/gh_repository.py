"""Read the repository a gh word names: OWNER/REPO, HOST/OWNER/REPO, a URL, or a -R option value."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from gh_options import Word

GITHUB_HOST = "github.com"
REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
REPOSITORY_SPEC = re.compile(
    r"(?:(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]+)/)?(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9_.-]+)"
)
# A HOST/OWNER/REPO argument, as gh repo view takes one: a dotted host name, then owner and name.
HOST_REPOSITORY = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]+/[^/]+/[^/]+")


@dataclass(frozen=True, slots=True)
class Repository:
    """A github.com repository a call names, by owner and name."""

    owner: str
    name: str


def repository_words(words: tuple[Word, ...]) -> list[Word]:
    """The repository words of a call: -R and --repo values in any spelling, URLs, and HOST/OWNER/REPO arguments."""
    found: list[Word] = []
    for index, word in enumerate(words):
        if word.dynamic:
            continue
        value = word.value
        if value == "--repo" or (value.startswith("-") and not value.startswith("--") and value.endswith("R")):
            found += words[index + 1 : index + 2]
        elif value.startswith("--repo="):
            found.append(Word(value.removeprefix("--repo="), value.removeprefix("--repo=")))
        elif value.startswith("-") and not value.startswith("--") and "R" in value:
            rest = value[value.index("R") + 1 :].removeprefix("=")
            found.append(Word(rest, rest))
        elif is_url(value) or HOST_REPOSITORY.match(value):
            found.append(word)
    return found


def repository(spec: str) -> Repository | None:
    """The github.com repository an OWNER/REPO, HOST/OWNER/REPO, or URL names; None for any other host."""
    if is_url(spec):
        parts = urlsplit(spec if "://" in spec else "https://" + spec)
        if parts.hostname != GITHUB_HOST:
            return None
        spec = "/".join(parts.path.strip("/").split("/")[:2])
    match = REPOSITORY_SPEC.fullmatch(spec)
    if match is None or (match["host"] or GITHUB_HOST).lower() != GITHUB_HOST:
        return None
    return Repository(match["owner"], match["name"].removesuffix(".git"))


def is_url(value: str) -> bool:
    """Whether gh reads the word as a URL: a scheme, a github.com path, or an ssh form."""
    lowered = value.lower()
    return "://" in value or lowered.startswith((GITHUB_HOST + "/", "git@", "ssh:"))
