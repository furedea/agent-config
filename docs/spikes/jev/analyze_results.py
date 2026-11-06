"""Print per-rule confusion counts, misses, cost and disagreement from results/*.jsonl."""

import collections
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
TOOLS = ("jev_lint", "jevlint")


def load(tool: str) -> list[dict]:
    return [json.loads(line) for line in (RESULTS / f"{tool}.jsonl").read_text().splitlines()]


def per_rule(rows: list[dict]) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        flagged = row["verdict"] == "violation"
        bad = row["label"] == "violating"
        counts[row["rule"]][(0 if flagged else 1) if bad else (2 if flagged else 3)] += 1
    return counts


def main() -> None:
    data = {tool: load(tool) for tool in TOOLS}
    for tool, rows in data.items():
        print("==", tool)
        for rule, (tp, fn, fp, tn) in per_rule(rows).items():
            print(f"{rule:28} TP={tp} FN={fn} FP={fp} TN={tn}")
        print(
            "misses:",
            [(r["rule"], r["function"]) for r in rows if r["label"] == "violating" and r["verdict"] != "violation"],
        )
        print(
            "usd:",
            sum(r["usd_per_judgement"] or 0 for r in rows),
            "tokens:",
            sum(r["input_tokens_per_judgement"] or 0 for r in rows),
        )
        print("invocation seconds:", sorted({(r["rule"], round(r["invocation_seconds"], 2)) for r in rows}))
        print(
            "confidences of violations:",
            sorted(round(r["confidence"], 2) for r in rows if r["confidence"] is not None),
        )
    first, second = ({(r["rule"], r["function"]): r["verdict"] for r in data[t]} for t in TOOLS)
    print("disagree:", [key for key in first if first[key] != second[key]])


main()


def raw_totals() -> None:
    spent = [json.loads(path.read_text()) for path in sorted((RESULTS / "raw").glob("jev_lint_*.json"))]
    print("jev-lint raw spent: subjects", sum(d["stats"]["subjects"] for d in spent), "calls", sum(d["spent"]["calls"] for d in spent))
    print("input tokens", sum(d["spent"]["inputTokens"] for d in spent), "output tokens", sum(d["spent"]["outputTokens"] for d in spent))
    print("usd", sum(d["spent"]["usd"] for d in spent), "elapsed ms", sum(d["elapsedMs"] for d in spent))
    other = [json.loads(path.read_text()) for path in sorted((RESULTS / "raw").glob("jevlint_*.json"))]
    print("jevlint evaluations", sum(d["evaluations"] for d in other), "code units", sum(d["codeUnits"] for d in other))


raw_totals()
