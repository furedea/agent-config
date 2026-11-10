# ADR-0022: Judge unquoted variables as the executing shell runs them

- Status: Accepted
- Date: 2026-11-11
- Related: [ADR-0009](0009_review_only_commands_that_reach_past_the_sandbox.md) (the run-time word and its word-splitting premise),
    [ADR-0015](0015_judge_only_statically_determinable_shell_text_in_the_guards.md) (rule 1: judge as the shell would run it)

In the context of the precise `gh` rules of ADR-0009, which asked about every unquoted variable in a command that
reaches past the sandbox (`gh run view 1 --job $J --log`, `gh pr edit 438 --body-file $TMPDIR/body.md`) because a
shell may split its value into extra arguments, facing the fact that Claude Code runs Bash-tool commands in the
user's login shell, zsh, which by default neither splits an unquoted value nor globs its result, so the prompt guarded
against an expansion the shell never performs and stopped three lanes in a row, we decided for making the premise
"an unquoted expansion may become several words" depend on the executing shell, reading an unquoted simple variable
as the single word zsh runs, with the one extra rule that a word made only of such variables vanishes when they are
all empty, and for keeping the shell-independent reading wherever zsh is not certain, and against adding a quoting
rule to the skills and against widening the `gh` allowlist form by form, to stop prompting for an expansion that is
safe where the shell is known while keeping ADR-0015's rule 1 true to what actually runs, accepting that an option
the user's zsh startup files change after the hook's reading (`setopt sh_word_split`, `setopt glob_subst`) is not
visible to the guard.

## Decisions

- **When the shell is known.** The reading applies only when the payload comes from Claude Code (no `provider`, or
    `claude`) and the hook's environment names zsh: `CLAUDE_CODE_SHELL` if set, otherwise `SHELL`. The hook inherits
    both from Claude Code, whose Bash tool runs in that shell. The renderer of this repository's `hooks.json` has no
    per-user value to bake in, so the hook reads its own environment instead of a rendered argument.
- **Other providers keep the old reading.** Codex, Devin, Hermes, Pi and dsh choose their own shell, and neither the
    payload nor the hook's environment says which, and Codex applies its own `shell_environment_policy` to the commands
    it runs. Unconfirmed, they ask as before until a provider-specific source is found.
- **One word, or none.** An unquoted `$name` or `${name}` of a scalar variable, alone or inside a word beside literal
    text (`$TMPDIR/body.md`), is judged as `"$name"` is: a plain placeholder that passes only where any value would.
    A word made only of such variables disappears when they are empty, so the command is also judged with each
    combination of those words removed (at most four such words); every remaining call must be allowed.
- **What still asks.** `${=name}`, `${~name}`, `$=name`, `$~name`, flags such as `${(s: :)name}`, subscripts
    (`$name[1]`, `${name[@]}`), modifiers (`${name:-x}`, `${#name}`, `${!name}`), positional parameters and `$@` `$*`,
    zsh's array and association parameters (`$path`, `$argv`, `$pipestatus`, `$commands`, ...), a word with a glob,
    brace, or leading tilde beside a variable, command substitution (ADR-0015's rule 2), a variable as the program, and
    a script another shell runs (`bash -c`, `sh -c`), which is still read as bash.
- **A command that may change the expansion asks.** `setopt`, `unsetopt`, `emulate`, `set`, `typeset`/`declare`/
    `local`, `read`, `eval`, `source`, `alias`, an array assignment (`a=(...)`, `a[2]=...`), and the other programs
    listed in `executing_shell.py` return the whole command to the shell-independent reading, because they can make
    `$name` an array or turn word splitting on.
- **Unchanged.** Pipes, redirects, `;`, `&&`, and `export X=$Y; gh ...` were never the cause: they already pass.

## Alternatives not taken

- **A quoting rule in the skills** ("always write `"$J"`"): the user rejected prose rules for what a guard can judge,
    and an agent forgets them.
- **Allowing `gh` forms with `$name` one by one:** it widens the allowlist by spelling, the pattern ADR-0009 and
    ADR-0015 rejected, and leaves the premise wrong.
- **Treating every shell as zsh:** a bash user (or a Codex session) would get an unprompted word split.

The known gap in ADR-0015 (`sha=<hex>; gh run list --commit $sha`) now passes where the shell is known to be zsh, as
the assignment is a plain scalar and `$sha` is a simple variable; elsewhere it still asks.
