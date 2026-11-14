"""Turn one parsed gh call into the operation it performs, its effect, and the repositories it acts on.

gh parses its options as pflag does: a value option takes the next word whatever it holds, and
options may follow positional arguments. A run-time word is accepted only where gh reads it as an
option's value or as data; anywhere it could become an option, the call is unclassified and asks.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import graphql_document
import shell_syntax
import shell_words
from gh_catalog import Catalog, CommandSpec, Effect

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
# A word whose only expansions are plain named parameters. In a call that is the whole line nothing
# assigns them, so each holds what the harness environment gave the shell and stays one word.
PARAMETER = r"\$(?:[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_\[])|\{[A-Za-z_][A-Za-z0-9_]*\})"
PLAIN_PARAMETER_WORD = re.compile(rf"""(?:[A-Za-z0-9_./:@=,+%#-]|{PARAMETER}|'[^']*'|"(?:[^"$`\\!]|{PARAMETER})*")+""")
# A run-time word starting with one of these cannot start with a dash.
LITERAL_START = re.compile(r"[\"']?[A-Za-z0-9_./:@=,+%#]")
FIELD_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
REPOSITORY_SPEC = re.compile(
    r"(?:(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]+)/)?(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9_.-]+)"
)
DOT_SEGMENT = re.compile(r"(?:^|/)(?:\.|%2e){1,2}(?:/|$)", re.IGNORECASE)
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
    `unscanned_files` marks a sent file whose path is known only at run time.
    """

    operations: tuple[str, ...]
    effect: Effect
    repositories: tuple[Repository, ...] = ()
    unknown_target: bool = False
    node: bool = False
    files: tuple[str, ...] = ()
    unscanned_files: bool = False

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


class _UnclassifiableError(ValueError):
    """Raised inside this module; `classify` returns it as an Unclassified value."""


@dataclass(frozen=True, slots=True)
class Word:
    """One argument as gh receives it, with what the shell may still do to it."""

    value: str
    source: str
    dynamic: bool = False
    spreading: bool = False

    @property
    def may_be_option(self) -> bool:
        """Whether gh could read the word as an option: it is one, may split, or may start with a dash at run time."""
        if self.spreading:
            return True
        return not LITERAL_START.match(self.source) if self.dynamic else self.value.startswith("-")


@dataclass(frozen=True, slots=True)
class OptionTable:
    """The options a command accepts: those taking a value, and flags taking none."""

    values: frozenset[str]
    flags: frozenset[str]


@dataclass(frozen=True, slots=True)
class OptionScan:
    """A call's arguments read against its option table."""

    options: tuple[tuple[str, Word], ...]
    positionals: tuple[Word, ...]
    flags: frozenset[str]

    def values_of(self, names: frozenset[str]) -> tuple[Word, ...]:
        """The value words given to any of the named options, in order."""
        return tuple(word for option, word in self.options if option in names)


@dataclass(frozen=True, slots=True)
class ApiRequest:
    """The HTTP request one gh api call sends."""

    method: str
    endpoint: Word
    fields: tuple[tuple[str, Word], ...]
    files: tuple[str, ...]
    unscanned_files: bool
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
        Word(value, source, dynamic, spreading and not (single_call and PLAIN_PARAMETER_WORD.fullmatch(source)))
        for value, source, dynamic, spreading in zip(
            command.arguments, command.words, command.dynamic, command.spreading, strict=True
        )
    )[1:]
    try:
        if command.appends_input:
            raise _UnclassifiableError("xargs appends arguments the guard cannot see")
        return _classify_words(words, catalog)
    except _UnclassifiableError as error:
        return Unclassified(str(error))
    except graphql_document.GraphQLSyntaxError as error:
        return Unclassified(f"the GraphQL document cannot be read: {error}")


def _classify_words(words: tuple[Word, ...], catalog: Catalog) -> GhCall:
    if not words or words[0].dynamic or words[0].spreading:
        raise _UnclassifiableError("the gh subcommand is not a literal word")
    if words[0].value == "api":
        return _classify_api(words[1:], catalog)
    if len(words) < 2 or words[1].dynamic or words[1].spreading:
        raise _UnclassifiableError("the gh subcommand is not a literal word")
    spec = catalog.commands.get(f"{words[0].value} {words[1].value}")
    if spec is None:
        raise _UnclassifiableError(f"'gh {words[0].value} {words[1].value}' is not in the gh operation table")
    if spec.effect is Effect.READ:
        return GhCall((spec.operation,), spec.effect)
    if spec.effect is Effect.LOCAL:
        return _classify_local(words[2:], spec)
    return _classify_write(words[2:], spec)


def _classify_local(words: tuple[Word, ...], spec: CommandSpec) -> GhCall:
    """A change to the local checkout, whose every option must be listed; `--` would pass options to git."""
    if any(word.value == "--" for word in words):
        raise _UnclassifiableError("arguments after -- reach another program")
    scan = _scan(words, OptionTable(spec.value_options, spec.flags))
    if any(word.may_be_option for word in scan.positionals):
        raise _UnclassifiableError("an argument may become an option at run time")
    return GhCall((spec.operation,), spec.effect)


def _classify_write(words: tuple[Word, ...], spec: CommandSpec) -> GhCall:
    flags = spec.flags | spec.irreversible_flags | spec.read_flags
    scan = _scan(words, OptionTable(spec.value_options | REPOSITORY_OPTIONS, flags))
    _check_write_words(scan, spec)
    targets = scan.values_of(REPOSITORY_OPTIONS | spec.repositories)
    targets += tuple(word for word in scan.positionals if _is_url(word.value))
    repositories = tuple(None if word.dynamic else repository(word.value) for word in targets)
    if scan.flags & spec.read_flags:
        return GhCall((spec.operation,), Effect.READ)
    effect = Effect.IRREVERSIBLE if scan.flags & spec.irreversible_flags else spec.effect
    files = scan.values_of(spec.files)
    return GhCall(
        (spec.operation,),
        effect,
        tuple(repository for repository in repositories if repository),
        None in repositories,
        files=tuple(word.value for word in files if not word.dynamic),
        unscanned_files=any(word.dynamic for word in files),
    )


def _check_write_words(scan: OptionScan, spec: CommandSpec) -> None:
    """Refuse a write whose words could carry an unseen option or unseen text."""
    if any(word.may_be_option for word in scan.positionals):
        raise _UnclassifiableError("an argument may become an option at run time")
    if any(word.spreading for _, word in scan.options):
        raise _UnclassifiableError("an option value may split into several words at run time")
    if any(word.dynamic and has_parameter(word.source) for word in scan.values_of(spec.texts)):
        raise _UnclassifiableError("text sent to GitHub holds a parameter expansion")


def _scan(words: tuple[Word, ...], table: OptionTable) -> OptionScan:
    """Read options as pflag does; an option the table does not name makes the call unclassified."""
    options: list[tuple[str, Word]] = []
    positionals: list[Word] = []
    found: set[str] = set()
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if word.value == "--" and not word.dynamic:
            positionals += words[index:]
            break
        if word.dynamic or not word.value.startswith("-") or word.value == "-":
            positionals.append(word)
            continue
        names, value, consumed = _option(word, words[index : index + 1], table)
        found |= names
        index += consumed
        if value is not None:
            options.append((next(iter(names & table.values)), value))
    return OptionScan(tuple(options), tuple(positionals), frozenset(found))


def _option(word: Word, following: tuple[Word, ...], table: OptionTable) -> tuple[frozenset[str], Word | None, int]:
    """The option names a word sets, its value word if one takes a value, and how many further words that used."""
    if word.value.startswith("--"):
        name, equals, inline = word.value.partition("=")
        if name in table.flags and not equals:
            return frozenset({name}), None, 0
        _require_value_option(name, table)
        return (frozenset({name}), Word(inline, inline), 0) if equals else _with_following(name, following)
    names: set[str] = set()
    for position, letter in enumerate(word.value[1:], 1):
        name = "-" + letter
        if name in table.flags:
            names.add(name)
            continue
        _require_value_option(name, table)
        rest = word.value[position + 1 :]
        _, value, consumed = (frozenset(), Word(rest, rest), 0) if rest else _with_following(name, following)
        return frozenset(names | {name}), value, consumed
    return frozenset(names), None, 0


def _require_value_option(name: str, table: OptionTable) -> None:
    if name not in table.values:
        raise _UnclassifiableError(f"option {name} is not in the gh operation table for this command")


def _with_following(name: str, following: tuple[Word, ...]) -> tuple[frozenset[str], Word, int]:
    if not following:
        raise _UnclassifiableError(f"option {name} has no value")
    return frozenset({name}), following[0], 1


def _classify_api(words: tuple[Word, ...], catalog: Catalog) -> GhCall:
    request = _api_request(words)
    if not request.endpoint.dynamic and request.path in GRAPHQL_PATHS:
        return _classify_graphql(request, catalog)
    if request.method in READ_METHODS:
        _check_read_files(request)
        return GhCall(("api.read",), Effect.READ, files=request.files)
    if request.endpoint.dynamic:
        raise _UnclassifiableError("a gh api write names its endpoint only at run time")
    _check_field_texts(request)
    if DOT_SEGMENT.search(request.path):
        raise _UnclassifiableError("a gh api write path holds a dot segment")
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
    )


