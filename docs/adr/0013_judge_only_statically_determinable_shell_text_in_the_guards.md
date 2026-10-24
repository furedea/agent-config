# ADR-0013: Judge only statically determinable shell text in the guards

- Status: Accepted
- Date: 2026-10-24

In the context of the guard hooks (`guard_git`, `guard_command`, the secret path and secret commit
checks) that inspect shell text before the OS sandbox from
[ADR-0011](0011_close_the_sandbox_escape_and_run_nix_inside.md) runs it, facing review rounds on
furedea/agent-config#3 that each found another spelling of the same operation (a quoted variable
name, a leading-zero descriptor, an appending assignment) and would never converge if every spelling
had to be closed, we decided for a two-part contract and against chasing each new spelling or
treating the guards as a complete boundary:

1. An operation written literally, or determinable from the text alone, is judged as the shell
   would run it: blocked or asked as the policy says. A static form that slips through is a bug.
2. Anything whose meaning is known only at run time is asked, uniformly rather than case by case:
   variables or command substitution in the program or path position, `eval`, a shell fed input
   the hook cannot read, functions or aliases defined in the same command, and similar forms.

A spelling outside both rules is recorded as a known gap rather than fixed under review pressure.
This keeps the guards predictable and reviews finite, accepting that a determined spelling can
still pass the supplementary guards, and that the sandbox, not the guards, remains the boundary.
