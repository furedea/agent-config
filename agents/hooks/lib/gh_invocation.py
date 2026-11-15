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
from gh_repository import (
    GITHUB_HOST,
    REPOSITORY_OPTIONS,
    Repository,
    is_url,
    repository,
    repository_words,
)

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
DOT_SEGMENT = re.compile(r"(?:^|/)(?:\.|%2e){1,2}(?:/|$)", re.IGNORECASE)
# --web, or a short option bundle holding -w, which opens the browser gh is configured with.
WEB_OPTION = re.compile(r"--web(?:=.*)?|-(?!-)[A-Za-z]*w.*")
PLAIN_PARAMETER = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})")
ISSUE_NUMBER = re.compile(r"#?[0-9]+")
STDIN_PATHS = re.compile(r"/dev/stdin|/dev/fd/0|/proc/self/fd/0")
# A run-time endpoint that starts with a literal path segment and slash, which no expansion can turn into a URL.
LITERAL_PATH_START = re.compile(r"[\"']?/?[A-Za-z0-9_.-]+/")
OWNER_PREFIX = re.compile(r"[\"']?[A-Za-z0-9-]+/")
REPOSITORY_PATH = re.compile(r"repos/(?P<owner>[^/]+)/(?P<name>[^/]+)")


@dataclass(frozen=True, slots=True)
class GhCall:
    """What one gh call does, as far as its words show.

    `repositories` are the repositories it names; with none and no other mark, the call acts on the
    repository gh picks from the working directory. `unknown_target` marks a repository or host
    known only at run time or outside github.com, and `node` a target named by GraphQL node ID.
    `files` are local files, named by literal paths, whose content the call sends, and
    `unscanned_files` are the source texts of sent file paths known only at run time, and `reads_stdin` a
    body read from standard input. `related` are repositories of issues the write links to, which must
    be trusted beside the target, whether that target is named or the working directory's.
    `reads_working_repository` marks a read or local change, whose working-directory remotes must keep
    gh on github.com even when an option seems to name a repository, since the guard does not parse
    every read option.
    """

    operations: tuple[str, ...]
    effect: Effect
    repositories: tuple[Repository, ...] = ()
    unknown_target: bool = False
    node: bool = False
    files: tuple[str, ...] = ()
    unscanned_files: tuple[str, ...] = ()
    reads_stdin: bool = False
    related: tuple[Repository, ...] = ()
    reads_working_repository: bool = False

    @property
    def label(self) -> str:
        """The operations, for messages and audit records."""
        return ",".join(self.operations)

    @property
    def implicit(self) -> bool:
        """Whether the call acts on the repository gh picks from the working directory."""
        return not (self.repositories or self.node)


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
        if spec.operation == "repo.view":
            _check_repository_arguments(words[2:])
        return GhCall((spec.operation,), spec.effect, reads_working_repository=True)
    if spec.effect is Effect.LOCAL:
        return _classify_local(words[2:], spec)
    return _classify_write(words[2:], spec, single_call)


def _check_read_repositories(words: tuple[Word, ...]) -> None:
    """Refuse a read whose repository option or URL names another host than github.com.

    A run-time repository passes when a literal owner and slash start it: gh could read only that
    owner, a name without a dot, as a host.
    """
    for word in words:
        if word.spreading:
            raise UnclassifiableError("a read takes a word that may split into options at run time")
        if not word.dynamic and WEB_OPTION.fullmatch(word.value):
            raise UnclassifiableError("a read opens a browser, which runs a program the guard cannot judge")
        if word.dynamic and (word.source.startswith("-") or _may_name_url(word) or not _plain_parameters(word)):
            raise UnclassifiableError("a read takes an option value, URL, or computed word known only at run time")
        if word.dynamic and "/" in word.source and not OWNER_PREFIX.match(word.source):
            raise UnclassifiableError("a read takes a path whose host part is known only at run time")
    if any(_names_foreign_host_once_expanded(word) for word in words if word.dynamic):
        raise UnclassifiableError("a read names another host than github.com once its parameters expand")
    for word in repository_words(words):
        if word.dynamic and not OWNER_PREFIX.match(word.source):
            raise UnclassifiableError("a read names its repository only at run time")
        if not word.dynamic and repository(word.value) is None:
            raise UnclassifiableError("a read names another host than github.com")


