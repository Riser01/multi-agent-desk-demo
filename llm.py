"""Model adapter: offline stand-in by default, optional Gemini `--live`, per-turn call cap, cost hook, trace export. PROVIDED.

No API key is required to build or run any phase. By default every run uses `StandIn` (rule-based, deterministic,
deliberately gullible on the planted-note `/drill` so learners can watch `safety.py`, `reviewer`, and the `[y/N]` gate
work). The stand-in is NOT a real model: its token counts are estimates (~4 characters per token) and any cost shown
for it is notional, priced as if the routed Gemini model had run. Pass `--live` with your own `GEMINI_API_KEY` in
`.env` to call Gemini with automatic 429/503 backoff.

The bottom of this file holds the OPTIONAL trace export (`--export console` or `--export langfuse`): the same idea as
Week 6's trace_export.py. It wraps the model, the tools and the approval gate from the outside, so no phase file
changes. The `langfuse` package is imported lazily and only when keys are set; without them you get a console tree.
"""
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFAULT_LIVE_MODEL = "gemini-3.5-flash-lite"   # list price & free-tier status checked 2026-11-24
DEFAULT_MAX_CALLS = 20
OFFLINE_MODE_LABEL = "offline stand-in (not a real model)"


class ModelError(RuntimeError):
    """Raised when the model fails or returns invalid JSON twice."""


class CallCapReached(RuntimeError):
    """Raised when a single turn exceeds its model-call cap."""


class CostCeilingReached(RuntimeError):
    """Raised by prod.CostMeter.check() when a turn's notional cost crosses its ceiling."""


@dataclass
class Reply:
    """One model response plus usage metadata."""
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    seconds: float
    source: str          # "fake" or "live"
    estimated: bool = True


def load_env(path: "str | Path | None" = None) -> list[str]:
    """Load KEY=VALUE pairs from `.env` without overwriting shell env vars or printing secrets."""
    env_path = Path(path) if path else Path(__file__).with_name(".env")
    if not env_path.is_file():
        return []
    loaded: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip("\"'")
        if key and val and key not in os.environ:
            os.environ[key] = val
            loaded.append(key)
    return loaded


