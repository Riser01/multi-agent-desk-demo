"""The shared state of the team, and the Team kit every agent node is handed. Built in W7-1.

A team of agents needs one place where the work so far lives, so that each agent can pick up from it. In LangGraph
that place is the graph STATE: a typed dictionary that every node reads, and that every node updates by returning
only the keys it changed. Two kinds of key behave differently, and that difference is the main idea of this file.
A plain key is OVERWRITTEN by the last node that writes it (the plan, the step counter, the status). A key with a
REDUCER is MERGED: `Annotated[list, operator.add]` means "append what this node returns to what is already there".
The results and the handoffs are append-only logs, so no agent can ever erase what another one did, and two agents
writing in the same step (the parallel stretch in extras/) cannot overwrite each other.

The desk itself is NOT in the state. It is the world, like a database: agents only ask, and every change goes through
the gate. So the Team dataclass carries the run-time things that are not state: the model, the desk, the approver,
the run log, and (from W7-7) the cost meter and the model routing. Each node gets the Team by closure (see graph.py).

What to look at
    TeamState      every key, which phase adds it, and which keys have reducers (results, handoffs).
    new_state()    the starting state for a goal, with every counter at zero, so no node has to guess a default.
    Team.ask()     how any agent asks its model: one line, so model choice and cost metering live in one place.
    Team.act()     how any agent touches the desk: always through gate.run_tool, with that agent's allow-list.
    finished()     the one rule for "is this run over?": a status has been set. Edges use it.
"""
import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, TypedDict

from gate import Outcome, approve_no, run_tool
from llm import ask_json


class TeamState(TypedDict, total=False):
    """Everything the agents share. Plain keys are overwritten; Annotated keys are merged by their reducer."""
    goal: str                                        # the user's words; no agent rewrites them
    results: Annotated[list[dict], operator.add]     # append-only: one {"agent", "task", "kind", "text"} per action
    handoffs: Annotated[list[dict], operator.add]    # append-only: every handoff sent (W7-2), "what each agent saw"
    turns: int                                       # model turns used by the looping agent (the turn cap reads it)
    plan: list[dict]                                 # the planner's steps (W7-2); overwritten, never merged
    step: int                                        # index of the next plan step to execute (W7-2)
    next: str                                        # the supervisor's route (W7-4)
    pending: dict                                    # an irreversible action waiting for the reviewer (W7-6)
    review_rounds: int                               # reviewer rejections for the current action (W7-6)
    feedback: str                                    # the reviewer's reason, shown to the worker on its retry (W7-6)
    status: str                                      # set by code when the run is over; never by a model's claim
    answer: str                                      # the final answer for the user


def new_state(goal: str) -> TeamState:
    """The starting state: the goal, empty logs and every counter at zero."""
    return TeamState(goal=goal, results=[], handoffs=[], turns=0, plan=[], step=0, next="", pending={},
                     review_rounds=0, feedback="", status="", answer="")


def finished(state: TeamState) -> bool:
    """A run is over exactly when a status has been set."""
    return bool(state.get("status"))


def result_lines(state: TeamState) -> list[str]:
    """The results so far as '- agent: task -> kind: text' lines, the 'done so far' an agent is shown."""
    return [f"- {r['agent']}: {r['task']} -> {r['kind']}: {r['text']}" for r in state.get("results", [])]


@dataclass
class Team:
    """The run-time kit that is not state: model, desk, approver, run log, and from W7-7 meter and routing."""
    model: Callable
    desk: Any
    run: Any
    approve: Callable = approve_no                    # default deny: an unattended run never says yes
    meter: Any = None                                 # prod.CostMeter from W7-7; None means "not metered"
    routing: dict = field(default_factory=dict)       # role -> model name from W7-7; empty means the default model

    def ask(self, role: str, system: str, user: str) -> dict:
        """Ask this role's model and return its JSON reply. Logging, metering and one re-ask happen in llm.ask_json."""
        data, _reply = ask_json(self.model, role, system, user, run=self.run, meter=self.meter,
                                model_name=self.routing.get(role))
        return data

    def act(self, actor: str, tool: str, args: Any, allowed: list[str]) -> Outcome:
        """Let an agent touch the desk: always through the gate, always with that agent's own allow-list."""
        return run_tool(tool, args, self.desk, allowed=allowed, approve=self.approve, actor=actor, run=self.run)
