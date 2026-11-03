# ADR-0018: Allow browser and desktop automation except named risky forms

- Status: Accepted
- Date: 2026-11-03
- Refines: ADR-0009

In the context of `agent-browser` and `agent-desktop` working only outside the Claude sandbox and
being called many times in a row, facing either a prompt on every call or no review at all, we
decided for listing their ordinary subcommand forms in the allowed-command rules so that they run
from the first call, for rule exceptions and unlisted forms that ask for connecting to a running
browser, profiles, saved state and sessions, browser launch options and providers, file transfer,
absolute, home, or parent-directory paths that outputs or inputs could name, desktop targets
the arguments cannot name (no `--app`, `--window-id`, focused-window or coordinate input, `batch`,
`launch`), and compound, expanded, quoted, or wrapped calls, and for forbidden rules scoped by
`programs` that read the decoded arguments ignoring case, so that `file:` and `chrome:` URLs and
terminals, System Settings, and credential apps, by English or Japanese name, stay denied, and against approving each program
once per session, because it needs a grant file outside the sandbox's writable state and a
PostToolUse step to confirm the approved call ran, a cost the one saved prompt does not repay,
accepting that Codex, whose hooks cannot ask, denies every asking form, that a ref-based
desktop action cannot be tied to its app from its arguments, that app names in other languages are
not denied, and that a relative output path through a symlink the session made can still write
outside the sandbox.
