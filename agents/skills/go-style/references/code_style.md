# Go Code Conventions

## Formatting

- gofumpt and goimports decide formatting and import grouping. Do not hand-format around them.

## Naming

- Use short, single-word package names.
- Avoid stutter: `config.Loader`, not `config.ConfigLoader`.
- Cast initialisms consistently: `ID`, `URL`, `HTTP`, not `Id`, `Url`, `Http`.
- Use the same receiver name across a type's methods.
- Let name length match scope: `i` in a short loop, a descriptive name for a package-level identifier.
- Avoid `manager`, `helper`, `util`, and `common` unless the name is already established locally.

## Comments and Documentation

- Doc comments on exported identifiers start with the identifier name: `// Load reads ...`.
- Comments explain why, not what.
- Architectural choices, dependency decisions, and external-tool boundary rules belong in ADRs.

## Logging and Diagnostics

- Keep human diagnostics on stderr and machine-readable command output on stdout.
