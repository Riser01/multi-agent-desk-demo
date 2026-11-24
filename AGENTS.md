# Rules for any coding agent working in this folder

You are helping a learner turn a one-agent Desk Assistant into a small team of agents with LangGraph. These rules apply whatever coding agent you are.

1. **One phase at a time.** Build only the phase you were asked for (W7-1, W7-2, W7-3, W7-4, W7-6, W7-7). Do not add anything from a later phase, even if it looks useful.
2. **Only these files are yours to create or edit:** `state.py`, `handoff.py`, `planner.py`, `executor.py`, `supervisor.py`, `workers.py`, `reviewer.py`, `prod.py`, `graph.py`. **No other new files**: no helper modules, no extra folders, no config files, no `__init__.py`.
3. **Use exactly the names, signatures, state keys, message formats and statuses in `docs/02-technical-spec.md`.** Do not rename, paraphrase or redesign the contract. If the spec and your habits disagree, the spec wins. The tests read those exact names.
4. **Read-only files.** Never edit `tests/`, `check.py`, `docs/`, `data/`, `extras/`, or the provided files `agent.py`, `config.py`, `llm.py`, `stand_in.py`, `desk_tools.py`, `gate.py`, `obs.py`, `baseline.py`, `compare.py`. If a test seems wrong, tell the learner; do not change it.
5. **Dependencies:** standard library plus `langgraph==1.2.23` (in `requirements.txt`). Do not add packages. Do not use `langgraph-supervisor` or `langchain` agents: the supervisor is hand-written on purpose.
6. **Every action on the desk goes through `Team.act` (which calls `gate.run_tool`).** Never call a tool's `run` directly, never bypass the gate, never retry a write.
7. **Always pass an explicit `recursion_limit`** when running a graph (LangGraph 1.2.23's default is 10,007). Use `run_graph` from the spec.
8. **No live model calls while building.** Run checks and try-it commands offline (the default). Never add `--live` yourself; that spends the learner's quota.
9. **Comment standard (checked by `python check.py style`):** every file opens with a short story in plain prose (what the file is; why the team needs it and what goes wrong without it; what to look at, naming the key functions); every function and class has a one-line docstring; inline comments explain *why* (what a rule protects), not *what*. No change-log words ("now", "fixed"), no local paths, no secrets. See `docs/02-technical-spec.md` section 11.
10. **Use `python` (not `python3`) with the project's `.venv` turned on, on Mac and Windows.** Run `python check.py N` until it is green, then `python check.py` to make sure earlier phases are still green. Report the actual output, not a guess.
11. **Do not open `solution/` on your own.** Build from `docs/` first. Open a file in `solution/` only when the learner asks you to (after two failed tries, or after the phase is green), and never copy it in wholesale.
12. **Never read, print or ask for a key.** Keys live only in `.env`. Never open `.env`.
13. Keep it small and plain. A reader who is not a programmer should be able to follow each function.
