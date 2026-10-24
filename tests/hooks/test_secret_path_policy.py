"""Secret path rules deny credential-shaped files without denying ordinary source code."""

import pytest

from tests.runtime import REPO_ROOT, load_script_module


policy = load_script_module("agents/hooks/lib/secret_path_policy.py", "secret_path_policy")
RULES = policy.load(REPO_ROOT / "agents/hooks/rules/secret_path_policy.json")


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "config/github.token",
        "config/api_token",
        "auth/token.json",
        "certs/server.key",
        "certs/server.pem",
        "certs/client.p12",
        "keys/api_key.json",
        "home/.netrc",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "sub/.env",
        "a/b/.env.local",
        "x/id_rsa",
        "x/id_ed25519",
        "deep/dir/credentials.json",
        "keys/service-account-prod.json",
    ],
)
def test_credential_paths_are_denied(path: str) -> None:
    assert policy.blocked_rule(path, RULES) is not None


@pytest.mark.parametrize(
    "path",
    [
        ".venv/lib/python3.15/site-packages/pygments/token.py",
        ".envrc",
        "src/tokenizer.rs",
        "src/keyboard.ts",
        "lib/monkey_patch.py",
        "docs/token_design.md",
    ],
)
def test_source_code_paths_are_readable(path: str) -> None:
    assert policy.blocked_rule(path, RULES) is None
