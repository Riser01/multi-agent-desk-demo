# Instructor runbook: Sunday 29 Nov (Build Hours)

## Minutes
| Build Hour 1 | Min | Build Hour 2 | Min |
|---|---|---|---|
| W7-0 baseline, you run it on screen | 5 | W7-4 supervisor + workers | 22 |
| W7-1 state + one agent node | 22 | W7-6 reviewer | 20 |
| W7-2 planner + executor | 25 | W7-7 cost meter + ceiling (Your turn); routing / prompt-hash *if time* | 18 |
| W7-3: demo 3 breaks (5), build (5), Your turn (8) | 18 | W7-8 compare.py shown + 5 min monitor/canary | 10 |
| buffer | 15 | buffer | 15 |

**Drop order when behind:** (1) W7-7 routing and prompt-hash experiments; (2) W7-6 build: show `docs/sample-runs/06a-reviewer-blocks-planted-note.txt` and its `.html` instead; (3) W7-8 live part: show `docs/sample-runs/08a-compare-offline.html`.

## Words to use
- The terminal approval question is a **blocking callback in the gate**. Do not call it "interrupt". LangGraph's `interrupt()` (pause, checkpointer, resume) is on the slides only.
- The team path (`--setup team`) has **no plan validation**; without `--review`, the gate and the human are the defence (`04b` shows the cost).
- Offline numbers are **estimates from a stand-in**; costs are **notional, at list price, 2026-11-24**; replays are **REPLAYED (scripted)**.

## Before class (rehearsal, 30 min, the day before)
1. Fresh clone into a new folder, Python 3.11+, venv, `pip install -r requirements.txt`, `python check.py`: provided 24 green, every phase "not built yet".
2. `cd solution`, `python check.py` (all green), `python check.py extras` (7 green).
3. Run every try-it in `GUIDE.md` from `solution/`; open `out/latest.html` and `out/compare.html` on the projector at a readable zoom.
4. Pre-open `docs/sample-runs/` in a file browser: it is the fallback for every step.

## Live-key checklist (owner, once, with your own key, before class)
Never on the projector; `.env` only.
```bash
python baseline.py "Archive the dentist task." --approve ask --live --record data/replays/live-baseline.json
```
```bash
python compare.py --live --runs 5 --scenarios S1,S2,S4
```
```bash
python agent.py "Delete the dentist task." --setup team --review --approve no --live --export langfuse
```
Unverified until you do this: the model names `gemini-3.5-flash-lite` and `gemini-2.5-flash-lite` have never been called live from this repo, and Langfuse export has only been tested against an unreachable host. If a name 404s, change `GEMINI_MODEL` and `ROUTING` in `solution/prod.py`, then tell learners.

## Safe-state reset (a learner's folder is broken)
Keep their work first, then restore the reference for the phase they are on:
Mac:
```bash
mkdir -p my-work && cp *.py my-work/
```
```bash
unzip -o checkpoints/after-W7-3.zip
```
Windows (Command Prompt): copy the `.py` files to a `my-work` folder in File Explorer, then `tar -xf checkpoints\after-W7-3.zip` (overwrites files). Then `python check.py`. Use `after-W7-1.zip`, `after-W7-2.zip`, `after-W7-3.zip` or `after-W7-4.zip` as fits. Each holds only the files and wiring up to that phase.

## Before showing extras/monitor.py
It reads every run in `logs/` and fires `ALERT stopped early` for earlier capped runs (the ceiling demo, a no-reducer fan-out). Clear `logs/` first (Mac `rm -rf logs`, Windows `rmdir /s /q logs`), make two or three fresh runs, then run it.

## When the coding agent fails
- **Out of quota / credits:** stop prompting. Copy the phase's files from `solution/` (`cp solution/state.py .`), run the check, and read the file aloud with the class: the docstring tells the story.
- **Agent drift** (edits tests or provided files, invents names, adds files): provided files and tests are tracked, so `git checkout -- <file>` restores them (ZIP users: re-download the ZIP and copy that one file back). Learner-built files are untracked: restore them by re-extracting the matching checkpoint (`unzip -o checkpoints/after-W7-N.zip`, Windows `tar -xf checkpoints\after-W7-N.zip`). Delete any extra files the agent made, then re-prompt with the exact "Ask your agent exactly this" block plus "Use exactly the names in docs/02-technical-spec.md".
- **Check stays red after two tries:** paste the spec section, then compare with `solution/`.

## The solution folder
The public repo ships `solution/` from the start (as in Week 6). `AGENTS.md` rule 11 tells coding agents not to read it until the learner asks. Say so at the start: "it is there for after two tries or after green".
