"""Evaluate explicit Git operations without relying on whitespace-based argument parsing."""

from pathlib import Path
import re
import subprocess


PROTECTED_BRANCHES = {"main", "master"}
DESTRUCTIVE_VERBS = {"clean", "filter-branch", "filter-repo", "replace"}
FORCE_FLAGS = {"-f", "--force"}
DANGEROUS_OPTIONS = {
    "branch": {"-D"},
    "rm": FORCE_FLAGS,
    "mv": FORCE_FLAGS,
    "symbolic-ref": {"-d", "--delete"},
    "update-ref": {"-d", "--delete"},
    "gc": {"--prune"},
    "reset": {"--hard", "--keep", "--merge"},
    "switch": {"-f", "--force", "-C", "--force-create", "--discard-changes"},
    "checkout": {"-f", "--force", "-B", "--", "."},
}
OPTION_VERBS = frozenset({*DANGEROUS_OPTIONS, "push", "restore"})
"""Verbs whose verdict depends on their arguments, so a run-time argument can hide a destructive form."""
SUBCOMMAND_VERBS = {"worktree": {"remove"}, "reflog": set()}
"""Verbs judged by a subcommand, mapped to the subcommands whose verdict also depends on their arguments."""
LONG_OPTIONS = {
    verb: frozenset(names.split())
    for verb, names in {
        "reset": "--auto-advance --hard --intent-to-add --inter-hunk-context --keep --merge --mixed --no-refresh "
        "--patch --pathspec-file-nul --pathspec-from-file --quiet --recurse-submodules --refresh --soft --unified",
        "push": "--all --atomic --branches --delete --dry-run --exec --follow-tags --force --force-if-includes "
        "--force-with-lease --ipv4 --ipv6 --mirror --no-verify --porcelain --progress --prune --push-option --quiet "
        "--receive-pack --recurse-submodules --repo --set-upstream --signed --tags --thin --verbose --verify",
        "checkout": "--auto-advance --conflict --detach --force --guess --ignore-other-worktrees "
        "--ignore-skip-worktree-bits --inter-hunk-context --merge --orphan --ours --overlay --overwrite-ignore "
        "--patch --pathspec-file-nul --pathspec-from-file --progress --quiet --recurse-submodules --theirs --track "
        "--unified",
        "switch": "--conflict --create --detach --discard-changes --force --force-create --guess "
        "--ignore-other-worktrees --merge --orphan --overwrite-ignore --progress --quiet --recurse-submodules --track",
        "restore": "--conflict --ignore-skip-worktree-bits --ignore-unmerged --inter-hunk-context --merge --ours "
        "--overlay --patch --pathspec-file-nul --pathspec-from-file --progress --quiet --recurse-submodules --source "
        "--staged --theirs --unified --worktree --no-staged --no-worktree",
        "rm": "--cached --dry-run --force --ignore-unmatch --pathspec-file-nul --pathspec-from-file --quiet --sparse",
        "mv": "--dry-run --force --sparse --verbose",
        "gc": "--aggressive --auto --cruft --detach --expire-to --force --keep-largest-pack --max-cruft-size --prune "
        "--quiet",
        "symbolic-ref": "--delete --no-recurse --quiet --recurse --short",
        "update-ref": "--batch-updates --create-reflog --deref --no-deref --stdin",
        "branch": "--abbrev --all --color --column --contains --copy --create-reflog --delete --edit-description "
        "--force --format --ignore-case --list --merged --move --no-contains --no-merged --omit-empty --points-at "
        "--quiet --recurse-submodules --remotes --set-upstream-to --show-current --sort --track --unset-upstream "
        "--verbose",
        "worktree": "--force",
        "commit": "--ahead-behind --all --allow-empty --allow-empty-message --amend --author --branch --cleanup --date "
        "--dry-run --edit --file --fixup --gpg-sign --include --inter-hunk-context --interactive --long --message "
        "--no-post-rewrite --no-verify --null --only --patch --pathspec-file-nul --pathspec-from-file --porcelain "
        "--post-rewrite --quiet --reedit-message --reset-author --reuse-message --short --signoff --squash --status "
        "--template --trailer --unified --untracked-files --verbose --verify",
        "tag": "--annotate --cleanup --color --column --contains --create-reflog --delete --edit --file --force "
        "--format --ignore-case --list --local-user --merged --message --no-column --no-contains --no-merged "
        "--omit-empty --points-at --sign --sort --trailer --verify",
    }.items()
}
"""The long options of each judged verb, as `git <verb> -h` lists them, so an abbreviation reads as git reads it."""


