"""The model seam: every agent asks a model through ONE function here, so a run can be fake, replayed or live. PROVIDED.

A team of agents makes many model calls, and on a free key every call is quota. So nothing in this repo calls a real
model unless you ask for it with `--live`. By default a run uses the offline stand-in (stand_in.py): a rule-based
fake that answers every agent role, costs nothing and gives the same answer every time. Tests use FakeModel, which
replays exact scripted replies. A recorded run can be replayed with ReplayModel. Only GeminiModel talks to Google.

All four have the same shape:  model(role, system, user, model_name=None) -> Reply
so an agent node cannot tell which one it is talking to, and the tests can check exactly what each agent saw.

What to look at
    Reply           text plus usage: input and output tokens, model name, seconds, and where it came from
                    (fake, replay or live). Offline token counts are ESTIMATES (characters / 4) and say so.
    ask_json()      the one call every agent makes: logs what the agent saw, calls the model, logs the reply with
                    time and tokens, charges the cost meter (W7-7: meter.charge() then meter.check()), and parses
                    the JSON. One bad-JSON reply gets one
                    polite re-ask, because asking again changes nothing; a second bad reply is a ModelError.
    Capped          a per-run call cap. When a run reaches max_calls model calls, CallCapReached stops it. This is
                    quota safety, and the reason a looping team cannot burn your free tier.
    GeminiModel     the live adapter (google-genai). A 429 (quota) or 503 (busy) is waited out with growing pauses up
                    to LLM_MAX_WAIT_SECONDS, then reported in plain words. The key is read from the environment and
                    never printed.
    ReplayModel     plays back a saved file. A file with "kind": "scripted" was written by hand to show a failure
                    shape and is labelled REPLAYED, never passed off as a live run. `--record` writes a real one.
    make_model()    builds the right model for --mode fake|replay|live, wrapped in the call cap.
"""
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

DEFAULT_LIVE_MODEL = "gemini-3.5-flash-lite"   # free tier "yes" on the Gemini pricing page, read 2026-11-24
# Which model a call uses: the role's entry in prod.ROUTING (from W7-7) wins; without routing, GEMINI_MODEL, else the default.
DEFAULT_MAX_CALLS = 30                          # per-run call cap; agent.py --max-calls changes it
RETRY_CODES = {429, 500, 502, 503, 504}         # busy or quota: safe to ask again, a model call changes nothing


class ModelError(RuntimeError):
    """The model failed or kept replying with something that is not the JSON we asked for."""


class CallCapReached(RuntimeError):
    """The run used its whole model-call budget. Raised instead of making one more call."""


class CostCeilingReached(RuntimeError):
    """The run's notional cost passed its ceiling. Raised by your CostMeter.check() in W7-7; run_graph stops the run."""


@dataclass
class Reply:
    """One model answer plus what it cost to get it."""
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    seconds: float
    source: str              # "fake", "replay" or "live"
    estimated: bool = True   # True when the token counts are characters / 4, not the provider's own count


