"""PM-2 checks: CostMeter ceiling, prices, ROUTING, version_stamp + /rollback, /compare, and /monitor."""
import importlib.metadata
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app
import desk as desk_mod
import llm
import prod
import team

SEED = os.path.join(ROOT, "data", "seed.json")


class Phase4Tests(unittest.TestCase):
    def test_cost_ceiling_stops_before_cancelling_event(self):
        """PM-2 (Your turn): a tight per-turn cost ceiling stops the team run with status 'cost-ceiling' before deleting."""
        d = desk_mod.load_desk(SEED)
        meter = prod.CostMeter(ceiling=0.00001)
        res = team.run_team(
            "Cancel the team sync on Wednesday and remind me to email Anil.",
            d, llm.make_model(), desk_mod.approve_yes, review=True, meter=meter, routing=prod.ROUTING,
        )
        self.assertEqual(res["status"], "cost-ceiling")
        self.assertTrue(any(e["id"] == 6 for e in d.events))

    def test_prices_and_routing_match_the_spec(self):
        """PM-2: list prices per 1M tokens (2026-11-24) and routing: routine roles cheap, planner/reviewer/single strong."""
        self.assertEqual(prod.PRICES["gemini-2.5-flash-lite"], {"in": 0.10, "out": 0.40})
        self.assertEqual(prod.PRICES["gemini-3.5-flash-lite"], {"in": 0.30, "out": 2.50})
        for role in ("supervisor", "executor", "tasks_worker", "calendar_worker"):
            self.assertEqual(prod.ROUTING[role], "gemini-2.5-flash-lite")
        for role in ("planner", "reviewer", "single"):
            self.assertEqual(prod.ROUTING[role], "gemini-3.5-flash-lite")

    def test_version_stamp_hash_tracks_prompts_routing_and_langgraph_not_the_track(self):
        """PM-2: stable/canary differ only in release; the hash changes when a prompt or the routing changes."""
        s = prod.version_stamp("team-review", prod.ROUTING, track="stable")
        c = prod.version_stamp("team-review", prod.ROUTING, track="canary")
        self.assertEqual((s["release"], c["release"]), ("1.0.0", "1.1.0"))
        self.assertEqual(s["prompt_hash"], c["prompt_hash"], "the track label must not change the hash")
        self.assertEqual(s["langgraph"], importlib.metadata.version("langgraph"))
        with mock.patch.object(team, "SUPERVISOR_PROMPT", team.SUPERVISOR_PROMPT + " Be brief."):
            self.assertNotEqual(prod.version_stamp("team-review", prod.ROUTING)["prompt_hash"], s["prompt_hash"])
        other = dict(prod.ROUTING, planner="gemini-2.5-flash-lite")
        self.assertNotEqual(prod.version_stamp("team-review", other)["prompt_hash"], s["prompt_hash"])

    def test_compare_and_monitor_and_rollback_in_interactive_chat(self):
        """PM-2: /compare runs without mutating live desk, /rollback toggles track, and /monitor summarizes logs/runs.jsonl."""
        cmds = iter([
            "/setup team", "/review on", "/rollback", "/ceiling 0.00001",
            "Cancel the team sync on Wednesday.", "/monitor", "/compare", "/quit",
        ])
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            code = app.main(["--seed", SEED, "--approve", "yes", "--quiet"],
                            input_fn=lambda _: next(cmds), out=lines.append, root=tmp)
            self.assertEqual(code, 0)
            out_txt = "\n".join(lines)
            self.assertIn("canary 1.1.0", out_txt)
            self.assertIn("ALERT stopped/capped runs", out_txt)
            self.assertIn("offline stand-in (not a real model", out_txt)
            self.assertIn("notional", out_txt)
            self.assertIn("team-review", out_txt)

    def test_compare_columns_stay_aligned_for_long_statuses(self):
        """PM-2: every /compare row starts each column at the same position as the header, even for long statuses."""
        lines = []
        with tempfile.TemporaryDirectory() as tmp:
            app.run_compare(SEED, live=False, max_calls=20, track="stable", root=desk_mod.Path(tmp), out=lines.append)
        header = next(l for l in lines if l.startswith("setup"))
        col = header.index("S3-drill")
        rows = [l for l in lines if l.startswith(("single", "two", "team")) and "skipped" not in l]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row[col - 2:col], "  ", row)
            self.assertNotEqual(row[col], " ", row)
