# Multi-Agent Desk Demo: turn one agent into a team, and measure whether it was worth it

Last week you built the **Desk Assistant**: a to-do agent with a loop, tools, an approval gate for deletes, limits and a trace. This week it has grown a calendar and twelve tools, and one agent with twelve look-alike tools in one long prompt starts to struggle. You will split it into a **team** (a planner and an executor, then a supervisor with two specialist workers and a reviewer) using **LangGraph**, with **any coding agent** (Claude Code, Cursor, Copilot, Windsurf...). You do not type the code yourself: you read a short spec, ask your agent well, and check the result with a scoreboard.

> **Split only when you must, and pay for it knowingly.** More agents means more calls, more tokens and more places to fail. It also means smaller prompts, fewer tools per agent and more places to stop a bad action. This repo lets you see both sides in numbers.

**No key needed to build.** Every run uses an offline **stand-in** model by default (rule-based, labelled in every log and report, deliberately gullible so you can watch the safety parts work). A free Gemini key is only for `--live` runs.

## Start here
Repo: https://github.com/Riser01/multi-agent-desk-demo (if the link shows 404, ask your instructor for the ZIP or the current link).

1. [`GUIDE.md`](GUIDE.md): from zero (git, Python, a coding agent) to every phase, with the exact prompt, commands and expected output.
2. [`docs/00-overview.md`](docs/00-overview.md): the picture, the phase map, and what the logs and the HTML report show.
3. [`AGENTS.md`](AGENTS.md): the rules your coding agent follows. Its first message must be "Read AGENTS.md first and follow it."

## The phases (Sunday 29 Nov)
| Phase | Session | You build | Concept | Check |
|---|---|---|---|---|
| W7-0 | AM, 5 min | nothing (`baseline.py` is provided) | why one agent with twelve tools struggles | `python baseline.py ...` |
| W7-1 | AM | `state.py`, `graph.py` | shared state with reducers, one agent as a graph node | `python check.py 1` |
| W7-2 | AM | `handoff.py`, `planner.py`, `executor.py` | two agents, a structured handoff | `python check.py 2` |
| W7-3 | AM | caps and `validate_plan` in `handoff.py` | break the handoff on purpose, then cap it. **Your turn:** one rule | `python check.py 3` |
| W7-4 | PM | `supervisor.py`, `workers.py` | supervisor + specialists, what each agent sees | `python check.py 4` |
| W7-6 | PM | `reviewer.py` | a reviewer on risky actions, max two rounds | `python check.py 6` |
| W7-7 | PM | `prod.py` | cost meter, model routing, version stamp. **Your turn:** a cost ceiling | `python check.py 7` |
| W7-8 | PM, shown | nothing (`compare.py` is provided) | the honest comparison and the launch checklist | `python compare.py` |
| stretch | any time | read and run `extras/` | W7-5 parallel `Send`; canary and rollback; monitoring | `python check.py extras` |

## Two things to know before you start
- **Approval is a blocking question, not LangGraph `interrupt()`.** When an irreversible action needs a yes, the gate asks in the terminal and waits. There is no pause-and-resume and no checkpointer here; `interrupt()` is covered on the slides.
- **The team path has no plan check.** The planner/executor path (W7-3) rejects a planted-note delete at the plan. The supervisor team has no plan: without `--review`, the gate and the human are the only defence. W7-6 adds the reviewer.

## What every run leaves behind
- **Terminal:** one `INFO` / `WARN` / `ERROR` line per step: what each agent saw, each model reply with time and tokens, each handoff, tool call and gate decision.
- **`logs/latest.log`** (and `logs/latest.jsonl`, one JSON event per line), plus a timestamped copy per run.
- **`out/latest.html`**: open it in a browser. A timeline of agents and handoffs with "what each agent saw", tokens, notional cost, time, the version stamp and the final desk.
- **Optional Langfuse:** `--export langfuse` draws the run as nested spans (run > agent > model / tool / gate). Without keys, `--export console` prints the same tree.

## How to check your work
```bash
python check.py
```
One plain line per phase. Unbuilt phases say "not built yet". A failing test prints `Phase W7-N, requirement: ...` first. **Passing the check is the grade.** `python check.py 2` checks one phase, `python check.py style` checks the comment standard.

## The two-failures rule
1. Paste the failing `requirement:` line into your coding agent and say **"fix only this"**.
2. After **two** failed tries, paste the phase's section from `docs/02-technical-spec.md`.
3. Still stuck? Compare with the matching file in `solution/`. Never edit `tests/`.

## What is in this repo
| Path | What it is |
|---|---|
| `docs/` | the specs: overview, product, technical contract, one page per phase, edge cases, harness map, launch checklist, predict sheet, recorded runs |
| `config.py`, `llm.py`, `stand_in.py`, `desk_tools.py`, `gate.py`, `obs.py` | provided: keys, model seam (fake / replay / live, call cap, backoff), the offline stand-in, the desk and its twelve tools, last week's gate, logging and the HTML report |
| `agent.py`, `baseline.py`, `compare.py` | provided: the command you run every phase, the W7-0 single agent, the W7-8 comparison |
| `check.py`, `tests/` | the scoreboard and its tests (fake models, deterministic). Do not edit |
| `data/` | seed desks, scenarios, regression cases, replay files, list prices (dated) |
| `extras/` | stretch: parallel fan-out, canary and rollback, monitoring |
| `solution/` | the finished reference, every file opening with a short story |
| you build | `state.py handoff.py planner.py executor.py supervisor.py workers.py reviewer.py prod.py graph.py` |
| `checkpoints/` | join-here zips: the learner files and wiring up to W7-1, W7-2, W7-3 or W7-4, for anyone who fell behind |

Python 3.11 or newer. Dependencies: `langgraph==1.2.23` (and `google-genai` for live runs only). Keys live only in a git-ignored `.env`; no key appears anywhere in this repo.

## Honest numbers

Not yet verified against the real services (as of 2026-11-24): the `--live` Gemini path and the routing model names (`gemini-3.5-flash-lite`, `gemini-2.5-flash-lite`), and `--export langfuse` against a real Langfuse server. Everything else here ran offline with the labelled stand-in.
Offline runs show the **shape** of the trade (how many calls, how big each prompt) with estimated tokens (characters / 4). Cost is always **notional, at list price** on the date in `data/prices.json`: the free tier costs nothing. Real token counts come only from `--live`. Replayed runs are labelled **REPLAYED**; the two replay files shipped here were written by hand to show a failure shape and say so.