def _check_repository_arguments(words: tuple[Word, ...]) -> None:
    """Refuse a repository argument gh would read as HOST/OWNER/REPO, or as a URL, on another host than github.com."""
    for word in words:
        if word.dynamic and not OWNER_PREFIX.match(word.source):
            raise UnclassifiableError("a repository argument is known only at run time")
        if word.dynamic or word.value.startswith("-"):
            continue
        if ("/" in word.value or ":" in word.value) and repository(word.value) is None:
            raise UnclassifiableError("a repository argument names another host than github.com")


def _classify_local(words: tuple[Word, ...], spec: CommandSpec) -> GhCall:
    """A change to the local checkout, whose every option must be listed; `--` would pass options to git."""
    if any(word.value == "--" for word in words):
        raise UnclassifiableError("arguments after -- reach another program")
    if any(word.dynamic for word in words):
        raise UnclassifiableError("a local change takes a word known only at run time")
    _check_read_repositories(words)
    scan = gh_options.scan(words, OptionTable(spec.value_options, spec.flags))
    if spec.operation == "repo.clone":
        _check_repository_arguments(scan.positionals[:1])
    return GhCall((spec.operation,), spec.effect, reads_working_repository=True)


def _classify_write(words: tuple[Word, ...], spec: CommandSpec, single_call: bool) -> GhCall:
    flags = spec.flags | spec.irreversible_flags | spec.read_flags
    scan = gh_options.scan(words, OptionTable(spec.value_options | REPOSITORY_OPTIONS, flags))
    _check_write_words(scan)
    _check_sent_values(scan.values_of(spec.values | spec.texts) + scan.positionals, single_call)
    targets = scan.values_of(REPOSITORY_OPTIONS)
    # Only issue and pull request commands take a URL argument as their target; elsewhere it is a name.
    if spec.operation.startswith(("issue.", "pr.")):
        targets += tuple(word for word in scan.positionals if is_url(word.value))
    repositories = tuple(None if word.dynamic else repository(word.value) for word in targets)
    # Linked issues and --branch-repo name further repositories the write changes, never its own target.
    linked = scan.values_of(spec.repositories) + _reference_targets(scan.values_of(spec.references))
    related = tuple(None if word.dynamic else repository(word.value) for word in linked)
    data_options = spec.texts | spec.files
    for group in spec.required:
        # A body may be computed text or a run-time file the scan judges; any other required value must be literal.
        # A group names one flag by its aliases, and pflag keeps the last value given, so only that one counts.
        given = [(option, word) for option, word in scan.options if option in group][-1:]
        literal = any(
            word.value.strip("\"'") and (option in data_options or not word.dynamic) for option, word in given
        )
        if not literal and not scan.flags & group & (spec.flags | spec.irreversible_flags):
            raise UnclassifiableError(f"'{spec.operation}' needs one of {', '.join(sorted(group))}")
    if spec.required_any and not scan.flags & spec.required_any:
        raise UnclassifiableError(f"'{spec.operation}' needs at least one option saying what to change")
    if scan.flags & spec.read_flags:
        _check_read_repositories(words)
        return GhCall((spec.operation,), Effect.READ, reads_working_repository=True)
    effect = Effect.IRREVERSIBLE if scan.flags & spec.irreversible_flags else spec.effect
    files = scan.values_of(spec.files)
    paths = [sent_path(word.value) for word in files if not word.dynamic]
    return GhCall(
        (spec.operation,),
        effect,
        tuple(repository for repository in repositories if repository),
        None in repositories or None in related,
        files=tuple(path for path in paths if path != "-"),
        unscanned_files=tuple(word.source for word in files if word.dynamic),
        reads_stdin="-" in paths,
        related=tuple(repository for repository in related if repository),
    )


def _reference_targets(words: tuple[Word, ...]) -> tuple[Word, ...]:
    """The repositories related issues name: none for a bare number, any other form judged as a repository.

    A run-time reference stands for an unknown repository; OWNER/REPO#N and HOST/OWNER/REPO#N lose the number.
    """
    dynamic = tuple(word for word in words if word.dynamic)
    parts = (part.strip() for word in words if not word.dynamic for part in word.value.split(","))
    names = (part if is_url(part) else part.partition("#")[0] for part in parts if not ISSUE_NUMBER.fullmatch(part))
    return dynamic + tuple(Word(name, name) for name in names)


def _check_write_words(scan: OptionScan) -> None:
    """Refuse a write whose words could carry an option the guard does not see."""
    if any(word.may_be_option for word in scan.positionals):
        raise UnclassifiableError("an argument may become an option at run time")
    if any(_may_name_url(word) for word in scan.positionals):
        raise UnclassifiableError("an argument may become a URL at run time")
    if any(word.spreading for _, word in scan.options):
        raise UnclassifiableError("an option value may split into several words at run time")


