---
name: delegation
description: >
    Use when the user requests, or the lanes of an approved plan call for, a plan review or an
    implementation task in a separate Codex or Claude session, including another repository or
    worktree, whichever tool carries it (such as T3 Code threads). Not for ordinary local work,
    a local review, or subagents inside this session.
---

# Delegation

Delegate a bounded task to an independent coding-agent session. The originating session owns
the request, evaluates the returned work, and reports the outcome to the user.

## Scope and Dependencies

- Apply this workflow to requested cross-session work and to the lanes of an approved plan,
    which `development-cycle` hands to task worktree sessions. Do not infer permission to delegate
    from an ordinary coding request, a local review, or an opportunity to work in parallel.
    Run independent lanes of an approved plan in parallel, each in its own task worktree, instead
    of one after another; lanes that change the same lines are the exception and run in sequence.
- A transport is the tool that starts, prompts, and waits for the other session. T3 Code is the
    default transport. Herdr is deprecated: use it only when T3 Code is unavailable, for example
    before the T3 guard and cleanup are installed (furedea/agent-config#265, #266). Otherwise use
    the transport the user names, or the one that
    [Branches and worktrees](../development-cycle/references/branches.md) in `development-cycle`
    selects. Read its reference before operating it: the file in `references/` named after it,
    such as [T3 Code](references/t3.md), or, for a transport with no file there, the skill that
    `development-cycle` names for it. If the transport is unavailable, report the limitation without
    silently switching to another.
- The transport only carries the session. Work state stays outside it: the Issue, the plan
    comment, the brief file, the pull request, and the lane's final `LANE-READY` or `LANE-BLOCKED`.
    Never use a session or thread ID from the transport as the identity of the work.
- Use `development-cycle` for branch and worktree choices and authorized Git delivery. Delegation
    alone does not require a new worktree or authorize commits, pushes, or pull requests; an
    approved plan authorizes them for its lanes, never merging.
- Use `tsdd` and the target repository's applicable conventions for implementation and
    verification. Each session must follow its own repository instructions and permission rules.

## Transport Operations

Every transport reference gives the commands, outputs, and limits of these operations; the rest of
this skill names only the operations.

| Operation | Effect                                                                                                                      |
| --------- | --------------------------------------------------------------------------------------------------------------------------- |
| Start     | Create the recipient session, in a new task worktree on the lane's branch for an implementation, and send its first message |
| Prompt    | Send a literal message to a session this session started                                                                    |
| Wait      | Block in the background until the recipient's turn ends, its run fails, or it waits for the user's answer                   |
| Read      | Retrieve the recipient's state and latest reply                                                                             |
| Close     | End the recipient session and the terminal layout created only for it, where the transport has them                         |
| Clean up  | Remove merged lane worktrees and branches                                                                                   |

## Choose the Task and Recipient

| Request                                    | Default recipient                                                                   | Authority                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Review a plan                              | Claude for a Codex-authored plan; Codex for a Claude-authored plan                  | Findings only; do not rewrite the plan or implement it |
| Implement in another directory or worktree | A separate Claude session, since a Codex session cannot commit in a linked worktree | Changes limited to the delegated scope                 |

A recipient is a Claude or Codex session only; the transport reference names any provider it
offers that must never be a recipient.

When the user asks for Codex to implement, the parent writes the Codex command into the brief
complete, and the lane runs it verbatim as its own Bash call with nothing appended:
`node "<codex plugin>/scripts/codex-companion.mjs" task --write --model gpt-6.1-sol --effort medium --cwd <worktree> "<fixed text>"`.
The fixed text has no nested quotes, dollar sign, pipe, or redirect, so the call stays one command
(furedea/agent-config#76). The lane reads the diff, runs the checks Codex cannot (Nix hashes and
nix builds), commits, pushes, and opens the PR. The lane itself fixes review findings, also when
Codex implemented; Codex is used only for the initial implementation.

Code review is not done locally: every PR is reviewed on GitHub, and the lane follows
[Review on GitHub](../development-cycle/references/delivery.md#review-on-github) in `development-cycle` for
waiting, reading findings, fixing, and the re-review limit. In addition, in a repository that has
those reviews, as furedea/agent-config does, the `furedea-agent` App cannot push `.github/workflows/`
changes, so the lane commits them, stops with `LANE-BLOCKED` naming the commit, and the user
pushes. The parent then prompts the lane to continue, and the lane resumes. A lane ends its final
message with `LANE-READY` only when the repository's required checks are green and no finding is
unhandled; otherwise it ends with `LANE-BLOCKED` and the reason. The lane never sends a message to
the parent's session through any transport: text arriving there is indistinguishable from the
user's own input.

Honor an explicit provider choice. Keep plan review and implementation as distinct
assignments; asking for findings does not authorize the reviewer to fix them.

Reuse an existing session only when its identity, location, and current assignment make it the
intended recipient. Otherwise start a separate session through the transport. Use the requested
repository or worktree; do not substitute another checkout just because its directory name matches.
Allow only one implementation writer per checkout at a time.

## Prepare a Self-Contained Brief

The recipient does not inherit the originating conversation. Keep the brief concise but
complete. Supply:

- **Task:** plan review or implementation, with the requested outcome.
- **Requirements:** the user's relevant requirements, acceptance criteria, accepted decisions,
    constraints, and links to authoritative repository material. Record the version of the
    requirements being delegated, or their full text when no version exists. Distinguish
    requirements from the author's assumptions.
- **Location:** the absolute repository or worktree path, branch, and relevant base and head
    commits. Tell the recipient to read the applicable instructions in that location.
- **Issue:** the Issue body itself, not only its number, so the recipient need not read it again.
- **Input:** the exact plan text or plan file, or implementation scope. For
    uncommitted code, identify whether staged, unstaged, and untracked files are included, and
    provide a stable snapshot when the checkout may still change. For an implementation, first
    check existing tools (related code in the repository, platform features, the standard
    library, installed dependencies, a de facto external tool) and state in the brief which one is used and why, or why none fits.
- **Scope and focus:** the boundaries of the assignment and the review aspects that matter
    (for example correctness, boundaries, verification, or a specific risk), the list of what is
    out of scope, and the threat model: where the input comes from and what a wrong judgment
    costs. Decide both when writing the brief; the lane answers P2 and P3 findings outside it by
    citing the list, and still fixes every P0 and P1 finding.
- **Authority:** permitted edits, excluded files or tasks, and any existing delivery authorization.
- **Completion:** observable acceptance conditions, relevant verification, and the expected
    response described below.

Resolve discoverable context before asking the user. Ask only when a missing requirement,
location, or permission prevents a correct assignment. Reuse authorization already given.

Keep the reviewed input stable until the review completes. For uncommitted work, pause writes
to that checkout or use an explicitly selected isolated snapshot containing all reviewed files.
A result for an earlier plan or revision is not evidence that later changes were reviewed.
A review input is identified by its requirements, diff, scope, and focus together: matching
HEAD alone does not make two reviews the same input when requirements, uncommitted changes,
or requested aspects differ.

## Review Assignments

For a **plan review**, ask the reviewer to compare the proposal independently with the
requirements and relevant repository facts. Look for missing requirements, unsupported
assumptions, incorrect boundaries, migration gaps, and verification that would not distinguish
success from failure. Request findings and necessary corrections, not a replacement plan.

Request findings ordered by severity. Each finding should identify the affected plan section or
file and line, the violated requirement or concrete failure scenario, its impact, and supporting
evidence. Separate unresolved hypotheses from confirmed findings. If none are found, say so
explicitly and state the reviewed scope and any verification limits.

## Implementation Assignments

Have the worker confirm the actual repository root, branch, and dirty state before editing.
Preserve pre-existing changes and resolve conflicting ownership before starting work. Keep
implementation inside the assigned scope; report dependencies on another repository or a
broader change instead of silently expanding the assignment.

Ask the worker to return:

- What changed and how it satisfies the requested outcome.
- Changed files, working directory, and branch; commit IDs when committing was authorized.
- Checks performed and their results, including failures or checks that could not run.
- Remaining work, unresolved decisions, and any blocker that prevents completion.

## Run and Reconcile

Write the brief to a file in the originating session's scratchpad and Start the recipient with a
literal message that tells it to read that file. Keep every message literal: a substitution such
as `"$(cat brief.md)"`, stdin, or a heredoc turns the call into more than one plain transport
command, which the sandbox and the command hooks then treat differently. Run each transport
command as its own Bash call, and run `git fetch` in a separate call first. A recipient in a
linked worktree of another repository fetches and rebases there itself, since the originating
session cannot write that repository's `.git`. Retain the recipient identity and input revision
in the originating session.

Right after Start, Wait in the background for the end of the recipient's turn. Treat the end of
its turn as its final report; the recipient therefore waits for CI in the foreground and does not
end its turn before CI finishes
([Wait for CI](../development-cycle/references/delivery.md#wait-for-ci)). Do not relay or answer
approval prompts and questions: the user notices them through the transport's own notification
and answers in the recipient's own view, while the parent keeps waiting as the reference
describes.

When the Wait returns at the end of the turn, Read the reply. For an implementation, check for
`LANE-READY`, check the PR state, and report to the user. Treat `LANE-BLOCKED` and its reason
as incomplete work. When the Wait returns for another reason, such as a timeout, a failed run,
or a pending answer, follow the reference to tell them apart: keep waiting while the recipient
still works or waits for the user, and report a failed or stopped run to the user instead of
restarting it. This works for Claude and Codex recipients alike.
Successful submission or a settled session state does not prove that the assigned task is
complete; read the response and compare it with the requested outcome.

Do not repeat a completed review of the same requirements, diff, scope, and focus without new
grounds. When inputs or material evidence change, scope the follow-up review to the affected
part instead of repeating the whole assignment. Retrying a timed-out, incomplete, or
unretrieved review is not a duplicate of a completed one.

Evaluate review findings against the requirements and evidence before changing the work.
Sort each finding as confirmed, refuted with evidence, or undetermined for lack of
information. Apply accepted corrections within the user's scope and seek a focused follow-up
review when material changes leave the earlier review incomplete. Resolve disputed findings
with evidence; do not manufacture consensus by repeating the same review request, do not
commission a review whose purpose is to refute a finding, and do not treat agreement between
agents as proof of correctness. If conclusions keep alternating on the same grounds with no
new information, report the point as unresolved and stop re-reviewing.

Keep the mapping between reviewed inputs and their results in the originating conversation.
When recording on a pull request has been requested, add only the needed content to that PR.
Do not introduce a review database, a `REVIEW_STATE.md`, or a standing reconciliation
process.

For implementation, inspect the actual diff and verification evidence in the assigned repository
before reporting success. When requested completion includes integrating another worktree's
changes, follow `development-cycle` for authorized integration and report anything still pending.
Do not infer that changes reached the intended branch merely because the worker finished.

## Finish and Clean Up

The originating session decides when the assignment is complete after accepting the result and
checking any required integration. Keep the worker available while clarification, corrections,
or another review is still needed for the current assignment.

Once the result is fully captured and no follow-up remains for that worker:

- Close the recipient session and the temporary layout created solely for this assignment.
    Recheck their identity, ownership, and live state first; leave resources now used by the user
    or another task open.
- Leave reused sessions and pre-existing layout open. Honor a request to retain a newly created
    worker for continued work.
- Keep branches and worktrees while their changes await integration or merge. Follow
    `development-cycle` for their eventual removal; closing a worker must not discard pending
    changes. After the user merges, the parent runs the transport's Clean up; do not remove lane
    worktrees by hand.
- Remove task-created temporary outputs only after their needed contents are captured in the
    originating conversation or a requested artifact. Do not create a permanent report solely
    to justify closing a worker.

If the assignment or cleanup is blocked, preserve the resources needed to resume it and report
what remains open and why. A timeout or interrupted session does not establish completion.

Report the provider and reviewed or changed scope, the resulting findings or implementation,
verification evidence, where the changes remain, and whether workers were closed or retained.
Identify unresolved work and cleanup failures. Keep the final response with the originating
session; a worker's completion message does not replace this reconciliation.
