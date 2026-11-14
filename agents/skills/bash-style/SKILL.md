---
name: bash-style
description: >
    User-specific conventions for designing, writing, and reviewing Bash scripts and bats tests.
---

# Shell Script Coding Style Guidelines

## Working Directory and Tracing

- Choose the working directory by responsibility. Hooks that operate on a project must use the
  target project's working directory. Resolve bundled resources relative to the script's location.
  Use `cd "$(dirname "$0")"` only when all relative operations should use that location.
- `set -x` prints expanded commands to stderr before execution. Enable tracing only when useful
  for debugging; keep it disabled by default for scripts handling secrets or user input.

If tracing was explicitly enabled, suppress it around noisy or sensitive sections. Restore it only
when subsequent commands are safe to trace:

```sh
set +x
# ... noisy or sensitive section ...
set -x
```

## usage Function

Print the documentation from the `usage` function with a heredoc inside its body:

```sh
function usage() {
  cat <<EOF
Description:
    Description of this script.

Usage:
    $0 [OPTIONS] <FILE>

Options:
    --version, -v: print "$(basename "$0")" version
    --help, -h: print this
EOF
}
```

For requested help (`--help`/`-h`), call `usage` and `exit 0`. For missing or invalid arguments,
call `usage >&2` and `exit 1`.

## Constants

Declare constants with `readonly`. Names use `SCREAMING_SNAKE_CASE`:

```sh
readonly INPUT_DIR="$SCRIPT_DIR/../data/input"
readonly MAX_RETRY=3
```

## Variables

- Use default values for variables that may be empty or undefined:
    ```sh
    readonly OUTPUT="${1:-output.txt}"   # default value
    readonly NAME="${NAME:?NAME is required}"  # error if unset/empty
    ```
- Define variables just before first use (minimize lifetime)

## Naming

| Kind      | Convention                          | Example                |
| --------- | ----------------------------------- | ---------------------- |
| Constants | `SCREAMING_SNAKE_CASE` + `readonly` | `readonly MAX_RETRY=3` |
| Variables | `snake_case`                        | `input_file="..."`     |

## Local Variables

Declare function-local variables with `local`:

```sh
function build_output() {
  local _src="$1"
  local _dst="$2"
  cp "$_src" "$_dst"
}
```

## Formatting

Indent with **2 spaces** (Google Shell Style Guide convention). Configure via `.editorconfig` at the project root; `shfmt` reads it automatically. Run `shfmt -d <file>` to check.

## Task-Specific References

- When creating a new script and a complete skeleton is useful, read
  [script_template.md](references/script_template.md).
- When designing, writing, or reviewing bats tests, read
  [bats_testing.md](references/bats_testing.md) for layout, fixtures, assertions, and test commands.
  Shell scripts use bats for tests; available tools are bats, shellcheck, and shfmt.

Read only the reference relevant to the task.
