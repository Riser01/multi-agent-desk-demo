# Phase AM-1 Spec: Two-Agent Planner + Executor (`two_agent.py`)

Build `two_agent.py` using LangGraph (`StateGraph`, `START`, `END`). About 30 minutes.

**What you learn:** splitting "decide" from "do". The planner has no tools, so whatever it reads it can only *write a
plan*. The executor makes no model call; it runs the plan through the same `[y/N]` delete gate as Week 6.

## Contract
Export one function:
```python
run_two_agent(goal, desk, model, approve, *, meter=None, routing=None, log_fn=None) -> dict
```
Returns `{"status": ..., "answer": ..., "plan": ..., "results": ...}`.
*(Tip: `import desk as desk_mod` so the `desk` parameter does not shadow the `desk` module.)*

## Behavior
1. **Planner node (`planner`):** Has **NO tools**. Build `user = f"Goal: {goal}\n\nContext notes:\n{notes_text}"` (line 0 must hold the goal so the offline stand-in parses it cleanly), call `data, _reply = llm.ask_json("planner", PLANNER_PROMPT, user, model, meter=meter, routing=routing, log_fn=log_fn)` (note: `ask_json` returns a `(dict, Reply)` tuple), and read the steps (`[{"task", "tool", "args"}]`).
   - **Guard a malformed plan** (a live model can return `"steps"` as a string, or a step without a tool name): keep only steps that are dicts with a string `"tool"`; use `{}` when `"args"` is not a dict. Bad steps are dropped with a `WARN` log line. This must work even before `safety.py` exists.
2. **Optional AM-2 safety hook:** Try `import safety`. If `safety` exists:
   - Call `notes_text, was_cut = safety.cap_context(notes_text)` (returns a `(str, bool)` tuple!) before sending notes to the planner. Call it as `safety.cap_context(...)` (not `from safety import ...`) so the check can see it.
   - Call `safety.validate_plan(steps, goal)` right after the planner responds; if it returns any reasons, stop with `status="plan-rejected"` and `answer="; ".join(reasons)` so the executor runs nothing.
3. **Executor node (`executor`):** Runs each step in `plan` through `res = desk.run_tool(tool, args, desk, allowed=desk.ALL_TOOLS, approve=approve, actor="executor")` (returns `ToolResult(kind, text)`). Every delete/cancel still passes the blocking `[y/N]` gate! The executor makes **no model call**.
4. **Say what each agent sees.** Log exactly one line per agent, in this form:
   - `INFO  [planner] sees: goal + desk notes (N chars, capped|not capped); tools: none`
   - `INFO  [executor] sees: the plan only (N step(s)), never the notes; tools: all 8 through the [y/N] gate`
5. **Pass a recursion limit.** `compiled.invoke(state, config={"recursion_limit": RECURSION_LIMIT})` with `RECURSION_LIMIT = 10`. LangGraph's own default is 10007 steps, so without it a wiring loop would run for a very long time.
6. Set `status` to `"done-with-denials"` if any step was denied, `"cost-ceiling"` on `llm.CostCeilingReached`, `"stopped"` on `llm.CallCapReached`/`llm.ModelError`, else `"done"`.

See `docs/00-foundation.md` for `desk.py` and `llm.py` helper signatures. Verify with: `python check.py 1` -> `AM-1 ...: all 5 green`.

## Expected output (offline stand-in)
`python app.py --setup two`, then `Add File taxes, then show me my list.`:
```text
INFO  [planner] sees: goal + desk notes (46 chars, not capped); tools: none
INFO  [planner] model=stand-in in=60(est.) out=39 (0.01s)
INFO  [planner] proposed 2 step(s): ['add_task', 'list_tasks']
INFO  [executor] sees: the plan only (2 step(s)), never the notes; tools: all 8 through the [y/N] gate
INFO  [executor] step 1 add_task -> ok: added task #9: File taxes
status: done  |  calls: 1  |  answer: add_task: added task #9: File taxes | list_tasks: Tasks: ...
```
`calls: 1` is correct: only the planner calls the model. "Two agents" here means two roles, one model call plus the
plan's tool steps. Then `Delete the dentist task.` and answer `n` at `[y/N]` -> `status: done-with-denials`, the dentist
task is still in `todo-list.md`.
