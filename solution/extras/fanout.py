"""W7-5 (stretch): parallel workers with LangGraph's Send, and why the results key needs a reducer.

When a goal has parts that do not depend on each other ("add a dentist appointment AND add a task to buy a gift"),
the workers do not have to wait for each other. A conditional edge can return a list of Send(node, input) objects:
LangGraph then runs that node once per Send, in the same step, and a node with a plain edge after them runs once,
when all of them are done. Two things make this safe, and this file shows both:

    the reducer   every worker writes the same 'results' key in the same step. With Annotated[list, operator.add]
                  the lists are joined. Without it LangGraph refuses: InvalidUpdateError ("Can receive only one
                  value per step"). Run with --no-reducer to see that error, explained.
    the lock      the workers share one desk (the world), and one id counter. A lock around the gate call makes
                  each change atomic, so two workers cannot hand out the same id. (DESK_LOCK demonstrates the idea;
                  an offline test cannot prove it prevents a race, because the stand-in answers too fast to collide.)

Quota safety: the default runs the parts one after another (sequential). `--parallel` uses Send. `--delay 0.5`
adds a SIMULATED half-second per model call so you can see the time saved offline; it is labelled in the output.

It is self-contained (stand-in, gate and obs only), so it runs even before you build the team.
Run:  python extras/fanout.py --parallel --delay 0.5
"""
import argparse
import operator
import os
import sys
import threading
import time
from typing import Annotated, TypedDict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import obs  # noqa: E402
from desk_tools import CALENDAR_TOOLS, TASK_TOOLS, desk_to_dict, desk_view, load_desk  # noqa: E402
from gate import approve_no, run_tool  # noqa: E402
from llm import ask_json  # noqa: E402
from stand_in import StandIn, classify, split_goal  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GOAL = "Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift for Anil."
DESK_LOCK = threading.Lock()   # one writer at a time on the shared desk


class FanState(TypedDict, total=False):
    """The fan-out state. 'results' has a reducer, so parallel workers' lists are joined, not overwritten."""
    goal: str
    results: Annotated[list[dict], operator.add]


class PlainState(TypedDict, total=False):
    """The same state WITHOUT a reducer: parallel writes to 'results' are refused by LangGraph."""
    goal: str
    results: list[dict]


def build(desk, model, run, *, reducer: bool = True, delay: float = 0.0):
    """split -(Send x N)-> worker -> merge -> END. Each Send carries one part of the goal to its own worker run."""
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Send

    def fan_out(state):
        """The conditional edge: one Send per independent part of the goal."""
        parts = split_goal(state["goal"])
        run.log("route", "split", f"fan-out: {len(parts)} part(s) in parallel")
        return [Send("worker", {"part": part}) for part in parts]

    def worker(payload):
        """One worker run: pick the specialist by the part, ask the model, act through the gate under the lock."""
        name = "calendar" if classify(payload["part"]) in CALENDAR_TOOLS else "tasks"
        tools = CALENDAR_TOOLS if name == "calendar" else TASK_TOOLS
        if delay:
            time.sleep(delay)          # SIMULATED model latency, so the parallel win is visible offline
        message = f"task: {payload['part']}\ncontext:\n{desk_view(desk, part='events' if name == 'calendar' else 'tasks')}"
        data, _ = ask_json(model, name, f"You are the {name} worker.", message, run=run)
        with DESK_LOCK:                # the desk is shared: one change at a time
            outcome = run_tool(str(data.get("tool")), data.get("args"), desk, allowed=tools, approve=approve_no, actor=name, run=run)
        return {"results": [{"agent": name, "task": payload["part"], "kind": outcome.kind, "text": outcome.text}]}

    def merge(state):
        """The aggregator: runs once, after every worker of the step has finished."""
        run.log("route", "merge", f"merged {len(state['results'])} result(s)")
        return {}

    builder = StateGraph(FanState if reducer else PlainState)
    builder.add_node("worker", worker)
    builder.add_node("merge", merge)
    builder.add_conditional_edges(START, fan_out, ["worker"])
    builder.add_edge("worker", "merge")
    builder.add_edge("merge", END)
    return builder.compile()


def run_parts(goal: str, *, parallel: bool, reducer: bool = True, delay: float = 0.0, quiet: bool = False, out=print, save: bool = True):
    """Run the goal's parts in parallel (Send) or one by one. Returns (status, results, seconds)."""
    from langgraph.errors import InvalidUpdateError
    desk = load_desk(os.path.join(ROOT, "data", "seeds", "desk_week.json"))
    model = StandIn()
    run = obs.Run("fanout-parallel" if parallel else "fanout-sequential", goal=goal, quiet=quiet, out=out, save=save,
                  label="offline stand-in" + (f"; SIMULATED latency {delay}s per model call" if delay else ""))
    started, results, status = time.time(), [], "done"
    try:
        if parallel:
            final = build(desk, model, run, reducer=reducer, delay=delay).invoke({"goal": goal, "results": []}, {"recursion_limit": 10})
            results = final["results"]
        else:
            graph = build(desk, model, run, reducer=True, delay=delay)
            for part in split_goal(goal):      # the same worker, one part at a time: half the speed, half the burst
                results += graph.invoke({"goal": part, "results": []}, {"recursion_limit": 10})["results"]
    except InvalidUpdateError as err:
        status = "no-reducer"
        run.log("error", "graph", f"InvalidUpdateError: {str(err).splitlines()[0]}  -> add Annotated[list, operator.add] to 'results'", level="ERROR")
    seconds = round(time.time() - started, 2)
    run.finish(status, f"{len(results)} result(s) in {seconds}s", desk_to_dict(desk))
    return status, results, seconds


def main(argv=None) -> int:
    """Command line for the stretch phase."""
    parser = argparse.ArgumentParser(description="W7-5: parallel workers with Send and a reducer.")
    parser.add_argument("goal", nargs="?", default=GOAL)
    parser.add_argument("--parallel", action="store_true", help="fan out with Send (default: one part at a time)")
    parser.add_argument("--no-reducer", action="store_true", help="drop the reducer and watch LangGraph refuse")
    parser.add_argument("--delay", type=float, default=0.0, help="SIMULATED seconds per model call")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    status, results, seconds = run_parts(args.goal, parallel=args.parallel or args.no_reducer, reducer=not args.no_reducer,
                                         delay=args.delay, quiet=args.quiet)
    print(f"status: {status}\nresults: {len(results)}\nseconds: {seconds}" + (" (includes SIMULATED latency)" if args.delay else ""))
    for r in results:
        print(f"  {r['agent']}: {r['task']} -> {r['kind']}: {r['text']}")
    return 0 if status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
