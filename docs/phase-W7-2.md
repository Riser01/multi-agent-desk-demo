# Phase W7-2: two agents, planner then executor, with a structured handoff (25 min)

## The concept
Split "decide what to do" from "do it". The **planner** reads the goal and the desk once and writes numbered steps, each naming one tool. It has no tools: it cannot change the desk even if fooled. The **executor** does one step per visit and sees only that step's **handoff**.

A handoff is not free text. It is a small checked record with four parts:
| Part | Here | Why |
|---|---|---|
| task | one action in plain words | the receiver does one thing |
| context | the desk lines it needs | not the whole history, not the goal |
| constraints | `use only the tool: add_task`, ... | rules travel with the work |
| return address | `finish` (W7-4: `supervisor`) | someone reads the result |

The executor's allow-list for a step is exactly the one tool the plan named (least privilege per step). Every action still goes through the gate. As Week 6 said: **a plan is a proposal, not a permission.**

## What you build
`handoff.py` (`Handoff`, `make_handoff`, `HandoffError`, `PlanStep`, `parse_plan`), `planner.py`, `executor.py`, and `build_two_agent` (+ `after_plan`, `after_step`) in `graph.py`.
Contract: `02-technical-spec.md` sections 5 (not the W7-3 parts), 6 (planner, executor), 7.

## Ask your agent exactly this
> Read `AGENTS.md` and `docs/02-technical-spec.md`. Build Phase W7-2 only: `handoff.py` (section 5 without the W7-3 caps and `validate_plan`), `planner.py` and `executor.py` (sections 6 and 7), and `after_plan`, `after_step`, `build_two_agent` in `graph.py`. Use the exact message formats of section 6. The executor's allow-list is `[step.tool]`. Make `python check.py 2` pass, then run `python check.py` to confirm W7-1 is still green. Never edit `tests/` or the provided files. If a function this phase asks for already exists (for example `build_team` from a checkpoint), keep it and only create what is missing.

## Check
```bash
python check.py 2
python check.py
```
```text
Phase W7-1  State and one agent node: all 12 green
Phase W7-2  Planner and executor: all 8 green
```

## Try it
```bash
python agent.py "Add File taxes, then show me my list." --setup two --approve no
```
What you should see (`sample-runs/02a-two-agent-add-and-list.txt`):
```text
INFO  ... [planner   ] plan    2 step(s) | 1. add_task: Add "File taxes"  (why: the user asked for it) | 2. list_tasks: show me my list ...
INFO  ... [planner   ] handoff planner -> executor (step 1 of 2): Add "File taxes"
INFO  ... [executor  ] saw     task: Add "File taxes" | context: | tasks: | 1: Mon 23 Nov: renew car insurance | ...
INFO  ... [executor  ] model   stand-in replied in 0.00s (205 in / 13 out tokens, est.): {"tool": "add_task", "args": {"text": "File taxes"}}
INFO  ... [run       ] run     ended: status=done after 3 model calls, 740 in / 64 out tokens (est.), 0.0s
```
Compare with W7-1: the same goal costs roughly 1.5 to 2 times fewer input tokens as planner + executor than as one agent with twelve tools, because the executor's menu is one line (exact numbers vary with wording; the recorded run shows one example). In `out/latest.html`, open the executor's "what it saw": no goal, no plan, one task.

## What you learn
- A handoff schema makes "what each agent sees" a design decision you can test.
- Least privilege can be per step, not just per agent.
- A plan is data you can check before anything happens (that is W7-3).

## Common mistakes
- Passing the whole goal or the whole plan to the executor ("just in case").
- Letting the executor pick any tool: then the plan is decoration.
- Building the handoff text by hand in several places instead of one `to_text()`.
