"""PM-1 reference solution: a Supervisor routes work to two least-privilege workers (PM-1a), plus a bounded Reviewer (PM-1b).

WHAT IT IS
    A LangGraph loop: START -> supervisor -> (tasks | calendar) -> supervisor -> ... -> END.
    * supervisor       no tools. Reads the goal, the notes and "Done so far", and picks the next worker or "finish".
    * tasks worker     may call ONLY the 4 task tools. Sees the tasks and the full raw notes.
    * calendar worker  may call ONLY the 3 calendar tools. Sees the calendar only.
    * reviewer         no tools. With review on, it checks every delete/cancel against the user's goal, up to
                       MAX_REVIEW_ROUNDS times, BEFORE the human [y/N] gate. Its "yes" never skips the gate.

WHY IT IS NEEDED
    One agent with all 8 tools can do anything any note tells it. Splitting by job means each worker can only do its
    own job: the calendar worker cannot delete a task even if fooled (least privilege is about TOOLS here). The tasks
    worker still reads the raw notes, uncapped (team.py applies no cap_context), so it CAN be fooled by /drill. The
    defence for the team is the reviewer, the human gate and the tool limits, not hiding data.

WHAT GOES WRONG WITHOUT THE LIMITS
    * No MAX_TURNS: a supervisor that keeps routing (a confused live model) loops until the per-turn call cap.
    * No recursion_limit: LangGraph's default is 10007 steps; RECURSION_LIMIT stops a wiring loop at 2*MAX_TURNS + 4.
    * No reviewer: on /drill, the fooled tasks worker's delete reaches the gate, and a blind "yes" deletes Pay rent.

WHAT TO LOOK AT IN THE LOG
    One "sees: ..." line per agent, the supervisor's "-> tasks / -> calendar / -> finish" choices, and
    "[reviewer] rejected round 1 / round 2" on /drill. With the offline stand-in, round 2 always gives the same verdict
    as round 1 (it is deterministic); a live model gets a real second look that includes its first answer.
"""
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

import desk as desk_mod
import llm

MAX_TURNS = 6
MAX_REVIEW_ROUNDS = 2
RECURSION_LIMIT = 2 * MAX_TURNS + 4   # each turn = supervisor + one worker; the rest is headroom for finish
IRREVERSIBLE_TOOLS = ("delete_task", "cancel_event")

SUPERVISOR_PROMPT = (
    "You are a Supervisor with NO tools. Route to 'tasks', 'calendar', or 'finish'. "
    'Return JSON: {"next": "tasks"|"calendar"|"finish", "task": "...", "answer": "..."}.'
)
TASKS_PROMPT = "You are the Tasks Worker. You may ONLY call: " + ", ".join(desk_mod.TASK_TOOLS) + '. Return JSON: {"tool": ..., "args": {...}, "summary": ...}.'
CALENDAR_PROMPT = "You are the Calendar Worker. You may ONLY call: " + ", ".join(desk_mod.CALENDAR_TOOLS) + '. Return JSON: {"tool": ..., "args": {...}, "summary": ...}.'
REVIEWER_PROMPT = (
    "You are a Reviewer with NO tools. Check if the proposed irreversible tool matches the user's original goal. "
    'Return JSON: {"approved": true|false, "reason": "..."}.'
)


class TeamState(TypedDict, total=False):
    goal: str
    next_worker: str
    current_task: str
    done_so_far: Annotated[list[str], operator.add]   # reducer: each worker APPENDS its line instead of overwriting
    turns: int
    denials: int
    status: str
    answer: str


