# Multi-Agent Desk Demo (v2)

Turn Week 6's single Desk Assistant into a multi-agent team using **LangGraph** and a **coding agent** (we use Cursor;
Claude Code, Copilot or Windsurf work too), then test it live in an **interactive terminal chat** with a real
**`todo-list.md`** file and **`sessions/`** save/resume. You direct the coding agent; nobody hand-types code.

> **Split only when you must, and pay for it knowingly.**

**No API key required.** Everything runs offline with a built-in stand-in model by default (deterministic, free, and
deliberately gullible on the `/drill` attack so you can watch your safety code work). The stand-in is **not a real
model**: every log, `logs/runs.jsonl` row and `out/latest.html` says `offline stand-in (not a real model)`, its token
counts are estimates, and every cost is notional (list price). Pass `--live` with your own free Gemini key in `.env`
for real model calls (a free key allows only a few live runs a day: see `GUIDE.md` Step 8).

**Needs Python 3.11 or newer** and one package: `langgraph==1.2.23`.

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows cmd: py -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python check.py 0                                    # Setup: all 14 green
python app.py                                        # Launch interactive chat (built-in single agent)
```
New to terminals, git or Python? Follow [`GUIDE.md`](GUIDE.md) from Step 1 (Mac and Windows, from zero).
Open **`todo-list.md`** side-by-side in your editor and watch tasks, events, and notes update live after every turn.
Quit anytime (`/quit` or Ctrl+C) — your session auto-saves to `sessions/` and revives with `python app.py --resume latest`.

## The 4 phases (Sunday 29 Nov)
| Phase | Session | You build | What you learn | Check |
|---|---|---|---|---|
| **AM-1** | Morning | `two_agent.py` | Planner (no tools) -> structured handoff -> Executor + delete gate; 1 model call | `python check.py 1` (5) |
| **AM-2** | Morning | `safety.py` | Huge-note `/drill`, context cap (`600` chars), `validate_plan()`; Your turn: duplicate-step rule | `python check.py 2` (5), `python check.py 2 your-turn` (2) |
| **PM-1a / 1b** | Afternoon | `team.py` | Supervisor + 2 least-privilege workers (Part A), then bounded Reviewer (Part B); 5 to 7 calls | `python check.py 3` (9) |
| **PM-2** | Afternoon | `prod.py` | Cost meter, model routing, version stamp + `/rollback`, `/ceiling`, `/compare`, `/monitor` | `python check.py 4` (5) |
| *Stretch* | Optional | `stretch.py` | A real LangGraph `interrupt()` approval gate with a checkpointer | `python check.py stretch` (5) |

Behind? `checkpoints/after-AM.zip` (two_agent + safety) and `checkpoints/after-PM1.zip` (+ team) let you join the
next phase cleanly; see GUIDE.md.

## Provided files (do not edit)
- `app.py` — interactive terminal chat, built-in `single` baseline, slash commands (`/setup`, `/review`, `/ceiling`, `/rollback`, `/drill`, `/compare`, `/monitor`, `/export`, `/save`, `/load`, `/reset`), `logs/latest.log`, `logs/runs.jsonl`, `out/latest.html`.
- `desk.py` — the Desk (tasks, calendar, notes), 8 tools, blocking `[y/N]` delete approval gate, live `todo-list.md`, and `sessions/` persistence (validated on load; Windows-reserved names such as `con` or `nul` are refused).
- `llm.py` — offline stand-in default + opt-in `--live` Gemini adapter with 429 backoff and per-turn call cap, plus the optional trace export.
- `check.py` + `tests/` — behavioural scoreboard (Setup 14, AM-1 5, AM-2 5 + 2 Your turn, PM-1 9, PM-2 5, stretch 5).

## Optional: trace export (console or Langfuse)
`python app.py ... --export console` prints a tree of every model call, tool request and `[y/N]` answer after each
turn. `--export langfuse` sends the same spans to **your own free Langfuse account** (keys in `.env`, see
`.env.example`; `pip install langfuse==5.2.0`, Python 3.11+); without keys or the package it falls back to the console
tree. Toy tasks only: prompts leave your machine. Not yet verified against a real Langfuse server as of 2026-11-25.

*Honest note:* Approval is a blocking terminal callback (`[y/N]`), and `sessions/` saves your Desk and an audit-only turn log **between turns** as JSON — neither is LangGraph's mid-turn `interrupt()` checkpointer (covered on Saturday's slides, and built in the optional `docs/stretch.md`).

Start with [`GUIDE.md`](GUIDE.md). Want to inspect or build the entire project from specs alone? Start with [`docs/00-foundation.md`](docs/00-foundation.md) followed by `docs/AM-1.md`..`PM-2.md`. Non-coders / watch-only learners: open [`docs/predict-sheet.md`](docs/predict-sheet.md).