def _check_read_files(request: ApiRequest) -> None:
    """Refuse a read that sends a file named only at run time, which no scan can see before it leaves."""
    if request.unscanned_files:
        raise _UnclassifiableError("a GitHub read sends a file named only at run time")


def _check_field_texts(request: ApiRequest) -> None:
    """Refuse a write whose field text, other than an @file path, expands a parameter."""
    for _, word in request.fields:
        if word.dynamic and not word.value.partition("=")[2].startswith("@") and has_parameter(word.source):
            raise _UnclassifiableError("text sent to GitHub holds a parameter expansion")


def _api_request(words: tuple[Word, ...]) -> ApiRequest:
    if any(word.spreading for word in words):
        raise _UnclassifiableError("a gh api argument may split into several words at run time")
    scan = _scan(words, OptionTable(API_VALUES, API_FLAGS))
    if len(scan.positionals) != 1 or scan.positionals[0].may_be_option:
        raise _UnclassifiableError("gh api needs exactly one endpoint that cannot become an option")
    if any(word.dynamic for word in scan.values_of(METHOD_OPTIONS | HEADER_OPTIONS | {"--hostname"})):
        raise _UnclassifiableError("a gh api method, header, or host is known only at run time")
    if any(METHOD_OVERRIDE.match(word.value) for word in scan.values_of(HEADER_OPTIONS)):
        raise _UnclassifiableError("a gh api header overrides the method")
    if _names_foreign_host(scan):
        raise _UnclassifiableError("a gh api request goes to another host than api.github.com")
    fields = tuple((option, word) for option, word in scan.options if option in FIELD_OPTIONS)
    sends_body = bool(fields or scan.values_of(frozenset({"--input"})))
    methods = scan.values_of(METHOD_OPTIONS)
    return ApiRequest(
        methods[-1].value.upper() if methods else "POST" if sends_body else "GET",
        scan.positionals[0],
        fields,
        _sent_files(scan),
        any(word.dynamic for word in _file_words(scan)),
        bool(scan.values_of(frozenset({"--input"}))),
    )


