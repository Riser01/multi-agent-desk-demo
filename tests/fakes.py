"""Test helpers: a scripted model that says exactly what each role should answer, and a recorder for graph configs.

The offline stand-in in llm.py always gives the same, sensible answers. Some safety limits only matter when a model
misbehaves (a supervisor that never finishes, a worker that asks for the wrong tool, a reviewer that changes its
mind). ScriptedModel plays those misbehaving models so the limits can be tested offline, with no key and no network.
"""
import json
from contextlib import contextmanager
from unittest import mock

import llm


class ScriptedModel:
    """Callable like llm.make_model(): model(role, system, user, model_name=None) -> llm.Reply.

    script maps a role to a list of JSON payloads (used in order, the last one repeats) or to a function of the user
    text that returns a payload. Every prompt is recorded in .seen[role]; .calls counts all calls.
    """
    label = "scripted test model"

    def __init__(self, script: dict):
        self.script = script
        self.seen: dict[str, list[str]] = {}
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    def count(self, role: str) -> int:
        return len(self.seen.get(role, []))

    def __call__(self, role, system, user, model_name=None):
        self.calls += 1
        self.seen.setdefault(role, []).append(user)
        rule = self.script.get(role, {"tool": "list_tasks", "args": {}})
        if callable(rule):
            payload = rule(user)
        elif isinstance(rule, list):
            idx = min(self.count(role) - 1, len(rule) - 1)
            payload = rule[idx]
        else:
            payload = rule
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return llm.Reply(text=text, input_tokens=10, output_tokens=5, model=model_name or "stand-in",
                         seconds=0.0, source="fake", estimated=True)


@contextmanager
def record_graph_configs():
    """Record the `config` passed to every LangGraph invoke() inside the block (to check recursion_limit)."""
    from langgraph.pregel import Pregel
    seen: list = []
    original = Pregel.invoke

    def spy(self, input, config=None, **kwargs):
        seen.append(config)
        return original(self, input, config, **kwargs)

    with mock.patch.object(Pregel, "invoke", spy):
        yield seen
