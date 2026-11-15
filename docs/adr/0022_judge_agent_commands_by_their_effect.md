# ADR-0022: Judge agent commands by their effect

- Status: Accepted
- Date: 2026-11-14
- Refines: ADR-0009, ADR-0006, ADR-0015
- Amended with: ADR-0021 (static ast-grep rules block; amendment in a separate change)

In the context of the command guards that decide allow, ask, or deny for agent shell commands,
facing a day (2026-11-14) with 101 prompts, most of them for effects that stay inside the
sandbox or act reversibly on the agent's own repositories, and caused by how a command was written
(an unlisted `gh` form, a shell function, a loop, an unparsed construct) rather than by what it
does, while [#181](https://github.com/furedea/agent-config/issues/181) moves external operations
to a Capability / Effect Gateway with grants, we decided for judging each command by its effect
and asking only when the effect widens the agent's authority or cannot be undone, and against
widening the allowlist form by form (ADR-0009 already rejected this) and against asking whenever
the text is not fully parsed, to make a prompt mean "this changes what the agent may do or cannot
be taken back", accepting that the guard is a review layer, not a boundary, that the
classification of external programs must stay precise, and that a class B dependency add
only defers the code: the added package runs later under a class A command (`cargo test`,
`pytest`, `go test`) inside the sandbox, where the sandbox, not the prompt, is the protection.

## Protection order

Each layer is trusted over the ones after it, and a later layer never compensates for a missing
earlier one by prompting more:

1. Sink enforcement (the service refuses the operation).
2. OS isolation (the sandbox from ADR-0011).
3. Typed classification (a program's arguments parsed into target, operation, and reversibility).
4. Command-string review (the static inspection of ADR-0015).
5. Human prompt.

## Classes

| Class | Effect                                 | Examples                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Decision |
| ----- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| A     | Stays inside the environment           | edit, build, test, `rm` of a generated, ignored, or clean tracked file inside writable roots, shell functions, loops                                                                                                                                                                                                                                                                                                                                                                            | allow    |
| B     | External, inside the grant, reversible | PR / issue create, edit, comment, review reply, `resolveReviewThread` on a trusted owner's repository; read-only `gh`; `git fetch` and a push of the agent's own topic branch to a trusted owner's remote (the forms the current policy allows); Herdr panes the agent created; dependency adds that run no package code at add time (`cargo add`, `GOTOOLCHAIN=local go get`, `uv add --no-build`, `npm install --ignore-scripts`)                                                             | allow    |
| C     | Widens authority                       | writes to repositories of owners not in `trusted_owners.json`; non-allowlisted hosts; secrets not already denied (every `gh auth` form stays a hard denial); sandbox escape; fetched-package execution (`npx`, `uvx`, `bunx`, `pnpm dlx`, `nix run`, `nix shell`, `uv run --with`, `npm install` without `--ignore-scripts`, `go get` that may switch toolchains, and any `uv add` without `--no-build`, because resolving or syncing can run an sdist build backend)                           | ask      |
| D     | Promotes or cannot be undone           | `gh pr merge`, `gh release create` / `edit` / `upload` / `delete` / `delete-asset`, `gh api` with a write method other than a listed class B call (including `-X DELETE`, which asks today even for a repository), `rm` of an untracked file or a file with uncommitted edits, `git stash drop` / `clear`, `git remote add` / `set-url`, `kill` / `pkill` that send a signal (not `kill -l` / `-L`), `herdr server` forms that start, stop, reload, or update (not read-only `agent-manifests`) | ask      |

The deny list in `agents/command_permissions.json` is unchanged and is not restated here. What
it denies today stays a hard denial and is never moved to class D: for example `gh repo
delete` / `archive` / `rename` / `transfer` / `edit` / `create`, all of `gh secret`, recursive
`rm`, and `git push --force` without lease. `gh api -X DELETE repos/{owner}/{repo}` is not denied
today and asks as class D; making it a deny is a separate change. A known program in a form the table does not list is not
class B: an external operation outside B asks as C or D, so `gh api -X PATCH`, `-X PUT`, and
`-X POST` on settings, protection, or collaborators ask. Separately, the user decided that
static ast-grep rules, which check edited source files and not shell commands, block rather than
advise. This is a decision not yet implemented: it reverses the advice-only reading in ADR-0021,
which is being amended in a separate change so that both ADRs agree. Class D is the ask tier for operations that are not denied. The classes
follow one rule: A loses nothing the sandbox does not hold (a generated, ignored, or clean
tracked file is recoverable by rebuild or checkout); an `rm` that destroys the only copy asks;
D loses state outside the working tree (stashes,
processes, release assets) or promotes work to a shared target. Function and loop bodies are judged by the commands inside them, so a
class D operation hidden in `f() { gh pr merge 1; }; f` still asks. A construct the guard cannot
read, or a program it cannot determine (`eval`, `$cmd ...`, a shell fed unreadable input), asks
unless every program it could involve is known to be class A. A run-time argument of a known
program passes where every possible value keeps the classified target and operation (ADR-0009;
`gh pr view "$NUMBER" --json state`), which narrows the uniform ask of ADR-0015 rule 2 (rule 1
stands).

## Mapping to #181

Class B is the standing grant of the future Gateway: the trusted owners, the Herdr panes created
by the session, and the dependency adds. Policy data takes the shape target x operation x decision,
so a Gateway grant (action, resource, constraints) can later replace the table without changing
the classes. Class C is a grant widening and class D is a promotion; both need an
agent-independent path in #181 and stay a human decision here.

## Moved to sink enforcement (recommended, not changed here)

Settings changes are the owner's decision, so this ADR only recommends them:

- Scope the GitHub App permissions to what class B needs, with no `Administration` or `Contents`
    write beyond it. GitHub has no separate merge permission: the merge endpoint needs the same
    `Pull requests: write` as class B, so the permission cannot stop a merge.
- Add a ruleset that requires the owner's approval on every branch a PR may merge into (`main`
    and any `develop` or `release/*` branch), not on `main` alone. This, or the future Gateway, is
    the enforcement point that stops `gh pr merge` without the owner even if a prompt is bypassed.

The ruleset stops the agent's merge only when all three conditions hold, each a setting the owner decides:

- A required approval is not an owner approval by itself, because any writer can approve unless
    the rule restricts who counts. The ruleset must require code-owner review with a `CODEOWNERS`
    entry for the owner (this repository has none yet), or otherwise restrict approvals to the
    owner.
- The ruleset must dismiss stale approvals when new commits are pushed, because the agent can
    push after the owner approves; otherwise an approval of an earlier revision lets the app
    merge code the owner never reviewed (or the Gateway enforces owner review of the latest
    revision).
- The agent's GitHub App must not be a bypass actor of the ruleset, since a bypass actor merges
    without the rules applying.

Merges into a branch the ruleset does not cover, or while any condition fails, stay guarded
only by the class D prompt.

## Measurement target

Twenty-four hours after deploy, count prompts: at most 10 a day, and every one class C or D. A
prompt outside C and D is a misclassification and is fixed by the classification, not by
widening a prefix.
