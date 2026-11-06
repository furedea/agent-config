"""Score both tools on every judged function from results/raw and results/run.log.

Every function in an example file is a judged unit. Functions named under "violating" in labels.json
are positives; every other function (including methods of the value objects) is a negative. Time is
reported two ways: the tool's own figure where it gives one, and the process wall time from run.log
(for jev-lint that includes the `nix shell` and `npx` start-up).
"""

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

SPIKE = Path(__file__).resolve().parent
RAW = SPIKE / "results" / "raw"


@dataclass(frozen=True)
class Unit:
    name: str
    line: int
    is_violating: bool


def units_of(spec: dict) -> list[Unit]:
    tree = ast.parse((SPIKE / "examples" / spec["file"]).read_text())
    return [
        Unit(node.name, node.lineno, node.name in spec["violating"])
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]


def flagged_lines(tool: str, rule: str) -> set[int]:
    data = json.loads((RAW / f"{tool}_{rule.replace('-', '_')}.json").read_text())
    key = "line" if tool == "jev_lint" else "startLine"
    return {row[key] for row in data["findings"]}


def wall_seconds() -> dict[tuple[str, str], float]:
    """Process wall time per (tool, example file name), read from run.log."""
    walls: dict[tuple[str, str], float] = {}
    pending: tuple[str, str] | None = None
    for line in (SPIKE / "results" / "run.log").read_text().splitlines():
        if line.startswith("$ ") and (match := re.search(r"(\w+\.py)", line)):
            pending = ("jev_lint" if "jev-lint@" in line else "jevlint", match.group(1))
        elif line.startswith("exit=") and pending:
            walls[pending] = float(re.search(r"wall=([\d.]+)s", line).group(1))
            pending = None
    return walls


def score(tool: str, labels: dict) -> dict:
    counts = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    false_positives: list[str] = []
    misses: list[str] = []
    for rule, spec in labels.items():
        flagged = flagged_lines(tool, rule)
        for unit in units_of(spec):
            hit = unit.line in flagged
            counts[("tp" if hit else "fn") if unit.is_violating else ("fp" if hit else "tn")] += 1
            if hit and not unit.is_violating:
                false_positives.append(f"{rule}:{unit.name}")
            if unit.is_violating and not hit:
                misses.append(f"{rule}:{unit.name}")
    return {**counts, "false_positives": false_positives, "misses": misses}


def report(tool: str, labels: dict) -> None:
    result = score(tool, labels)
    judged = sum(result[k] for k in ("tp", "fn", "fp", "tn"))
    precision = result["tp"] / (result["tp"] + result["fp"])
    recall = result["tp"] / (result["tp"] + result["fn"])
    walls = wall_seconds()
    wall_total = sum(w for (name, _), w in walls.items() if name == tool)
    print(f"== {tool}: judged={judged} TP={result['tp']} FN={result['fn']} FP={result['fp']} TN={result['tn']}")
    print(f"   precision={precision:.2f} recall={recall:.2f}")
    print(f"   false positives: {result['false_positives']}")
    print(f"   misses: {result['misses']}")
    print(f"   process wall total={wall_total:.2f}s per judgement={wall_total / judged:.3f}s")
    if tool == "jev_lint":
        spent = [json.loads(p.read_text()) for p in sorted(RAW.glob("jev_lint_*.json"))]
        print(f"   self-reported elapsed={sum(d['elapsedMs'] for d in spent) / 1000:.2f}s", end=" ")
        print(f"per judgement={sum(d['elapsedMs'] for d in spent) / 1000 / judged:.3f}s")
        tokens_in = sum(d["spent"]["inputTokens"] for d in spent)
        tokens_out = sum(d["spent"]["outputTokens"] for d in spent)
        usd = sum(d["spent"]["usd"] for d in spent)
        print(f"   tokens in={tokens_in} out={tokens_out} usd={usd:.6f} per judgement usd={usd / judged:.7f}")


def main() -> None:
    labels = json.loads((SPIKE / "labels.json").read_text())
    for tool in ("jev_lint", "jevlint"):
        report(tool, labels)


main()