def estimate_tokens(text: str) -> int:
    """A rough token count for offline runs: about four characters per token. Always labelled as an estimate."""
    return max(1, len(text) // 4)


def parse_json(text: str) -> dict:
    """The first JSON object in a reply, even inside a fenced block or after chatter. Raises ValueError otherwise."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in the reply: {text.strip()[:80]!r}")
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError as err:
        raise ValueError(f"the reply is not valid JSON: {text.strip()[:80]!r}") from err
    if not isinstance(value, dict):
        raise ValueError("the reply is JSON but not an object")
    return value


class FakeModel:
    """Scripted replies per role, for tests. Records every call, so a test can check exactly what each agent saw."""

    def __init__(self, script: "dict[str, list[Any]] | Callable[[str, str, str], Any]", model_name: str = "fake-model"):
        """script maps a role to its replies in order (dicts are sent as JSON); the last one repeats. Or a function."""
        self.script = script
        self.model_name = model_name
        self.position: dict[str, int] = {}
        self.calls: list[dict] = []

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        """Return the next scripted reply for this role."""
        self.calls.append({"role": role, "system": system, "user": user, "model": model_name})
        if callable(self.script):
            answer = self.script(role, system, user)
        else:
            replies = self.script.get(role) or [{"final": f"no scripted reply for role {role}"}]
            index = self.position.get(role, 0)
            self.position[role] = index + 1
            answer = replies[min(index, len(replies) - 1)]
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return Reply(text, estimate_tokens(system + user), estimate_tokens(text), model_name or self.model_name, 0.0, "fake")

    def roles(self) -> list[str]:
        """The roles that were asked, in order. Handy for checking the route a run took."""
        return [c["role"] for c in self.calls]


class ReplayModel:
    """Plays back a saved run. Each role gets its saved replies in order; running out is an error, not a guess."""

    def __init__(self, path: str):
        """Load a replay file: {"label", "kind": "scripted"|"recorded", "replies": [{"role", "text", ...}]}."""
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.kind = data.get("kind", "scripted")
        self.label = f"REPLAYED ({self.kind}): {data.get('label', path)}"
        self.queue: dict[str, list[dict]] = {}
        for item in data["replies"]:
            self.queue.setdefault(item["role"], []).append(item)

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        """The next saved reply for this role, with saved token counts when the file has them."""
        if not self.queue.get(role):
            raise ModelError(f"the replay file has no more replies for role '{role}'")
        item = self.queue[role].pop(0)
        recorded = "input_tokens" in item and self.kind == "recorded"
        return Reply(item["text"], item.get("input_tokens") or estimate_tokens(system + user),
                     item.get("output_tokens") or estimate_tokens(item["text"]),
                     item.get("model") or model_name or "replay", float(item.get("seconds", 0.0)), "replay", not recorded)


class GeminiModel:
    """The live adapter: one Gemini call per ask, JSON replies, temperature 0, quota errors waited out."""

    def __init__(self, model_name: "str | None" = None):
        """Read the key and default model from the environment. Fails at once, in plain words, if there is no key."""
        self.key = os.environ.get("GEMINI_API_KEY", "")
        if not self.key:
            raise ModelError("No API key. Put GEMINI_API_KEY in .env (see .env.example), or run without --live.")
        self.default = model_name or os.environ.get("GEMINI_MODEL") or DEFAULT_LIVE_MODEL
        try:
            from google import genai               # imported only for live runs, so offline needs no install
        except ImportError:
            raise ModelError("Live runs need the Gemini package: pip install -r requirements.txt") from None
        self.genai = genai
        self.client = genai.Client(api_key=self.key)

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        """One generate_content call. Retries only busy or quota errors, with growing pauses, up to a total cap."""
        from google.genai import errors, types
        model = model_name or self.default
        config = types.GenerateContentConfig(system_instruction=system, temperature=0, response_mime_type="application/json")
        cap = float(os.environ.get("LLM_MAX_WAIT_SECONDS", "70"))
        waited, attempt, started = 0.0, 0, time.time()
        while True:
            try:
                response = self.client.models.generate_content(model=model, contents=user, config=config)
                break
            except errors.APIError as err:
                delay = 2.0 * (2 ** attempt) + random.random()     # 2s, 4s, 8s ... plus jitter
                if err.code in RETRY_CODES and waited + delay <= cap:
                    time.sleep(delay)
                    waited, attempt = waited + delay, attempt + 1
                    continue
                hint = (" (free-tier quota for this model: wait a minute; to switch models set GEMINI_MODEL in .env before W7-7,"
                        " or change ROUTING in prod.py from W7-7 on)") if err.code == 429 else ""
                raise ModelError(f"model API error {err.code}{hint}") from None   # no key, no request body in the message
        usage = response.usage_metadata
        text = response.text or ""
        if not text.strip():
            raise ModelError("the model returned no text (blocked or cut off)")
        return Reply(text, (usage and usage.prompt_token_count) or estimate_tokens(system + user),
                     (usage and usage.candidates_token_count) or estimate_tokens(text),
                     model, round(time.time() - started, 2), "live", not (usage and usage.prompt_token_count))


class Capped:
    """Wraps any model with a per-run call cap, and optionally records every reply to a replay file."""

    def __init__(self, model: Any, max_calls: int = DEFAULT_MAX_CALLS, record: bool = False):
        """max_calls is the budget for one run. record=True keeps every reply so save() can write a replay file."""
        self.model, self.max_calls, self.calls = model, max_calls, 0
        self.recorded: "list[dict] | None" = [] if record else None
        self.label = getattr(model, "label", "")

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        """Refuse the call once the budget is spent; otherwise pass it through."""
        if self.calls >= self.max_calls:
            raise CallCapReached(f"call cap reached: {self.max_calls} model calls in this run")
        self.calls += 1
        reply = self.model(role, system, user, model_name)
        if self.recorded is not None:
            self.recorded.append({"role": role, **{k: v for k, v in asdict(reply).items() if k != "source"}})
        return reply

    def save(self, path: str, label: str) -> None:
        """Write the recorded replies as a replay file (kind "recorded"): prompts are not saved, only replies."""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"label": label, "kind": "recorded", "recorded_on": time.strftime("%Y-%m-%d"),
                       "replies": self.recorded or []}, handle, indent=1)


def make_model(mode: str = "fake", *, replay_path: "str | None" = None, max_calls: int = DEFAULT_MAX_CALLS,
               record: bool = False) -> Capped:
    """The model for a run: "fake" (offline stand-in, the default), "replay" (a saved file) or "live" (Gemini)."""
    if mode == "fake":
        from stand_in import StandIn
        base: Any = StandIn()
    elif mode == "replay":
        if not replay_path:
            raise ModelError("--mode replay needs --replay PATH (a file in data/replays/)")
        base = ReplayModel(replay_path)
    elif mode == "live":
        base = GeminiModel()
    else:
        raise ModelError(f"unknown mode {mode!r}: use fake, replay or live")
    return Capped(base, max_calls=max_calls, record=record)


def ask_json(model: Callable, role: str, system: str, user: str, *, run: Any = None, meter: Any = None,
             model_name: "str | None" = None) -> "tuple[dict, Reply]":
    """Ask one agent's model and return (parsed JSON, reply). Logs what the agent saw and what it said, charges the meter."""
    if run is not None:
        run.log("saw", role, user, chars=len(user))        # "what each agent saw": the exact message, every time
    reply = model(role, system, user, model_name)
    _account(reply, role, run, meter)
    try:
        return parse_json(reply.text), reply
    except ValueError:
        if run is not None:
            run.log("model", role, f"reply was not JSON, asking once more: {reply.text[:80]!r}", level="WARN")
        again = model(role, system + "\nYour last reply was not valid JSON. Reply with ONE JSON object only.", user, model_name)
        _account(again, role, run, meter)
        try:
            return parse_json(again.text), again
        except ValueError as err:
            raise ModelError(f"{role} replied twice without valid JSON: {err}") from None


def _account(reply: Reply, role: str, run: Any, meter: Any) -> None:
    """Log one reply with its time and tokens, then charge the cost meter (which may stop the run at the ceiling)."""
    if run is not None:
        run.model_call(role, reply)
    if meter is not None:
        usd = meter.charge(role, reply)       # adds this call to the bill; never raises
        if run is not None:
            run.log("cost", role, f"${usd:.6f} this call, ${meter.total_usd:.6f} so far (notional)", usd=usd,
                    total_usd=meter.total_usd, price_date=getattr(meter, "price_date", ""))
        meter.check()                          # raises CostCeilingReached once the bill passes the ceiling
