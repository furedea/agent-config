---
name: development-cycle
description: >
    Use for repository changes and their delivery, including edits that stop short of a commit:
    starting a new project (creating a GitHub repository, applying standard GitHub settings to
    an existing one, or setting up a development environment), securing, creating, updating, and
    closing Issues, saving and updating plan comments, resuming and reconciling Issue-based work,
    branch/worktree selection, commits, pushes, pull requests, CI and review handling, and
    permitted merge and Git cleanup. Explanation, investigation, review, or plan discussion alone
    does not authorize publication or implementation.
---

# Development Cycle

This skill is the map of the cycle from a request to a completed change. Read only the
reference for the stage at hand; continue to use the selected checkout and branch while they
remain suitable for the task.

## Stages

1. **Start**: only for a new project or a missing repository or development environment.
2. **Issue and plan**: secure the Issue the work needs and share a plan when the work warrants one.
3. **Implementation**: follow [tsdd](../tsdd/SKILL.md) on the selected branch or worktree.
4. **Delivery**: commit by intent, push, open the pull request, and handle CI and review.
5. **Completion**: reconcile the Issue, plan, and PR status after delivery or merge.

Apply only the stages the request needs, and pass the Issue number and plan URL forward so the
branch or PR can be associated with them.

## Task-Specific References

| Task                                                              | Read                                                     |
| ----------------------------------------------------------------- | -------------------------------------------------------- |
| Create a GitHub repository or start a new project                 | [Start a project](references/project_setup.md)           |
| Apply standard GitHub settings to an existing repository          | [Repository setup](references/repository_setup.md)       |
| Introduce or complete a project Nix environment                   | [Development environment](references/dev_environment.md) |
| Issue creation/reuse, Issue content, plan comments, resume        | [Issues and plans](references/issue_plan.md)             |
| Selecting or changing the checkout, worktree, or branch           | [Branches and worktrees](references/branches.md)         |
| Planning or preparing authorized commits                          | [Commits](references/commits.md)                         |
| Preparing an authorized push, pull request, or rebase             | [Delivery](references/delivery.md)                       |
| Publishing a stacked or red-green pull request the user asked for | [Stacked pull requests](references/stacked_prs.md)       |

Delegate other responsibilities:

- Testing and implementation methodology → [tsdd](../tsdd/SKILL.md).
- Information authority and temporary document lifetime → [source-of-truth](../source-of-truth/SKILL.md).
- Design decision records → [adr](../adr/SKILL.md).
- Work delegated to another session through Herdr → [herdr-delegation](../herdr-delegation/SKILL.md).

## Authorization

Follow the existing user-managed authorization policy and the current request. This skill does
not define standing permissions or expand publication authority.

- Inspect Git state before edits: current branch, `git status --porcelain=v1`, and recent commit style when commit messages will be written.
- Never overwrite, reset, clean, or discard user changes unless the user explicitly asked for that exact destructive action.
- Ordinary implementation and PR-creation requests do not authorize merging; merge only when explicitly requested and permitted by repository and runtime rules.
- Commit, push, and create pull requests only within the user's request or an explicit standing authorization. Permission to execute a command is not authorization to perform that action for the task. Do not repeat confirmation for steps already covered by the authorized workflow; runtime approval requirements still apply.
- When commits are authorized, group them by reviewable intent. Multiple TSDD cycles may belong to one commit; do not force a commit for every cycle.
- Keep branch names and commit subjects aligned with the primary intent of the change, not with filenames.
- Explanation, investigation, review, or plan discussion alone does not authorize publication or implementation. Review-only requests authorize inspection and findings, not edits or delivery.
- A request to fix a bug covers implementation and verification, not commits or publication. A request to fix and commit adds local recording; a request to fix and open a PR also covers necessary commits and pushes, but not merging.
- After posting a plan, stop until the user approves it. Approval authorizes each lane's worktree session, commits, pushes, and pull request, not merging; see [Branches and worktrees](references/branches.md).
