"""Observability: one call to log an event, and every run leaves a terminal log, a log file and an HTML report. PROVIDED.

With one agent you can read a run in the terminal. With a team you cannot: four agents, handoffs between them,
tool calls, gate decisions and tokens interleave, and the first question after any surprise is "what did each
agent actually see?". So every event goes through ONE method, Run.log(kind, agent, text), and this file turns that
single stream into four views of the same run:

    the terminal     one INFO/WARN/ERROR line per event while the run goes (`--quiet` turns it off)
    logs/            run-<time>-<setup>.log (the same lines) and .jsonl (one JSON object per event), copied to
                     logs/latest.log and logs/latest.jsonl (copies, not links, so they open anywhere)
    out/             run-<time>-<setup>.html and out/latest.html: a self-contained page with the timeline, every
                     handoff and "what each agent saw", tool calls, gate decisions, tokens, notional cost, time,
                     the version stamp and the final result. Open it in any browser.
    a trace viewer   optional (`--export langfuse`): nested spans run > agent > model / tool / gate in Langfuse
                     5.2.0, plus LangGraph's own node spans through Langfuse's CallbackHandler. Without keys or the
                     package it prints the same tree in the terminal instead (`--export console`).

You never edit this file. Your code only calls run.log(...) (rarely: llm.ask_json and gate.run_tool already log
models, tools and gates for you) and wraps each node with run.wrap(name, fn) so each agent turn is one span.

What to look at
    Run.log()          the one logging API. kind is one of KINDS; level INFO, WARN or ERROR; extra fields go to JSONL.
    Run.model_call()   logs one model reply with seconds and tokens, and keeps the run totals.
    Run.wrap()         turns a node function into one traced "agent turn" (a span in Langfuse, a block in the tree).
    Run.finish()       writes the files and returns their paths. Call it exactly once, at the end of a run.
    render_html()      the report page. Plain HTML and CSS, no scripts, no internet needed to open it.
"""
import html
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager, nullcontext
from typing import Any, Callable

KINDS = ("run", "agent", "saw", "model", "handoff", "plan", "tool", "gate", "review", "cap", "route", "cost", "error")
ROOT = os.path.dirname(os.path.abspath(__file__))
TERMINAL_CHARS = 200      # a terminal line shows this much of an event; the files keep more
FILE_CHARS = 4000         # the most any one event keeps in the files (a guard against a huge note)


def _one_line(text: str, limit: int) -> str:
    """Newlines become ' | ' so one event is one line; long text is cut with a visible marker."""
    flat = str(text).replace("\r", "").replace("\n", " | ")
    return flat if len(flat) <= limit else flat[:limit] + " ..."


