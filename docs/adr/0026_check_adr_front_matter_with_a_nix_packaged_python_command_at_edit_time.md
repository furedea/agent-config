---
status: accepted
date: 2026-11-16
related: [ADR-0021, ADR-0023, ADR-0025]
---

# Check ADR front matter with a Nix-packaged Python command that runs at edit time

## Context and Problem Statement

ADR-0025 fixed the front-matter shape of ADRs and left its verification to later changes: a check for ID uniqueness
and supersession consistency, and a check that the bodies of accepted ADRs do not change. The check must read
structured YAML and a reference graph, it should tell the agent about a violation when the agent writes the file and
not after a push, and other repositories will run it too. Where does the check live, in what language, and where does
it run?

## Considered Options

* About 280 lines of bash in a composite action of `furedea/reusable-workflows` (the first attempt, #33 there)
* A Python command packaged with Nix in this repository, validating against a JSON Schema, run by the edit hook and by CI
* Markdownlint front-matter rules only

## Decision Outcome

Chosen option: "A Python command packaged with Nix in this repository, validating against a JSON Schema, run by the
edit hook and by CI", because it is the only option that runs at the earliest tier that can judge the rule (ADR-0023:
static, at the agent's edit, as ADR-0021 requires of static checks) and still gives CI the same verdict, and because
YAML parsing and a reference graph are what bash handles worst.

* `adr-check` (`tools/adr-check/`, built by `nix/adr_check.nix` as `packages.<system>.adr-check`) validates each front
  matter against `tools/adr-check/src/adrcheck/front_matter.schema.json`, the single machine-readable definition of the
  shape in ADR-0025, then checks across files: duplicate IDs, unresolved unprefixed references, and supersession
  that is not recorded on both sides. With `--base <commit>` it also fails when an ADR accepted at that commit is
  removed, renumbered, or has its body changed; front-matter changes stay allowed.
* The input is the fixed shape only. A file that does not match is a violation and is never interpreted: prose metadata
  lines and the formats of other repositories are not parsed, and IDs with a repository prefix are not resolved.
* The command is a Python project with its own `tools/adr-check/pyproject.toml`, the one place that declares its
  name, version, dependencies (`jsonschema`, `ruamel.yaml`), and entry point; `nix/adr_check.nix` builds it from that
  file, and it is a uv workspace member so that ty, ruff, and the tests see the same dependencies. The hooks stay
  standard-library-only and call the command; `lint_format.py` runs it, without `--base`, on the directory of an
  edited or deleted `docs/adr/*.md` and returns the findings as context without blocking, as ADR-0021 specifies for
  static rules. The protection of accepted bodies needs a base commit, so only CI enforces it. CI
  runs `nix run github:furedea/agent-config/<sha>#adr-check -- --base <base> docs/adr`.

### Consequences

* Good, because the agent learns of a shape or reference violation in the turn that causes it, and CI and the hook
  cannot disagree about the shape.
* Good, because a change to the shape is a change to one schema file, with a test.
* Bad, because the command exists only where Nix provides it; the hook stays silent without it, so a machine without
  the package gets the CI verdict only.
* Bad, because the command runs on the stable channel's Python, not the 3.15 of the hooks, and its source must stay
  valid there.

## More Information

Rejected for these reasons: bash in a composite action runs only in CI, so the agent finds out after pushing, and it
parses YAML and follows references badly; markdownlint cannot compare files or read git history, so it leaves
uniqueness, supersession, and accepted bodies unchecked.
