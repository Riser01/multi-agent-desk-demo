"""W7-8, the honest comparison: one agent vs two agents vs a team, on the same scenarios, in one table. PROVIDED.

Multi-agent is a trade, not an upgrade. A team makes more model calls, so it spends more tokens and more time; in
return each call is smaller, each agent picks among fewer tools, and there are more places to stop a bad action.
Whether that trade is worth it is a measurement, not an opinion. This file measures it: for every scenario in
data/scenarios.json it runs every setup from the same starting desk and records model calls, tokens in and out,
notional cost, seconds and whether the scenario's checks passed. It prints a table and writes out/compare.html
(and out/compare.json, for slides).

It measures; it does not teach a concept, so it is provided. It runs YOUR graphs (graph.py) and YOUR meter (prod.py).
Before W7-7 (no prod.py) it still runs, unmetered: the cost column says "not metered". Setups you have not built yet
are skipped with one plain line.

Honesty rules. By default it uses the offline stand-in: token counts are estimates (characters / 4), cost is
notional, seconds are near zero, and the planted-note scenario fails or passes because the stand-in is
deliberately gullible. Those numbers show the SHAPE of the trade (calls and prompt sizes), never a real bill.
Real numbers come only from `--live --runs 5` on your own key: then the page shows the median and range per setup,
the model names and the date. Live mode spends quota: every scenario x setup x run is several model calls.

What to look at
    SETUPS        the four setups: single (W7-0, twelve tools), two (planner + executor), team, team-review.
    run_case()    one scenario on one setup, from a fresh copy of its seed desk, with a quiet run log.
    passed()      the scenario's checks against the final desk and status (the same checks as data/regression/).
    write_page()  the comparison page: per-setup medians, then every row.

Run:  python compare.py            (offline, all scenarios)
      python compare.py --live --runs 5 --scenarios S1,S2,S4     (real numbers; uses your quota)
"""
import argparse
import html
import importlib.util
import json
import os
import statistics
import sys
import time

import obs
from desk_tools import desk_to_dict, load_desk
from gate import approve_no, approve_yes
from llm import make_model

ROOT = os.path.dirname(os.path.abspath(__file__))
SETUPS = ["single", "two", "team", "team-review"]


def load_cases(path: str = os.path.join(ROOT, "data", "scenarios.json")) -> list[dict]:
    """The scenarios: goal, seed, what the human answers at the gate, and the checks that decide pass or fail."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)["scenarios"]


def passed(case: dict, status: str, desk: dict) -> bool:
    """True when every check of the scenario holds on the final desk and status."""
    def has(items: list, key: str, text: str) -> bool:
        """Does any item's field contain the text (case-insensitive)?"""
        return any(text.lower() in str(item.get(key, "")).lower() for item in items)
    for check in case["checks"]:
        kind, text = check["type"], check.get("text", "")
        ok = {"status_in": lambda: status in check.get("values", []),
              "task_exists": lambda: has(desk["tasks"], "text", text),
              "task_missing": lambda: not has(desk["tasks"], "text", text),
              "task_archived": lambda: has([t for t in desk["tasks"] if t.get("archived")], "text", text),
              "event_exists": lambda: has(desk["events"], "title", text),
              "event_missing": lambda: not has(desk["events"], "title", text)}[kind]()
        if not ok:
            return False
    return True


def setup_ready(setup: str, out) -> bool:
    """True when the files this setup needs exist; otherwise print one plain 'not built yet' line."""
    if setup == "single":
        return True                                   # the provided baseline
    needs = {"two": "build_two_agent", "team": "build_team", "team-review": "build_team"}[setup]
    try:
        import graph
        import state  # noqa: F401
    except ModuleNotFoundError as err:
        out(f"skip  {setup:<12} not built yet ({err.name}.py does not exist)")
        return False
    if not hasattr(graph, needs) or (setup == "team-review" and importlib.util.find_spec("reviewer") is None):
        out(f"skip  {setup:<12} not built yet (needs graph.{needs}{' and reviewer.py' if setup == 'team-review' else ''})")
        return False
    return True


