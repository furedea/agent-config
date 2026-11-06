"""Run jev-lint and jevlint on the spike rules and write one JSONL row per judgement.

Called by measure.sh. The JSONL rows cover every function in the examples (those not listed in
labels.json count as conforming), matching analyze_results.py, which rescores from results/raw.
The API key is read by the tools from the environment; this module never
reads, prints or stores it, and redacts it from anything it logs.
"""

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SPIKE_DIR / "results"
JEV_LINT_VERSION = "0.7.0"


@dataclass(frozen=True)
class Unit:
    name: str
    first_line: int
    last_line: int
    label: str


@dataclass(frozen=True)
class Case:
    rule_id: str
    ask: str
    source: Path
    units: tuple[Unit, ...]
    function_count: int


@dataclass(frozen=True)
class Outcome:
    findings: dict[int, float | None]
    seconds: float
    input_tokens: int | None
    usd: float | None
    error: str | None


def load_cases() -> list[Case]:
    labels = json.loads((SPIKE_DIR / "labels.json").read_text())
    return [build_case(rule_id, spec) for rule_id, spec in labels.items()]


def build_case(rule_id: str, spec: dict) -> Case:
    source = SPIKE_DIR / "examples" / spec["file"]
    functions = [node for node in ast.walk(ast.parse(source.read_text())) if isinstance(node, ast.FunctionDef)]
    violating = set(spec["violating"])
    units = tuple(
        Unit(
            node.name,
            node.lineno,
            node.end_lineno or node.lineno,
            "violating" if node.name in violating else "conforming",
        )
        for node in functions
    )
    return Case(rule_id, spec["ask"], source, units, len(functions))


def scrub(text: str, work: Path) -> str:
    """Replace local paths so committed results carry no username or home directory."""
    for real, placeholder in ((str(work), "<work>"), (str(SPIKE_DIR.parents[2]), "<repo>"), (str(Path.home()), "~")):
        text = text.replace(real, placeholder)
    return text


class Log:
    def __init__(self, path: Path, work: Path) -> None:
        self._path = path
        self._work = work
        self._secret = os.environ.get("TYPESAFE_API_KEY", "")

    def write(self, message: str) -> None:
        if len(self._secret) >= 8:
            message = message.replace(self._secret, "[redacted]")
        with self._path.open("a") as handle:
            handle.write(scrub(message, self._work) + "\n")


def run_command(command: list[str], cwd: Path | None, log: Log) -> tuple[subprocess.CompletedProcess, float]:
    log.write("$ " + " ".join(command))
    started = time.monotonic()
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    seconds = time.monotonic() - started
    log.write(f"exit={done.returncode} wall={seconds:.2f}s stderr={done.stderr.strip()[:400]!r}")
    return done, seconds


def match_findings(case: Case, found: list[tuple[int, float | None]]) -> dict[int, float | None]:
    """Map each flagged unit's first line to the finding's confidence (names repeat, lines do not)."""
    verdicts: dict[int, float | None] = {}
    for unit in case.units:
        for line, confidence in found:
            if unit.first_line <= line <= unit.last_line:
                verdicts[unit.first_line] = confidence
    return verdicts


def jev_lint_outcome(case: Case, work: Path, raw_dir: Path, log: Log, plan: bool) -> Outcome:
    rule_file = work / "jev-lint" / f"{case.rule_id}.yml"
    rule_file.parent.mkdir(parents=True, exist_ok=True)
    rule_file.write_text(
        json.dumps(
            {
                "id": case.rule_id,
                "languages": ["Python"],
                "rule": {"kind": "function_definition"},
                "subject": "node",
                "ask": case.ask,
            }
        )
    )
    command = [
        "nix", "shell", "nixpkgs#nodejs_24", "nixpkgs#ast-grep", "-c",
        "npx", "-y", f"jev-lint@{JEV_LINT_VERSION}", "check", str(case.source),
        "-R", str(rule_file), "--no-config", "--cache", "none", "--json",
    ]  # fmt: skip
    if plan:
        command += ["--dry-run"]
    done, wall = run_command(command, None, log)
    (raw_dir / f"jev_lint_{case.rule_id.replace('-', '_')}.json").write_text(scrub(done.stdout, work))
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError:
        return Outcome({}, wall, None, None, f"unparsable output, exit {done.returncode}")
    errors = data.get("errors") or []
    error = json.dumps(errors)[:300] if errors else None
    if plan:
        return Outcome({}, wall, data.get("tokens"), data.get("usd"), error)
    spent = data.get("spent") or {}
    found = [(row["line"], row.get("confidence")) for row in data.get("findings", [])]
    return Outcome(match_findings(case, found), wall, spent.get("inputTokens"), spent.get("usd"), error)


