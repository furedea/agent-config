# Go Code Conventions

## Naming

- Use short, single-word package names.
- Cast initialisms consistently: `ID`, `URL`, `HTTP`, not `Id`, `Url`, `Http`.
- Use the same receiver name across a type's methods.
- Let name length match scope: `i` in a short loop, a descriptive name for a package-level identifier.
- Avoid `manager`, `helper`, `util`, and `common` unless the name is already established locally.

## Comments and Documentation

- Comments explain why, not what.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.

## Logging and Diagnostics

- Keep human diagnostics on stderr and machine-readable command output on stdout.
