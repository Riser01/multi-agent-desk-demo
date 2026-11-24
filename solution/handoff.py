"""The handoff: the structured message one agent sends another, and the plan the planner writes. W7-2, capped in W7-3.

When one agent passes work to another, everything the receiver knows arrives in that message. Pass too little and
the receiver guesses; pass the whole history and it drowns, pays for every token, and inherits every planted note.
So a handoff here is not free text. It is a small, checked record with four parts: the TASK (one thing to do), the
CONTEXT (only what the receiver needs), the CONSTRAINTS (the rules it must keep) and the RETURN ADDRESS (who reads
the result). Plus who sent it and to whom, so the trace can show every arrow.

The plan is the same idea one level up: the planner's reply is parsed into PlanStep records and checked before a
single step runs. A bad plan stopped here costs one model call; a bad plan executed costs a deleted task.

W7-3 adds the caps, because a handoff is also an attack path. A task over MAX_TASK_CHARS is refused, a context over
MAX_CONTEXT_CHARS is cut with a visible marker (a 1,500-character pasted note cannot flood the next agent), and
validate_plan() refuses a plan that is too long, names a tool the team may not use, or deletes something when the
user never asked to delete anything (the planted-note attack).

What to look at
    Handoff, to_text()   the four parts, and exactly what the receiving agent sees: nothing more.
    make_handoff()       the only way to build one: it validates, and (W7-3) caps the context.
    PlanStep, parse_plan()  the planner's reply as checked records; a malformed plan raises HandoffError.
    validate_plan()      W7-3: the plan rules, each returning one plain sentence. "Your turn" adds one more rule here.
"""
from dataclasses import asdict, dataclass

from desk_tools import DELETE_WORDS, TOOLS

MAX_TASK_CHARS = 200      # W7-3: a task longer than this is refused, not cut: a cut task means a different task
MAX_CONTEXT_CHARS = 600   # W7-3: the context is cut to this, with " [truncated]", so no note can flood the receiver
MAX_PLAN_STEPS = 5        # W7-3: a longer plan is refused; one goal should not need more


class HandoffError(ValueError):
    """A handoff or a plan that breaks the schema. The message says which rule, in plain words."""


@dataclass(frozen=True)
class Handoff:
    """One arrow between two agents: who to whom, the task, the context, the constraints and the return address."""
    from_agent: str
    to_agent: str
    task: str
    context: str
    constraints: tuple
    return_to: str
    capped: bool = False          # W7-3: True when the context was cut to MAX_CONTEXT_CHARS

    def to_text(self) -> str:
        """Exactly what the receiving agent sees. The section names are fixed (spec section 6)."""
        return "\n".join([f"task: {self.task}", "context:", self.context or "(none)", "constraints:",
                          *[f"- {rule}" for rule in self.constraints], f"return to: {self.return_to}"])

    def to_dict(self) -> dict:
        """Plain data for the state's handoffs log (LangGraph state should hold plain values)."""
        return asdict(self)


def make_handoff(from_agent: str, to_agent: str, task: str, context: str = "", constraints: "list[str] | tuple" = (),
                 return_to: str = "") -> Handoff:
    """Build a checked handoff. Raises HandoffError on a broken one; cuts an oversized context (W7-3)."""
    if not from_agent or not to_agent:
        raise HandoffError("a handoff needs a sender and a receiver")
    if not isinstance(task, str) or not task.strip():
        raise HandoffError("a handoff needs a task in plain words")
    if len(task) > MAX_TASK_CHARS:            # W7-3: refuse, because a cut task would be a different task
        raise HandoffError(f"the task is {len(task)} characters; the cap is {MAX_TASK_CHARS}")
    capped = len(context) > MAX_CONTEXT_CHARS  # W7-3: cut, because a shorter context is still the same job
    if capped:
        context = context[:MAX_CONTEXT_CHARS] + " [truncated]"
    return Handoff(from_agent, to_agent, task.strip(), context, tuple(constraints), return_to or from_agent, capped)


@dataclass(frozen=True)
class PlanStep:
    """One step of a plan: what to do, which tool does it, and why (the why makes a bad step easy to spot)."""
    task: str
    tool: str
    why: str = ""


def parse_plan(data: dict) -> list[PlanStep]:
    """Turn the planner's JSON reply into PlanSteps. Raises HandoffError when the shape is wrong."""
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list):
        raise HandoffError("the plan has no 'steps' list")
    plan = []
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("task"), str) or not isinstance(step.get("tool"), str):
            raise HandoffError(f"step {number} needs a 'task' and a 'tool'")
        plan.append(PlanStep(step["task"], step["tool"], str(step.get("why", ""))))
    return plan


def validate_plan(steps: list[PlanStep], goal: str, allowed: list[str]) -> list[str]:
    """W7-3: every rule the plan breaks, one plain sentence each. An empty list means the plan may run."""
    problems = []
    if not steps:
        problems.append("the plan is empty")
    if len(steps) > MAX_PLAN_STEPS:
        problems.append(f"the plan has {len(steps)} steps; the cap is {MAX_PLAN_STEPS}")
    asked_to_delete = any(word in goal.lower() for word in DELETE_WORDS)
    for number, step in enumerate(steps, 1):
        if step.tool not in allowed:
            problems.append(f"step {number} uses {step.tool}, which is not a tool this team may use")
        elif TOOLS[step.tool].risk == "irreversible" and not asked_to_delete:
            # the planted-note attack: a delete the user never asked for came from text in the data
            problems.append(f"step {number} uses {step.tool}, which cannot be undone, but the goal never asks to delete, remove, clear or cancel anything")
        if len(step.task) > MAX_TASK_CHARS:
            problems.append(f"step {number} task is {len(step.task)} characters; the cap is {MAX_TASK_CHARS}")
    return problems
