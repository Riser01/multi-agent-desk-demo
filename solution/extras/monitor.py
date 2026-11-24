"""W7-7c (stretch): monitoring after launch: a sampled-review file, alert rules, and failures turned into test cases.

A launched agent is not finished; it is watched. Three habits, each a few lines here, all reading the logs/*.jsonl
files every run already writes:

    sampled review   a person reads a fixed share of runs every week. sample() picks them deterministically (by a
                     hash of the run name, so a re-run picks the same ones) and writes out/sampled-review.md: per
                     run the goal, status, answer and actions, with the questions a reviewer should answer.
    alert rules      a few rules that matter, not a hundred that do not: a cost spike, a high denial rate, runs that
                     stopped early. ALERTS holds them as plain functions; each prints one ALERT line when it fires.
    failure -> test  a run that went wrong becomes a regression case in data/regression/, in the same format as the
                     scenarios, so it is checked forever after (compare.py and the tests read that folder).

Run:  python extras/monitor.py                       review sample + alerts over logs/
      python extras/monitor.py --to-regression logs/latest.jsonl --check "task_exists:Pay rent"
"""
import argparse
import glob
import hashlib
import json
import os
import re
import statistics
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read_run(path: str) -> dict:
    """One .jsonl run file as {"header": ..., "events": [...]}."""
    with open(path, encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    return {"path": path, "header": lines[0], "events": lines[1:]}


def load_runs(folder: str) -> list[dict]:
    """Every run in a logs folder (the latest.jsonl copy is skipped, it repeats one run)."""
    return [read_run(p) for p in sorted(glob.glob(os.path.join(folder, "run-*.jsonl")))]


def sample(runs: list[dict], share: float) -> list[dict]:
    """A deterministic sample: a run is picked when the hash of its file name falls under the share."""
    return [r for r in runs if int(hashlib.sha256(os.path.basename(r["path"]).encode()).hexdigest(), 16) % 1000 < share * 1000]


def review_file(runs: list[dict]) -> str:
    """The sampled-review markdown: one section per run with the questions a person should answer."""
    parts = ["# Sampled review", "", f"{len(runs)} run(s). For each: was the answer true? Did any action happen that the user did not ask for?", ""]
    for r in runs:
        head, result = r["header"], r["header"].get("result") or {}
        actions = [e["text"] for e in r["events"] if e["kind"] in ("tool", "gate", "review")]
        parts += [f"## {os.path.basename(r['path'])}", f"- goal: {head.get('goal')}", f"- status: {result.get('status')}",
                  f"- answer: {result.get('answer')}", "- actions:", *[f"  - {a[:160]}" for a in actions],
                  "- [ ] answer matches the desk   - [ ] no unasked action   - [ ] would you ship this run?", ""]
    return "\n".join(parts)


def _cost(run: dict) -> float:
    """The run's notional cost from its last cost event (0 when it was not metered)."""
    costs = [e.get("total_usd", 0.0) for e in run["events"] if e["kind"] == "cost"]
    return costs[-1] if costs else 0.0


def _gates(run: dict) -> "tuple[int, int]":
    """(denied, asked) gate decisions in a run."""
    gates = [e for e in run["events"] if e["kind"] == "gate"]
    return sum(e.get("decision") == "denied" for e in gates), len(gates)


ALERTS = [  # name, rule(run, all runs) -> True when it fires, what to do
    ("cost spike", lambda r, runs: _cost(r) > 3 * (statistics.median([_cost(x) for x in runs]) or float("inf")),
     "a run cost over 3x the median: look for a loop or a huge input"),
    ("denial rate", lambda r, runs: _gates(r)[1] >= 2 and _gates(r)[0] / _gates(r)[1] > 0.5,
     "most gate questions were refused: the agent keeps asking for things people do not want"),
    ("stopped early", lambda r, runs: (r["header"].get("result") or {}).get("status") not in ("done", "done-with-denials"),
     "the run hit a cap or an error: read its log"),
]


def alerts(runs: list[dict]) -> list[str]:
    """Every alert line that fires over these runs."""
    lines = []
    for run in runs:
        for name, rule, advice in ALERTS:
            if rule(run, runs):
                lines.append(f"ALERT {name}: {os.path.basename(run['path'])}: {advice}")
    return lines


def to_regression(run_path: str, checks: list[str], folder: str) -> str:
    """Turn one run into a regression case file in data/regression/. checks are 'type:text', e.g. 'task_exists:Pay rent'."""
    head = read_run(run_path)["header"]
    meta = head.get("meta") or {}
    seed = os.path.splitext(os.path.basename(meta.get("seed", "desk_week.json")))[0]
    existing = glob.glob(os.path.join(folder, "R*.json"))
    number = 1 + max([int(re.match(r"R(\d+)", os.path.basename(p)).group(1)) for p in existing] or [0])
    slug = re.sub(r"[^a-z0-9]+", "-", head.get("goal", "case").lower()).strip("-")[:40]
    case = {"id": f"R{number}", "title": f"Regression from {os.path.basename(run_path)}", "goal": head.get("goal"),
            "seed": seed, "approve": meta.get("approve", "no") if meta.get("approve") in ("yes", "no") else "no",
            "from_run": os.path.basename(run_path),
            "checks": [{"type": c.split(":", 1)[0], "text": c.split(":", 1)[1]} for c in checks]}
    path = os.path.join(folder, f"R{number}-{slug}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(case, handle, indent=1)
    return path


def main(argv=None, root: str = ROOT, out=print) -> int:
    """Write the review sample and print alerts, or turn one run into a regression case."""
    parser = argparse.ArgumentParser(description="Sampled review, alerts and regression cases from logs/.")
    parser.add_argument("--share", type=float, default=0.2, help="share of runs to sample for human review")
    parser.add_argument("--to-regression", help="a run's .jsonl file to turn into a regression case")
    parser.add_argument("--check", action="append", default=[], help="'type:text', e.g. task_exists:Pay rent (repeatable)")
    args = parser.parse_args(argv)
    if args.to_regression:
        if not args.check:
            out("add at least one --check, e.g. --check \"task_exists:Pay rent\"")
            return 2
        path = to_regression(args.to_regression, args.check, os.path.join(root, "data", "regression"))
        out(f"regression case written: {os.path.relpath(path, root)}")
        return 0
    runs = load_runs(os.path.join(root, "logs"))
    if not runs:
        out("no runs in logs/ yet: run agent.py a few times first")
        return 1
    picked = sample(runs, args.share) or runs[-1:]
    os.makedirs(os.path.join(root, "out"), exist_ok=True)
    with open(os.path.join(root, "out", "sampled-review.md"), "w", encoding="utf-8") as handle:
        handle.write(review_file(picked))
    out(f"sampled {len(picked)} of {len(runs)} run(s) for review: out/sampled-review.md")
    fired = alerts(runs)
    for line in fired:
        out(line)
    out(f"{len(fired)} alert(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
