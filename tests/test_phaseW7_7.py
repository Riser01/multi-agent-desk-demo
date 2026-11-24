"""Phase W7-7 acceptance tests: the cost meter, the ceiling that stops a run, model routing and the version stamp."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fakes import call, kinds, seed, team_with

import graph
import prod
from llm import CostCeilingReached, Reply

PRICES = {"read_on": "2026-11-24", "fallback": "b", "models": {"a": {"input": 1.0, "output": 2.0}, "b": {"input": 10.0, "output": 20.0}}}


class PhaseW7_7(unittest.TestCase):
    def test_price_is_tokens_times_list_price_per_million(self):
        """price_usd: 1,000,000 input tokens at $1/M plus 500,000 output at $2/M is $2.00; unknown models use the fallback."""
        self.assertAlmostEqual(prod.price_usd("a", 1_000_000, 500_000, PRICES), 2.0)
        self.assertAlmostEqual(prod.price_usd("unknown", 1_000_000, 0, PRICES), 10.0)

    def test_the_meter_adds_up_and_only_check_enforces_the_ceiling(self):
        """CostMeter.charge adds each call (per role too) and never raises; check() raises CostCeilingReached once over."""
        meter = prod.CostMeter(ceiling_usd=1.5, prices=PRICES)
        meter.charge("planner", Reply("{}", 1_000_000, 0, "a", 0, "fake"))
        meter.check()
        meter.charge("tasks", Reply("{}", 1_000_000, 0, "a", 0, "fake"))
        self.assertAlmostEqual(meter.total_usd, 2.0)
        self.assertEqual(set(meter.by_role), {"planner", "tasks"})
        with self.assertRaises(CostCeilingReached):
            meter.check()
        prod.CostMeter(ceiling_usd=None, prices=PRICES).check()

    def test_the_ceiling_stops_the_run(self):
        """With a tiny ceiling, the team run stops with status 'cost-ceiling' before finishing, and the stop is logged."""
        script = {"supervisor": [{"next": "tasks", "task": "List my tasks"}], "tasks": [call("list_tasks")]}
        team, model = team_with(script, meter=prod.CostMeter(ceiling_usd=0.0000001), routing=dict(prod.ROUTING))
        final = graph.run_graph(graph.build_team(team), "List my tasks.", team)
        self.assertEqual(final["status"], "cost-ceiling")
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(kinds(team.run, "cost"))

    def test_routing_sends_each_role_to_its_model(self):
        """ROUTING names a model for every role, cheaper for supervisor and workers; Team.ask passes it to the model."""
        for role in ("agent", "planner", "executor", "supervisor", "tasks", "calendar", "reviewer"):
            self.assertIn(role, prod.ROUTING)
        prices = prod.load_prices()["models"]
        self.assertLessEqual(prices[prod.ROUTING["supervisor"]]["input"], prices[prod.ROUTING["planner"]]["input"])
        team, model = team_with({"supervisor": [{"next": "finish", "answer": "ok"}]}, routing=dict(prod.ROUTING))
        graph.run_graph(graph.build_team(team), "x", team)
        self.assertEqual(model.calls[0]["model"], prod.ROUTING["supervisor"])

    def test_the_version_stamp_changes_when_a_prompt_changes(self):
        """version_stamp has app, setup, prompts, langgraph and models; editing any prompt changes the prompts hash."""
        stamp = prod.version_stamp("team", prod.ROUTING)
        self.assertTrue({"app", "setup", "prompts", "langgraph", "models"} <= set(stamp))
        import planner
        with patch.object(planner, "PLANNER_PROMPT", planner.PLANNER_PROMPT + " Be brief."):
            self.assertNotEqual(prod.version_stamp("team")["prompts"], stamp["prompts"])
        import reviewer
        with patch.object(reviewer, "REVIEWER_PROMPT", reviewer.REVIEWER_PROMPT + " Be strict."):
            self.assertNotEqual(prod.prompt_version(), stamp["prompts"])

    def test_every_run_is_stamped_and_costed_in_the_files(self):
        """agent.py stamps the version in the log header and the HTML shows 'notional, at list price, <date>'."""
        import agent
        with tempfile.TemporaryDirectory() as folder:
            code = agent.main(["Show me my list.", "--setup", "team", "--approve", "no", "--seed", seed("desk_week"), "--quiet"],
                              out=lambda line: None, root=folder)
            header = json.loads(open(os.path.join(folder, "logs", "latest.jsonl")).readline())
            page = open(os.path.join(folder, "out", "latest.html"), encoding="utf-8").read()
        self.assertEqual(code, 0)
        self.assertEqual(header["version"]["prompts"], prod.prompt_version())
        self.assertIn("notional, at list price, 2026-11-24", page)

    def test_the_ceiling_flag_stops_a_real_command(self):
        """agent.py --ceiling 0.0000001 ends the run with 'status: cost-ceiling' and exit code 1."""
        import agent
        printed = []
        with tempfile.TemporaryDirectory() as folder:
            code = agent.main(["Show me my list.", "--setup", "team", "--approve", "no", "--seed", seed("desk_week"), "--quiet",
                               "--ceiling", "0.0000001"], out=printed.append, root=folder)
        self.assertEqual(code, 1)
        self.assertIn("status: cost-ceiling", printed)
