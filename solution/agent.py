"""The command line: run the Desk Assistant as one agent, two agents or a team, and see every step. PROVIDED.

This is the file you run, and you do not write it: it is plumbing, not a lesson. It reads the flags, loads a starting desk from a seed file, picks the model (the offline
stand-in unless you say --live), builds the graph for the setup you asked for, runs it with obs.py recording
everything, and prints where the log and the HTML report are. It holds no agent logic: that lives in the agent
files, the wiring in graph.py, the safety in gate.py. So the same command runs every phase, and a setup you have
not built yet says so in plain words instead of crashing.

Every flag works from W7-1 so the commands in GUIDE.md never change; a flag whose phase you have not built is
accepted and has no effect yet (--review needs W7-6, --ceiling needs W7-7). It reads what you build: graph.py's
builders and run_graph (W7-1 on), state.Team, and prod.py when it exists (W7-7). Approval is a plain blocking
callback (gate.make_ask asks in the terminal); it is NOT LangGraph's interrupt(), so no checkpointer is involved. Each run starts from the seed again:
this week is about the team, not memory, so nothing is saved between runs.

What to look at
    SETUPS        setup name -> the graph builder in graph.py, and the phase that adds it.
    production()  W7-7: the cost meter, the model routing and the version stamp, when prod.py exists.
    main()        flags -> desk, model, Team, graph -> run_graph -> obs files -> summary. Exit 0 / 1 / 2.

Run:  python agent.py "Add File taxes, then show me my list." --setup two
"""
import argparse
import importlib
import sys

import obs
from desk_tools import desk_to_dict, load_desk
from gate import approve_no, approve_yes, make_ask
from llm import ModelError, make_model

SETUPS = {"single": ("build_single", "W7-1"), "two": ("build_two_agent", "W7-2"), "team": ("build_team", "W7-4")}


def production(setup: str, ceiling: "float | None"):
    """W7-7: (meter, routing, version) from prod.py, or (None, {}, None) before prod.py exists."""
    try:
        import prod
    except ImportError:
        return None, {}, None
    return prod.CostMeter(ceiling), dict(prod.ROUTING), prod.version_stamp(setup, prod.ROUTING)


def parse_args(argv):
    """The flags. All of them exist from W7-1, so the commands in GUIDE.md work in every phase."""
    parser = argparse.ArgumentParser(description="Run the Desk Assistant as one agent, two agents or a team.")
    parser.add_argument("goal")
    parser.add_argument("--setup", choices=list(SETUPS), default="single")
    parser.add_argument("--review", action="store_true", help="team only: the reviewer checks irreversible actions (W7-6)")
    parser.add_argument("--seed", default="data/seeds/desk_week.json")
    parser.add_argument("--approve", choices=["ask", "yes", "no"], default="ask")
    parser.add_argument("--mode", choices=["fake", "replay", "live"], default="fake")
    parser.add_argument("--live", action="store_true", help="same as --mode live: uses your Gemini key and quota")
    parser.add_argument("--replay", help="a replay file for --mode replay")
    parser.add_argument("--record", help="save this run's replies as a replay file")
    parser.add_argument("--max-calls", type=int, default=30, help="per-run model call cap")
    parser.add_argument("--ceiling", type=float, help="cost ceiling in USD, notional (W7-7)")
    parser.add_argument("--export", choices=["none", "console", "langfuse"], default="none")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv=None, *, model=None, input_fn=input, out=print, root=None) -> int:
    """Run once. Exit 0 when the run finished (done or done-with-denials), 1 when it stopped early, 2 on a setup problem."""
    args = parse_args(argv)
    mode = "live" if args.live else args.mode
    builder_name, phase = SETUPS[args.setup]
    try:
        graph = importlib.import_module("graph")        # yours: built from W7-1 on
        from state import Team
    except ModuleNotFoundError as err:
        if err.name in ("graph", "state"):
            out(f"configuration error: {err.name}.py is not built yet (W7-1). Build it first, then run this again.")
            return 2
        raise
    builder = getattr(graph, builder_name, None)
    if builder is None:
        out(f"configuration error: setup '{args.setup}' is not built yet ({phase} adds graph.{builder_name})")
        return 2
    try:
        desk = load_desk(args.seed)
        model = model or make_model(mode, replay_path=args.replay, max_calls=args.max_calls, record=bool(args.record))
        name = args.setup + ("-review" if args.setup == "team" and args.review else "")
        meter, routing, version = production(name, args.ceiling)   # the stamp names the real setup, review included
    except (OSError, ValueError, ModelError) as err:
        out(f"configuration error: {err}")
        return 2
    approve = {"yes": approve_yes, "no": approve_no}.get(args.approve) or make_ask(input_fn, out)
    run = obs.Run(name, goal=args.goal, mode=mode, label=getattr(model, "label", ""), version=version,
                  quiet=args.quiet, export=args.export, root=root, out=out, meta={"seed": args.seed, "approve": args.approve})
    team = Team(model=model, desk=desk, run=run, approve=approve, meter=meter, routing=routing)
    compiled = builder(team, review=args.review) if args.setup == "team" else builder(team)
    final = graph.run_graph(compiled, args.goal, team)
    paths = run.finish(final["status"], final.get("answer", ""), desk_to_dict(desk))
    if args.record and hasattr(model, "save"):
        model.save(args.record, f"recorded from agent.py --setup {args.setup}, goal: {args.goal}")
    for line in obs.summary(final["status"], final.get("answer", ""), desk_to_dict(desk), paths):
        out(line)
    return 0 if final["status"] in ("done", "done-with-denials") else 1


if __name__ == "__main__":
    import config
    config.load_env()
    sys.exit(main())
