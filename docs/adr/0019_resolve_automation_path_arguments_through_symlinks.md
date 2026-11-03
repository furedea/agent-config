# ADR-0019: Resolve automation path arguments through symlinks

- Status: Accepted
- Date: 2026-11-03
- Refines: ADR-0018

In the context of `agent-browser` and `agent-desktop` running outside the sandbox, where an argument
such as an output path could reach a file outside the sandbox through a symlink the session made in
its worktree, where `agent-browser` hands output paths to a long-lived daemon that opens a relative
path from the directory it started in, where it loads `agent-browser.json` from its working
directory, and where both CLIs gain options with every update, facing a hole ADR-0018 accepted, we
decided for letting each allowed subcommand use only options listed for it from the upstream sources,
keeping only those that neither read nor write a path nor reach another process or session, so that
an unlisted option, `--name=value` included, asks; for resolving every argument of an allowed call,
and every option value after `=`, with symlinks followed in each existing component, and for running
the call unprompted only when each resolves inside the command's Git worktree or the session's
temporary directories, the roots the verification hook already treats as the session's own; for
asking for every form whose file the browser daemon writes (`screenshot`, `pdf`, `trace stop`,
`profiler stop`, `network har stop`) except the exact argument lists `agent-browser screenshot` and
`agent-browser screenshot --full`, whose file the daemon names under its own directory; for asking
for any `agent-browser` call beside an `agent-browser.json`; and for asking when a symlink dangles or
loops, a component cannot be read, or the working directory is unknown; and against a denylist of
risky options, which missed `--action-policy`, `--ca-cert`, and agent-desktop's `--trace` and
`clipboard-get --out` and would let each new option through silently, against reproducing how the
browser CLI parses its arguments to find the daemon's path, which three reviews in a row bypassed with
options, interleaved flags, and file names starting with `-`, and against asking for every call that
names a file, which would prompt for ordinary desktop outputs, accepting that a browser output needs
approval, that a bare screenshot lands in `~/.agent-browser/tmp/screenshots` outside the worktree,
that a text value starting with `-` asks, that a useful option a CLI update adds asks until listed,
that a session can still swap a link between the hook's check and the program opening the path, that
writes inside the worktree may reach paths the sandbox protects there, such as
`.claude/settings.json`, and that an argument coinciding with the name of a symlink pointing
elsewhere asks even when it is not a path.
