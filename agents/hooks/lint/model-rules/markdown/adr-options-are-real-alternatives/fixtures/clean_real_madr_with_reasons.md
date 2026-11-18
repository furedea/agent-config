---
status: accepted
date: 2026-11-15
amended:
  - "2026-11-16: the front-matter and accepted-body checks are the adr-check command, see ADR-0026"
related: [ADR-0021, ADR-0023]
---

# Adopt MADR with structured front matter for ADRs

## Context and Problem Statement

ADRs here use a one-sentence Y-Statement with a bulleted metadata block. Agents write them, and people and agents read
them. The sentence grows unreadable as a decision gains reasons (ADR-0021), rejected alternatives have no place of
their own, and the metadata (status, supersession, amendments) is free text that no tool can read. No official ADR
standard exists. Which format should new ADRs use, and what happens to the existing ones?

## Considered Options

* Keep the Y-Statement form with the bulleted metadata
* Nygard's original format (Context, Decision, Status, Consequences)
* [MADR](https://github.com/adr/madr), the minimal variant by default, with the metadata in YAML front matter
* A third-party ADR CLI to create and manage the files

## Decision Outcome

Chosen option: "MADR, minimal variant, with the metadata in YAML front matter", because it gives a place to each thing
the `adr` skill already demands (rejected alternatives in Considered Options, the justification in the sentence
`Chosen option: "X", because Y`, the trade-off in Consequences) and the 2026 study arXiv 2604.27333 rated it strongest
for rationale depth, which matters more here than writing cost because agents write the ADRs.

* Front matter: `status` (proposed, accepted, rejected, deprecated, superseded), `date`, and optionally `supersedes`,
  `superseded-by` (exactly when the status is superseded), `partly-superseded-by`, `amended` (a list of
  `"YYYY-MM-DD: what changed"`), and `related`; the ID comes from the file name, which keeps the
  `NNNN_words.md` convention. MADR's `decision-makers`, `consulted`, and `informed` may be used in new ADRs.
* New ADRs start from the vendored minimal template in `agents/skills/adr/references/template.md` and use the title
  line `# <short title>` without an ID. The full-variant sections are added only when needed.
* Existing ADRs keep their bodies byte for byte; only their metadata moved into front matter. Lines that fit no key
  became `related` entries, with a YAML comment where they carried prose. An ADR of another repository is written
  `dotfiles/ADR-NNNN` in any key, so a check resolves only the IDs without a prefix.
* Verification is added by later changes, each placed at the earliest tier that can judge it (ADR-0023): markdownlint
  MD043 scoped to `docs/adr/` for the section structure, `lychee --offline` for links between ADRs, a small front-matter
  check for ID uniqueness and supersession consistency, a CI check that the bodies of accepted ADRs do not change, and
  Jev for writing quality. None is part of this decision's change.

### Consequences

* Good, because each ADR states its alternatives and reasons in a fixed place, and the metadata can be checked by a
  program instead of read as prose.
* Good, because the skill shrinks to judgement: the mechanics are "copy the template and fill it".
* Bad, because new and old ADRs have different bodies until, if ever, the old ones are rewritten, and the Y-Statement
  and MADR forms coexist.
* Bad, because the front-matter shape is this repository's own, and the checks that enforce it do not exist yet.

## More Information

Rejected for these reasons: Nygard has no place for rejected options; keeping the Y-Statement keeps the unreadable
single sentence and the unstructured metadata; adr-tools was last released in 2018, `adrs` is small, and the tools
that MADR lists support only MADR 2.1.2.
