# ADR-0022: Judge unquoted variables as the executing shell runs them

- Status: Accepted
- Date: 2026-11-11
- Related: [ADR-0009](0009_review_only_commands_that_reach_past_the_sandbox.md) (the run-time word and its word-splitting premise),
    [ADR-0015](0015_judge_only_statically_determinable_shell_text_in_the_guards.md) (rule 1: judge what the text proves)

In the context of the precise `gh` rules of ADR-0009, which asked about every unquoted variable in a command that
reaches past the sandbox (`gh run view 1 --job $J --log`, `gh pr edit 438 --body-file $TMPDIR/body.md`) because a
shell may split its value into extra arguments, facing the fact that Claude Code runs Bash-tool commands in the
user's login shell, zsh, which by default neither splits an unquoted scalar nor globs its result, so the prompt
guarded against an expansion the shell never performs and stopped three lanes in a row, we decided for making the
premise "an unquoted expansion may become several words" depend on the executing shell, and for treating an
unquoted `$name` as the single word zsh runs only where the command's own text proves the variable is a scalar, and
against excluding the forms that are not one word, to stop prompting for an expansion that is safe where the text
shows it while keeping ADR-0015's rule 1 true to what actually runs, accepting that a variable set outside the
command (`$J` with no assignment before it) still asks, and that an option the user's zsh startup files change
(`setopt sh_word_split`, `glob_subst`, `ksh_arrays`) is not visible to the guard.

## Decisions

- **When the shell is known.** The reading applies only when the payload comes from Claude Code (no `provider`, or
    `claude`) and the hook's environment names zsh: `CLAUDE_CODE_SHELL` if set, otherwise `SHELL`. The hook inherits
    both from Claude Code, whose Bash tool runs in that shell. The renderer of this repository's `hooks.json` has no
    per-user value to bake in, so the hook reads its own environment instead of a rendered argument.
- **Other providers keep the old reading.** Codex, Devin, Hermes, Pi and dsh choose their own shell, and neither the
    payload nor the hook's environment says which, and Codex applies its own `shell_environment_policy` to the commands
    it runs. Unconfirmed, they ask as before until a provider-specific source is found.
- **Which names count as one word.** A plain unquoted `$name` or `${name}` is judged as `"$name"` is (a placeholder
    that passes only where any value would) when either holds:
    1. The name was assigned before the call, in the same command, by a plain `name=value` (also `name+=value` and
        `export name=value`), the value being any word, a quoted expansion, or `$(...)`, and no statement between an
        assignment and the call is anything but such an assignment.
    2. The name is `HOME`, `PWD`, `TMPDIR` or `USER`, which zsh never makes an array. This too needs the call to
        follow nothing but plain assignments, since an earlier `setopt` would change it.
- **Where the call may stand.** Only a call that is the statement's first command or a member of its pipeline counts,
    so `J=1; gh ... $J | head`, `J=1; gh ... $J && echo done`, and `J=1; echo x | gh ... $J` pass; a call on the right of
    `&&` or `||`, in the background, or inside a function, block, subshell, loop, branch, or `bash -c` does not. A
    statement that is not a plain assignment ends the run of statements the call may follow, so `cd`, `setopt`, `trap`,
    `typeset`, `read`, `unset`, `eval`, a definition, and any construct that may skip or retarget an assignment (`||`, `&`,
    a subshell) make every later call ask without being listed anywhere.
- **One word, or none.** A word made only of such variables disappears when they are empty, so the command is also
    judged with each combination of those words removed (at most four such words); every remaining call must be allowed.
- **What still asks.** Any other name (a variable set outside the command, `$path`, `$argv`, `$commands`, positional
    parameters, `$@`), `${=name}`, `${~name}`, `$=name`, `$~name`, flags, subscripts, modifiers, a word with a glob, brace,
    or leading tilde beside the variable, and command substitution in a call's own words (ADR-0015's rule 2).
- **Independent fix.** `$=name` and `$~name` are read by shfmt as a `$` followed by literal text, so they used to pass as
    a static word; they now ask in every shell.
- **Known gap.** Assigning a zsh special parameter that is an association (`commands=x`, `aliases=x`) fails in zsh and
    leaves its many-valued content, which the text cannot show; such a name is unlikely in a command and is left to the
    sandbox and the provider's own prompt.

## Alternatives not taken

- **Treat every unquoted `$name` as one word under zsh, and list the exceptions.** The first implementation did this:
    it listed zsh's array and association parameters, the builtins that create arrays (`typeset`, `read -A`,
    `export -T`, `zstyle -a`, `zparseopts -a`), and the commands that change options (`setopt`, `emulate`, `trap`, a `-`
    or `command` prefix). Each round of review found another form the list lacked, because zsh has no closed set of
    ways to make a variable an array or turn on word splitting. ADR-0015 says to judge what the text proves and to
    record the rest as a gap; an exception list inverts that, so it is replaced by naming the cases that are proven.
- **A quoting rule in the skills** ("always write `"$J"`"): the user rejected prose rules for what a guard can judge.
- **Allowing `gh` forms with `$name` one by one:** it widens the allowlist by spelling, the pattern ADR-0009 and
    ADR-0015 rejected, and leaves the premise wrong.
- **Treating every shell as zsh:** a bash user (or a Codex session) would get an unprompted word split.

The known gap in ADR-0015 (`sha=<hex>; gh run list --commit $sha`) now passes where the shell is known to be zsh,
because the assignment is plain and directly precedes the call; elsewhere it still asks.
