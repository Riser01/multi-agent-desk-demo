"""Small helpers shared by the tests: a quiet run log, a desk with chosen items, a team with a scripted model.

Tests must give the same answer every time, with no key and no network, so every model here is llm.FakeModel: it
replays exact scripted replies per role and records every message it was sent. That record is how a test checks
"what each agent saw", which is the heart of this week. The run log is quiet and writes no files, so a test run
leaves nothing behind.

What to look at
    quiet_run()   an obs.Run that prints nothing and saves nothing, but still collects every event.
    desk_with()   a Desk with the given task texts (ids 1, 2, 3 ...) and optional events after them.
    team_with()   a Team around a FakeModel script, a desk and an approver. Returns (team, model).
    call()        one tool-call reply: call("add_task", text="x") -> {"tool": "add_task", "args": {"text": "x"}}.
    saw()         the messages one role was sent, in order.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)   # make the project folder importable however the tests are started

import obs  # noqa: E402
from desk_tools import Desk, load_desk  # noqa: E402
from gate import approve_no  # noqa: E402
from llm import FakeModel  # noqa: E402


def seed(name: str) -> str:
    """The path of a seed file in data/seeds/."""
    return os.path.join(ROOT, "data", "seeds", f"{name}.json")


def quiet_run(name: str = "test", **kwargs) -> obs.Run:
    """A run log that prints nothing and writes no files, but keeps every event for the test to read."""
    return obs.Run(name, quiet=True, save=False, **kwargs)


def desk_with(*tasks: str, events: tuple = ()) -> Desk:
    """A desk holding these task texts (ids 1..n) and these (when, title) events (ids after the tasks)."""
    desk = Desk()
    for text in tasks:
        desk.tasks.append({"id": desk.next_id, "text": text, "done": False, "archived": False})
        desk.next_id += 1
    for when, title in events:
        desk.events.append({"id": desk.next_id, "when": when, "title": title})
        desk.next_id += 1
    return desk


def team_with(script, desk=None, approve=approve_no, **kwargs):
    """A Team around a scripted FakeModel. Returns (team, model) so the test can read model.calls."""
    from state import Team
    model = FakeModel(script)
    team = Team(model=model, desk=desk if desk is not None else load_desk(seed("desk_week")), run=quiet_run(),
                approve=approve, **kwargs)
    return team, model


def call(tool: str, **args) -> dict:
    """One scripted tool-call reply."""
    return {"tool": tool, "args": args}


def saw(model: FakeModel, role: str) -> list[str]:
    """Every message the given role was sent, in order: what that agent saw."""
    return [c["user"] for c in model.calls if c["role"] == role]


def kinds(run: obs.Run, kind: str) -> list[dict]:
    """The events of one kind in a run log."""
    return [e for e in run.events if e["kind"] == kind]