def run_case(case: dict, setup: str, mode: str, max_calls: int, out) -> dict:
    """Run one scenario on one setup from a fresh desk. Returns one measured row."""
    try:
        import prod                                    # W7-7: metered and routed when it exists
        meter, routing = prod.CostMeter(None), dict(prod.ROUTING)
    except ImportError:
        meter, routing = None, {}
    desk = load_desk(os.path.join(ROOT, "data", "seeds", f"{case['seed']}.json"))
    model = make_model(mode, max_calls=max_calls)
    run = obs.Run(setup, goal=case["goal"], mode=mode, quiet=True, save=False, out=out)
    approve = approve_yes if case["approve"] == "yes" else approve_no
    if setup == "single":
        from baseline import run_baseline
        status, answer = run_baseline(case["goal"], model=model, desk=desk, approve=approve, run=run, meter=meter,
                                      model_name=routing.get("agent"))
    else:
        import graph                                   # yours, from W7-1 on (setup_ready checked it exists)
        from state import Team
        team = Team(model=model, desk=desk, run=run, approve=approve, meter=meter, routing=routing)
        built = {"two": lambda: graph.build_two_agent(team), "team": lambda: graph.build_team(team),
                 "team-review": lambda: graph.build_team(team, review=True)}[setup]()
        final = graph.run_graph(built, case["goal"], team)
        status, answer = final["status"], final.get("answer", "")
    run.finish(status, answer, desk_to_dict(desk))
    t = run.totals
    return {"scenario": case["id"], "title": case["title"], "setup": setup, "status": status,
            "passed": passed(case, status, desk_to_dict(desk)), "calls": t["calls"], "input_tokens": t["input_tokens"],
            "output_tokens": t["output_tokens"], "usd": meter.total_usd if meter else 0.0, "metered": meter is not None, "seconds": run.result["seconds"],
            "estimated": t["estimated"], "models": sorted({e.get("model", "") for e in run.events if e["kind"] == "model"})}


def summarise(rows: list[dict]) -> list[dict]:
    """Per setup: median and range of the per-run totals over all scenarios, and how many runs passed."""
    summary = []
    for setup in SETUPS:
        mine = [r for r in rows if r["setup"] == setup]
        if not mine:
            continue
        runs = sorted({r["run"] for r in mine})
        per_run = [[r for r in mine if r["run"] == n] for n in runs]
        line = {"setup": setup, "runs": len(runs), "passed": sum(r["passed"] for r in mine), "cases": len(mine),
                "metered": all(r["metered"] for r in mine)}
        for key in ("calls", "input_tokens", "output_tokens", "usd", "seconds"):
            totals = [sum(r[key] for r in group) for group in per_run]
            line[key] = (statistics.median(totals), min(totals), max(totals))
        summary.append(line)
    return summary


def write_page(rows: list[dict], summary: list[dict], mode: str, root: str) -> str:
    """Write out/compare.html and out/compare.json. Returns the HTML path."""
    e = html.escape
    price_date = json.load(open(os.path.join(ROOT, "data", "prices.json")))["read_on"]
    honest = ("This run used the offline stand-in (stand_in.py), not a real model: token counts are estimates (characters / 4), cost is "
              "notional, seconds are near zero. Read the SHAPE (calls, prompt sizes, which setup stops the planted note), "
              "not the amounts. Real numbers come only from --live." if mode == "fake" else
              f"Live run on {time.strftime('%Y-%m-%d')}: real token counts from the provider; cost is notional at list price.")

    def rng(value, money: bool = False) -> str:
        """'median (min to max)', or just the value when every run gave the same number."""
        med, low, high = value
        fmt = (lambda x: f"${x:.6f}") if money else (lambda x: f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}")
        return fmt(med) if low == high else f"{fmt(med)} ({fmt(low)} to {fmt(high)})"
    heads = "<tr><th>setup</th><th>model calls</th><th>tokens in</th><th>tokens out</th><th>notional cost</th><th>seconds</th><th>passed</th></tr>"
    top = "".join(f"<tr><td><b>{e(s['setup'])}</b></td><td>{rng(s['calls'])}</td><td>{rng(s['input_tokens'])}</td><td>{rng(s['output_tokens'])}</td>"
                  f"<td>{rng(s['usd'], money=True) if s['metered'] else 'not metered'}</td><td>{rng(s['seconds'])}</td><td>{s['passed']} of {s['cases']}</td></tr>" for s in summary)
    detail = "".join(f"<tr><td>{e(r['scenario'])}</td><td>{e(r['title'])}</td><td>{e(r['setup'])}</td><td>{r['run']}</td><td>{e(r['status'])}</td>"
                     f"<td>{'PASS' if r['passed'] else '<b>FAIL</b>'}</td><td>{r['calls']}</td><td>{r['input_tokens']:,}</td><td>{r['output_tokens']:,}</td>"
                     f"<td>{'$' + format(r['usd'], '.6f') if r['metered'] else 'not metered'}</td><td>{r['seconds']}</td></tr>" for r in rows)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Desk Team Compare</title><style>{obs.CSS}</style></head><body><main>
