---
name: github-actions-style
description: >
    Apply this user's conventions when creating, changing, or reviewing GitHub Actions workflows
    and composite actions.
---

# GitHub Actions Coding Conventions

These patterns are easy to overlook but important for security and reliability.

## 1. Permissions — Whitelist Approach

The default `GITHUB_TOKEN` has read/write access to the repo, which is broader than most jobs need. Grant only what each job actually requires.

```yaml
permissions: {} # workflow level: deny-all

jobs:
    build:
        permissions:
            contents: read # checkout
            pull-requests: write # post comments
```

Common permission keys: `contents`, `issues`, `pull-requests`, `packages`, `id-token` (OIDC), `checks`, `statuses`.

## 2. timeout-minutes

Choose a timeout appropriate for the job — typically 5–15 minutes for CI.

```yaml
jobs:
    build:
        timeout-minutes: 10
```

## 3. Shell Settings

For debugging, add `set -x` at the top of a `run:` block to print each command and its output to stderr before execution:

```yaml
- run: |
      set -x
      uv run --frozen pytest
```

## 4. Concurrency

Use `cancel-in-progress: false` for deploy workflows that must run in order; cancel stale runs everywhere else.

## 5. Cache Design

- Measure representative cold and warm runs before adding a cache. Prefer
  GitHub's cache backend; use an external backend only when self-hosted runner
  locality and measured transfer time justify its credentials and operating
  cost.
- Include every compatibility boundary in the primary key. Use partial matches
  only when the consumer validates and reconciles stale contents; otherwise
  require an exact match. Always keep a correct cache-miss fallback.
- Account for cache scope: pull-request caches are scoped to their merge refs
  and are not reusable by the default branch or sibling pull requests.
- Treat default-branch cache contents as readable by pull requests. Do not
  cache broad paths that may contain credentials. When using an external shared
  backend, do not let untrusted workflows write caches that privileged
  workflows later execute.

## 6. Workflow File Names

Name workflow files in kebab-case with the `.yml` extension (e.g. `release-please.yml`). This is the GitHub Actions convention and an exception to the general underscore rule for file names.