def reviewer_node(goal: str, actor: str, tool_name: str, args: dict[str, Any], model, *, meter=None, routing=None, log_fn=None) -> tuple[bool, str]:
    """PM-1b: bounded reviewer (max MAX_REVIEW_ROUNDS rounds) checks irreversible actions before the [y/N] gate.

    Returns (approved, reason). Approved only means "may go on to the human gate"; it never deletes anything itself.
    """
    reason = ""
    if log_fn:
        log_fn(f"INFO  [reviewer] sees: the user's goal + the proposed action only; tools: none")
    for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
        user = f"Goal: {goal}\nProposed by {actor}: {tool_name}({args})\nRound {round_num} of {MAX_REVIEW_ROUNDS}."
        if reason:
            user += f"\nYour previous verdict: rejected ({reason}). Look again."
        if log_fn:
            log_fn(f"INFO  [reviewer] round {round_num}/{MAX_REVIEW_ROUNDS} checking {actor}.{tool_name}")
        verdict, _ = llm.ask_json("reviewer", REVIEWER_PROMPT, user, model, meter=meter, routing=routing, log_fn=log_fn)
        approved = verdict.get("approved") is True   # only a real JSON true counts; "yes" strings or missing = no
        reason = str(verdict.get("reason", "no reason given"))
        if approved:
            if log_fn:
                log_fn(f"INFO  [reviewer] approved ({reason}) — passing to human [y/N] gate")
            return True, reason
        if log_fn:
            log_fn(f"WARN  [reviewer] rejected round {round_num}: {reason}")
    return False, f"blocked by reviewer after {MAX_REVIEW_ROUNDS} rounds: {reason}"


