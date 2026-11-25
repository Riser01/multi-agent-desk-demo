# Optional Stretch Spec: a real LangGraph `interrupt()` approval gate (`stretch.py`)

Harder, optional, for after PM-2 or at home. About 30 to 45 minutes. Nothing else in the repo depends on it.

**What you learn:** the main demo's `[y/N]` gate is a blocking terminal callback: fine on a laptop, but a web app or
chat bot cannot hold a thread open for hours waiting for a human. LangGraph's `interrupt()` instead **pauses the
graph, saves its state in a checkpointer under a `thread_id`, and returns**. Any later call resumes it with
`Command(resume="y")` and the same `thread_id`. This is the mechanism Saturday's slides describe.

## Contract
Build `stretch.py` (LangGraph + `desk` + `llm`):
1. Constants: `IRREVERSIBLE_TOOLS = ("delete_task", "cancel_event")`, `RECURSION_LIMIT = 10`.
2. `build_gate_graph(desk, model, *, checkpointer=None, log_fn=None)` returns a compiled graph
   `START -> plan -> gate -> act -> END`, compiled with `checkpointer or InMemorySaver()`
   (`from langgraph.checkpoint.memory import InMemorySaver`).
   - `plan`: the AM-1 planner (no tools): `llm.ask_json("planner", ...)` with the goal on line 0; keep only well-formed steps.
   - `gate`: if any step uses an irreversible tool, call
     `answer = interrupt({"question": "Allow these irreversible steps? [y/N]", "steps": [...]})`
     (`from langgraph.types import interrupt, Command`) and return `{"approved": answer.strip().lower() in ("y", "yes")}`.
     Blank or anything else = no. No risky step -> `{"approved": False}` without pausing.
   - `act`: run every step through `desk.run_tool(..., allowed=desk.ALL_TOOLS, approve=lambda *_: approved, actor="executor")`;
     status `done-with-denials` if any step was denied, else `done`.
3. `start(graph, goal, thread_id) -> dict` and `resume(graph, thread_id, answer) -> dict`, both invoking with
   `config={"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}`.
   Paused: `{"status": "waiting", "question": <the interrupt value>}` (the default `invoke` returns it under
   `"__interrupt__"`). Finished: `{"status": ..., "answer": ...}`.

## The three rules that make interrupt() safe
1. **No side effect before `interrupt()`.** On resume LangGraph re-runs the paused node from its first line. Anything
   the gate node did before pausing would happen twice. Change the desk only in `act`.
2. **Same checkpointer, same `thread_id`.** Without both there is nothing to resume.
3. **No bare `try/except` around `interrupt()`.** It pauses by raising internally; swallowing it breaks the pause.

## Check and try it
```bash
python check.py stretch
python stretch.py "Delete the dentist task."
```
Expected: `Stretch  interrupt() approval gate (stretch.py, optional): all 5 green`, then:
```text
thread 8af633f8: waiting
paused at the gate, state saved: {'question': 'Allow these irreversible steps? [y/N]', 'steps': ["delete_task {'id': 3}"]}
  Allow? [y/N]: n
resumed: status done-with-denials | delete_task: human denied deleting task #3 (Book dentist appointment)
model calls: 1 (the plan was not made again after the pause)
```
(The thread id is random.) `model calls: 1` after resuming is the point: the checkpoint kept the plan, so the planner
was not asked again. Answer `y` instead and task #3 is deleted.

## Other stretch idea (no check provided)
Parallel fan-out: send the tasks and calendar slices to two workers at once with `Send` and merge their results with
a reducer (`Annotated[list[str], operator.add]`). Without the reducer LangGraph raises `InvalidUpdateError` on the
concurrent writes: a good failure to see once.
