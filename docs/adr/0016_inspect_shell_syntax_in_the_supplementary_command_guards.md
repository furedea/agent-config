# ADR-0016: Inspect shell syntax in the supplementary command guards

- Status: Accepted
- Date: 2026-10-24
- Originally: the command-guard paragraph of furedea/dotfiles ADR-0026
- Related: [ADR-0015](0015_judge_only_statically_determinable_shell_text_in_the_guards.md) (what the guards judge)

In the context of personal hooks that decide whether an agent's shell command may run, facing
provider permission rules that match command prefixes and cannot see what a pipeline, a redirection,
or a quoted argument actually does, we decided for supplementary guards that inspect the syntax tree
that shfmt produces, reject syntax they cannot interpret statically, and keep the existing POSIX ERE
and PCRE2 policy dialects by passing them to grep and ripgrep, and against re-implementing the
policy dialects in the hook language or treating the guards as a replacement for the provider's
permissions, to make the policy decisions directly testable while the dialects stay the ones the
provider rules already use, accepting a dependency on shfmt, grep, and ripgrep at run time.

The guards do not replace the provider's permissions or the sandbox boundary. The sandbox from
[ADR-0011](0011_close_the_sandbox_escape_and_run_nix_inside.md) remains the boundary.