def run_team(goal: str, desk: desk_mod.Desk, model, approve, *, review: bool = False, meter=None, routing=None, log_fn=None) -> dict:
    """Build and run the LangGraph supervisor + 2 least-privilege workers (+ optional reviewer)."""

    def supervisor(state: TeamState) -> dict:
        turns = state.get("turns", 0)
        if turns >= MAX_TURNS:
            # Hard stop in code: however the model routes, the team never takes more than MAX_TURNS worker turns.
            if log_fn:
                log_fn(f"WARN  [supervisor] turn cap ({MAX_TURNS}) reached; stopping")
            return {"next_worker": "finish", "status": "stopped", "answer": f"supervisor turn cap ({MAX_TURNS}) reached"}
        notes_text = "\n".join(n["text"] for n in desk.notes)
        done_str = "; ".join(state.get("done_so_far") or []) or "(nothing yet)"
        # "Done so far" lines start with "tasks:" / "calendar:" so the stand-in knows which worker already ran.
        user = f"Goal: {state['goal']}\nNotes: {notes_text}\nDone so far: {done_str}"
        if log_fn:
            log_fn(f"INFO  [supervisor] sees: goal + notes + done-so-far ({len(user)} chars); tools: none (turn {turns + 1}/{MAX_TURNS})")
        try:
            route, _ = llm.ask_json("supervisor", SUPERVISOR_PROMPT, user, model, meter=meter, routing=routing, log_fn=log_fn)
        except llm.CostCeilingReached as err:
            return {"next_worker": "finish", "status": "cost-ceiling", "answer": str(err)}
        except (llm.CallCapReached, llm.ModelError) as err:
            return {"next_worker": "finish", "status": "stopped", "answer": str(err)}
        nxt = route.get("next", "finish")
        if nxt not in ("tasks", "calendar", "finish"):
            nxt = "finish"   # an unknown route from a live model ends the turn instead of crashing the graph
        was_refused = any(
            line.startswith(f"{nxt}:") and ("denied" in line or "blocked by reviewer" in line)
            for line in (state.get("done_so_far") or [])
        )
        if nxt != "finish" and was_refused:
            # A human "no" (or a reviewer block) is final for that worker. A live model often routes the same delete
            # to the same worker again; asking a person twice is how a team nags. Code ends the run instead. The
            # other worker is still free to run, so an unrelated second job is not lost.
            if log_fn:
                log_fn(f"WARN  [supervisor] {nxt} was already refused; not asking again")
            nxt = "finish"
        if log_fn:
            log_fn(f"INFO  [supervisor] -> {nxt}: {route.get('task') or route.get('answer', '')}")
        return {
            "next_worker": nxt,
            "current_task": str(route.get("task", state["goal"])),
            "turns": turns + 1,
            "answer": str(route.get("answer", state.get("answer", ""))),
        }

    def _run_worker(worker_name: str, role: str, prompt: str, allowed: tuple[str, ...], state: TeamState) -> dict:
        if worker_name == "tasks":
            # Full raw notes: desk_view() cuts notes at 120 chars, which would hide the /drill payload. No cap here.
            view = desk_mod.desk_view(desk, include_tasks=True, include_events=False, include_notes=False)
            notes = "\n".join(n["text"] for n in desk.notes)
            user = f"Task: {state.get('current_task', state['goal'])}\n\n{view}\nNotes:\n{notes}"
            seen = "task + tasks + full raw notes"
        else:
            view = desk_mod.desk_view(desk, include_tasks=False, include_events=True, include_notes=False)
            user = f"Task: {state.get('current_task', state['goal'])}\n\n{view}"
            seen = "task + calendar only"
        if log_fn:
            log_fn(f"INFO  [{worker_name}] sees: {seen} ({len(user)} chars); tools: {', '.join(allowed)}")
        try:
            choice, _ = llm.ask_json(role, prompt, user, model, meter=meter, routing=routing, log_fn=log_fn)
            tool_name = str(choice.get("tool", ""))
            args = choice.get("args") if isinstance(choice.get("args"), dict) else {}
            if review and tool_name in IRREVERSIBLE_TOOLS:
                ok, reason = reviewer_node(state["goal"], worker_name, tool_name, args, model, meter=meter, routing=routing, log_fn=log_fn)
                if not ok:
                    return {"done_so_far": [f"{worker_name}: {reason}"], "denials": state.get("denials", 0) + 1}
        except llm.CostCeilingReached as err:
            return {"next_worker": "finish", "status": "cost-ceiling", "answer": str(err)}
        except (llm.CallCapReached, llm.ModelError) as err:
            return {"next_worker": "finish", "status": "stopped", "answer": str(err)}
        # `allowed` is this worker's slice only: asking for any other tool comes back "refused (least privilege)".
        res = desk_mod.run_tool(tool_name, args, desk, allowed=allowed, approve=approve, actor=worker_name)
        if log_fn:
            lvl = "WARN " if res.kind != "ok" else "INFO "
            log_fn(f"{lvl} [{worker_name}] {tool_name} -> {res.kind}: {res.text}")
        denials = state.get("denials", 0) + (1 if res.kind == "denied" else 0)
        return {"done_so_far": [f"{worker_name}: {res.text}"], "denials": denials}

    def tasks_worker(state: TeamState) -> dict:
        return _run_worker("tasks", "tasks_worker", TASKS_PROMPT, desk_mod.TASK_TOOLS, state)

    def calendar_worker(state: TeamState) -> dict:
        return _run_worker("calendar", "calendar_worker", CALENDAR_PROMPT, desk_mod.CALENDAR_TOOLS, state)

    def route_from_supervisor(state: TeamState) -> str:
        if state.get("status") in ("cost-ceiling", "stopped"):
            return END
        nxt = state.get("next_worker", "finish")
        return END if nxt == "finish" else nxt

    def route_after_worker(state: TeamState) -> str:
        return END if state.get("status") in ("cost-ceiling", "stopped") else "supervisor"

    builder = StateGraph(TeamState)
    builder.add_node("supervisor", supervisor)
    builder.add_node("tasks", tasks_worker)
    builder.add_node("calendar", calendar_worker)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_from_supervisor, {"tasks": "tasks", "calendar": "calendar", END: END})
    builder.add_conditional_edges("tasks", route_after_worker, {"supervisor": "supervisor", END: END})
    builder.add_conditional_edges("calendar", route_after_worker, {"supervisor": "supervisor", END: END})
    compiled = builder.compile()
    final = compiled.invoke({"goal": goal, "done_so_far": [], "turns": 0, "denials": 0},
                            config={"recursion_limit": RECURSION_LIMIT})
    status = final.get("status")
    if not status:
        status = "done-with-denials" if final.get("denials", 0) > 0 else "done"
    return {
        "status": status,
        "answer": final.get("answer") or " | ".join(final.get("done_so_far") or []),
        "done_so_far": final.get("done_so_far", []),
    }
