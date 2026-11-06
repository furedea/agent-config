# Jev spike: rule set (issue #75)

Seven rules taken from `agents/AGENTS.md` (Coding Guidelines). Each is still prose and needs a reader
who has seen both the name and the body, so no linter or ast-grep pattern decides it. The unit judged
is one Python function. Ground truth is `labels.json`; the examples are in `examples/`.

| id                          | Question (one sentence, as given to the model)                                                             | Source line in AGENTS.md                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `single-purpose-function`   | This function does more than one job, or mixes levels of abstraction.                                      | Keep functions single-purpose at one abstraction level                    |
| `query-has-side-effects`    | A function named like a query (get, is, has, find, count) changes state or performs I/O.                   | Name command functions for side effects and query functions for the value |
| `comment-restates-code`     | A comment in this function restates what the next line does instead of a non-obvious constraint or why.    | Minimize comments; use them for non-obvious constraints and intent        |
| `anonymous-argument-bundle` | Arguments are grouped into an anonymous dict, tuple or list that is not a named domain type.               | Group arguments only into a named type for a real domain concept          |
| `revalidates-parsed-input`  | This function re-validates a value that its type or caller already guarantees.                             | Parse raw input into constrained types once at the boundary               |
| `name-omits-unit`           | A name holds a quantity with a unit, or a flag, and the name does not say which unit or is not a question. | Include units and boolean prefixes where they clarify meaning             |
| `primitive-for-invariant`   | A raw primitive carries a value with validation rules or behavior that belongs to a value object.          | Prefer Value Objects over raw primitives for values with invariants       |

Labels: `violating` means the rule should fire on that function. The examples are written to be
unambiguous to a human reviewer; borderline cases are labelled by the author and may be disputed,
which the report states as a limit.
