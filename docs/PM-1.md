# Phase PM-1 Spec: Supervisor, Specialist Workers & Reviewer (`team.py`)

Build `team.py` in two clean checkpoints (20 min + 20 min) using LangGraph `StateGraph`.

**What you learn:** routing work to specialists that each hold only the tools for their job (least privilege), and
adding a tool-less reviewer in front of the human gate (defence in depth). Also what it costs: 5 to 7 model calls
where the single agent makes 1.

## Part A (20 min): Supervisor + 2 Least-Privilege Workers
- Constants: `MAX_TURNS = 6` and `RECURSION_LIMIT = 2 * MAX_TURNS + 4` (each turn = supervisor + one worker).
- **`supervisor` node (NO tools):** Sees `goal`, full `desk.notes` text, and `done_so_far`. Format the user prompt with `Done so far: ...` where completed worker items are prefixed `"tasks: ..."` or `"calendar: ..."` (the offline stand-in checks those prefixes so it knows when to return `{"next": "finish", ...}`). Call `route, _ = llm.ask_json("supervisor", ..., user, model, ...)` -> `{"next": "tasks"|"calendar"|"finish", "task": "...", "answer": "..."}`. An unknown `next` value means finish. If the model routes to a worker whose earlier line in `done_so_far` says it was denied by a person or blocked by the reviewer, finish instead (log `WARN  [supervisor] <worker> was already refused; not asking again`): a human "no" is final for that worker, and a live model will otherwise ask again. Stop with `status="stopped"` if `turns >= MAX_TURNS` (checked in code before the model call, so a supervisor that never says finish makes at most 6 calls).
- **`tasks_worker`:** Allowed ONLY `desk.TASK_TOOLS`. Sees the tasks + the **full raw `desk.notes` text** (do NOT rely only on `desk_view(..., include_notes=True)` because `desk_view` truncates notes at 120 chars and would hide the `/drill` payload). Put the task on line 0 (`Task: {task}`) and call `llm.ask_json("tasks_worker", ...)` -> `{"tool": ..., "args": {...}, "summary": ...}`.
- **`calendar_worker`:** Allowed ONLY `desk.CALENDAR_TOOLS` and sees only calendar events (`desk_view(desk, include_tasks=False, include_events=True, include_notes=False)`). Call `llm.ask_json("calendar_worker", ...)` -> `{"tool": ..., "args": {...}, "summary": ...}`.
- Each worker passes its own slice as `allowed=` to `desk.run_tool`, so asking for another worker's tool comes back `refused (... not allowed ... least privilege)`. Use `{}` when the model's `"args"` is not a dict.
- **What least privilege means here:** it limits TOOLS, not data. The tasks worker still reads the raw notes, and `team.py` applies **no** `cap_context`, so the tasks worker can be fooled by `/drill`. The team's defences are the tool limits, the reviewer (Part B) and the human `[y/N]` gate.
- **Say what each agent sees** (one line each): `INFO  [supervisor] sees: ...`, `INFO  [tasks] sees: ...`, `INFO  [calendar] sees: ...`.
- Export `run_team(goal, desk, model, approve, *, review=False, meter=None, routing=None, log_fn=None) -> dict` and call `compiled.invoke(state, config={"recursion_limit": RECURSION_LIMIT})`. It returns a dict with the keys `status`, `answer` and `done_so_far` (the list of worker lines; the tests read it). *(Tip: `import desk as desk_mod` so the `desk` parameter does not shadow the `desk` module.)*
- **Pause & test Part A:** In `python app.py --setup team`, run `Cancel the team sync on Wednesday and remind me to email Anil.` and answer `y` at the gate. Expected: supervisor -> calendar (cancel, gate) -> supervisor -> tasks (adds `email Anil`) -> supervisor -> finish, `status: done  |  calls: 5`.

## Part B (20 min): Bounded Reviewer (Defense-in-Depth)
- Constant: `MAX_REVIEW_ROUNDS = 2`.
- Export `reviewer_node(goal, actor, tool_name, args, model, *, meter=None, routing=None, log_fn=None) -> tuple[bool, str]`:
  - Tool-less reviewer called when `review=True` and a worker proposes an irreversible tool (`delete_task`, `cancel_event`).
  - Log `INFO  [reviewer] sees: the user's goal + the proposed action only; tools: none`.
  - Include a `"Goal: {goal}"` line in the prompt (required by the offline stand-in to verify whether the user asked to delete/cancel).
  - Runs at most `MAX_REVIEW_ROUNDS` rounds via `verdict, _ = llm.ask_json("reviewer", ...)` -> `{"approved": true|false, "reason": "..."}`. Only a real JSON `true` approves: `"false"` (a string), `"yes"` or a missing field count as a rejection.
  - **What a "round" means:** a rejected round is asked again, with its previous verdict added to the prompt. A live model gets a genuine second look. The offline stand-in is deterministic, so its round 2 always repeats round 1; that is expected, and the check uses a scripted reviewer to test the counter.
  - If approved, the action STILL passes through the blocking `[y/N]` human gate (reviewer is defense-in-depth, never a bypass). If rejected after 2 rounds, block the action and increment denials (`status="done-with-denials"`).

See `docs/00-foundation.md` for helper signatures. Verify with: `python check.py 3` -> `PM-1 ...: all 9 green`.

## Expected output (offline stand-in)
`/drill`, `Tidy up my tasks.` with `/review off` and a blind `y`: the tasks worker obeys the note and Pay rent is
deleted (`status: done  |  calls: 3`). `/reset`, `/review on`, `/drill`, `Tidy up my tasks.`:
```text
INFO  [tasks] sees: task + tasks + full raw notes (1087 chars); tools: add_task, list_tasks, complete_task, delete_task
INFO  [reviewer] sees: the user's goal + the proposed action only; tools: none
WARN  [reviewer] rejected round 1: User goal did not ask for an irreversible delete/cancel.
WARN  [reviewer] rejected round 2: User goal did not ask for an irreversible delete/cancel.
status: done-with-denials  |  calls: 7  |  answer: All requested desk actions processed.
```
No `[y/N]` question appears: the reviewer stopped the delete before the gate, and Pay rent stays in `todo-list.md`.
