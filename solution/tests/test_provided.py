"""Checks on the PROVIDED files (config, llm, stand_in, desk_tools, gate, obs, baseline, data). They should always be green.

These run with the standard library only, offline, before you build anything. If one fails, a provided file was
changed or a data file was damaged: do not edit the provided files, get a fresh copy.
"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fakes import ROOT, call, desk_with, quiet_run, seed

import desk_tools
import gate
import llm
import obs


class Provided(unittest.TestCase):
    # ---- config.py ----
    def test_env_file_fills_missing_keys_but_never_overrides_the_shell(self):
        """config.load_env reads KEY=VALUE lines, ignores blanks and comments, lets your shell win, and returns names only."""
        import config
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"A_SHELL": "shell"}, clear=True):
            path = os.path.join(folder, ".env")
            with open(path, "w") as handle:
                handle.write("# comment\nA_SHELL=file\nNEW_KEY='value'\nEMPTY=\n")
            names = config.load_env(path)
            self.assertEqual(names, ["NEW_KEY"])
            self.assertEqual(os.environ["A_SHELL"], "shell")
            self.assertNotIn("EMPTY", os.environ)

    # ---- llm.py ----
    def test_fake_model_replays_per_role_and_records_what_each_agent_saw(self):
        """FakeModel replays scripted replies per role (the last one repeats) and records every message it was sent."""
        model = llm.FakeModel({"planner": [{"steps": []}], "executor": [call("list_tasks"), {"final": "x"}]})
        self.assertEqual(json.loads(model("executor", "s", "u1").text), call("list_tasks"))
        model("executor", "s", "u2")
        self.assertEqual(json.loads(model("executor", "s", "u3").text), {"final": "x"})
        self.assertEqual([c["user"] for c in model.calls], ["u1", "u2", "u3"])
        self.assertTrue(model("planner", "s", "u").estimated)

    def test_call_cap_stops_a_run_before_one_call_too_many(self):
        """Capped refuses the call after max_calls with CallCapReached, so a looping team cannot burn the quota."""
        capped = llm.Capped(llm.FakeModel({"x": ["{}"]}), max_calls=2)
        capped("x", "", "")
        capped("x", "", "")
        with self.assertRaises(llm.CallCapReached):
            capped("x", "", "")

    def test_ask_json_logs_what_the_agent_saw_and_reasks_once_on_bad_json(self):
        """ask_json logs a 'saw' and a 'model' event, re-asks once on bad JSON, and raises ModelError the second time."""
        run = quiet_run()
        data, _ = llm.ask_json(llm.FakeModel({"r": ["not json", '{"ok": 1}']}), "r", "sys", "hello", run=run)
        self.assertEqual(data, {"ok": 1})
        self.assertEqual(run.totals["calls"], 2)
        self.assertTrue(any(e["kind"] == "model" and e["level"] == "WARN" for e in run.events))
        with self.assertRaises(llm.ModelError):
            llm.ask_json(llm.FakeModel({"r": ["nope"]}), "r", "sys", "hello")

    def test_ask_json_charges_the_meter_and_the_meter_can_stop_the_run(self):
        """ask_json calls meter.charge() for every reply, logs the cost, then meter.check(), which may stop the run."""
        class Meter:
            """A stand-in meter that stops after the first charge."""
            total_usd, price_date = 0.0, "test"

            def charge(self, role, reply):
                """Add a fixed cost."""
                self.total_usd += 1.0
                return 1.0

            def check(self):
                """Always over the ceiling."""
                raise llm.CostCeilingReached("over")
        run = quiet_run()
        with self.assertRaises(llm.CostCeilingReached):
            llm.ask_json(llm.FakeModel({"r": ['{"a": 1}']}), "r", "s", "u", run=run, meter=Meter())
        self.assertEqual(run.events[-1]["kind"], "cost")

    def test_replay_files_are_labelled_and_running_out_is_an_error(self):
        """A replay file says REPLAYED and whether it was scripted or recorded; running out of replies is a ModelError."""
        model = llm.ReplayModel(os.path.join(ROOT, "data", "replays", "w7-0-misroute.json"))
        self.assertIn("REPLAYED (scripted)", model.label)
        for _ in range(3):
            model("agent", "s", "u")
        with self.assertRaises(llm.ModelError):
            model("agent", "s", "u")

    def test_live_mode_without_a_key_fails_in_plain_words(self):
        """--live with no GEMINI_API_KEY stops at once with a plain message that names .env, never a traceback."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(llm.ModelError) as caught:
                llm.make_model("live")
        self.assertIn(".env", str(caught.exception))

    def test_live_adapter_waits_out_a_429_and_never_prints_the_key(self):
        """GeminiModel retries a 429 with a pause, then succeeds; usage comes from the provider; the key is never in errors."""
        try:
            from google.genai import errors
        except ImportError:
            self.skipTest("google-genai is not installed (only live runs need it)")
        replies = [errors.APIError(429, {"error": {"code": 429}}),
                   SimpleNamespace(text='{"final": "ok"}', usage_metadata=SimpleNamespace(prompt_token_count=40, candidates_token_count=5))]

        def fake_generate(**_kwargs):
            """Fail once with 429, then answer."""
            item = replies.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        with patch.dict(os.environ, {"GEMINI_API_KEY": "KEY-SECRET-123"}, clear=True), patch("time.sleep") as slept:
            model = llm.GeminiModel()
            model.client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate))
            reply = model("agent", "sys", "user")
            self.assertEqual((reply.input_tokens, reply.output_tokens, reply.estimated), (40, 5, False))
            self.assertTrue(slept.called)
            model.client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **k: (_ for _ in ()).throw(errors.APIError(403, {}))))
            with self.assertRaises(llm.ModelError) as caught:
                model("agent", "sys", "user")
            self.assertNotIn("KEY-SECRET-123", str(caught.exception))

    # ---- desk_tools.py ----
    def test_every_seed_loads_and_a_damaged_desk_is_refused(self):
        """All seed files load; a desk with a repeated id or a too-low next_id raises ValueError instead of guessing."""
        for name in ("desk_week", "trap", "long_note"):
            self.assertTrue(desk_tools.load_desk(seed(name)).tasks)
        with self.assertRaises(ValueError):
            desk_tools.desk_from_dict({"next_id": 3, "tasks": [{"id": 1, "text": "a"}, {"id": 1, "text": "b"}]})
        with self.assertRaises(ValueError):
            desk_tools.desk_from_dict({"next_id": 1, "tasks": [{"id": 1, "text": "a"}]})

    def test_twelve_tools_with_risk_tiers_in_code(self):
        """There are twelve tools; delete_task, clear_done and cancel_event are irreversible; workers get short lists."""
        self.assertEqual(len(desk_tools.ALL_TOOLS), 12)
        self.assertEqual(sorted(n for n, t in desk_tools.TOOLS.items() if t.risk == "irreversible"),
                         ["cancel_event", "clear_done", "delete_task"])
        self.assertTrue(set(desk_tools.TASK_TOOLS).isdisjoint(desk_tools.CALENDAR_TOOLS))

    def test_views_cut_each_item_so_ids_stay_visible(self):
        """desk_view and list_tasks cut each item to 100 characters, so a huge note cannot hide the other ids."""
        desk = desk_tools.load_desk(seed("long_note"))
        view = desk_tools.desk_view(desk)
        self.assertLess(len(view), 1500)
        self.assertIn("7: ", view)
        self.assertGreater(len(desk_tools.desk_view(desk, preview=None)), 1500)

    # ---- gate.py ----
    def test_gate_allow_list_input_check_and_default_deny(self):
        """The gate refuses a tool not on the agent's list, bad input and an unknown tool, and denies with no approver."""
        desk = desk_with("Pay rent")
        self.assertIn("not allowed", gate.run_tool("delete_task", {"id": 1}, desk, allowed=["list_tasks"], approve=gate.approve_yes, actor="x").text)
        self.assertEqual(gate.run_tool("delete_task", {"id": True}, desk, allowed=["delete_task"], approve=gate.approve_yes, actor="x").kind, "error")
        self.assertEqual(gate.run_tool("delete_task", {"id": 1}, desk, allowed=["delete_task"], approve=None, actor="x").kind, "denied")
        self.assertEqual(len(desk.tasks), 1)

    def test_gate_asks_with_plain_words_and_a_crash_means_no(self):
        """An irreversible tool asks with the real task text; a crashing approver is a refusal; a yes runs it once."""
        desk = desk_with("Pay rent")
        questions = []
        gate.run_tool("delete_task", {"id": 1}, desk, allowed=["delete_task"], actor="x",
                      approve=lambda n, a, w: questions.append(w) or False)
        self.assertIn("Pay rent", questions[0])

        def crash(*_):
            """An approver that breaks."""
            raise RuntimeError("broken")
        self.assertEqual(gate.run_tool("delete_task", {"id": 1}, desk, allowed=["delete_task"], approve=crash, actor="x").kind, "denied")
        self.assertEqual(gate.run_tool("delete_task", {"id": 1}, desk, allowed=["delete_task"], approve=gate.approve_yes, actor="x").kind, "ok")
        self.assertEqual(desk.tasks, [])

    def test_a_crashing_input_check_is_a_refusal(self):
        """If a tool's own validate() raises, the gate refuses the call (kind 'error') and nothing runs."""
        import desk_tools as dt
        broken = dt.Tool("boom", "x", {}, "write", lambda a: 1 / 0, lambda a, d: "ran")
        with patch.dict(dt.TOOLS, {"boom": broken}):
            outcome = gate.run_tool("boom", {}, desk_with(), allowed=["boom"], approve=gate.approve_yes, actor="x")
        self.assertEqual(outcome.kind, "error")
        self.assertIn("input check crashed", outcome.text)

    def test_agent_cli_says_not_built_yet_without_graph(self):
        """agent.py (provided) prints a plain 'not built yet' line and exits 2 when graph.py does not exist."""
        import sys as _sys
        import agent
        printed = []
        with patch.dict(_sys.modules, {"graph": None}):
            code = agent.main(["x", "--seed", seed("desk_week")], out=printed.append)
        self.assertEqual(code, 2)
        self.assertIn("not built yet", printed[0])

    def test_the_terminal_approver_says_no_unless_typed_yes(self):
        """gate.make_ask: 'y' or 'yes' allows; a blank answer or no keyboard at all (EOFError) means no (default deny)."""
        def eof(_prompt):
            """No person at the keyboard."""
            raise EOFError
        quiet = lambda line: None
        self.assertTrue(gate.make_ask(lambda p: "yes", quiet)("delete_task", {}, "w"))
        self.assertFalse(gate.make_ask(lambda p: "", quiet)("delete_task", {}, "w"))
        self.assertFalse(gate.make_ask(eof, quiet)("delete_task", {}, "w"))

    def test_results_are_cut_with_a_marker(self):
        """A long result is cut to MAX_RESULT_CHARS and marked [truncated]."""
        self.assertTrue(gate.cut("x" * 500).endswith(" [truncated]"))
        self.assertEqual(len(gate.cut("x" * 500)), gate.MAX_RESULT_CHARS + len(" [truncated]"))

    # ---- obs.py ----
    def test_a_run_writes_log_jsonl_html_and_latest_copies(self):
        """finish() writes logs/run-*.log and .jsonl, out/run-*.html, and real copies named latest.*."""
        with tempfile.TemporaryDirectory() as folder:
            run = obs.Run("demo", goal="Add File taxes", quiet=True, root=folder)
            run.log("tool", "executor", "add_task -> ok")
            paths = run.finish("done", "ok", {"tasks": [{"id": 1, "text": "File taxes"}], "events": []})
            for ext, folder_name in (("log", "logs"), ("jsonl", "logs"), ("html", "out")):
                latest = os.path.join(folder, folder_name, f"latest.{ext}")
                self.assertTrue(os.path.isfile(paths[ext]) and os.path.isfile(latest))
                self.assertFalse(os.path.islink(latest))
            page = open(os.path.join(folder, "out", "latest.html"), encoding="utf-8").read()
            self.assertIn("Add File taxes", page)
            self.assertIn("not stamped yet", page)
            lines = open(os.path.join(folder, "logs", "latest.jsonl"), encoding="utf-8").read().splitlines()
            self.assertEqual(json.loads(lines[0])["kind"], "header")

    def test_terminal_lines_and_no_secret_in_any_output(self):
        """Every event prints one line with level, time, agent and kind; an API key in the environment never appears."""
        printed = []
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GEMINI_API_KEY": "KEY-SECRET-123"}):
            run = obs.Run("demo", goal="g", root=folder, out=printed.append)
            run.log("gate", "tasks", "delete task 1 -> denied", level="WARN")
            run.finish("done", "ok", {})
            files = "".join(open(os.path.join(folder, d, f), encoding="utf-8").read()
                            for d in ("logs", "out") for f in os.listdir(os.path.join(folder, d)))
        self.assertTrue(any(line.startswith("WARN") and "[tasks" in line and "gate" in line for line in printed))
        self.assertNotIn("KEY-SECRET-123", "\n".join(printed) + files)

    def test_trace_export_nests_run_agent_model_tool(self):
        """With a trace client, a run opens nested observations: run > agent > model/tool; without one it prints a tree."""
        opened = []

        class Span:
            """A fake observation context."""
            def __init__(self, name):
                """Remember the name."""
                self.name = name

            def __enter__(self):
                """Record the opening."""
                opened.append(self.name)
                return self

            def __exit__(self, *a):
                """Nothing to close."""
                return False

            def update(self, **k):
                """Accept the final output."""

        client = SimpleNamespace(start_as_current_observation=lambda name, **k: Span(name), flush=lambda: None)
        run = obs.Run("team", quiet=True, save=False, export="langfuse", langfuse_client=client)
        with run.agent("tasks"):
            run.model_call("tasks", llm.Reply("{}", 10, 2, "m", 0.1, "fake"))
            run.log("tool", "tasks", "list_tasks -> ok", tool="list_tasks")
        run.finish("done", "ok", {})
        self.assertEqual(opened, ["run team", "tasks", "tasks model", "tool list_tasks"])
        printed = []
        tree_run = obs.Run("team", out=printed.append, save=False, export="console")
        with tree_run.agent("tasks"):
            tree_run.log("tool", "tasks", "list_tasks -> ok")
        tree_run.finish("done", "ok", {})
        self.assertTrue(any(line.startswith("TRACE run team") for line in printed))

    # ---- stand_in.py and baseline.py (W7-0) ----
    def test_stand_in_splits_goals_and_routes_by_keywords(self):
        """The offline stand-in splits 'X, then Y' into parts and picks archive_task for 'archive', add_event for a dated appointment."""
        from stand_in import classify, split_goal
        self.assertEqual(split_goal('Add "File taxes", then show me my list.'), ['Add "File taxes"', "show me my list"])
        self.assertEqual(classify("Archive the dentist task"), "archive_task")
        self.assertEqual(classify("Add a dentist appointment on Fri 27 Nov 10:00"), "add_event")

    def test_baseline_replay_is_labelled_and_the_gate_still_holds(self):
        """W7-0: the replayed misroute is labelled REPLAYED, picks delete for 'archive', is denied, and the task stays."""
        import baseline
        printed = []
        with tempfile.TemporaryDirectory() as folder:
            code = baseline.main(["Archive the dentist task.", "--mode", "replay", "--replay",
                                  os.path.join(ROOT, "data", "replays", "w7-0-misroute.json"), "--approve", "no",
                                  "--seed", seed("desk_week")], out=printed.append, root=folder)
        text = "\n".join(printed)
        self.assertEqual(code, 0)
        self.assertIn("REPLAYED (scripted)", text)
        self.assertIn("delete task 4", text)
        self.assertIn("4: Book dentist appointment", text)

    def test_baseline_offline_sends_all_twelve_tools_every_call(self):
        """W7-0: the single agent's prompt carries all twelve tools on every call (the token cost of one big agent)."""
        import baseline
        for name in desk_tools.ALL_TOOLS:
            self.assertIn(f"- {name}(", baseline.AGENT_PROMPT)

    # ---- data/ ----
    def test_scenarios_prices_and_regression_cases_are_well_formed(self):
        """scenarios.json and data/regression/ use known seeds and check types; prices.json names its source and date."""
        known = {"status_in", "task_exists", "task_missing", "task_archived", "event_exists", "event_missing"}
        cases = json.load(open(os.path.join(ROOT, "data", "scenarios.json")))["scenarios"]
        folder = os.path.join(ROOT, "data", "regression")
        cases += [json.load(open(os.path.join(folder, f))) for f in os.listdir(folder) if f.endswith(".json")]
        for case in cases:
            self.assertTrue(os.path.isfile(seed(case["seed"])), case["id"])
            self.assertTrue({c["type"] for c in case["checks"]} <= known, case["id"])
        prices = json.load(open(os.path.join(ROOT, "data", "prices.json")))
        self.assertTrue(prices["source"].startswith("https://") and prices["read_on"])
        self.assertIn(prices["fallback"], prices["models"])