def _names_foreign_host(scan: OptionScan) -> bool:
    if any(word.value.lower() != GITHUB_HOST for word in scan.values_of(frozenset({"--hostname"}))):
        return True
    endpoint = scan.positionals[0]
    return "://" in endpoint.value and (endpoint.dynamic or urlsplit(endpoint.value).hostname != "api." + GITHUB_HOST)


def _file_words(scan: OptionScan) -> tuple[Word, ...]:
    """The words naming a file a gh api call sends: --input values and -F values read with @."""
    typed = tuple(word for word in scan.values_of(TYPED_FIELD_OPTIONS) if word.value.partition("=")[2].startswith("@"))
    return scan.values_of(frozenset({"--input"})) + typed


def _sent_files(scan: OptionScan) -> tuple[str, ...]:
    """Literal local files a gh api call sends; standard input is not a file."""
    paths = (
        word.value.partition("=")[2][1:] if "=" in word.value else word.value
        for word in _file_words(scan)
        if not word.dynamic
    )
    return tuple(path for path in paths if path != "-")


def _classify_graphql(request: ApiRequest, catalog: Catalog) -> GhCall:
    if request.method != "POST":
        raise _UnclassifiableError("a GraphQL request with another method than POST")
    found = graphql_document.operations(_document(request))
    types = {item.type for item in found}
    if graphql_document.OperationType.SUBSCRIPTION in types:
        raise _UnclassifiableError("a GraphQL subscription")
    mutated = [
        field for item in found if item.type == graphql_document.OperationType.MUTATION for field in item.root_fields
    ]
    if not mutated:
        _check_read_files(request)
        return GhCall(("graphql.query",), Effect.READ, files=request.files)
    _check_field_texts(request)
    unknown = [field for field in mutated if field not in catalog.mutations]
    if unknown:
        return GhCall(
            tuple(f"graphql.{field}" for field in unknown), Effect.IRREVERSIBLE, node=True, files=request.files
        )
    operations = [catalog.mutations[field] for field in mutated]
    reversible = all(item.effect is Effect.REVERSIBLE for item in operations)
    names = tuple(sorted({item.name for item in operations}))
    effect = Effect.REVERSIBLE if reversible else Effect.IRREVERSIBLE
    return GhCall(names, effect, node=True, files=request.files, unscanned_files=request.unscanned_files)


def _document(request: ApiRequest) -> str:
    """The text of the one literal query field given inline."""
    if request.sends_input or any(word.dynamic and not FIELD_KEY.match(word.source) for _, word in request.fields):
        raise _UnclassifiableError("a GraphQL request body or field name is known only at run time")
    queries = [(option, word) for option, word in request.fields if word.value.partition("=")[0] == "query"]
    if len(queries) != 1 or queries[0][1].dynamic:
        raise _UnclassifiableError("a GraphQL request needs exactly one literal query field")
    ((option, word),) = queries
    text = word.value.partition("=")[2]
    if option in TYPED_FIELD_OPTIONS and text.startswith("@"):
        raise _UnclassifiableError("a GraphQL document read from a file may change before gh reads it")
    return text


def has_parameter(source: str) -> bool:
    """Whether a word expands a parameter other than HOME outside any command substitution.

    A substitution's commands are judged on their own and its text is part of the command, so a body
    built by one, such as a quoted heredoc through cat, hides no value of its own.
    """
    tree = shell_syntax.syntax_tree(": " + source)
    return any(
        node.get("Type") == "ParamExp" and not shell_words.is_home_parameter(node)
        for node in shell_words.word_nodes(tree)
    )


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
