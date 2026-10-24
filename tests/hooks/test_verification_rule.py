"""Default test mappings and Codex verification hooks stay consistent."""

import json


from tests.runtime import REPO_ROOT


DEFAULTS = REPO_ROOT / "agents/hooks/rules/related_test_defaults.json"


def test_rule_file_is_a_json_object() -> None:
    assert isinstance(json.loads(DEFAULTS.read_text()), dict)


def test_defaults_define_repository_test_conventions() -> None:
    rules = json.loads(DEFAULTS.read_text())
    assert set(rules) == {"bats", "python", "rust", "javascript_typescript"}
    assert rules["bats"]["source_extensions"] == [".sh", ".bats"]
    assert {"{stem}.bats", "test_{stem}.bats"} <= set(rules["bats"]["test_patterns"])
    assert rules["python"]["source_extensions"] == [".py"]
    assert {"test_{stem}.py", "{stem}_test.py"} <= set(rules["python"]["test_patterns"])
    assert "pyproject.toml" in rules["python"]["project_markers"]
    assert rules["rust"]["source_extensions"] == [".rs"]
    assert "Cargo.toml" in rules["rust"]["project_markers"]
    assert rules["rust"]["integration_test_dir"] == "tests"
    assert "src" in rules["rust"]["source_dirs"]
    assert rules["javascript_typescript"]["source_extensions"] == [".js", ".jsx", ".ts", ".tsx"]
    assert "{stem}.test.ts" in rules["javascript_typescript"]["test_patterns"]


def test_defaults_have_no_obsolete_lint_entry_point() -> None:
    assert all("lint_hook" not in rule for rule in json.loads(DEFAULTS.read_text()).values())


def test_codex_verifies_changes_before_stopping() -> None:
    hooks = json.loads((REPO_ROOT / "agents/hooks.json").read_text())
    commands = [hook["command"] for group in hooks["codex"]["hooks"]["Stop"] for hook in group["hooks"]]
    assert '"$HOME/.claude/hooks/verification_session.py" codex stop' in commands


def test_codex_session_end_hook_respects_timeout_limit() -> None:
    hooks = json.loads((REPO_ROOT / "agents/hooks.json").read_text())
    handlers = [hook for group in hooks["codex"]["hooks"]["SessionEnd"] for hook in group["hooks"]]
    assert all(handler.get("timeout", 3) <= 3 for handler in handlers)
