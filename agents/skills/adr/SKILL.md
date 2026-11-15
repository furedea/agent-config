---
name: adr
description: >
    Use to create, review, update, supersede, or deprecate ADRs under docs/adr/, or when a change
    selects a library, framework, database, protocol, hosting, or tool among real alternatives;
    picks an architectural pattern; sets a durable constraint not obvious from code; or reverses
    a previous decision. Not for local implementation details understandable from the code.
---

# Architecture Decision Records

Record a broad decision in `docs/adr/` in the same task that makes it; create the directory if it does not exist.
`tsdd` owns the tests, this skill owns the rationale. New ADRs use [MADR](https://github.com/adr/madr), unless the
repository already has ADRs in another format: then follow that repository's format, file naming, and status values,
and adopt MADR only when asked.

## Decision Test

Write an ADR when a future maintainer would ask "why this approach instead of the obvious alternative?" and the Why
spans several files, components, or future changes, or is costly to reverse. Considering alternatives alone does not
justify one for a local, easily reversible choice; use code, tests, or a comment.

## Inspect First

1. Read the titles and front matter of the existing ADRs, then search them for the topic, the chosen option, and the
   rejected alternatives.
2. If an ADR already covers the decision, make the code follow it instead of writing a duplicate.
3. If the decision reverses or materially changes an accepted ADR, write a new one that supersedes it.

## Write

1. Copy [references/template.md](references/template.md) to `docs/adr/NNNN_words.md`: NNNN is the highest existing ID
   plus one (`0001` in an empty directory; never reuse an ID), and the words are underscore-separated unless the
   existing files differ. The ID comes from the file name.
2. Fill the front matter. Use `accepted` when the decision is implemented in the same change, `proposed` when it is
   not. The title line is `# <short title>` without an ID.
3. Fill the template. Add MADR's full-variant sections only when the minimal ones are too compressed.
4. To supersede, set `supersedes` in the new ADR and `status: superseded` plus `superseded-by` in the old one, in the
   same change. Edit nothing else in an accepted ADR's body; record later changes in `amended`.

## Writing Rules

- Record Why, not What or How; link to requirement sources and tests instead of copying them.
- List under Considered Options only the alternatives that were actually considered; never add padding options.
- Make the Chosen option sentence carry the justification, and state the accepted trade-off in Consequences.
- Write in English for public repositories, short enough that future agents read it.

## Non-Goals

No ADRs for ordinary refactors, language or framework defaults without a project-specific reason, test cases or
acceptance criteria, narrow code comments, or scratch plans.
