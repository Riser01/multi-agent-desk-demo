"""The production layer: a cost meter with a ceiling, model routing per role, and a version stamp on every run. W7-7.

A team multiplies model calls, so it multiplies the bill, and nobody sees a bill per task unless code adds it up.
The meter here prices every call as it happens (tokens x list price) and keeps the total for the run. The CEILING
turns that number into a rule: once the run's cost passes it, CostMeter.check() raises CostCeilingReached and
run_graph stops the run with status "cost-ceiling". A runaway loop costs at most the ceiling, not your month.

Routing is the cheap half of cost control: not every role needs the same model. Routing decisions and single tool
calls go to the cheapest model; the planner and the reviewer, where judgement matters, get a stronger one. The
version stamp makes every run answer "which prompts, which models, which code?", which is what you need the day a
change makes things worse and you have to roll back.

Honest numbers. On the free tier you pay nothing, so every cost here is NOTIONAL: what the same run would cost on a
paid key, at the list price on the date in data/prices.json. Offline, token counts are estimates (characters / 4),
so offline costs are estimates of estimates. Only `--live` runs give real token counts.

What to look at
    load_prices(), price_usd()   list prices from data/prices.json (dated, with the source URL), per 1M tokens.
    CostMeter                    charge() adds one call to the bill; check() enforces the ceiling.
    ROUTING                      role -> model name. Change it and the version stamp changes with it.
    version_stamp()              app version, a short hash of every prompt, the model per role, the LangGraph version.
"""
import hashlib
import json
import os
from importlib.metadata import version as package_version

from llm import CostCeilingReached

APP_VERSION = "1.0.0"
PRICES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "prices.json")
CHEAP, STRONG = "gemini-2.5-flash-lite", "gemini-3.5-flash-lite"
ROUTING = {"agent": STRONG, "planner": STRONG, "reviewer": STRONG,          # judgement: the stronger model
           "executor": CHEAP, "supervisor": CHEAP, "tasks": CHEAP, "calendar": CHEAP}   # one routing or tool choice: cheap


def load_prices(path: str = PRICES_PATH) -> dict:
    """The price file: models with input and output USD per 1M tokens, the source and the date it was read."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def price_usd(model: str, input_tokens: int, output_tokens: int, prices: dict) -> float:
    """What one call costs at list price. An unknown model is priced as the file's fallback model, never as free."""
    rate = prices["models"].get(model) or prices["models"][prices["fallback"]]
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000


class CostMeter:
    """Adds up the notional cost of a run, per role, and stops the run once it passes the ceiling."""

    def __init__(self, ceiling_usd: "float | None" = None, prices: "dict | None" = None):
        """ceiling_usd=None means 'meter, but never stop'."""
        self.ceiling_usd = ceiling_usd
        self.prices = prices or load_prices()
        self.price_date = self.prices.get("read_on", "?")
        self.total_usd = 0.0
        self.calls = 0
        self.by_role: dict[str, float] = {}

    def charge(self, role: str, reply) -> float:
        """Add one model reply to the bill and return what it cost. Never raises: check() is the rule."""
        usd = price_usd(reply.model, reply.input_tokens, reply.output_tokens, self.prices)
        self.total_usd += usd
        self.calls += 1
        self.by_role[role] = self.by_role.get(role, 0.0) + usd
        return usd

    def check(self) -> None:
        """The ceiling: raise CostCeilingReached once the run's total is over it."""
        if self.ceiling_usd is not None and self.total_usd > self.ceiling_usd:
            raise CostCeilingReached(f"cost ceiling reached: ${self.total_usd:.6f} is over ${self.ceiling_usd:.6f} (notional)")


def prompt_version() -> str:
    """A short hash of every agent prompt: change one word in any prompt and the stamp changes."""
    from baseline import AGENT_PROMPT
    from executor import EXECUTOR_PROMPT
    from graph import SINGLE_PROMPT
    from planner import PLANNER_PROMPT
    from reviewer import REVIEWER_PROMPT
    from supervisor import SUPERVISOR_PROMPT
    from workers import WORKER_PROMPT
    text = "\n".join([AGENT_PROMPT, SINGLE_PROMPT, PLANNER_PROMPT, EXECUTOR_PROMPT, SUPERVISOR_PROMPT, WORKER_PROMPT, REVIEWER_PROMPT])
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def version_stamp(setup: str, routing: "dict | None" = None) -> dict:
    """Everything that defines this run's behaviour, small enough to print on every run and every report."""
    return {"app": APP_VERSION, "setup": setup, "prompts": prompt_version(), "langgraph": package_version("langgraph"),
            "models": dict(routing if routing is not None else ROUTING)}
