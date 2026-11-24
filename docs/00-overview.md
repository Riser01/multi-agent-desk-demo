# Overview: from one agent to a team, and how to know it worked

## The story
Week 6 built the Desk Assistant: a model plus a harness (loop, tools, context, memory, gates, verify, trace). It has grown a calendar and twelve tools. One agent with twelve look-alike tools pays for the whole menu on every call and must pick the right look-alike every time (W7-0). So we split it, in two steps, and measure each step.

```text
W7-1  one agent node            START -> agent (loops) -> finish
W7-2  planner -> executor       START -> planner -> executor (one step per visit) -> finish
W7-4  supervisor + specialists  START -> supervisor -(Command)-> tasks | calendar -> supervisor ... -> finish
W7-6  + reviewer                worker -(irreversible)-> reviewer -> act (human gate) | worker (retry) | supervisor
```

## Minutes (Sunday 29 Nov)
| Build Hour 1 (morning) | Min | | Build Hour 2 (afternoon) | Min |
|---|---|---|---|---|
| W7-0 baseline (run only) | 5 | | W7-4 supervisor + workers | 22 |
| W7-1 state + one agent node | 22 | | W7-6 reviewer | 20 |
| W7-2 planner + executor | 25 | | W7-7 cost meter + ceiling (Your turn); routing and prompt-hash experiments *if time* | 18 |
| W7-3 caps + validation (Your turn 8) | 18 | | W7-8 comparison, shown, incl. 5 min of `extras/monitor.py` and `extras/canary.py` | 10 |
| **buffer** | **15** | | **buffer** | **15** |

*If time* items can be dropped without breaking anything later. Drop order when behind: W7-7 routing experiments, then W7-6 (show the recorded run instead). Behind as a learner: the join-here blocks in `GUIDE.md` and `checkpoints/`.

## How a human approves
The gate asks in the terminal and waits for `y` or `n`: a plain blocking callback. It is **not** LangGraph's `interrupt()` (pause, checkpoint, resume), which is on the slides but not used here, so no checkpointer is needed.

## Three layers (keep them apart)
| Layer | What it is | Files |
|---|---|---|
| **Team** (you build) | who does what, what each agent sees, how they hand off, the caps | `state.py handoff.py planner.py executor.py supervisor.py workers.py reviewer.py prod.py graph.py` |
| **Desk + gate** (last week's output, provided) | the twelve tools, risk tiers, the human approval gate, truncation | `desk_tools.py gate.py` |
| **Plumbing** (provided) | model seam (fake / replay / live), the offline stand-in, logging and the report | `agent.py llm.py stand_in.py obs.py config.py` |

## The phase map
| Phase | You build | Pattern / concept | Check |
|---|---|---|---|
| W7-0 | nothing | the single-agent baseline | `python baseline.py ...` |
| W7-1 | `state.py`, `graph.py` | state + reducers, one agent node, caps | `python check.py 1` |
| W7-2 | `handoff.py`, `planner.py`, `executor.py` | planner / executor, structured handoff | `python check.py 2` |
| W7-3 | caps + `validate_plan` | break the handoff, cap it | `python check.py 3` |
| W7-4 | `supervisor.py`, `workers.py` | supervisor (router), specialists, what each sees | `python check.py 4` |
| W7-5 | stretch, `extras/fanout.py` | parallel workers, `Send`, reducer | `python check.py extras` |
| W7-6 | `reviewer.py` | reviewer (critic), round cap as an edge | `python check.py 6` |
| W7-7 | `prod.py` | cost per task, ceiling, routing, version stamp | `python check.py 7` |
| W7-8 | nothing | the comparison, the launch checklist | `python compare.py` |

## What every run shows you
- **Terminal:** `INFO` / `WARN` / `ERROR` lines, one per event: `saw` (the exact message an agent got), `model` (reply, seconds, tokens), `handoff`, `route`, `plan`, `tool`, `gate`, `review`, `cap`, `cost`.
- **`logs/latest.log`** and **`logs/latest.jsonl`** (and a timestamped copy of each).
- **`out/latest.html`**: open it in a browser. Totals, per-agent calls and tokens, the timeline with every handoff and "what it saw" (click to expand), the final desk, the version stamp.
- **`--export console`** prints the trace tree; **`--export langfuse`** sends it to Langfuse (optional).

## Fake, replayed, live
| Mode | Flag | What answers | Use |
|---|---|---|---|
| fake (default) | none | `stand_in.py`: rule-based, deliberately gullible, free | building, class, the checks' try-its |
| replay | `--mode replay --replay FILE` | a saved file, labelled REPLAYED (scripted or recorded) | showing a known failure shape; re-running a recorded live run |
| live | `--live` | Gemini with your key; per-run call cap, waits out 429 | the only real evidence about a model |

The tests use `FakeModel` (exact scripted replies), so `check.py` gives the same result every time. **Passing `python check.py N` is the grade for phase N.**
