"""Turn one parsed gh call into the operation it performs, its effect, and the repositories it acts on.

gh parses its options as pflag does: a value option takes the next word whatever it holds, and
options may follow positional arguments. A run-time word is accepted only where gh reads it as an
option's value or as data; anywhere it could become an option, the call is unclassified and asks.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import gh_options
import graphql_document
import shell_syntax
from gh_catalog import Catalog, CommandSpec, Effect
from gh_options import (
    OptionScan,
    OptionTable,
    UnclassifiableError,
    Word,
    has_parameter,
    stays_one_word,
)

GITHUB_HOST = "github.com"
REPOSITORY_OPTIONS = frozenset({"-R", "--repo"})
METHOD_OPTIONS = frozenset({"-X", "--method"})
HEADER_OPTIONS = frozenset({"-H", "--header"})
TYPED_FIELD_OPTIONS = frozenset({"-F", "--field"})
FIELD_OPTIONS = TYPED_FIELD_OPTIONS | {"-f", "--raw-field"}
API_VALUES = METHOD_OPTIONS | HEADER_OPTIONS | FIELD_OPTIONS
API_VALUES |= {"--hostname", "--input", "-q", "--jq", "-t", "--template", "--cache", "-p", "--preview"}
API_FLAGS = frozenset(
    {"--paginate", "--slurp", "-i", "--include", "--silent", "--verbose", "--allow-escape-sequences"}
)
READ_METHODS = frozenset({"GET", "HEAD"})
GRAPHQL_PATHS = frozenset({"graphql", "api/graphql"})
METHOD_OVERRIDE = re.compile(r"\s*x-(?:http-)?method(?:-override)?\s*:", re.IGNORECASE)
FIELD_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
REPOSITORY_SPEC = re.compile(
    r"(?:(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]+)/)?(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9_.-]+)"
)
DOT_SEGMENT = re.compile(r"(?:^|/)(?:\.|%2e){1,2}(?:/|$)", re.IGNORECASE)
STDIN_PATHS = re.compile(r"/dev/stdin|/dev/fd/0|/proc/self/fd/0")
# A run-time endpoint that starts with a literal path segment and slash, which no expansion can turn into a URL.
LITERAL_PATH_START = re.compile(r"[\"']?/?[A-Za-z0-9_.-]+/")
OWNER_PREFIX = re.compile(r"[\"']?[A-Za-z0-9-]+/")
REPOSITORY_PATH = re.compile(r"repos/(?P<owner>[^/]+)/(?P<name>[^/]+)")


@dataclass(frozen=True, slots=True)
class Repository:
    """A github.com repository a call names, by owner and name."""

    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class GhCall:
    """What one gh call does, as far as its words show.

    `repositories` are the repositories it names; with none and no other mark, the call acts on the
    repository gh picks from the working directory. `unknown_target` marks a repository or host
    known only at run time or outside github.com, and `node` a target named by GraphQL node ID.
    `files` are local files, named by literal paths, whose content the call sends, and
    `unscanned_files` are the source texts of sent file paths known only at run time, and `reads_stdin` a
    body read from standard input.
    """

    operations: tuple[str, ...]
    effect: Effect
    repositories: tuple[Repository, ...] = ()
    unknown_target: bool = False
    node: bool = False
    files: tuple[str, ...] = ()
    unscanned_files: tuple[str, ...] = ()
    reads_stdin: bool = False

    @property
    def label(self) -> str:
        """The operations, for messages and audit records."""
        return ",".join(self.operations)

    @property
    def implicit(self) -> bool:
        """Whether the call acts on the repository gh picks from the working directory."""
        return not (self.repositories or self.unknown_target or self.node)


@dataclass(frozen=True, slots=True)
class Unclassified:
    """Why the guard cannot tell what a gh call does."""

    reason: str


@dataclass(frozen=True, slots=True)
class ApiRequest:
    """The HTTP request one gh api call sends."""

    method: str
    endpoint: Word
    fields: tuple[tuple[str, Word], ...]
    files: tuple[str, ...]
    unscanned_files: tuple[str, ...]
    reads_stdin: bool
    sends_input: bool

    @property
    def path(self) -> str:
        """The endpoint path without a leading slash, the API host, or a query string."""
        endpoint = self.endpoint.value
        if "://" in endpoint:
            endpoint = urlsplit(endpoint).path
        return endpoint.split("?", 1)[0].lstrip("/")


def classify(command: shell_syntax.Command, catalog: Catalog, *, single_call: bool) -> GhCall | Unclassified:
    """Classify a canonical gh call; `single_call` says the line is this one call and assigns nothing."""
    words = tuple(
        Word(value, source, dynamic, spreading and not (single_call and stays_one_word(source)))
        for value, source, dynamic, spreading in zip(
            command.arguments, command.words, command.dynamic, command.spreading, strict=True
        )
    )[1:]
    try:
        if command.appends_input:
            raise UnclassifiableError("xargs appends arguments the guard cannot see")
        return _classify_words(words, catalog, single_call)
    except UnclassifiableError as error:
        return Unclassified(str(error))
    except graphql_document.GraphQLSyntaxError as error:
        return Unclassified(f"the GraphQL document cannot be read: {error}")


def _classify_words(words: tuple[Word, ...], catalog: Catalog, single_call: bool) -> GhCall:
    if not words or words[0].dynamic or words[0].spreading:
        raise UnclassifiableError("the gh subcommand is not a literal word")
    if words[0].value == "api":
        return _classify_api(words[1:], catalog, single_call)
    if len(words) < 2 or words[1].dynamic or words[1].spreading:
        raise UnclassifiableError("the gh subcommand is not a literal word")
    spec = catalog.commands.get(f"{words[0].value} {words[1].value}")
    if spec is None:
        raise UnclassifiableError(f"'gh {words[0].value} {words[1].value}' is not in the gh operation table")
    if spec.effect is Effect.READ:
        _check_read_repositories(words[2:])
        return GhCall((spec.operation,), spec.effect)
    if spec.effect is Effect.LOCAL:
        return _classify_local(words[2:], spec)
    return _classify_write(words[2:], spec, single_call)


def _check_read_repositories(words: tuple[Word, ...]) -> None:
    """Refuse a read whose repository option or URL names another host than github.com.

    A run-time repository passes when a literal owner and slash start it: gh could read only that
    owner, a name without a dot, as a host.
    """
    for word in words:
        if word.dynamic and (word.source.startswith("-") or _may_name_url(word)):
            raise UnclassifiableError("a read takes an option value or URL known only at run time")
    for word in _repository_words(words):
        if word.dynamic and not OWNER_PREFIX.match(word.source):
            raise UnclassifiableError("a read names its repository only at run time")
        if not word.dynamic and repository(word.value) is None:
            raise UnclassifiableError("a read names another host than github.com")


def _repository_words(words: tuple[Word, ...]) -> list[Word]:
    """The values given to -R or --repo in any spelling pflag reads, a short bundle included, and each URL."""
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
        elif _is_url(value):
            found.append(word)
    return found


def _classify_local(words: tuple[Word, ...], spec: CommandSpec) -> GhCall:
    """A change to the local checkout, whose every option must be listed; `--` would pass options to git."""
    if any(word.value == "--" for word in words):
        raise UnclassifiableError("arguments after -- reach another program")
    scan = gh_options.scan(words, OptionTable(spec.value_options, spec.flags))
    if any(word.may_be_option for word in scan.positionals):
        raise UnclassifiableError("an argument may become an option at run time")
    return GhCall((spec.operation,), spec.effect)


def _classify_write(words: tuple[Word, ...], spec: CommandSpec, single_call: bool) -> GhCall:
    flags = spec.flags | spec.irreversible_flags | spec.read_flags
    scan = gh_options.scan(words, OptionTable(spec.value_options | REPOSITORY_OPTIONS, flags))
    _check_write_words(scan)
    _check_sent_values(scan.values_of(spec.values | spec.texts) + scan.positionals, single_call)
    targets = scan.values_of(REPOSITORY_OPTIONS | spec.repositories)
    targets += tuple(word for word in scan.positionals if _is_url(word.value))
    repositories = tuple(None if word.dynamic else repository(word.value) for word in targets)
    if scan.flags & spec.read_flags:
        return GhCall((spec.operation,), Effect.READ)
    effect = Effect.IRREVERSIBLE if scan.flags & spec.irreversible_flags else spec.effect
    files = scan.values_of(spec.files)
    paths = [_stdin_path(word.value) for word in files if not word.dynamic]
    return GhCall(
        (spec.operation,),
        effect,
        tuple(repository for repository in repositories if repository),
        None in repositories,
        files=tuple(path for path in paths if path != "-"),
        unscanned_files=tuple(word.source for word in files if word.dynamic),
        reads_stdin="-" in paths,
    )


def _check_write_words(scan: OptionScan) -> None:
    """Refuse a write whose words could carry an option the guard does not see."""
    if any(word.may_be_option for word in scan.positionals):
        raise UnclassifiableError("an argument may become an option at run time")
    if any(_may_name_url(word) for word in scan.positionals):
        raise UnclassifiableError("an argument may become a URL at run time")
    if any(word.spreading for _, word in scan.options):
        raise UnclassifiableError("an option value may split into several words at run time")


def _check_sent_values(words: tuple[Word, ...], single_call: bool) -> None:
    """Refuse a value sent to GitHub that the guard cannot read before it leaves.

    A parameter may hold any secret of the environment. A command substitution is visible text only
    on a line whose other commands just print, such as a body through a quoted heredoc.
    """
    for word in words:
        if word.dynamic and has_parameter(word.source):
            raise UnclassifiableError("a value sent to GitHub holds a parameter expansion")
        if word.dynamic and not single_call:
            raise UnclassifiableError("a value sent to GitHub is built by a command that does more than print")


def _classify_api(words: tuple[Word, ...], catalog: Catalog, single_call: bool) -> GhCall:
    request = _api_request(words)
    texts = tuple(
        word for option, word in request.fields if option not in TYPED_FIELD_OPTIONS or not _names_file(word)
    )
    _check_sent_values(texts, single_call)
    if not request.endpoint.dynamic and request.path in GRAPHQL_PATHS:
        return _classify_graphql(request, catalog)
    if request.method in READ_METHODS:
        _check_read_files(request)
        return GhCall(("api.read",), Effect.READ, files=request.files, reads_stdin=request.reads_stdin)
    if request.endpoint.dynamic:
        raise UnclassifiableError("a gh api write names its endpoint only at run time")
    if DOT_SEGMENT.search(request.path):
        raise UnclassifiableError("a gh api write path holds a dot segment")
    route = catalog.route(request.method, request.path)
    if route is None:
        return GhCall((f"api.{request.method.lower()}",), Effect.IRREVERSIBLE, unknown_target=True)
    match = REPOSITORY_PATH.match(request.path)
    placeholder = match is not None and "{" in match["owner"] + match["name"]
    repositories = (Repository(match["owner"], match["name"]),) if match and not placeholder else ()
    unknown = not (repositories or placeholder)
    return GhCall(
        (route.operation,),
        route.effect,
        repositories,
        unknown,
        files=request.files,
        unscanned_files=request.unscanned_files,
        reads_stdin=request.reads_stdin,
    )


def _check_read_files(request: ApiRequest) -> None:
    """Refuse a read that sends a file named only at run time, which no scan can see before it leaves."""
    if request.unscanned_files:
        raise UnclassifiableError("a GitHub read sends a file named only at run time")


def _api_request(words: tuple[Word, ...]) -> ApiRequest:
    if any(word.spreading for word in words):
        raise UnclassifiableError("a gh api argument may split into several words at run time")
    scan = gh_options.scan(words, OptionTable(API_VALUES, API_FLAGS))
    if len(scan.positionals) != 1 or scan.positionals[0].may_be_option:
        raise UnclassifiableError("gh api needs exactly one endpoint that cannot become an option")
    endpoint = scan.positionals[0]
    if endpoint.dynamic and not LITERAL_PATH_START.match(endpoint.source):
        raise UnclassifiableError("a gh api endpoint known at run time must start with a literal path segment")
    if any(word.dynamic for word in scan.values_of(METHOD_OPTIONS | HEADER_OPTIONS | {"--hostname"})):
        raise UnclassifiableError("a gh api method, header, or host is known only at run time")
    if any(METHOD_OVERRIDE.match(word.value) for word in scan.values_of(HEADER_OPTIONS)):
        raise UnclassifiableError("a gh api header overrides the method")
    if _names_foreign_host(scan):
        raise UnclassifiableError("a gh api request goes to another host than api.github.com")
    fields = tuple((option, word) for option, word in scan.options if option in FIELD_OPTIONS)
    sends_body = bool(fields or scan.values_of(frozenset({"--input"})))
    methods = scan.values_of(METHOD_OPTIONS)
    return ApiRequest(
        methods[-1].value.upper() if methods else "POST" if sends_body else "GET",
        scan.positionals[0],
        fields,
        _sent_files(scan),
        tuple(_file_source(word) for word in _file_words(scan) if word.dynamic),
        any(_file_path(word) == "-" for word in _file_words(scan)),
        bool(scan.values_of(frozenset({"--input"}))),
    )


def _names_foreign_host(scan: OptionScan) -> bool:
    if any(word.value.lower() != GITHUB_HOST for word in scan.values_of(frozenset({"--hostname"}))):
        return True
    endpoint = scan.positionals[0]
    if "://" not in endpoint.value:
        return False
    parts = urlsplit(endpoint.value)
    return endpoint.dynamic or parts.scheme != "https" or parts.hostname != "api." + GITHUB_HOST


def _file_words(scan: OptionScan) -> tuple[Word, ...]:
    """The words naming a file a gh api call sends: --input values and -F values read with @."""
    typed = tuple(word for word in scan.values_of(TYPED_FIELD_OPTIONS) if _names_file(word))
    return scan.values_of(frozenset({"--input"})) + typed


def _sent_files(scan: OptionScan) -> tuple[str, ...]:
    """Literal local files a gh api call sends; standard input is not a file."""
    paths = (_file_path(word) for word in _file_words(scan) if not word.dynamic)
    return tuple(path for path in paths if path != "-")


def _names_file(word: Word) -> bool:
    """Whether a -F field value reads a file, as key=@path."""
    return word.value.partition("=")[2].startswith("@")


def _may_name_url(word: Word) -> bool:
    """Whether a run-time word could become a URL: it holds a colon, or its literal start begins a scheme.

    A word that starts with an expansion is judged elsewhere: as an option for a write, and for a read
    the sandbox's network allowlist and gh's per-host login keep it from reaching another host.
    """
    if not word.dynamic:
        return False
    lead = re.sub(r"[\"'\\]", "", re.split(r"[$`]", word.source, maxsplit=1)[0]).lower()
    return ":" in word.source or (bool(lead) and any(scheme.startswith(lead) for scheme in ("https://", "http://")))


def _stdin_path(path: str) -> str:
    """`-` for a path that is standard input; refuse any other device, process, or non-regular file.

    The path is resolved the way the shell's open would, through `~`, `..`, and symlinks.
    """
    resolved = Path(os.path.realpath(Path(path).expanduser()))
    if path == "-" or STDIN_PATHS.fullmatch(path) or STDIN_PATHS.fullmatch(str(resolved)):
        return "-"
    if str(resolved).startswith(("/dev/", "/proc/")) or (resolved.exists() and not resolved.is_file()):
        raise UnclassifiableError("a sent file is a device, process, or other non-regular file")
    return path


def _file_source(word: Word) -> str:
    """The source text of the path a run-time file word names, after a key=@ prefix."""
    return word.source.partition("=")[2].removeprefix("@") if _names_file(word) else word.source


def _file_path(word: Word) -> str:
    """The path a file word names: an --input value as is, a key=@path field after its @."""
    return _stdin_path(word.value.partition("=")[2][1:] if _names_file(word) else word.value)


def _classify_graphql(request: ApiRequest, catalog: Catalog) -> GhCall:
    if request.method != "POST":
        raise UnclassifiableError("a GraphQL request with another method than POST")
    found = graphql_document.operations(_document(request))
    types = {item.type for item in found}
    if graphql_document.OperationType.SUBSCRIPTION in types:
        raise UnclassifiableError("a GraphQL subscription")
    mutated = [
        field for item in found if item.type == graphql_document.OperationType.MUTATION for field in item.root_fields
    ]
    if not mutated:
        _check_read_files(request)
        return GhCall(("graphql.query",), Effect.READ, files=request.files, reads_stdin=request.reads_stdin)
    unknown = [field for field in mutated if field not in catalog.mutations]
    if unknown:
        return GhCall(
            tuple(f"graphql.{field}" for field in unknown), Effect.IRREVERSIBLE, node=True, files=request.files
        )
    operations = [catalog.mutations[field] for field in mutated]
    reversible = all(item.effect is Effect.REVERSIBLE for item in operations)
    names = tuple(sorted({item.name for item in operations}))
    effect = Effect.REVERSIBLE if reversible else Effect.IRREVERSIBLE
    return GhCall(
        names,
        effect,
        node=True,
        files=request.files,
        unscanned_files=request.unscanned_files,
        reads_stdin=request.reads_stdin,
    )


def _document(request: ApiRequest) -> str:
    """The text of the one literal query field given inline."""
    if request.sends_input or any(word.dynamic and not FIELD_KEY.match(word.source) for _, word in request.fields):
        raise UnclassifiableError("a GraphQL request body or field name is known only at run time")
    queries = [(option, word) for option, word in request.fields if word.value.partition("=")[0] == "query"]
    if len(queries) != 1 or queries[0][1].dynamic:
        raise UnclassifiableError("a GraphQL request needs exactly one literal query field")
    ((option, word),) = queries
    text = word.value.partition("=")[2]
    if option in TYPED_FIELD_OPTIONS and text.startswith("@"):
        raise UnclassifiableError("a GraphQL document read from a file may change before gh reads it")
    return text


def repository(spec: str) -> Repository | None:
    """The github.com repository an OWNER/REPO, HOST/OWNER/REPO, or URL names; None for any other host."""
    if _is_url(spec):
        parts = urlsplit(spec if "://" in spec else "https://" + spec)
        if parts.hostname != GITHUB_HOST:
            return None
        spec = "/".join(parts.path.strip("/").split("/")[:2])
    match = REPOSITORY_SPEC.fullmatch(spec)
    if match is None or (match["host"] or GITHUB_HOST).lower() != GITHUB_HOST:
        return None
    return Repository(match["owner"], match["name"].removesuffix(".git"))


def _is_url(value: str) -> bool:
    return "://" in value or value.lower().startswith(GITHUB_HOST + "/")