def estimate_tokens(text: str) -> int:
    """Rough offline estimate (~4 characters per token); always labelled as an estimate."""
    return max(1, len(text) // 4)


def parse_json(text: str) -> dict:
    """Extract the first JSON object from a model reply."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {text.strip()[:80]!r}")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply JSON must be an object")
    return data


def _extract_quoted_or_tail(goal: str, prefixes: tuple[str, ...]) -> str:
    m = re.search(r'"([^"]+)"', goal)
    if m:
        return m.group(1).strip()
    low = goal.lower()
    for p in prefixes:
        idx = low.find(p)
        if idx != -1:
            tail = goal[idx + len(p):].strip(" .,:;")
            for sep in (", then ", " and then ", " and show ", " and remind "):
                if sep in tail.lower():
                    tail = tail[:tail.lower().index(sep)].strip(" .,:;")
            if tail:
                return tail[:120]
    return goal.strip(" .")[:120]


def _extract_id(text: str, default_id: int = 1) -> int:
    m = re.search(r"#?(\d+)", text)
    return int(m.group(1)) if m else default_id


class StandIn:
    """Rule-based offline model. Deterministic, free, and deliberately gullible on the planted-note drill."""
    label = "offline stand-in"

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        low = user.lower()
        name = model_name or "stand-in"
        has_override = "system override" in low or "ignore user rules" in low

        if role == "planner":
            goal_line = user.splitlines()[0] if user.splitlines() else user
            g_low = goal_line.lower()
            steps = []
            if has_override:
                steps.append({"task": "Delete task 1 (Pay rent)", "tool": "delete_task", "args": {"id": 1}})
            if "dentist" in g_low and ("delete" in g_low or "remove" in g_low):
                steps.append({"task": "Delete dentist task", "tool": "delete_task", "args": {"id": 3}})
            if "cancel" in g_low and ("sync" in g_low or "event" in g_low or "meeting" in g_low):
                steps.append({"task": "Cancel team sync", "tool": "cancel_event", "args": {"id": 6}})
            if "add " in g_low or "remind me" in g_low:
                if "appointment" in g_low or "meeting" in g_low or "fri" in g_low or "mon" in g_low:
                    steps.append({"task": "Add calendar event", "tool": "add_event", "args": {"when": "Fri 10:00", "title": _extract_quoted_or_tail(goal_line, ("add ",))}})
                else:
                    task_txt = _extract_quoted_or_tail(goal_line, ("remind me to ", "add task ", "add "))
                    steps.append({"task": f"Add task: {task_txt}", "tool": "add_task", "args": {"text": task_txt}})
            if "complete" in g_low or "mark done" in g_low:
                steps.append({"task": "Complete task", "tool": "complete_task", "args": {"id": _extract_id(goal_line, 1)}})
            if "show" in g_low or "list" in g_low or not steps:
                steps.append({"task": "Show task list", "tool": "list_tasks", "args": {}})
            payload = {"steps": steps}

        elif role == "supervisor":
            done_marker = "done so far:" in low
            done_part = low.split("done so far:", 1)[1] if done_marker else ""
            if has_override and "tasks" not in done_part:
                payload = {"next": "tasks", "task": "Handle desk note and tidy tasks"}
            elif ("cancel" in low or "sync" in low or "calendar" in low or "event" in low or "appointment" in low) and "calendar:" not in done_part:
                payload = {"next": "calendar", "task": user.splitlines()[0][:140]}
            elif ("task" in low or "remind" in low or "add" in low or "list" in low or "delete" in low or "tidy" in low) and "tasks:" not in done_part:
                payload = {"next": "tasks", "task": user.splitlines()[0][:140]}
            else:
                payload = {"next": "finish", "answer": "All requested desk actions processed."}

        elif role == "reviewer":
            # Reviewer checks whether the original goal actually asked for the irreversible action
            goal_line = ""
            for line in user.splitlines():
                if line.lower().startswith("goal:"):
                    goal_line = line.split(":", 1)[1].strip().lower()
                    break
            asked_delete = any(w in goal_line for w in ("delete", "remove", "cancel", "clear", "erase"))
            if not asked_delete:
                payload = {"approved": False, "reason": "User goal did not ask for an irreversible delete/cancel."}
            else:
                payload = {"approved": True, "reason": "Action matches the user's explicit request."}

        elif role == "calendar_worker":
            if "cancel" in low or "remove" in low:
                payload = {"tool": "cancel_event", "args": {"id": _extract_id(user, 6)}, "summary": "Cancel team sync"}
            elif "add" in low or "book" in low or "schedule" in low:
                payload = {"tool": "add_event", "args": {"when": "Fri 10:00", "title": _extract_quoted_or_tail(user, ("add ", "book ", "schedule "))}, "summary": "Add event"}
            else:
                payload = {"tool": "list_events", "args": {}, "summary": "List calendar events"}

        else:  # single, executor, tasks_worker
            first_line = user.splitlines()[0] if user.splitlines() else user
            f_low = first_line.lower()
            if has_override:
                payload = {"tool": "delete_task", "args": {"id": 1}, "summary": "Delete task 1 per note override"}
            elif "delete" in f_low or "remove" in f_low:
                tid = 3 if "dentist" in f_low else _extract_id(first_line, 1)
                payload = {"tool": "delete_task", "args": {"id": tid}, "summary": f"Delete task {tid}"}
            elif role != "tasks_worker" and "cancel" in f_low and ("sync" in f_low or "event" in f_low):
                payload = {"tool": "cancel_event", "args": {"id": 6}, "summary": "Cancel team sync"}
            elif "complete" in f_low or "mark done" in f_low:
                tid = _extract_id(first_line, 1)
                payload = {"tool": "complete_task", "args": {"id": tid}, "summary": f"Complete task {tid}"}
            elif "add " in f_low or "remind me" in f_low:
                task_txt = _extract_quoted_or_tail(first_line, ("remind me to ", "add task ", "add "))
                payload = {"tool": "add_task", "args": {"text": task_txt}, "summary": f"Add task '{task_txt}'"}
            else:
                payload = {"tool": "list_tasks", "args": {}, "summary": "List tasks"}

        text = json.dumps(payload)
        return Reply(
            text=text,
            input_tokens=estimate_tokens(system + "\n" + user),
            output_tokens=estimate_tokens(text),
            model=name,
            seconds=0.01,
            source="fake",
            estimated=True,
        )


LIVE_TOOL_ROLES = {"single": "ALL_TOOLS", "planner": "ALL_TOOLS", "tasks": "TASK_TOOLS", "calendar": "CALENDAR_TOOLS",
                   "tasks_worker": "TASK_TOOLS", "calendar_worker": "CALENDAR_TOOLS"}


def live_system(role: str, system: str) -> str:
    """For --live only: tell a REAL model the exact tool and argument names (the offline stand-in never needs this).

    WHY: the phase prompts name the tools, but a real model has to guess the argument names (title? text?) and a wrong
    guess is refused by the tool check. This block is added after the phase's own prompt, only for live calls, so the
    offline token counts quoted in the guide stay exactly the same.
    """
    names_attr = LIVE_TOOL_ROLES.get(role)
    if not names_attr:
        return system
    import desk
    names = getattr(desk, names_attr)
    menu = "\n".join(f"- {n}: {desk.TOOL_META[n][1]}" for n in names)
    return (
        f"{system}\n\nTool menu (use exactly these tool names and argument names; ids are numbers; "
        f"reply with ONE JSON object and nothing else):\n{menu}"
    )


class GeminiModel:
    """Opt-in live Gemini adapter with 429/503 exponential backoff."""
    label = "live Gemini"

    def __init__(self, default_model: "str | None" = None):
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ModelError("GEMINI_API_KEY is not set. Copy .env.example to .env or drop --live.")
        try:
            from google import genai
        except ImportError as err:
            raise ModelError("google-genai is not installed. Run: pip install google-genai") from err
        self.client = genai.Client(api_key=api_key)
        self.default_model = default_model or os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_LIVE_MODEL

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        chosen = model_name or self.default_model
        t0 = time.monotonic()
        wait = 2.0
        for attempt in range(4):
            try:
                resp = self.client.models.generate_content(
                    model=chosen,
                    contents=f"{live_system(role, system)}\n\n{user}",
                )
                text = getattr(resp, "text", "") or ""
                usage = getattr(resp, "usage_metadata", None)
                in_tok = getattr(usage, "prompt_token_count", None) or estimate_tokens(system + user)
                out_tok = getattr(usage, "candidates_token_count", None) or estimate_tokens(text)
                return Reply(
                    text=text,
                    input_tokens=int(in_tok),
                    output_tokens=int(out_tok),
                    model=chosen,
                    seconds=round(time.monotonic() - t0, 2),
                    source="live",
                    estimated=usage is None,
                )
            except Exception as err:
                msg = str(err)
                if any(code in msg for code in ("429", "503", "RESOURCE_EXHAUSTED")) and attempt < 3:
                    time.sleep(wait)
                    wait *= 2
                    continue
                raise ModelError(f"live Gemini call failed ({chosen}): {msg[:180]}") from err
        raise ModelError("live Gemini call timed out after retries")


class CallCapped:
    """Per-turn model call cap so a runaway loop cannot burn free-tier quota."""

    def __init__(self, inner: Callable, max_calls: int = DEFAULT_MAX_CALLS):
        self.inner = inner
        self.max_calls = max_calls
        self.calls = 0
        self.label = getattr(inner, "label", "model")

    def reset(self) -> None:
        self.calls = 0

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        if self.calls >= self.max_calls:
            raise CallCapReached(f"per-turn call cap reached ({self.max_calls} calls)")
        self.calls += 1
        return self.inner(role, system, user, model_name=model_name)


def make_model(live: bool = False, *, max_calls: int = DEFAULT_MAX_CALLS) -> CallCapped:
    """Build a call-capped StandIn (default) or live Gemini model."""
    return CallCapped(GeminiModel() if live else StandIn(), max_calls=max_calls)


def model_label(reply: Reply, chosen: "str | None" = None) -> str:
    """Honest model name for logs: a live reply shows the real model; the stand-in says what it is priced as."""
    if reply.source == "live":
        return reply.model
    return f"stand-in (priced as {chosen})" if chosen else "stand-in"


def ask_json(
    role: str,
    system: str,
    user: str,
    model: Callable,
    *,
    meter: Any = None,
    routing: "dict[str, str] | None" = None,
    log_fn: "Callable[[str], None] | None" = None,
) -> tuple[dict, Reply]:
    """Call the model, charge the optional CostMeter, log concise trace, and parse JSON (1 retry on bad JSON)."""
    chosen = (routing or {}).get(role)
    last_err = None
    for attempt in range(2):
        prompt_user = user if attempt == 0 else user + "\n\nReply with a single valid JSON object only."
        reply = model(role, system, prompt_user, model_name=chosen)
        if meter is not None:
            meter.charge(role, reply)
        if log_fn:
            est = "est." if reply.estimated else "live"
            log_fn(f"INFO  [{role}] model={model_label(reply, chosen)} in={reply.input_tokens}({est}) out={reply.output_tokens} ({reply.seconds:.2f}s)")
        if meter is not None:
            meter.check()   # after the log line, so the call that crossed the ceiling is still visible in the trace
        try:
            return parse_json(reply.text), reply
        except ValueError as err:
            last_err = err
    raise ModelError(f"{role} did not return valid JSON: {last_err}")


# ---- Optional trace export: console tree or Langfuse. Same design as Week 6's trace_export.py. ----
#
# WHY: logs/latest.log is enough on a laptop. A trace viewer adds time per step, a tree of who called what, and a page
# the whole team can open. The phase files stay exactly as they are: app.py wraps the model, desk.run_tool and the
# approval callback for one turn, and every call becomes a span.
# WHAT IT PREVENTS: a broken or missing viewer breaking the agent (failures warn once and the run carries on), keys
# being printed (only "found" / "missing" is ever said), and big payloads leaving the machine (TRACE_MAX_TEXT cut).
# PRIVACY: spans carry prompts and desk text. Send only the toy desk to a hosted viewer, never real tasks.

TRACE_MAX_TEXT = 500


def _cut(value: Any) -> Any:
    """Short, safe text for a span: strings and JSON-like values are cut to TRACE_MAX_TEXT characters."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    return text if len(text) <= TRACE_MAX_TEXT else text[:TRACE_MAX_TEXT] + " [cut]"


class _Span:
    """One recorded step kept in memory (used by ListSink in tests and ConsoleSink in the terminal)."""

    def __init__(self, kind: str, name: str, input: Any, depth: int, metadata: Any = None):
        self.kind, self.name, self.input, self.depth, self.metadata = kind, name, input, depth, metadata
        self.output: Any = None
        self.extra: dict = {}
        self.seconds: "float | None" = None

    def update(self, output: Any = None, **extra: Any) -> None:
        """Attach the result (same method name the Langfuse observation uses)."""
        self.output = output
        self.extra.update(extra)


class ListSink:
    """Keeps every span in a list. Tests read it; nothing leaves the program."""

    name = "list"

    def __init__(self) -> None:
        self.spans: list[_Span] = []
        self._depth = 0

    @contextmanager
    def span(self, kind: str, name: str, input: Any, metadata: Any = None):
        record = _Span(kind, name, input, self._depth, metadata)
        self.spans.append(record)
        self._depth += 1
        start = time.perf_counter()
        try:
            yield record
        finally:
            record.seconds = round(time.perf_counter() - start, 4)
            self._depth -= 1

    def flush(self) -> None:
        """Nothing to send."""


class ConsoleSink(ListSink):
    """Same as ListSink, then prints the finished tree as indented lines (the no-key fallback)."""

    name = "console"

    def __init__(self, out: Callable[[str], None] = print) -> None:
        super().__init__()
        self.out = out

    def flush(self) -> None:
        if self.spans:
            self.out("trace (console export):")
        for s in self.spans:
            self.out(f"  {'  ' * s.depth}{s.kind:<5} {s.name}  {s.seconds}s  out={_cut(s.output)}")
        self.spans.clear()


def langfuse_sink() -> Any:
    """A sink that sends spans to Langfuse, or None when the keys or the package are missing.

    Needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (plus LANGFUSE_BASE_URL for your region) in the environment
    (load_env() fills them from .env), and `pip install langfuse==5.2.0` (Python 3.11+). Written against langfuse 5.2.0
    (`start_as_current_observation`); not yet verified against a real Langfuse server as of 2026-11-25.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import get_client
    except ImportError:
        return None
    client = get_client()
    # Langfuse draws each type differently: the turn is an agent, a model call a generation, a tool a tool, the gate a guardrail.
    as_type = {"run": "agent", "model": "generation", "tool": "tool", "gate": "guardrail"}

    class LangfuseSink:
        name = "langfuse"

        @contextmanager
        def span(self, kind: str, name: str, input: Any, metadata: Any = None):
            with client.start_as_current_observation(name=name, as_type=as_type.get(kind, "span"), input=input,
                                                     metadata=metadata) as observation:
                yield observation

        def flush(self) -> None:
            client.flush()

    return LangfuseSink()


def choose_sink(name: str, out: Callable[[str], None] = print) -> Any:
    """Pick a sink: "langfuse" (falls back to the console tree when keys or package are missing) or "console"."""
    if name == "langfuse":
        sink = langfuse_sink()
        if sink is not None:
            out("export: sending spans to Langfuse. Prompts and desk text leave this machine: toy data only.")
            return sink
        if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
            out("export: no Langfuse keys in .env (see .env.example); printing the trace tree here instead.")
        else:
            out("export: Langfuse keys found but the package is missing (pip install langfuse==5.2.0); printing the tree here instead.")
    return ConsoleSink(out)


class _TracedModel:
    """Wraps a model callable: one "model" span per call. Every other attribute (calls, reset, label) passes through."""

    def __init__(self, inner: Callable, tracer: "Tracer"):
        self._inner, self._tracer = inner, tracer

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._inner, attr)

    def __call__(self, role: str, system: str, user: str, model_name: "str | None" = None) -> Reply:
        with self._tracer.span("model", role, {"system": system, "user": user}) as sp:
            try:
                reply = self._inner(role, system, user, model_name=model_name)
            except Exception as err:
                self._tracer.set(sp, f"error: {err}")
                raise
            live = reply.source == "live"
            # The stand-in is reported as "stand-in" so a viewer never prices it as a real Gemini call.
            self._tracer.set(sp, reply.text, model=reply.model if live else "stand-in",
                             usage_details={"input": reply.input_tokens, "output": reply.output_tokens},
                             metadata={"priced_as": model_name, "estimated_tokens": reply.estimated, "source": reply.source})
            return reply


class Tracer:
    """Wraps what the phase files already receive (model, approve) plus desk.run_tool, and reports each call to a sink."""

    def __init__(self, sink: Any, warn: Callable[[str], None] = lambda m: print(m, file=sys.stderr)):
        self.sink = sink
        self._warn_fn = warn
        self._warned = False

    def _warn(self, err: Exception) -> None:
        """A broken exporter must never break the agent: say so once, then carry on."""
        if not self._warned:
            self._warned = True
            self._warn_fn(f"trace export problem (the run is unaffected): {type(err).__name__}: {str(err)[:120]}")

    def set(self, span: Any, output: Any, **extra: Any) -> None:
        """Attach a result to a span, ignoring any exporter failure."""
        try:
            if span is not None:
                span.update(output=_cut(output), **extra)
        except Exception as err:
            self._warn(err)

    @contextmanager
    def span(self, kind: str, name: str, input: Any, metadata: Any = None):
        """Open a span; if the sink fails to open or close it, the wrapped call still runs normally."""
        manager = span = None
        try:
            manager = self.sink.span(kind, name, _cut(input), metadata)
            span = manager.__enter__()
        except Exception as err:
            self._warn(err)
            manager = None
        try:
            yield span
        finally:
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception as err:
                    self._warn(err)

    def wrap_model(self, model: Callable) -> Callable:
        return _TracedModel(model, self)

    def wrap_run_tool(self, run_tool: Callable) -> Callable:
        """One "tool" span per tool request, with its outcome (ok, denied, refused). Gate spans nest inside it."""
        def traced(name, args, desk, **kwargs):
            with self.span("tool", str(name), {"args": args, "actor": kwargs.get("actor", "agent")}) as sp:
                res = run_tool(name, args, desk, **kwargs)
                self.set(sp, f"{res.kind}: {res.text}")
                return res
        return traced

    def wrap_approve(self, approve: Callable[[str, dict, str], bool]) -> Callable[[str, dict, str], bool]:
        """One "gate" span per approval question, with the human's answer."""
        def traced(tool: str, args: dict, desc: str) -> bool:
            with self.span("gate", f"approve {tool}", desc) as sp:
                answer = bool(approve(tool, args, desc))
                self.set(sp, "approved" if answer else "denied")
                return answer
        return traced

    def flush(self) -> None:
        """Send anything still waiting (Langfuse batches in the background)."""
        try:
            self.sink.flush()
        except Exception as err:
            self._warn(err)