def jevlint_outcome(case: Case, work: Path, raw_dir: Path, log: Log, plan: bool) -> Outcome:
    project = work / "jevlint" / case.rule_id
    project.mkdir(parents=True, exist_ok=True)
    (project / case.source.name).write_text(case.source.read_text())
    (project / ".jevlint.json").write_text(
        json.dumps(
            {
                "languages": {"python": {}},
                "rules": [{"id": case.rule_id, "description": case.ask, "severity": "error", "kinds": ["function"]}],
            }
        )
    )
    if plan:
        return Outcome({}, 0.0, None, None, None)  # jevlint has no dry-run; nothing to validate in --plan
    command = [str(work / "bin" / "jevlint"), "check", "--format", "json", "--refresh-cache", case.source.name]
    done, wall = run_command(command, project, log)
    (raw_dir / f"jevlint_{case.rule_id.replace('-', '_')}.json").write_text(scrub(done.stdout, work))
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError:
        return Outcome({}, wall, None, None, f"unparsable output, exit {done.returncode}")
    found = [(row["startLine"], row.get("confidence")) for row in data.get("findings", [])]
    return Outcome(match_findings(case, found), wall, None, None, None)


TOOLS = {"jev-lint": jev_lint_outcome, "jevlint": jevlint_outcome}


def rows_for(tool: str, case: Case, outcome: Outcome, model: str) -> list[dict]:
    count = max(case.function_count, 1)
    return [
        {
            "tool": tool,
            "rule": case.rule_id,
            "function": unit.name,
            "label": unit.label,
            "verdict": "error" if outcome.error else ("violation" if unit.first_line in outcome.findings else "pass"),
            "confidence": outcome.findings.get(unit.first_line),
            "seconds": outcome.seconds / count,
            "invocation_seconds": outcome.seconds,
            "judgements_in_invocation": count,
            "input_tokens_per_judgement": None if outcome.input_tokens is None else outcome.input_tokens / count,
            "usd_per_judgement": None if outcome.usd is None else outcome.usd / count,
            "error": outcome.error,
            "model": model,
        }
        for unit in case.units
    ]


def summarize(tool: str, rows: list[dict]) -> str:
    scored = [row for row in rows if row["verdict"] != "error"]
    true_pos = sum(1 for r in scored if r["label"] == "violating" and r["verdict"] == "violation")
    false_pos = sum(1 for r in scored if r["label"] == "conforming" and r["verdict"] == "violation")
    false_neg = sum(1 for r in scored if r["label"] == "violating" and r["verdict"] == "pass")
    precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else float("nan")
    recall = true_pos / (true_pos + false_neg) if true_pos + false_neg else float("nan")
    seconds = sum(r["seconds"] for r in rows) / len(rows) if rows else float("nan")
    tokens = sum(r["input_tokens_per_judgement"] or 0 for r in rows)
    errors = len(rows) - len(scored)
    return (
        f"{tool:9} judgements={len(rows)} errors={errors} TP={true_pos} FP={false_pos} FN={false_neg} "
        f"precision={precision:.2f} recall={recall:.2f} sec/judgement={seconds:.2f} input_tokens={tokens:.0f}"
    )


def run_tool(tool: str, args: argparse.Namespace, log: Log) -> list[dict]:
    raw_dir = RESULTS_DIR / ("plan_raw" if args.plan else "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for case in load_cases():
        try:
            outcome = TOOLS[tool](case, args.work, raw_dir, log, args.plan)
        except Exception as error:
            log.write(f"{tool} {case.rule_id}: {error!r}")
            outcome = Outcome({}, 0.0, None, None, repr(error)[:300])
        rows += rows_for(tool, case, outcome, args.model)
    if not args.plan:
        (RESULTS_DIR / f"{tool.replace('-', '_')}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--plan", action="store_true", help="no model calls: validate rules and price with jev-lint --dry-run"
    )
    args = parser.parse_args()
    RESULTS_DIR.mkdir(exist_ok=True)
    log = Log(RESULTS_DIR / ("plan.log" if args.plan else "run.log"), args.work)
    log.write(f"== start model={args.model} jev-lint={JEV_LINT_VERSION} plan={args.plan}")
    failures = 0
    for tool in TOOLS:
        rows = run_tool(tool, args, log)
        print(f"{tool:9} planned judgements={len(rows)} (no model calls)" if args.plan else summarize(tool, rows))
        failures += sum(row["verdict"] == "error" for row in rows)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
