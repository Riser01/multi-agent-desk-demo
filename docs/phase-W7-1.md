# Phase W7-1: shared state, and one agent as a graph node (22 min)

## The concept
A team needs one place where the work so far lives. In LangGraph that is the **state**: a typed dictionary every node reads, and every node updates by returning **only the keys it changed**. Two kinds of key:
- a plain key is **overwritten** by the last writer (`status`, `plan`, `step`);
- a key with a **reducer** is **merged**: `Annotated[list, operator.add]` appends. `results` and `handoffs` are append-only logs, so no agent can erase what another one did.

The desk is **not** in the state: it is the world, like a database. The `Team` dataclass carries the things that are not state (model, desk, approver, run log). Every agent asks its model with `team.ask(...)` and touches the desk only with `team.act(...)`, which goes through last week's gate.

Then you rebuild last week's agent as a graph: one `agent` node that loops on itself through a **conditional edge**, a turn cap checked before every call, and an explicit `recursion_limit` as a backstop (LangGraph 1.2.23's default is 10,007; ours is 40, sized for the worst team case).

`agent.py`, the command you run, is **provided**: it reads the flags, loads the desk, builds your graph and writes the logs. You build only the two files below.

## What you build
`state.py` (`TeamState`, `new_state`, `finished`, `result_lines`, `Team`) and `graph.py` (`node`, `agent_node`, `after_agent`, `finish_node`, `build_single`, `run_graph`).
Contract: `02-technical-spec.md` sections 3, 4 and 6 (role `agent`). Section 11 describes the provided `agent.py`.

## Ask your agent exactly this
> Read `AGENTS.md` and `docs/02-technical-spec.md`. Build Phase W7-1 only: create `state.py` (section 3), `graph.py` with `RECURSION_LIMIT`, `MAX_TURNS`, `SINGLE_PROMPT`, `node`, `agent_message`, `agent_node`, `after_agent`, `finish_node`, `build_single` and `run_graph` (section 4 and the `agent` row of section 6), (the provided `agent.py` calls them; do not edit it). Use exactly the names, state keys, reducers and statuses in the spec. Every desk action goes through `Team.act`. Make `python check.py 1` pass and do not stop until it passes. Never edit `tests/` or the provided files.

## Check
```bash
python check.py 1
```
```text
Phase W7-1  State and one agent node: all 12 green
```

## Try it
```bash
python agent.py "Add File taxes, then show me my list." --setup single --approve no
```
What you should see (`sample-runs/01a-single-add-and-list.txt`):
```text
INFO  +  0.00s  [agent     ] saw     goal: Add "File taxes", then show me my list. | desk: | tasks: | 1: Mon 23 Nov: ...
INFO  +  0.00s  [agent     ] model   stand-in replied in 0.00s (388 in / 13 out tokens, est.): {"tool": "add_task", "args": {"text": "File taxes"}}
INFO  +  0.00s  [agent     ] tool    add_task {"text": "File taxes"}  ->  ok: added task 9
INFO  +  0.00s  [run       ] run     ended: status=done after 3 model calls, 1259 in / 45 out tokens (est.), 0.0s
status: done
log:    logs/latest.log  (this run: logs/run-...-single.log)
report: out/latest.html  (open it in a browser)
```
Then the gate, answering `n`:
```bash
python agent.py "Delete the dentist task." --setup single --approve ask
```
```text
APPROVAL NEEDED: delete task 4: "Book dentist appointment". Cannot be undone. Allow? [y/N]
WARN  ... [agent     ] gate    delete task 4: "Book dentist appointment"  ->  denied
status: done-with-denials
```
Open `out/latest.html`: the timeline shows each turn, "what it saw" (click to expand), every tool call and the gate decision.

## What you learn
- State is shared memory with rules: reducers decide merge vs overwrite.
- A loop in a graph is a conditional edge; its exit is code (the turn cap), not the model's goodwill.
- `recursion_limit` is a backstop you must set yourself.

## Common mistakes
- Returning the whole state from a node instead of only the changed keys.
- Putting the desk inside the state (then every node copies the world, and nothing goes through the gate).
- Forgetting `recursion_limit`: a runaway loop would run 10,007 steps.
- Calling the terminal approval question an "interrupt": it is a plain blocking callback in the gate; LangGraph's `interrupt()` (pause, checkpoint, resume) is not used here.
- Checking the turn cap after the model call (one call too many).
