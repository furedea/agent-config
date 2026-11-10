# Git Delivery

For implementation tasks:

1. Inspect branch and dirty state.
2. Select the checkout and branch using [Branches and worktrees](branches.md).
3. Follow `tsdd` for development and verification, including path selection and assessing whether refactoring is warranted.
4. Complete the requested change and [Local Verification Before Delivery](#local-verification-before-delivery), fixing problems caused by the change. Report unrelated failures or unavailable verification without claiming success.
5. If delivery is authorized under [Operating Rules](../SKILL.md#operating-rules), commit by intent and perform the requested publication steps:
    - `git fetch origin`
    - optionally `git rebase origin/<base>` before the first push when the feature branch should be refreshed onto the latest base
    - `git push origin <branch>`
    - `gh pr create --base <base> --head <branch> --title "<title>" --body "$(cat <<'EOF' … EOF)"`, with a [pull request body](#pull-request-body) written inline
6. Stop before merge; merging is a human decision unless the user explicitly asks for it. When the user asks, `gh pr merge` prompts for approval, and that prompt is the authorization step.

For explicit PR requests:

1. If the user asked for a stacked or red-green pull request, follow [Stacked pull requests](stacked_prs.md) instead of steps 2 and 3.
2. Confirm the target base branch if it is not obvious from the repo default.
3. Follow [Local Verification Before Delivery](#local-verification-before-delivery), then push the feature branch with `git push origin <branch>`.
4. Create a normal PR with `gh pr create --base <base> --head <branch> --title "<title>"` and a
   [pull request body](#pull-request-body) passed inline through a quoted heredoc:

    ```bash
    gh pr create --base main --head <branch> --title "<title>" --body "$(cat <<'EOF'
    <body>
    EOF
    )"
    ```

    Do not write the body to a file; `--body-file -` reading the same heredoc is also fine. The
    quoted `'EOF'` keeps backticks and `$` literal, so code spans in the body are never run.

Do not pass `-u` or `--set-upstream` to `git push`: setting the upstream writes `.git/config`,
which the sandbox protects, so the push succeeds but the command exits with an error. Name the
branch explicitly in later pushes and in `gh pr create --head`.

For rebase and force-push:

- `git rebase origin/<base>` refreshes a PR branch before its first push. Non-interactive rebases onto other refs, including `--onto`, are allowed when the task needs them; reflog can undo them.
- `git rebase --continue` and `git rebase --abort` complete or recover a rebase.
- Interactive rebase is outside the default workflow.
- After rebasing a branch this task already pushed, publish it with `git push --force-with-lease --force-if-includes origin <branch>`. The lease refuses to overwrite commits that were pushed elsewhere, and `--force-if-includes` refuses when a background fetch hid them. Never use bare `--force`, `+refspec` pushes, or any force push to the default branch. If the lease is rejected, stop and ask the user.

## Pull Request Body

Write the title in English as a Conventional Commits subject stating the primary intent, and the
body in the [Issue, Plan, and PR Format](../../issue-workflow/SKILL.md#issue-plan-and-pr-format).
Do not use `-f`/`--fill`; commit messages do not carry this content. The body must include:

- A summary of what actually changed.
- `Closes #N` only when the PR fully resolves the Issue; otherwise `Refs #N`.
- A link to the plan comment, when one exists.
- Verification evidence: what ran and its result, or what could not run.
- Material departures from the plan, or none.

Squash merges take the PR title as the commit subject and the PR body as its body
(`squash_merge_commit_message: PR_BODY` in `github/repo_settings.json`), so the Japanese body
becomes the default branch commit body.

For what the PR body owns relative to the Issue and plan, follow
[Information Placement](../../source-of-truth/SKILL.md#information-placement).

## Wait for CI

After every push, wait for the PR's checks before handling review findings or reporting.

1. Run `gh pr checks <n> --watch --fail-fast` in the background and wait for its completion
   notification; do not poll. Right after a push only some checks may be registered while the main
   workflow run is still queued, so an early successful exit is not completion. The wait is complete
   only when the repository's required aggregate check (`all-green` where it exists) appears in
   `gh pr checks <n>` and is no longer pending; elsewhere, when the required checks are present and
   finished. If `--watch` returns earlier, start it again, or follow the queued or in-progress run
   with `gh run watch <run-id>`.
2. On failure, identify the failing check with `gh pr checks <n>` and read its log with
   `gh run view <run-id> --log-failed`.
3. Classify the cause:
    - Review check (`claude-review`, `codex-review`) that failed because it raised findings: handle
      it under [Review on GitHub](#review-on-github), not here. `--fail-fast` exits at the first
      failure, so first run `gh pr checks <n> --watch` (without it) until the remaining checks finish.
    - `all-green`: an aggregate of the other checks; classify its failure by the underlying checks.
    - Code-caused (test, lint, format, type check, Nix build or check): fix it, run the same check
      locally, push, and return to step 1.
    - External (AI review usage limit, GitHub or runner outage, network): do not change the work.
      If a retry can help, run `gh run rerun <run-id> --failed` once and return to step 1; if the
      check fails again or a retry cannot help, stop and report the check name and reason.
    - Undetermined: do not guess a fix; stop and report the check name and reason.
4. Stop and report when the same check still fails after three fix attempts.

A lane ends such a report with `LANE-BLOCKED: <reason>`; other sessions report to the user.

## Review on GitHub

In a repository that has them, as furedea/agent-config does, every PR is reviewed on GitHub by
`claude-review` and `codex-review`, both part of `all-green`; do not run a local code review there.
Elsewhere, wait for that repository's required checks and follow its own review process. The
mechanism is in the
[reusable-workflows README](https://github.com/furedea/reusable-workflows#readme).

1. After pushing, [wait for CI](#wait-for-ci) until every check has finished; failures that are review findings are
   handled by the following steps.
2. Read the findings: Claude's inline comments and summary comment, and Codex's inline comments and
   Codex Review Summary (`codex-review-state`), with
   `gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate` (the path comes right after
   `gh api`, or the command asks for confirmation) and `gh pr view <n> --comments`.
3. Fix every finding of any severity, then push; the push re-runs both reviews. Do not defer a
   finding to the user.
4. Do not change the work for a finding that repeats on the same grounds, is a matter of taste, or
   is refuted with evidence. Answer it in its thread and record it in the PR body with the reason.
5. Stop and report the open findings instead of looping when a P0 or P1 finding repeats, when an
   area keeps failing, or after the third re-review that still raises new findings.

## Local Verification Before Delivery

1. Complete required local verification before delivery without waiting for Stop.
2. Normally invoke the shared verify entry point while preparing the delivery commit.
3. Let shared verify reuse valid results when available.
4. Let the existing pre-commit hooks run normally at commit time.
5. Refresh necessary evidence if formatting, fixes, rebase, or other changes alter inputs after
   verification.
6. After PR creation, check CI and [review on GitHub](#review-on-github) and proceed only to the authorized stage.

Stop does not necessarily run before commit, push, or merge, so it cannot be the only delivery
gate. For conditions requiring manual checks, follow
[TSDD Automatic Verification](../../tsdd/SKILL.md#automatic-verification).

## Verification Commands

Use the current record registered and reported by SessionStart as `<session-record>`. Never select
a record merely because its modification time is newest.

```bash
"$HOME/.claude/hooks/verification_session.py" verify "<session-record>"
```

Normally call verify directly before delivery; a status-then-verify sequence is not required.
When freshness is unclear, inspect state without starting checks:

```bash
"$HOME/.claude/hooks/verification_session.py" status "<session-record>"
```

Status exit code 0 means the query succeeded, not that verification passed. Judge verification
from the returned state and each result's applicability.
