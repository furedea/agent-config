"""Process-boundary fakes for the Stop-time model rules: no Keychain, no 1Password, no model, no network.

The fakes record what they were called with, so a test can state the exact argv and the environment that crossed the
boundary. The token and Environment ID are made up and appear nowhere outside these tests.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from tests.runtime import StubWriter

FAKE_TOKEN = "ops_FAKE_TOKEN_FOR_TESTS_ONLY"
ENVIRONMENT_ID = "abcdefghijklmnopqrstuvwxyz"

SECURITY = """
import json, sys
service = sys.argv[sys.argv.index("-s") + 1]
with open(@CALLS@, "a") as stream:
    stream.write(json.dumps({"program": "security", "argv": sys.argv[1:]}) + "\\n")
items = json.load(open(@KEYCHAIN@))
if service not in items:
    sys.exit(44)
print(items[service])
"""

OP = """
import json, os, sys
with open(@CALLS@, "a") as stream:
    stream.write(json.dumps({
        "program": "op",
        "argv": sys.argv[1:],
        "env_names": sorted(os.environ),
        "has_token": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") == @TOKEN@,
    }) + "\\n")
child = sys.argv[sys.argv.index("--") + 1:]
os.execvp(child[0], child)
"""

JEV_LINT = """
import json, os, sys, time
dry_run = "--dry-run" in sys.argv
with open(@CALLS@, "a") as stream:
    stream.write(json.dumps({
        "program": "jev-lint",
        "argv": sys.argv[1:],
        "cwd": os.getcwd(),
        "env_names": sorted(os.environ),
        "has_token": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") == @TOKEN@,
    }) + "\\n")
behavior = json.load(open(@BEHAVIOR@))
if dry_run:
    print(open(@PLAN@).read())
    sys.exit(0)
print(@TOKEN@, file=sys.stderr)
time.sleep(behavior.get("sleep", 0))
print(open(@REPORT@).read())
sys.exit(behavior.get("exit", 0))
"""


@dataclass(frozen=True, slots=True)
class Tools:
    """Fake `security`, `op` and `jev-lint` on PATH, and the files that steer and record them."""

    directory: Path

    @property
    def calls_file(self) -> Path:
        return self.directory / "calls.jsonl"

    def calls(self, program: str | None = None) -> list[dict]:
        """Every recorded invocation, optionally of one program, in order."""
        if not self.calls_file.exists():
            return []
        records = [json.loads(line) for line in self.calls_file.read_text().splitlines()]
        return [record for record in records if program in (None, record["program"])]

    def keychain(self, **items: str) -> None:
        """Replace the Keychain contents; a missing service makes the fake `security` fail."""
        (self.directory / "keychain.json").write_text(json.dumps(items))

    def plan(self, subjects: int, batches: list[tuple[str, int]] | None = None, cached: int = 0) -> None:
        """What `jev-lint review --dry-run --json` prints."""
        report = {
            "dryRun": True,
            "subjects": subjects,
            "cached": cached,
            "batches": [{"file": file, "subjects": count, "arm": "local"} for file, count in batches or []],
        }
        (self.directory / "plan.json").write_text(json.dumps(report))

    def report(self, findings: list[dict] | None = None, **extra: object) -> None:
        """What `jev-lint review --json` prints."""
        report = {"findings": findings or [], "spent": {"calls": 2}, "cachedCount": 1, **extra}
        (self.directory / "report.json").write_text(json.dumps(report))

    def raw_report(self, text: str) -> None:
        (self.directory / "report.json").write_text(text)

    def behave(self, **behavior: object) -> None:
        """Make the fake `jev-lint` exit with a status or sleep before it answers."""
        (self.directory / "behavior.json").write_text(json.dumps(behavior))


def finding(rule: str = "command-query-naming", file: str = "notes.txt", line: int = 3) -> dict:
    return {
        "rule": rule,
        "file": file,
        "line": line,
        "reported": True,
        "value": 0.71,
        "at": 0.5,
        "message": f"{rule}: the name promises a query but the body writes",
    }


def _fill(template: str, values: dict[str, str]) -> str:
    for placeholder, value in values.items():
        template = template.replace(placeholder, value)
    return template


def install_tools(executable: StubWriter, directory: Path) -> Tools:
    """Write the three fakes and give them a healthy default: a one-subject plan, one finding."""
    directory.mkdir(exist_ok=True)
    tools = Tools(directory)
    values = {
        "@CALLS@": repr(str(tools.calls_file)),
        "@KEYCHAIN@": repr(str(directory / "keychain.json")),
        "@PLAN@": repr(str(directory / "plan.json")),
        "@REPORT@": repr(str(directory / "report.json")),
        "@BEHAVIOR@": repr(str(directory / "behavior.json")),
        "@TOKEN@": repr(FAKE_TOKEN),
    }
    for name, template in (("security", SECURITY), ("op", OP), ("jev-lint", JEV_LINT)):
        executable(name, _fill(template, values))
    tools.keychain(
        **{
            "agent-model-rules-op-token": FAKE_TOKEN,
            "agent-model-rules-op-environment": ENVIRONMENT_ID,
        }
    )
    tools.plan(1, [("notes.txt", 1)])
    tools.report([finding()])
    tools.behave()
    return tools