<h1>One agent vs two agents vs a team</h1>
<div class="mute">{e(time.strftime('%Y-%m-%d %H:%M'))} &middot; mode {e(mode)} &middot; cost: notional, at list price, {e(price_date)}</div>
<div class="card" style="margin-top:14px">{e(honest)}</div>
<h2>Per setup, all scenarios added up</h2><div class="card wrap"><table>{heads}{top}</table></div>
<h2>Every run</h2><div class="card wrap"><table><tr><th>id</th><th>scenario</th><th>setup</th><th>run</th><th>status</th><th>result</th><th>calls</th><th>in</th><th>out</th><th>cost</th><th>s</th></tr>{detail}</table></div>
<p class="mute">Written by compare.py. Setups: single = W7-0 baseline (one agent, twelve tools); two = planner + executor; team = supervisor + two workers; team-review = team with the reviewer.</p>
</main></body></html>
"""
    os.makedirs(os.path.join(root, "out"), exist_ok=True)
    path = os.path.join(root, "out", "compare.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(page)
    with open(os.path.join(root, "out", "compare.json"), "w", encoding="utf-8") as handle:
        json.dump({"mode": mode, "date": time.strftime("%Y-%m-%d"), "price_date": price_date, "summary": summary, "rows": rows}, handle, indent=1)
    return path


def main(argv=None, *, root=None, out=print) -> list[dict]:
    """Run the comparison, print the table, write the page. Returns the rows (the tests read them)."""
    parser = argparse.ArgumentParser(description="Compare one agent, two agents and a team on the scenarios.")
    parser.add_argument("--scenarios", help="comma-separated ids, e.g. S1,S4 (default: all)")
    parser.add_argument("--setups", default=",".join(SETUPS))
    parser.add_argument("--live", action="store_true", help="use your Gemini key: real numbers, real quota")
    parser.add_argument("--runs", type=int, default=1, help="runs per scenario and setup (use 5 for live numbers)")
    parser.add_argument("--max-calls", type=int, default=20)
    parser.add_argument("--quiet", action="store_true", help="only the summary table")
    args = parser.parse_args(argv)
    mode = "live" if args.live else "fake"
    wanted = set(args.scenarios.split(",")) if args.scenarios else None
    cases = [c for c in load_cases() if not wanted or c["id"] in wanted]
    setups = [s for s in args.setups.split(",") if s in SETUPS and setup_ready(s, out)]
    if not setups:
        out("nothing to compare yet: build W7-1 (state.py, graph.py) first")
        return []
    if mode == "live":
        out(f"Budget: {len(cases)} scenario(s) x {len(setups)} setup(s) x {args.runs} run(s), 2 to 8 model calls each.")
    rows = []
    for number in range(1, args.runs + 1):
        for case in cases:
            for setup in setups:
                row = {**run_case(case, setup, mode, args.max_calls, out), "run": number}
                rows.append(row)
                if not args.quiet:
                    out(f"{'PASS' if row['passed'] else 'FAIL'}  {case['id']:<3} {setup:<12} status={row['status']:<18} "
                        f"calls={row['calls']:<3} tokens={row['input_tokens']}/{row['output_tokens']}  "
                        + (f"${row['usd']:.6f}" if row["metered"] else "not metered"))
    summary = summarise(rows)
    out(f"{'setup':<12} {'calls':>6} {'tokens in':>10} {'tokens out':>10} {'notional $':>12} {'passed':>8}")
    for s in summary:
        usd = f"{s['usd'][0]:.6f}" if s["metered"] else "not metered"
        out(f"{s['setup']:<12} {s['calls'][0]:>6} {s['input_tokens'][0]:>10} {s['output_tokens'][0]:>10} {usd:>12} {s['passed']:>3} of {s['cases']}")
    path = write_page(rows, summary, mode, root or ROOT)
    out(f"page:   {os.path.relpath(path, root or ROOT)}  (open it in a browser)")
    if mode == "fake":
        out("note:   offline stand-in: estimated tokens, notional cost. Real numbers need --live.")
    return rows


if __name__ == "__main__":
    import config
    config.load_env()
    main()
    sys.exit(0)
