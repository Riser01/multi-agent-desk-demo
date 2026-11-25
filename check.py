"""Scoreboard for Desk Assistant v2: 4 crisp behavioral phase checks + provided CLI checks. PROVIDED.

Usage:
    python check.py                 run provided checks + all 4 phases (+ the optional AM-2 Your turn line)
    python check.py 0               Setup: provided files only
    python check.py 1               AM-1 (two_agent.py)
    python check.py 2               AM-2 (safety.py, main contract)
    python check.py 2 your-turn     AM-2 Your turn exercise (duplicate-step rule in safety.py)
    python check.py 3               PM-1a/PM-1b (team.py)
    python check.py 4               PM-2 (prod.py)
    python check.py stretch         optional stretch (stretch.py: real LangGraph interrupt() approval gate)

Phases you have not built yet say "not built yet". That is expected, not a failure of your earlier work.
"""
import importlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]

PHASES = [
    ("1", "AM-1  Two-agent planner + executor (two_agent.py)", "test_phase1", [("two_agent", "run_two_agent")]),
    ("2", "AM-2  Handoff caps + plan check (safety.py)", "test_phase2", [("safety", "validate_plan"), ("safety", "cap_context")]),
    ("3", "PM-1  Supervisor, workers + reviewer (team.py)", "test_phase3", [("team", "run_team"), ("team", "reviewer_node")]),
    ("4", "PM-2  Cost meter, routing + version stamp (prod.py)", "test_phase4", [("prod", "CostMeter"), ("prod", "version_stamp")]),
]
# Optional extras: reported by name, never part of the all-green total of the 4 phases.
YOUR_TURN = ("2y", "AM-2  Your turn: duplicate-step rule (optional exercise)", "test_phase2_yourturn", [("safety", "validate_plan")])
STRETCH = ("stretch", "Stretch  interrupt() approval gate (stretch.py, optional)", "test_stretch", [("stretch", "build_gate_graph")])


def _run_suite(label: str, module_name: str) -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromName(module_name)
    result = unittest.TestResult()
    suite.run(result)
    total = result.testsRun
    bad = result.failures + result.errors
    if not bad:
        print(f"{label}: all {total} green")
        return True
    print(f"{label}: {total - len(bad)} of {total} green")
    for test, tb in bad:
        doc = (test.shortDescription() or test.id()).strip()
        last = [l for l in tb.strip().splitlines() if l.strip()][-1]
        print(f"    requirement: {doc}")
        print(f"        what happened: {last[:240]}")
    return False


def _missing(needs: list) -> "str | None":
    for mod_name, attr in needs:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError as err:
            if (err.name or "").split(".")[0] == "langgraph":
                return "LangGraph is not installed. Run: pip install -r requirements.txt"
            return f"not built yet ({mod_name}.py does not exist)"
        if not hasattr(mod, attr):
            return f"not built yet ({mod_name}.{attr} missing)"
    return None


def _phase(label: str, mod: str, needs: list) -> bool:
    miss = _missing(needs)
    if miss:
        print(f"{label}: {miss}")
        return False
    return _run_suite(label, mod)


def main(argv: list) -> int:
    words = [a.lower().strip() for a in argv]
    want = "-".join(words) if words else "all"
    want = {"2-your-turn": "2y", "2-yourturn": "2y", "your-turn": "2y"}.get(want, want)
    valid = {"all", "0", "1", "2", "2y", "3", "4", "stretch"}
    if want not in valid:
        print("Usage: python check.py [0|1|2|2 your-turn|3|4|stretch]")
        return 2
    results = []
    if want in ("all", "0"):
        results.append(_run_suite("Setup  provided CLI, desk, sessions & todo-list.md", "test_provided"))
    for key, label, mod, needs in PHASES:
        if want in ("all", key):
            results.append(_phase(label, mod, needs))
    if want == "all" and not _missing(YOUR_TURN[3]):
        _phase(YOUR_TURN[1], YOUR_TURN[2], YOUR_TURN[3])   # shown for information; optional, so not counted
    if want == "2y":
        results.append(_phase(YOUR_TURN[1], YOUR_TURN[2], YOUR_TURN[3]))
    if want == "stretch":
        results.append(_phase(STRETCH[1], STRETCH[2], STRETCH[3]))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