def branch(arguments: tuple[str, ...] = ()) -> str:
    """Read the current branch, retaining any supported global Git path options."""
    try:
        return subprocess.check_output(
            ["git", *arguments, "branch", "--show-current"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("cannot determine the implicit Git push target") from error


def git_arguments(arguments: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate supported global Git options from the subcommand."""
    index = 1
    while index < len(arguments) and arguments[index].startswith("-"):
        option = arguments[index]
        if option in {"-C", "-c", "--git-dir", "--work-tree"}:
            index += 2
        elif option.startswith(("--git-dir=", "--work-tree=", "--config-env=")) or option in {
            "--no-pager",
            "--paginate",
            "--no-optional-locks",
        }:
            index += 1
        else:
            raise ValueError(f"unsupported global Git option requires review: {option}")
    return arguments[1:index], arguments[index:]


def push_reason(arguments: tuple[str, ...], globals_: tuple[str, ...]) -> str:
    """Reject unleased force pushes and protected destinations, including implicit destinations."""
    flags = {argument.split("=", 1)[0] for argument in arguments}
    if flags & FORCE_FLAGS:
        return "force-push flag detected"
    if "--force-with-lease" in flags and "--force-if-includes" not in flags:
        return "force-with-lease without --force-if-includes detected"
    refspecs = push_refspecs(arguments)
    if not refspecs:
        destination = branch(globals_)
        return f"push target is '{destination}'" if destination in PROTECTED_BRANCHES else ""
    for refspec in refspecs:
        if refspec.startswith("+"):
            return "'+refspec' force push detected"
        destination = refspec.rsplit(":", 1)[-1]
        if destination == "HEAD":
            destination = branch(globals_)
        destination = destination.removeprefix("refs/heads/")
        if destination in PROTECTED_BRANCHES:
            return f"push target is '{destination}'"
    return ""


def push_refspecs(arguments: tuple[str, ...]) -> list[str]:
    """Return the refspecs after the remote, skipping options and their values."""
    positional: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            positional.extend(arguments[index + 1 :])
            break
        if argument in {"--repo", "--receive-pack", "--exec"}:
            index += 2
            continue
        if not argument.startswith("-"):
            positional.append(argument)
        index += 1
    return positional[1:]


def pushes_current_branch(arguments: tuple[str, ...]) -> bool:
    """Whether the push destination is read from the repository rather than named in the command."""
    refspecs = push_refspecs(arguments)
    return not refspecs or any(refspec.rsplit(":", 1)[-1] == "HEAD" for refspec in refspecs)


def reason(arguments: tuple[str, ...]) -> str:
    """Return the independently forbidden operation, or no supplementary objection."""
    if not arguments:
        return ""
    executable = Path(arguments[0]).name
    if executable == "gh" and arguments[1:3] == ("pr", "merge") and "--admin" in arguments[3:]:
        return "gh pr merge --admin bypasses branch protection"
    return git_reason(arguments) if executable == "git" else ""


def git_reason(arguments: tuple[str, ...]) -> str:
    globals_, command = git_arguments(arguments)
    if not command:
        return ""
    verb, *rest = command
    remaining = spelled_out(verb, tuple(rest))
    if sandboxed := sandbox_form_reason(verb, remaining):
        return sandboxed
    options = {argument.split("=", 1)[0] for argument in remaining}
    if verb == "push":
        return push_reason(remaining, globals_)
    destructive = verb in DESTRUCTIVE_VERBS
    destructive |= verb == "worktree" and bool(remaining) and remaining[0] in {"move", "repair"}
    destructive |= verb == "worktree" and remaining[:1] == ("remove",) and bool(options & FORCE_FLAGS)
    destructive |= verb == "reflog" and bool(remaining) and remaining[0] in {"delete", "expire"}
    destructive |= bool(options & DANGEROUS_OPTIONS.get(verb, set()))
    destructive |= verb == "branch" and forces_deletion(remaining)
    if verb == "restore":
        destructive = restores_worktree(remaining)
    return f"destructive git operation: {verb}" if destructive else ""


def forces_deletion(arguments: tuple[str, ...]) -> bool:
    """Whether a branch command deletes with force, spelled -D, -df, or --delete with --force in any form."""
    flags = set(option_flags(arguments))
    return "-D" in flags or bool(flags & {"-d", "--delete"} and flags & FORCE_FLAGS)


def restores_worktree(arguments: tuple[str, ...]) -> bool:
    """Whether git restore writes the working tree, as the last of each -S and -W toggle decides.

    Without either, restore writes the working tree; any --source also counts, as before.
    """
    staged, worktree = False, None
    for flag in option_flags(arguments):
        if flag in {"--source", "-s"}:
            return True
        if flag in {"--staged", "-S", "--no-staged"}:
            staged = flag != "--no-staged"
        elif flag in {"--worktree", "-W", "--no-worktree"}:
            worktree = flag != "--no-worktree"
    return not staged if worktree is None else worktree


def option_flags(arguments: tuple[str, ...]) -> list[str]:
    """The options before `--` in order, a long one without its value and a short cluster split into flags."""
    end = arguments.index("--") if "--" in arguments else len(arguments)
    flags: list[str] = []
    for argument in arguments[:end]:
        if argument.startswith("--"):
            flags.append(argument.split("=", 1)[0])
        elif re.fullmatch(r"-[A-Za-z]+", argument):
            flags += [f"-{flag}" for flag in argument[1:]]
    return flags


def spelled_out(verb: str, arguments: tuple[str, ...]) -> tuple[str, ...]:
    """Read each option before `--` under its full name; git accepts a unique abbreviation and rejects others."""
    end = arguments.index("--") if "--" in arguments else len(arguments)
    names = LONG_OPTIONS.get(verb, frozenset())
    return tuple(full_option(argument, names) for argument in arguments[:end]) + arguments[end:]


def full_option(argument: str, names: frozenset[str]) -> str:
    key, separator, value = argument.partition("=")
    if not key.startswith("--") or key in names:
        return argument
    matches = [name for name in names if name.startswith(key)]
    return matches[0] + separator + value if len(matches) == 1 else argument


def sandbox_form_reason(verb: str, arguments: tuple[str, ...]) -> str:
    """Name the agent form of a Git command whose usual form fails inside the sandbox."""
    signing = {"commit": ("-S", "--gpg-sign"), "tag": ("-s", "--sign", "-u", "--local-user")}
    if any(argument.split("=", 1)[0] in signing.get(verb, ()) for argument in arguments):
        return (
            "agent commits and tags are unsigned; drop the signing option, "
            "since the sandbox cannot reach the SSH agent that signs"
        )
    if verb == "push" and {"-u", "--set-upstream"} & set(arguments):
        return (
            "the sandbox cannot write .git/config; push with `git push origin <branch>` "
            "and open the pull request with `gh pr create --head <branch>`"
        )
    return ""