def _check_sent_values(words: tuple[Word, ...], single_call: bool, *, fields: bool = False) -> None:
    """Refuse a value sent to GitHub that the guard cannot read before it leaves.

    A parameter may hold any secret of the environment. A command substitution is visible text only
    on a line whose other commands just print, such as a body through a quoted heredoc. For gh api
    `fields`, a literal key= prefix is not part of the value.
    """
    for word in words:
        if word.dynamic and has_parameter(word.source):
            raise UnclassifiableError("a value sent to GitHub holds a parameter expansion")
        if word.dynamic and not single_call:
            raise UnclassifiableError("a value sent to GitHub is built by a command that does more than print")
        key = FIELD_KEY.match(word.source) if fields else None
        value = word.source[key.end() :] if key else word.source
        if word.dynamic and not _is_one_substitution(value):
            raise UnclassifiableError("a value sent to GitHub joins a substitution's output to other text")


def _is_one_substitution(source: str) -> bool:
    """Whether a word is exactly one command substitution, so no output joins other text the scan saw apart."""
    tree = shell_syntax.syntax_tree(": " + source)
    arguments = tree.get("Stmts", [{}])[0].get("Cmd", {}).get("Args", [])
    parts = arguments[1].get("Parts", []) if len(arguments) == 2 else []
    if len(parts) == 1 and parts[0].get("Type") == "DblQuoted":
        parts = parts[0].get("Parts", [])
    if len(parts) != 1 or parts[0].get("Type") != "CmdSubst":
        return False
    # One plain call inside, so no second command, pipe, or list adds output after the first.
    statements = parts[0].get("Stmts", [])
    return len(statements) == 1 and (statements[0].get("Cmd") or {}).get("Type") == "CallExpr"


def _classify_api(words: tuple[Word, ...], catalog: Catalog, single_call: bool) -> GhCall:
    request = _api_request(words)
    texts = tuple(
        word for option, word in request.fields if option not in TYPED_FIELD_OPTIONS or not _names_file(word)
    )
    _check_sent_values(texts, single_call, fields=True)
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
    repositories = (Repository(match["owner"], match["name"]),) if match else ()
    unknown = not repositories
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
    if endpoint.dynamic and not _plain_parameters(endpoint):
        raise UnclassifiableError("a gh api endpoint holds a substitution or parameter operator")
    if endpoint.dynamic and re.search(r"\$[A-Za-z_{(]|`", endpoint.source.partition("?")[2]):
        raise UnclassifiableError("a gh api query string holds a parameter expansion")
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


def _names_foreign_host_once_expanded(word: Word) -> bool:
    """Whether a plain-parameter word, expanded from the hook environment, names a host other than github.com."""
    expand = lambda part: PLAIN_PARAMETER.sub(lambda m: os.environ.get(m[1] or m[2], ""), part.strip('"'))  # noqa: E731
    parts = re.findall(r"""'[^']*'|"[^"]*"|[^'"]+""", word.source)
    value = "".join(part[1:-1] if part.startswith("'") else expand(part) for part in parts)
    return (is_url(value) or value.count("/") >= 2) and repository(value) is None


def _plain_parameters(word: Word) -> bool:
    """Whether a run-time word expands only plain named parameters, with no substitution or parameter operator."""
    return bool(gh_options.PLAIN_PARAMETER_WORD.fullmatch(word.source))


def _may_name_url(word: Word) -> bool:
    """Whether a run-time word could become a URL: it holds a colon, or its literal start begins a scheme.

    A word that starts with an expansion is judged elsewhere: a write asks for it as a possible option,
    and a read asks when it holds command output; a plain parameter holds the harness environment.
    """
    if not word.dynamic:
        return False
    lead = re.sub(r"[\"'\\]", "", re.split(r"[$`]", word.source, maxsplit=1)[0]).lower()
    return ":" in word.source or (bool(lead) and any(scheme.startswith(lead) for scheme in ("https://", "http://")))


def sent_path(path: str) -> str:
    """`-` for a path that is standard input; refuse any other device, process, or non-regular file.

    The path is the argument gh receives, a tilde the shell expanded included; it is resolved the way
    gh's open would, through `..` and symlinks.
    """
    resolved = Path(os.path.realpath(path))
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
    return sent_path(word.value.partition("=")[2][1:] if _names_file(word) else word.value)


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