class Run:
    """One run of the Desk Assistant: collects events, prints them live, and writes the log files and the report."""

    def __init__(self, name: str, *, goal: str = "", mode: str = "fake", label: str = "", version: "dict | None" = None,
                 quiet: bool = False, export: str = "none", root: "str | None" = None, save: bool = True,
                 out: Callable[[str], None] = print, langfuse_client: Any = None, meta: "dict | None" = None):
        """name is the setup (single, two, team ...). mode and label say where the replies come from, honestly.

        meta is any small extra fact worth keeping in the .jsonl header (agent.py stores the seed and the approver,
        so extras/monitor.py can turn a failed run into a regression case).
        """
        self.name, self.goal, self.mode, self.label, self.version = name, goal, mode, label, version
        self.meta = meta or {}
        self.quiet, self.export, self.save, self.out = quiet, export, save, out
        self.root = root or ROOT
        self.started = time.time()
        self.stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(self.started * 1000) % 1000:03d}"   # ms: two runs in one second never collide
        self.events: list[dict] = []
        self.totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0, "estimated": False}
        self.by_agent: dict[str, dict] = {}
        self._stack: list[str] = []            # the agent span we are inside, for the tree and Langfuse
        self._turns = 0
        self.lf, self._lf_root = None, None
        if export == "langfuse":
            self.lf = langfuse_client or _langfuse_client(self.out)
        if self.lf is not None:
            self._lf_root_cm = self.lf.start_as_current_observation(name=f"run {name}", as_type="chain",
                                                                    input={"goal": goal}, metadata={"version": version, "mode": mode})
            self._lf_root = self._lf_root_cm.__enter__()
        where = label or {"fake": "offline stand-in, not a real model", "live": "live model", "replay": "replayed file"}.get(mode, mode)
        self.log("run", "run", f"start {name}  mode={mode} ({where})  version={_stamp_text(version)}", goal=goal)

    # ---- the one logging API ----
    def log(self, kind: str, agent: str, text: str, level: str = "INFO", **data: Any) -> None:
        """Record one event: print it (unless quiet), keep it for the files, and send leaf events to Langfuse."""
        event = {"t": round(time.time() - self.started, 3), "level": level, "kind": kind, "agent": agent,
                 "span": self._stack[-1] if self._stack else "", "text": str(text)[:FILE_CHARS], **data}
        self.events.append(event)
        if not self.quiet:
            shown = _one_line(text, TERMINAL_CHARS)
            self.out(f"{level:<5} +{event['t']:6.2f}s  [{agent[:10]:<10}] {kind:<7} {shown}")
        if self.lf is not None and kind in ("tool", "gate"):
            with self.lf.start_as_current_observation(name=f"{kind} {data.get('tool', '')}".strip(),
                                                      as_type="tool" if kind == "tool" else "guardrail",
                                                      input=text, level="WARNING" if level != "INFO" else "DEFAULT"):
                pass

    def model_call(self, agent: str, reply: Any) -> None:
        """Log one model reply with its time and tokens, and add it to the run and per-agent totals."""
        self.totals["calls"] += 1
        self.totals["input_tokens"] += reply.input_tokens
        self.totals["output_tokens"] += reply.output_tokens
        self.totals["estimated"] = self.totals["estimated"] or reply.estimated
        mine = self.by_agent.setdefault(agent, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        mine["calls"] += 1
        mine["input_tokens"] += reply.input_tokens
        mine["output_tokens"] += reply.output_tokens
        est = ", est." if reply.estimated else ""
        who = reply.model                    # offline replies never pretend to come from the model they are priced as
        if reply.source != "live" and reply.model not in ("stand-in", "replay", "fake-model"):
            who = f"{'stand-in' if reply.source == 'fake' else reply.source} (priced as {reply.model})"
        self.log("model", agent, f"{who} replied in {reply.seconds:.2f}s ({reply.input_tokens} in / "
                 f"{reply.output_tokens} out tokens{est}): {reply.text}", model=reply.model, input_tokens=reply.input_tokens,
                 output_tokens=reply.output_tokens, seconds=reply.seconds, source=reply.source)
        if self.lf is not None:
            saw = next((e["text"] for e in reversed(self.events) if e["kind"] == "saw"), "")
            with self.lf.start_as_current_observation(name=f"{agent} model", as_type="generation", model=reply.model,
                                                      input=saw, output=reply.text,
                                                      usage_details={"input": reply.input_tokens, "output": reply.output_tokens}):
                pass

    @contextmanager
    def agent(self, name: str):
        """One agent turn: a block in the tree and a nested span in Langfuse."""
        self._turns += 1
        self._stack.append(f"{name}#{self._turns}")
        self.log("agent", name, f"turn {self._turns} starts")
        span = self.lf.start_as_current_observation(name=name, as_type="agent") if self.lf is not None else nullcontext()
        try:
            with span:
                yield
        finally:
            self._stack.pop()

    def wrap(self, name: str, fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Turn a node function into a traced agent turn. Use it when you add a node to the graph."""
        def node(state: Any) -> Any:
            """The node, run inside its agent span."""
            with self.agent(name):
                return fn(state)
        node.__name__ = name
        return node

    def callbacks(self) -> list:
        """LangGraph callbacks for the graph's config: Langfuse's CallbackHandler when exporting there, else none."""
        if self.lf is None:
            return []
        try:
            from langfuse.langchain import CallbackHandler
            return [CallbackHandler()]
        except Exception as err:           # a broken viewer must never break the run
            self.log("run", "run", f"Langfuse CallbackHandler unavailable ({type(err).__name__}); node spans skipped", level="WARN")
            return []

    # ---- the end of a run ----
    def finish(self, status: str, answer: str, desk: "dict | None" = None) -> dict:
        """Log the end, write the .log/.jsonl/.html files (and the latest copies), and return their paths."""
        seconds = round(time.time() - self.started, 2)
        cost = next((e for e in reversed(self.events) if e["kind"] == "cost"), None)
        self.totals["usd"] = cost["total_usd"] if cost else 0.0
        t = self.totals
        level = "INFO" if status in ("done", "done-with-denials") else "WARN"
        self.log("run", "run", f"ended: status={status} after {t['calls']} model calls, {t['input_tokens']} in / "
                 f"{t['output_tokens']} out tokens{' (est.)' if t['estimated'] else ''}, {seconds}s", level=level,
                 status=status, seconds=seconds)
        self.result = {"status": status, "answer": answer, "seconds": seconds, "desk": desk, **t}
        if self.lf is not None:
            try:
                self._lf_root.update(output={"status": status, "answer": answer})
                self._lf_root_cm.__exit__(None, None, None)
                self.lf.flush()
            except Exception as err:
                self.out(f"WARN  export: Langfuse flush failed ({type(err).__name__}); the local files are complete")
        elif self.export in ("console", "langfuse"):
            self.out(console_tree(self))
        if not self.save:
            return {}
        paths = {}
        for folder, ext, body in (("logs", "log", self._log_text()), ("logs", "jsonl", self._jsonl_text()),
                                  ("out", "html", render_html(self))):
            os.makedirs(os.path.join(self.root, folder), exist_ok=True)
            path = os.path.join(self.root, folder, f"run-{self.stamp}-{self.name}.{ext}")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            shutil.copyfile(path, os.path.join(self.root, folder, f"latest.{ext}"))   # a copy, not a link
            paths[ext] = path
        return paths

    def _log_text(self) -> str:
        """The .log file: the terminal lines, with more of each event kept."""
        return "\n".join(f"{e['level']:<5} +{e['t']:6.2f}s  [{e['agent'][:10]:<10}] {e['kind']:<7} {_one_line(e['text'], 1000)}"
                         for e in self.events) + "\n"

    def _jsonl_text(self) -> str:
        """The .jsonl file: one JSON object per event, ready for scripts (extras/monitor.py reads these)."""
        head = {"kind": "header", "name": self.name, "goal": self.goal, "mode": self.mode, "label": self.label,
                "version": self.version, "meta": self.meta, "result": getattr(self, "result", None), "by_agent": self.by_agent}
        return "\n".join(json.dumps(x, default=str) for x in [head, *self.events]) + "\n"


def summary(status: str, answer: str, desk: dict, paths: dict) -> list[str]:
    """The end-of-run lines every runner prints: status, answer, what is left on the desk, where the files are."""
    tasks = [t for t in desk.get("tasks", []) if not t.get("archived")]
    lines = [f"status: {status}", f"answer: {_one_line(answer, 300)}", f"tasks left: {len(tasks)}"]
    lines += [f"  {t['id']}: {t['text'][:70]}{' (done)' if t.get('done') else ''}" for t in tasks]
    lines += [f"events: {len(desk.get('events', []))}"] + [f"  {e['id']}: {e['when']}, {e['title'][:60]}" for e in desk.get("events", [])]
    if paths:
        lines += ["log:    logs/latest.log  (this run: " + os.path.relpath(paths["log"], ROOT) + ")",
                  "report: out/latest.html  (open it in a browser)"]
    return lines


def _stamp_text(version: "dict | None") -> str:
    """The version stamp on one line, or a plain note when there is none yet."""
    if not version:
        return "not stamped yet (W7-7)"
    return " ".join(f"{k}={v}" for k, v in version.items() if not isinstance(v, dict)) + \
        "".join(f" {k}=" + ",".join(f"{a}:{b}" for a, b in v.items()) for k, v in version.items() if isinstance(v, dict))


def _langfuse_client(out: Callable[[str], None]) -> Any:
    """The Langfuse client when keys and package are present; otherwise None, with one plain line saying why."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        out("export: no Langfuse keys in .env; printing the trace tree here instead.")
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception as err:
        print(f"export: Langfuse is not usable ({type(err).__name__}: pip install \"langfuse==5.2.0\"); "
              "printing the trace tree here instead.", file=sys.stderr)
        return None


def console_tree(run: Run) -> str:
    """The same nesting Langfuse shows (run > agent > model / tool / gate), as indented text."""
    lines = [f"TRACE run {run.name}  status={run.result['status']}  calls={run.totals['calls']}"]
    current = None
    for e in run.events:
        if e["kind"] == "agent":
            current = e["span"]
            lines.append(f"  agent {e['agent']}  ({e['text']})")
        elif e["kind"] in ("model", "tool", "gate", "handoff", "review", "cap"):
            indent = "    " if e["span"] and e["span"] == current else "  "
            lines.append(f"{indent}{e['kind']:<7} {_one_line(e['text'], 110)}")
    return "\n".join(lines)


CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e3e2dc;--ok:#1f7a4d;--warn:#a15c00;--err:#b42318;--acc:#2f5bd3}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#20201e;--ink:#ecebe6;--mute:#a3a29b;--line:#34332f;--ok:#4fbf86;--warn:#e0a03c;--err:#f07068;--acc:#8aa8ff}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.mute{color:var(--mute)}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.tile b{display:block;font-size:22px}.tile span{font-size:12px;color:var(--mute)}
.badge{display:inline-block;padding:2px 10px;border-radius:99px;font-weight:600;font-size:13px;color:#fff}
.ok{background:var(--ok)}.warn{background:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td.t{white-space:nowrap;color:var(--mute);font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:0 8px;border-radius:6px;border:1px solid var(--line);font-size:12px;white-space:nowrap}
tr.WARN td.k{color:var(--warn);font-weight:600}tr.ERROR td.k{color:var(--err);font-weight:600}
tr.handoff td{background:rgba(47,91,211,.07)}tr.agent td{border-top:2px solid var(--line)}
pre{white-space:pre-wrap;word-break:break-word;margin:6px 0 0;font:12px/1.4 ui-monospace,Menlo,monospace}
details summary{cursor:pointer;color:var(--acc)}.wrap{overflow-x:auto}
"""


def render_html(run: Run) -> str:
    """The report page for one run: header, totals, per-agent table, timeline with what each agent saw, final desk."""
    e = html.escape
    r = getattr(run, "result", {}) or {}
    t = run.totals
    cost = next((x for x in reversed(run.events) if x["kind"] == "cost"), None)
    cost_text = (f"${t['usd']:.6f}", f"notional, at list price, {cost.get('price_date', '?')}") if cost else ("not metered", "cost meter arrives in W7-7")
    est = " (estimated: characters / 4)" if t["estimated"] else ""
    status = r.get("status", "?")
    tiles = [(t["calls"], "model calls"), (f"{t['input_tokens']:,} / {t['output_tokens']:,}", f"tokens in / out{est}"),
             (cost_text[0], cost_text[1]), (f"{r.get('seconds', 0)}s", "wall-clock time"), (len(run.by_agent), "agents that called a model")]
    rows = []
    for x in run.events:
        body = e(x["text"])
        if x["kind"] in ("saw", "handoff", "plan") and len(x["text"]) > 140:
            body = f"<details><summary>{e(_one_line(x['text'], 120))}</summary><pre>{body}</pre></details>"
        elif x["kind"] == "saw":
            body = f"<pre>{body}</pre>"
        label = "what it saw" if x["kind"] == "saw" else x["kind"]
        rows.append(f"<tr class='{x['level']} {x['kind']}'><td class='t'>+{x['t']:.2f}s</td><td><span class='chip'>{e(x['agent'])}</span></td>"
                    f"<td class='k'>{e(label)}</td><td>{body}</td></tr>")
    agents = "".join(f"<tr><td>{e(a)}</td><td>{v['calls']}</td><td>{v['input_tokens']:,}</td><td>{v['output_tokens']:,}</td></tr>"
                     for a, v in run.by_agent.items())
    desk = r.get("desk") or {}
    tasks = "".join(f"<li>{x['id']}: {e(x['text'][:120])}{' (done)' if x.get('done') else ''}{' (archived)' if x.get('archived') else ''}</li>"
                    for x in desk.get("tasks", []))
    events = "".join(f"<li>{x['id']}: {e(x['when'])}, {e(x['title'])}</li>" for x in desk.get("events", []))
    source = run.label or {"fake": "Offline stand-in (stand_in.py), not a real model: replies are rule-based and tokens are estimates.",
                           "live": "Live model run.", "replay": "Replayed from a file."}.get(run.mode, run.mode)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Desk Team Run</title><style>{CSS}</style></head><body><main>
<h1>Desk Assistant run: {e(run.name)} <span class="badge {'ok' if status in ('done', 'done-with-denials') else 'warn'}">{e(status)}</span></h1>
<div class="mute">{e(time.strftime('%Y-%m-%d %H:%M', time.localtime(run.started)))} &middot; mode {e(run.mode)} &middot; version: {e(_stamp_text(run.version))}</div>
<div class="card" style="margin-top:14px"><div><b>Goal:</b> {e(run.goal)}</div><div><b>Answer:</b> {e(str(r.get('answer', '')))}</div>
<div class="mute" style="margin-top:6px">{e(source)}</div></div>
<div class="tiles">{''.join(f'<div class="card tile"><b>{e(str(a))}</b><span>{e(b)}</span></div>' for a, b in tiles)}</div>
<h2>Agents</h2><div class="card wrap"><table><tr><th>agent</th><th>model calls</th><th>tokens in</th><th>tokens out</th></tr>{agents or '<tr><td colspan=4>no model calls</td></tr>'}</table></div>
<h2>Timeline: every handoff, what each agent saw, every tool call and gate decision</h2>
<div class="card wrap"><table><tr><th>time</th><th>agent</th><th>event</th><th>detail</th></tr>{''.join(rows)}</table></div>
<h2>The desk at the end</h2><div class="card"><b>Tasks</b><ul>{tasks or '<li>none</li>'}</ul><b>Events</b><ul>{events or '<li>none</li>'}</ul></div>
<p class="mute">Written by obs.py. Same run as logs/run-{e(run.stamp)}-{e(run.name)}.log and .jsonl.</p>
</main></body></html>
"""
