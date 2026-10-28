# ADR-0017: Ask for every docker form the allowlist does not list

- Status: Accepted
- Date: 2026-10-28
- Refines: ADR-0009

In the context of `docker *` running outside the Claude sandbox and docker reaching host files
through `-v`, `--mount`, `cp`, `--env-file`, build contexts, compose files, and bind-backed named
volumes, facing unlisted forms such as `docker create`, `docker cp`, `docker container run`,
`docker compose run`, `docker buildx`, and `docker-compose` falling to the provider's automatic
judgment, we decided for governing `docker` and `docker-compose` in the allowed-command hook with a
rule flagged `ask_unlisted`, so that read-only inspection (`docker ps|images|logs`,
`docker compose ps|logs`) runs unprompted and every other form asks, and against a catch-all `ask`
prefix and against a parser of docker's mounts, to keep the allow and deny prefixes in effect,
because providers let an ask or deny prefix override the allow prefixes beneath it, so `docker`
ask would also prompt for `docker ps`, and leaving forms that already have an ask prefix (`docker
run`, `docker build`) to the provider's own prompt so that Codex, whose hooks cannot ask, keeps
prompting for them, accepting that Codex denies the other unlisted forms, and that a run-time
program name such as `$d run` is not seen.
