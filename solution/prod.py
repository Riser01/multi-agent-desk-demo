"""PM-2 reference solution: a notional cost meter with a hard ceiling, per-role model routing, and a release stamp.

WHAT IT IS
    * PRICES / CostMeter   turns every model call's tokens into notional US dollars and stops the turn (status
                           "cost-ceiling") the moment the total goes over the ceiling you set with /ceiling.
    * ROUTING              routine roles (supervisor, workers, executor) go to the cheaper model; judgement roles
                           (planner, reviewer, single) go to the stronger one.
    * version_stamp()      labels every run with its release (stable 1.0.0 / canary 1.1.0) and a short hash of what
                           actually drives behaviour: the prompts, the routing table, the setup and the LangGraph version.

WHY IT IS NEEDED
    A team makes 5 to 7 model calls where one agent makes 1, so cost has to be measured, not guessed, and capped in code
    (a model cannot be trusted to stop itself). The stamp answers "which version produced this run?" when a canary
    misbehaves and you /rollback: same prompts and routing = same hash, whatever the track label says.

WHAT GOES WRONG WITHOUT IT
    No ceiling: a looping live run spends until the call cap. No routing: every routine step pays the strong model's
    price. No stamp: two runs that behave differently cannot be told apart in logs/runs.jsonl.

HONEST LABELS
    Prices are list prices per 1M tokens, read 2026-11-24 from Google's Gemini API pricing page (research note c2-01).
    Offline, the stand-in's tokens are estimates (~4 characters per token), so every dollar figure is notional.
    Free-tier keys are billed $0; these numbers show what the same traffic would cost at list price.
"""
import hashlib
import importlib
import importlib.metadata
import json

import llm

# List prices per 1M tokens (notional, read 2026-11-24 from the Gemini API pricing page; re-check before quoting)
PRICES = {
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50},
}
PRICES_CHECKED = "2026-11-24"

# Route routine steps to the cheaper model, judgement steps (planner, reviewer) to the stronger model
ROUTING = {
    "single": "gemini-3.5-flash-lite",
    "supervisor": "gemini-2.5-flash-lite",
    "executor": "gemini-2.5-flash-lite",
    "tasks_worker": "gemini-2.5-flash-lite",
    "calendar_worker": "gemini-2.5-flash-lite",
    "planner": "gemini-3.5-flash-lite",
    "reviewer": "gemini-3.5-flash-lite",
}

RELEASES = {"stable": "1.0.0", "canary": "1.1.0"}
PROMPT_MODULES = ("app", "two_agent", "team")   # every *_PROMPT string in these files is part of the hash


class CostMeter:
    """Tracks per-turn notional USD cost and enforces an optional hard ceiling in code."""

    def __init__(self, ceiling: "float | None" = None):
        self.ceiling = ceiling
        self.total_usd = 0.0
        self.calls = 0
        self.in_tokens = 0
        self.out_tokens = 0

    def charge(self, role: str, reply: llm.Reply) -> float:
        # Unknown names (e.g. "stand-in" with no routing) are priced as the stronger model: never under-count.
        rate = PRICES.get(reply.model, PRICES["gemini-3.5-flash-lite"])
        usd = (reply.input_tokens * rate["in"] + reply.output_tokens * rate["out"]) / 1_000_000.0
        self.total_usd += usd
        self.calls += 1
        self.in_tokens += reply.input_tokens
        self.out_tokens += reply.output_tokens
        return usd

    def check(self) -> None:
        # llm.ask_json calls this right after every charge, so the turn stops on the call that crossed the line.
        if self.ceiling is not None and self.total_usd > self.ceiling:
            raise llm.CostCeilingReached(
                f"cost ceiling reached: ${self.total_usd:.6f} is over ${self.ceiling:.6f} (notional)"
            )


def _langgraph_version() -> str:
    try:
        return importlib.metadata.version("langgraph")
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def collect_prompts() -> dict[str, str]:
    """Every module-level *_PROMPT string in app.py, two_agent.py and team.py (files not built yet are skipped)."""
    prompts: dict[str, str] = {}
    for mod_name in PROMPT_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError as err:
            if err.name == mod_name:
                continue
            raise
        for attr in sorted(dir(mod)):
            value = getattr(mod, attr)
            if attr.endswith("_PROMPT") and isinstance(value, str):
                prompts[f"{mod_name}.{attr}"] = value
    return prompts


def version_stamp(setup: str, routing: dict, track: str = "stable") -> dict:
    """Stamp a run with its release track and an 8-character hash of prompts + routing + setup + LangGraph version.

    The track is shown separately and is NOT in the hash: /rollback changes the label, while the hash only changes
    when something that drives behaviour changes (a prompt edit, a routing change, a LangGraph upgrade).
    """
    clean_track = track if track in RELEASES else "stable"
    lg_version = _langgraph_version()
    payload = json.dumps(
        {"setup": setup, "routing": routing, "langgraph": lg_version, "prompts": collect_prompts()},
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return {
        "release": RELEASES[clean_track],
        "track": clean_track,
        "setup": setup,
        "prompt_hash": digest,
        "langgraph": lg_version,
        "routing": dict(routing),
    }
