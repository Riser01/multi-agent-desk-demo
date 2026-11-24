"""The gate: the one door every agent's action must pass through before it touches the desk. PROVIDED.

This is the safety half of last week's harness, carried forward. A model only ever PROPOSES an action. This file
decides what actually happens: is this agent allowed this tool at all, is the input sane, does a human say yes to
anything irreversible, and is the result short enough to hand back. With a team of agents this matters more, not
less: a planted note can travel from one agent to the next inside a handoff, and every agent is one more chance for
a fooled model to ask for a delete. Whatever agent asks, the same gate answers.

Every agent node you build calls run_tool() (through Team.act in state.py). You never edit this file.

What to look at in run_tool(), in order
    1 allow-list    a tool not on this agent's list is refused (least privilege: the calendar worker cannot delete
                    tasks, however it is asked).
    2 input check   unknown tool or bad arguments come back as an error line the model can read; nothing runs.
    3 the gate      only irreversible tools ask a human. No approver, or an approver or describe() that crashes,
                    means NO (default deny). The question shows the real effect ("delete task 4: Book dentist
                    appointment"), never a bare id.
    4 run once      a tool that fails is reported, never retried: a repeated write is worse than one failure.
    5 cut           the result is cut to MAX_RESULT_CHARS with " [truncated]", so no result floods the next agent.
"""
import json
from dataclasses import dataclass
from typing import Any, Callable

from desk_tools import TOOLS

MAX_RESULT_CHARS = 300     # the longest tool result handed back to any agent

Approve = Callable[[str, dict, str], bool]     # (tool name, args, plain words) -> allowed?


@dataclass
class Outcome:
    """What happened to one proposed action. kind is "ok", "error" or "denied"; text is what the agent reads."""
    kind: str
    text: str
    tool: str
    args: dict


def cut(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    """Context control: keep the first `limit` characters and mark the cut, so a reader knows something is missing."""
    return text if len(text) <= limit else text[:limit] + " [truncated]"


def args_text(args: dict) -> str:
    """Arguments as JSON text with sorted keys, the same spelling everywhere (log, report, tests)."""
    return json.dumps(args, sort_keys=True, default=str)


def run_tool(name: str, args: Any, desk: Any, *, allowed: list[str], approve: "Approve | None",
             actor: str, run: Any = None) -> Outcome:
    """Check, gate, run once, cut. Never raises: every problem comes back as an Outcome the agent can read."""
    args = args if isinstance(args, dict) else {}
    call = f"{name} {args_text(args)}"

    def done(kind: str, text: str, level: str = "INFO") -> Outcome:
        """Log the outcome once, in one place, and hand it back."""
        if run is not None:
            run.log("tool", actor, f"{call}  ->  {kind}: {cut(text, 160)}", level=level, tool=name, outcome=kind)
        return Outcome(kind, cut(text), name, args)

    # 1. allow-list (least privilege): an agent may use only the tools it was given
    if name not in allowed:
        return done("error", f"tool {name} is not allowed for {actor}", "WARN")
    # 2. input check: problems go back as text, nothing runs
    tool = TOOLS.get(name)
    if tool is None:
        return done("error", f"unknown tool {name}", "WARN")
    try:
        problem = tool.validate(args)
    except Exception as err:   # a crashing check is a refusal, never a pass
        problem = f"input check crashed: {err}"
    if problem:
        return done("error", problem, "WARN")
    # 3. the gate: irreversible actions need a human yes; no answer means no
    if tool.risk == "irreversible":
        allowed_by_human = False                  # default deny: stays False unless a human says yes
        words = call
        try:
            if tool.describe:
                words = tool.describe(args, desk)  # plain words, so the human sees the real effect
            if approve is not None:
                allowed_by_human = bool(approve(name, args, words))
        except Exception:
            allowed_by_human = False              # a crash in the approver or describe is a refusal
        if run is not None:
            run.log("gate", actor, f"{words}  ->  {'approved' if allowed_by_human else 'denied'}",
                    level="INFO" if allowed_by_human else "WARN", decision="approved" if allowed_by_human else "denied")
        if not allowed_by_human:
            return done("denied", f"{call} was not approved by the human. Do not retry it.", "WARN")
    # 4. run once: a failure is reported, never retried
    try:
        result = tool.run(args, desk)
    except Exception as err:
        return done("error", str(err), "WARN")
    # 5. cut: no result may flood the next agent
    return done("ok", result)


def approve_yes(_name: str, _args: dict, _words: str) -> bool:
    """An approver that always says yes. For demos only: a rubber stamp is not a gate."""
    return True


def approve_no(_name: str, _args: dict, _words: str) -> bool:
    """An approver that always says no. The safe default for unattended runs."""
    return False


def make_ask(input_fn: Callable[[str], str] = input, out: Callable[[str], None] = print) -> Approve:
    """An approver that asks a person in the terminal. Only "y" or "yes" means yes."""
    def ask(_name: str, _args: dict, words: str) -> bool:
        """Print the plain-words question and read the answer."""
        out(f"APPROVAL NEEDED: {words}. Cannot be undone. Allow? [y/N]")
        try:
            return input_fn("> ").strip().lower() in ("y", "yes")
        except EOFError:          # no person at the keyboard: no answer means no
            return False
    return ask
