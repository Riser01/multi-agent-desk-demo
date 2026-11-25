"""AM-1 reference solution: a Planner with no tools hands a written plan to an Executor that runs it through the gate.

WHAT IT IS
    A two-node LangGraph graph: START -> planner -> executor -> END. The planner reads the goal and the desk notes and
    writes a plan as JSON ({"steps": [{"task", "tool", "args"}]}). It has no tools, so reading a nasty note cannot
    delete anything by itself. The executor makes NO model call: it runs each planned step through desk.run_tool,
    where every delete or cancel still stops at the blocking [y/N] gate.

WHY SPLIT IT
    The single agent decides and acts in one breath. Splitting gives you a written plan you can inspect, test and
    refuse (AM-2's validate_plan does exactly that) before anything touches the desk.

WHAT GOES WRONG WITHOUT THE PIECES HERE
    * No gate in the executor: an obedient planner plus a planted note deletes "Pay rent" with nobody asked.
    * No recursion_limit: LangGraph's own default is 10007 steps, so a wiring mistake that loops would run (and bill)
      for a long time before stopping. Two nodes need two steps; RECURSION_LIMIT stops anything odd at 10.
    * Trusting the plan's shape: a live model can return "steps" as a string or a step without args. Bad steps are
      dropped with a WARN line here, so this works even before safety.py exists.

WHAT TO LOOK AT IN THE LOG
    "[planner] sees: ..." and "[executor] sees: ..." say exactly what each agent was shown. The planner is the only
    model call (calls: 1 offline); the executor only runs tools.
"""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

import desk as desk_mod
import llm

PLANNER_PROMPT = (
    "You are a Planner with NO tools. Read the goal and context, and return JSON: "
    '{"steps": [{"task": "...", "tool": "...", "args": {...}}]}.'
)
RECURSION_LIMIT = 10   # planner + executor = 2 graph steps; a bigger number would only hide a wiring loop


class TwoAgentState(TypedDict, total=False):
    goal: str
    context: str
    plan: list[dict[str, Any]]
    results: list[str]
    status: str
    answer: str


def _try_safety():
    """Hook AM-2 safety.py automatically once the learner builds it (None before that)."""
    try:
        import safety
        return safety
    except ModuleNotFoundError as err:
        if err.name == "safety":
            return None
        raise


def _clean_steps(raw: Any, log_fn) -> list[dict[str, Any]]:
    """Keep only well-formed steps ({"tool": str, "args": dict}); a malformed live plan never crashes the executor."""
    if not isinstance(raw, list):
        if raw and log_fn:
            log_fn(f"WARN  [planner] plan 'steps' is not a list ({type(raw).__name__}); nothing will run")
        return []
    steps = []
    for idx, step in enumerate(raw, 1):
        if not isinstance(step, dict) or not isinstance(step.get("tool"), str):
            if log_fn:
                log_fn(f"WARN  [planner] dropped malformed step {idx}: {str(step)[:80]}")
            continue
        args = step.get("args")
        steps.append({"task": str(step.get("task", "")), "tool": step["tool"], "args": args if isinstance(args, dict) else {}})
    return steps


def run_two_agent(goal: str, desk: desk_mod.Desk, model, approve, *, meter=None, routing=None, log_fn=None) -> dict:
    """Build and run the 2-node LangGraph (planner -> executor), applying safety.py caps if built."""
    safety = _try_safety()
    notes_text = "\n".join(n["text"] for n in desk.notes)
    capped = False
    if safety and hasattr(safety, "cap_context"):
        # AM-2: cut the notes BEFORE the planner reads them. The /drill payload sits at the very end of a huge note,
        # so the cap removes it before any model sees it.
        notes_text, capped = safety.cap_context(notes_text)
        if capped and log_fn:
            log_fn(f"WARN  [handoff] cap context cut to {safety.MAX_CONTEXT_CHARS} chars")

    def planner_node(state: TwoAgentState) -> dict:
        # Line 0 must be the goal: the offline stand-in reads the goal from line 0 only.
        user = f"Goal: {state['goal']}\n\nContext notes:\n{state['context']}"
        if log_fn:
            cut = "capped" if capped else "not capped"
            log_fn(f"INFO  [planner] sees: goal + desk notes ({len(state['context'])} chars, {cut}); tools: none")
        try:
            data, _ = llm.ask_json("planner", PLANNER_PROMPT, user, model, meter=meter, routing=routing, log_fn=log_fn)
        except llm.CostCeilingReached as err:
            return {"plan": [], "status": "cost-ceiling", "answer": str(err)}
        except (llm.CallCapReached, llm.ModelError) as err:
            return {"plan": [], "status": "stopped", "answer": str(err)}
        steps = _clean_steps(data.get("steps"), log_fn)
        if log_fn:
            log_fn(f"INFO  [planner] proposed {len(steps)} step(s): {[s.get('tool') for s in steps]}")
        if safety and hasattr(safety, "validate_plan"):
            # AM-2: the second barrier. Checked in plain code, so a fooled planner cannot talk its way past it.
            reasons = safety.validate_plan(steps, state["goal"])
            if reasons:
                msg = "; ".join(reasons)
                if log_fn:
                    log_fn(f"WARN  [safety] plan-rejected: {msg}")
                return {"plan": [], "status": "plan-rejected", "answer": msg}
        return {"plan": steps, "status": "planned"}

    def executor_node(state: TwoAgentState) -> dict:
        if state.get("status") != "planned":
            return {}   # the planner stopped (cost, cap, model error or rejected plan): run nothing
        plan = state.get("plan") or []
        if log_fn:
            log_fn(f"INFO  [executor] sees: the plan only ({len(plan)} step(s)), never the notes; tools: all 8 through the [y/N] gate")
        outputs, denials = [], 0
        for idx, step in enumerate(plan, 1):
            tool_name, args = step["tool"], step["args"]
            res = desk_mod.run_tool(tool_name, args, desk, allowed=desk_mod.ALL_TOOLS, approve=approve, actor="executor")
            if log_fn:
                lvl = "WARN " if res.kind != "ok" else "INFO "
                log_fn(f"{lvl} [executor] step {idx} {tool_name} -> {res.kind}: {res.text}")
            if res.kind == "denied":
                denials += 1
            outputs.append(f"{tool_name}: {res.text}")
        status = "done-with-denials" if denials else "done"
        return {"results": outputs, "status": status, "answer": " | ".join(outputs) or "No steps ran."}

    builder = StateGraph(TwoAgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_edge("executor", END)
    compiled = builder.compile()
    final = compiled.invoke({"goal": goal, "context": notes_text, "plan": [], "results": []},
                            config={"recursion_limit": RECURSION_LIMIT})
    return {
        "status": final.get("status", "done"),
        "answer": final.get("answer", ""),
        "plan": final.get("plan", []),
        "results": final.get("results", []),
    }
