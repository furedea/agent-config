# Start a Project

A request to start a new project runs the cycle from this stage; the user need not name the skill.

## Scope and Routing

Choose only the paths needed for the request; repository configuration and local environment
setup are independent tasks.

| Request                                                                        | Read                                                                      |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| Create a GitHub repository, with or without a template                         | [Repository setup](repository_setup.md)                                   |
| Apply standard GitHub settings to an existing repository                       | [Repository setup](repository_setup.md), existing repository section only |
| Introduce or complete a project Nix environment, including local-only projects | [Development environment](dev_environment.md)                             |
| Create a project and make it ready for development                             | Repository setup and development environment                              |

Do not introduce Nix or change GitHub settings merely because a code-editing task loads a
language skill. Machine-wide package and system configuration is outside this skill;
branches and authorized commits, pushes, and PRs follow [Branches and worktrees](branches.md), [Commits](commits.md), and [Delivery](delivery.md).

## Shared Principles

- Preserve existing source, manifests, lockfiles, CI, hooks, and project conventions. Adopt only
    the missing pieces needed by the request; a template is not an instruction to overwrite a repo.
- Inspect the chosen template or existing project for actual versions and provided files.
    Templates and project configuration own those facts, not copied inventories in this skill.
- Preserve checked-in locks. Environment initialization is not a dependency-upgrade request.
- Run language setup in the project's effective development environment, not the global fallback.
    Reading permission for `.envrc` and activation of that environment are distinct steps.
- Complete the requested setup and relevant verification. Report partial completion and blockers
    without expanding into unrelated repositories, global configuration, or publication.

## Language and Visibility

For a new project, choose the language and visibility from the requirements, then pass them to
`repo create` as `--lang <python|typescript|rust|go|tex|minimal>`; `repo` owns the mapping from
language to template. Default to private, and ask only for what the requirements cannot decide.
Use `minimal` for languages without a dedicated option. Then continue into the cycle with
[Issues and plans](issue_plan.md) or implementation.

| Language          | Development conventions       |
| ----------------- | ----------------------------- |
| Python            | `python-style`                |
| TypeScript        | `typescript-style`            |
| Rust              | `rust-style`                  |
| Go                | `go-style`                    |
| TeX               | Existing project conventions  |
| Other (`minimal`) | Relevant language conventions |

Read the reference for the requested workflow. The development-environment reference includes
language-specific notes; apply those relevant to the project. Existing projects need not have
been created from a template to use the environment-setup path.

## Completion and Handoff

- **Repository configuration only:** verify the requested remote settings and report their scope.
    No Nix activation, dependency installation, or language checks are required.
- **Repository creation only:** confirm the remote and clone destination, configuration outcome,
    and any local template adjustments. Do not silently extend this into language setup.
- **Development environment:** confirm the selected project toolchain and dependency environment
    work, preserve unrelated files, and record relevant verification results or limitations.
    Development can then follow `tsdd` and the corresponding language conventions.

Tests, lint, and formatting normally run through hooks. Follow `tsdd`'s Automatic Verification
policy: reuse successful results covering the current changes instead of duplicating them.
If a hook did not run or lacks coverage, use the narrowest required check. Environment smoke
checks and failure diagnosis remain appropriate; an installed hook is not evidence it passed.
