"""Optional stretch reference solution: a REAL LangGraph approval gate with interrupt() and a checkpointer.

WHAT IT IS
    A three-node graph: START -> plan -> gate -> act -> END, compiled with an InMemorySaver checkpointer.
    * plan  the planner (no tools) writes steps, exactly like AM-1.
    * gate  if any step is a delete/cancel, it calls interrupt({...}). The graph PAUSES, saves its state under a
            thread_id, and returns to the caller. Nothing waits on a terminal prompt inside the graph.
    * act   runs the steps; risky ones only if the human said yes when the graph was resumed.

WHY IT IS DIFFERENT FROM THE MAIN DEMO
    The main demo's [y/N] gate is a blocking terminal callback inside the tool call. That is fine for a laptop, but a
    web app or a chat bot cannot block a thread for hours waiting for a human. interrupt() saves the run instead, and
    any later process can resume it with Command(resume="y") and the same thread_id.

WHAT GOES WRONG IF YOU GET IT WRONG
    * A side effect BEFORE interrupt(): the gate node re-runs from its first line on resume, so it would happen twice.
      Here the gate only reads state before pausing; all desk changes happen in `act`.
    * No checkpointer, or a different thread_id on resume: there is nothing to resume.
    * A bare try/except around interrupt(): it would swallow the pause signal.

WHAT TO LOOK AT
    `python stretch.py "Delete the dentist task."` prints the paused question, asks you, then resumes. The planner's
    model call count stays at 1 after resuming: the saved checkpoint means the plan is not made again.
"""
import sys
import uuid
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import desk as desk_mod
import llm

PLANNER_PROMPT = (
    "You are a Planner with NO tools. Read the goal and context, and return JSON: "
    '{"steps": [{"task": "...", "tool": "...", "args": {...}}]}.'
)
IRREVERSIBLE_TOOLS = ("delete_task", "cancel_event")
RECURSION_LIMIT = 10


class GateState(TypedDict, total=False):
    goal: str
    steps: list[dict[str, Any]]
    approved: bool
    status: str
    answer: str


def build_gate_graph(desk: desk_mod.Desk, model, *, checkpointer=None, log_fn=None):
    """Compile the plan -> gate -> act graph with a checkpointer (InMemorySaver unless one is given)."""

    def plan(state: GateState) -> dict:
        notes = "\n".join(n["text"] for n in desk.notes)
        data, _ = llm.ask_json("planner", PLANNER_PROMPT, f"Goal: {state['goal']}\n\nContext notes:\n{notes}", model, log_fn=log_fn)
        raw = data.get("steps")
        steps = [s for s in raw if isinstance(s, dict) and isinstance(s.get("tool"), str)] if isinstance(raw, list) else []
        return {"steps": steps}

    def gate(state: GateState) -> dict:
        risky = [s for s in state.get("steps") or [] if s["tool"] in IRREVERSIBLE_TOOLS]
        if not risky:
            return {"approved": False}
        # No side effects above this line: on resume LangGraph re-runs this node from the top.
        answer = interrupt({"question": "Allow these irreversible steps? [y/N]",
                            "steps": [f"{s['tool']} {s.get('args') or {}}" for s in risky]})
        return {"approved": str(answer or "").strip().lower() in ("y", "yes")}

    def act(state: GateState) -> dict:
        approved = bool(state.get("approved"))
        outputs, denials = [], 0
        for step in state.get("steps") or []:
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            # The decision was taken at the interrupt; run_tool's own gate just applies it.
            res = desk_mod.run_tool(step["tool"], args, desk, allowed=desk_mod.ALL_TOOLS,
                                    approve=lambda *_: approved, actor="executor")
            denials += res.kind == "denied"
            outputs.append(f"{step['tool']}: {res.text}")
        return {"status": "done-with-denials" if denials else "done", "answer": " | ".join(outputs) or "No steps ran."}

    builder = StateGraph(GateState)
    builder.add_node("plan", plan)
    builder.add_node("gate", gate)
    builder.add_node("act", act)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "gate")
    builder.add_edge("gate", "act")
    builder.add_edge("act", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


def _result(out: dict) -> dict:
    if out.get("__interrupt__"):
        return {"status": "waiting", "question": out["__interrupt__"][0].value}
    return {"status": out.get("status", "done"), "answer": out.get("answer", "")}


def start(graph, goal: str, thread_id: str) -> dict:
    """Run until the graph finishes or pauses at the gate. Paused: {"status": "waiting", "question": {...}}."""
    return _result(graph.invoke({"goal": goal}, config=_config(thread_id)))


def resume(graph, thread_id: str, answer: str) -> dict:
    """Resume a paused run on the same thread_id with the human's answer ("y" approves; anything else denies)."""
    return _result(graph.invoke(Command(resume=answer), config=_config(thread_id)))


if __name__ == "__main__":
    desk = desk_mod.load_desk("data/seed.json")
    model = llm.make_model()
    graph = build_gate_graph(desk, model)
    thread = uuid.uuid4().hex[:8]
    goal = " ".join(sys.argv[1:]) or "Delete the dentist task."
    first = start(graph, goal, thread)
    print(f"thread {thread}: {first['status']}")
    if first["status"] == "waiting":
        print(f"paused at the gate, state saved: {first['question']}")
        try:
            reply = input("  Allow? [y/N]: ")
        except EOFError:
            reply = ""
        final = resume(graph, thread, reply)
        print(f"resumed: status {final['status']} | {final['answer']}")
    else:
        print(first.get("answer", ""))
    print(f"model calls: {model.calls} (the plan was not made again after the pause)")
    print("tasks left:", ", ".join(f"#{t['id']} {t['text']}" for t in desk.tasks))
